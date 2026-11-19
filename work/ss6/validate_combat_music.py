#!/usr/bin/env python3
"""Run the Japanese EE music service and the original stereo IOP CD/DMA thread."""
from array import array
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_combat_audio import ELF, ISO, PIN, RES, ROOT, SOURCE, Iso, OriginalDriver, sha

OUT=ROOT/'outputs/ss6-feasibility/combat_music_validation.json'
HALF=32768
PITCH=0x761


class MusicDriver(OriginalDriver):
    """Memory-ready optical drive; CD sector/alignment/rewind come from the IRX."""
    ee_boundaries=OriginalDriver.ee_boundaries+(0x31806c,)

    def ee_library(self,pc):
        assert pc==0x31806c
        p=self.ee
        a,b=[bytes(p.memory[i:i+64]).split(b"\0",1)[0] for i in p.registers[4:6]]
        p.put(2,(a>b)-(a<b))

    def __init__(self,iso):
        self.iso=iso
        self.transfers=[]
        self.reads=[]
        self.delays=[]
        self.switches=[]
        self.params=[]
        super().__init__(iso)
        self.ee.write(0x5a9e78,0x3200,4)
        # Boot 10c0d4 populates the on-disc catalog with sceCdSearchFile's
        # exact LBA/byte length. Preserve the ELF's original filename pointers.
        self.ee.write(0x3bd090,260,4)
        for index in range(260):
            at=0x3b1f68+index*32
            namep=self.ee.read(at,4)
            name=bytes(self.ee.memory[namep:namep+32]).split(b'\0',1)[0].decode()
            if not name.startswith('\\BGM'):continue
            info=iso.by_path[name[:-2].replace('\\','/')]
            assert self.ee.read(at+8,4)==info['lba']
            self.ee.write(at+24,info['size'],8)
        # IOP sysmem addresses of the two 320 KiB disc caches; SPU addresses
        # are still assigned by the original OPEN2.
        self.iop.write(0x4078,0x100000,4)
        self.iop.write(0x407c,0x170000,4)
        self.service(True)

    def sdk(self,pc):
        p=self.iop
        r=p.registers
        if pc==0x3910:p.put(2,2)  # sceCdDiskReady
        elif pc==0x38f0:
            sector,count,address=r[4:7]
            data=self.iso.read_at(sector*2048,count*2048)
            p.memory[address:address+len(data)]=data
            self.reads.append((sector,count))
            p.put(2,1)
        elif pc==0x3908:p.put(2,0)  # sceCdSync
        elif pc==0x3aa4:self.delays.append(r[4])
        elif pc==0x38b4:
            n=p.read(r[29]+16,4)
            src,dest=r[6:8]
            self.transfers.append((dest,bytes(p.memory[src:src+n])))
            p.put(2,n)
        elif pc in (0x3894,0x38a4):
            reg,value=r[4:6]
            self.params.append((reg,value))
            self.registers[reg]=value
        elif pc==0x389c:self.switches.append(tuple(r[4:6]))
        elif pc==0x38bc:p.put(2,1)  # LIBSD DMA completion

    def service(self,initial=False):
        # Each normal visit wakes the actual task from WaitSema once. Its
        # stack is independent of the IOP RPC worker which also uses this CPU.
        start=0x2248 if initial else 0x2274
        sp=0x1f00000 if initial else 0x1f00000-0x38
        def observe(pc):
            if pc==start:
                self.iop.put(29,sp)
                if not initial:self.iop.put(30,sp)
            self.sdk(pc)
        _,n=self.iop.run(start,limit=50000,stop_before=[0x2264],observe=observe)
        self.iop_steps+=n

    def state(self):
        return self.iop.read(0x40f0,4)

    def launch(self,track):
        stage=5<=track<=14
        self.call(0x2140b8 if stage else 0x213ff0,track,int(stage or track==2))
        assert self.ee.read(0x1553b40,4)==track+1
        for tick in range(1,7):
            self.call(0x2142c0)
            if tick!=6:assert self.state()==0
        assert self.state()==0x1000
        for wanted in (0x2000,0x3000,0x4000 if stage else 0x5000):
            self.service()
            assert self.state()==wanted
        assert self.delays==[100000,100000]
        if stage:
            assert (0x1501,3) not in self.switches
            self.call(0x214118)
            self.call(0x2142c0)
        assert self.state()==0x5000 and self.switches[-1]==(0x1501,3)
        assert [self.registers[k] for k in (1,0x101,3,0x103)]==[0x3200,0,0,0x3200]
        assert [self.registers[k] for k in (0x201,0x203,0x301,0x303,0x401,0x403)]==[PITCH,PITCH,15,15,0x1fc0,0x1fc0]


def decoded(data):
    out=array('h')
    p1=p2=0
    for block in range(0,len(data),16):
        header=data[block]
        a,b=((0,0),(60,0),(115,-52),(98,-55),(122,-60))[header>>4]
        for byte in data[block+2:block+16]:
            for nib in (byte%16,byte//16):
                value=((nib-16 if nib>=8 else nib)*4096>>(header%16))+(a*p1+b*p2+32)//64
                p2,p1=p1,max(-32768,min(32767,value))
                out.append(p1)
    return out


def capture(track,assets=RES):
    iso=Iso(ISO)
    d=MusicDriver(iso)
    stage=5<=track<=14
    d.launch(track)
    if stage or track==2:
        disc_size=iso.by_path[f'/BGM1/BGM{track:02}_L.VB']['size']
        # Cross the CD rewind and transfer the first complete half of the
        # next period. Each interrupt uploads one half to each SPU voice.
        needed=(disc_size+HALF-1)//HALF
        while len(d.transfers)<2*(needed+1):d.service()
        assert len(d.switches)==2 and d.switches[-1]==(0x1501,3)
        d.call(0x214150)
    else:
        while d.state()==0x5000:d.service()
        assert d.state()==0x6000 and len(d.transfers)==8
        d.service()
    assert d.state()==0 and d.switches[-1]==(0x1601,3)
    assert d.params[-4:]==[(1,0),(0x101,0),(3,0),(0x103,0)]
    sides=[]
    report={}
    for n,side in enumerate('LR'):
        path=f'/BGM{1 if stage or track==2 else 2}/BGM{track:02}_{side}.VB'
        disk=bytearray(iso.read(path))
        assert disk==(assets/f'bgm{track:02}_{side.lower()}.vb').read_bytes()
        address=0x1e0000+n*65536
        writes=[b for dest,b in d.transfers if dest in (address,address+HALF)]
        assert len(writes[0])==2*HALF and all(len(buf)==HALF for buf in writes[1:])
        wire=bytearray().join(writes)
        report[side]={'path':path,'file_bytes':len(disk),'file_sha256':sha(disk),'dma_bytes':len(wire),'dma_sha256':sha(wire)}
        # Every ADPCM payload, including the first bytes after the first full
        # disc rewind. The ring's flag at byte 1 of each block is transport data.
        size=len(disk)
        disk[1::16]=bytes(size//16)
        wire[1::16]=bytes(len(wire)//16)
        # The native player must reproduce the stale tail of a short CD cache
        # read. Track 2 has a half-full last DMA block in each channel.
        pad=(-size)%HALF
        period=disk+disk[size-160*2048:size-160*2048+pad]
        assert wire==(period*((len(wire)+len(period)-1)//len(period)))[:len(wire)]
        sides.append(decoded(wire[:len(period)]))
    if stage or track==2:
        assert d.reads.count(d.reads[0])>=2
    report.update(ee_instructions=d.ee_steps,iop_instructions=d.iop_steps,rpcs=dict(d.ops),sector_reads=d.reads,
                  initial_delay_us=d.delays[:2],sound_switches=d.switches,initial_ee_services=6)
    return sides,report,d.table


CPP=r"""
#include "combat_audio.hpp"
#include <array>
#include <fstream>
#include <iostream>
int main(int argc,char**argv) {
    ss6::CombatAudio audio(argv[1]);
    std::ofstream out(argv[2],std::ios::binary);
    std::array<int16_t,4096> buf;
    char op;int n;
    while(std::cin>>op>>n) {
        if(op=='M')audio.playMusic(0,2,0x3200);
        if(op=='P')audio.preloadMusic(0,5);
        if(op=='V')audio.playMusic(0,24,0x3200);
        if(op=='A')audio.startMusic(n);
        if(op=='T')while(n-->0)audio.tick();
        if(op=='S')audio.play(0,n);
        if(op=='Z')audio.stopMusic();
        if(op=='D'||op=='C')while(n>0) {
            int take=std::min(n,2048);
            audio.render(std::span<int16_t>(buf.data(),2*take));
            if(op=='C')out.write(reinterpret_cast<char*>(buf.data()),4*take);
            n-=take;
        }
    }
}
"""


def main():
    assert sha(ELF.read_bytes())==PIN
    select,select_report,table=capture(2)
    stage,stage_report,table=capture(5)
    victory,victory_report,_=capture(24)
    se=OriginalDriver(Iso(ISO))
    commands=[];expected=bytearray()
    track=None;age=0;end=0;repeat=False
    def cmd(c,n=0):commands.append(f'{c} {n}')
    def render(n,save=True):
        nonlocal age
        cmd('C' if save else 'D',n)
        if not save:
            if se.voices:se.render(n)
            age+=n
            return
        for frame in range(age,age+n):
            pos=frame*PITCH
            level=(14336,28672,32767)[frame] if frame<3 else min(32767,16383+4*((frame-3)//32768))
            dry=0
            for channel,voice in list(se.voices.items()):
                v=voice.next(table)
                if v is None:del se.voices[channel]
                else:dry+=v
            result=[]
            for side in range(2):
                base=pos//4096
                v=0
                if track and (repeat or base<end):
                    samples=track[side]
                    mix=sum(w*samples[(base+i)%len(samples)]//32768 for i,w in enumerate(table[(pos//16)%256]))
                    v=(mix*level//32768)*(0x3200*2)//32768
                result.append(max(-32768,min(32767,dry+v))*32766//32768)
            expected.extend(struct.pack('<hh',*result))
        age+=n
    cmd('M');cmd('T',17);render(800);cmd('T',1)
    track=select;age=0;repeat=True;end=len(select[0])
    render(991)
    target=(end*4096+PITCH-1)//PITCH-220
    render(target-age,False);render(441)
    cmd('Z');track=None;render(120)
    cmd('P');cmd('T',30);render(800);cmd('A',0x3200);cmd('T',1)
    track=stage;age=0;repeat=True;end=len(stage[0])
    render(997)
    se.call(0x212fa0,0,12);cmd('S',12);render(19001)
    # Sample windows through each half IRQ and both sides of the actual EOF.
    for block in range(1,39):
        target=((block*HALF//16*28)*4096+PITCH-1)//PITCH-77
        if age<target:render(target-age,False)
        render(211)
    cmd('Z');track=None;render(512)
    cmd('V');cmd('T',17);render(800);cmd('T',1)
    track=victory;age=0;repeat=False;end=len(victory[0])-HALF//16*28
    render(800);render(16577)
    target=(end*4096+PITCH-1)//PITCH-300
    render(target-age,False);render(600)
    # The current stereo voices remain keyed until the next EE visit even if
    # two queued requests both replace the pending cache slot before then.
    cmd('P');cmd('T',18);cmd('A',0x3200);cmd('T',1)
    track=stage;age=0;repeat=True;render(13)
    cmd('M');cmd('V');render(70)
    cmd('T',1);track=None;render(80)
    cmd('T',17);track=victory;age=0;repeat=False;render(160)
    assert any(expected)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);src=tmp/'test.cpp';src.write_text(CPP);exe=tmp/'mix';raw=tmp/'music.raw'
        subprocess.run(['c++','-O2','-std=c++20','-I',SOURCE,src,SOURCE/'combat_audio.cpp',SOURCE/'combat_music.cpp',SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
        subprocess.run([exe,RES,raw],input='\n'.join(commands)+'\n',text=True,check=True)
        got=raw.read_bytes()
    if got!=expected:
        for i,(a,b) in enumerate(zip(struct.iter_unpack('<2h',got),struct.iter_unpack('<2h',expected),strict=True)):
            if a!=b:raise AssertionError(('PCM divergence',i,a,b))
        raise AssertionError('Unequal PCM lengths')
    report=dict(status='passed',select02=select_report,stage05=stage_report,winner24=victory_report,stage_samples=len(stage[0]),
        winner_keyoff_samples=end,frames_compared=len(expected)//4,pcm_sha256=sha(expected),
        source_sha256={s:sha((SOURCE/s).read_bytes()) for s in ('combat_audio.cpp','combat_music.cpp','combat_sound_bank.cpp')},
        scope='Original EE service, ISO file catalog, IOP CD reads, SPU register writes and actual stereo DMA through wrap/EOF. PCM compares the two dry hardware voices and synchronous SE against an independent model. Device-ready optical and DMA fixtures; the 100 ms per initial CD read is observed in the IOP. No optical seek variation or physical DAC measurement.')
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    print(OUT,report['frames_compared'],report['pcm_sha256'])


if __name__=='__main__':main()
