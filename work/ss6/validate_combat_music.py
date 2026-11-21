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
from extract_stage_music import TRACKS, directory

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


class NameDriver(MusicDriver):
    """214210 ends in a tail call to the IOP OPEN RPC 2139d8: capture its two names."""
    ee_boundaries=MusicDriver.ee_boundaries+(0x2139d8,)

    def ee_library(self,pc):
        if pc!=0x2139d8:return super().ee_library(pc)
        p=self.ee
        self.opened=tuple(bytes(p.memory[a:a+64]).split(b'\0',1)[0].decode() for a in p.registers[4:6])


BLOCK=(0x1553b40,0x1553b44,0x1553b54,0x1553b58,0x5a9e80,0x5a9e84)
ENTRIES=((0x213ff0,'P',0,0),(0x214060,'G',1,0),(0x2140b8,'L',0,1))


def requests(native):
    """Every entry point, soundtrack, track and flag: the request block and the OPEN names."""
    d=NameDriver(Iso(ISO))
    lines=[];expected=[];jingles=0;opens=0
    for variant in (0,1):
        d.ee.write(0x43d056,variant,1)
        for entry,op,fade,preload in ENTRIES:
            for track in range(TRACKS):
                for flag in (0,1):
                    for a in BLOCK:d.ee.write(a,0xdead,4)
                    before=sum(d.ops.values())
                    d.call(entry,track,flag)
                    got=[d.ee.read(a,4) for a in BLOCK]
                    lines.append(f'{op} {variant} {track} {flag}')
                    if entry==0x213ff0 and track==23:
                        # 212d80(12): the block is untouched, the jingle reaches the IOP.
                        assert got==[0xdead]*6 and sum(d.ops.values())>before,(variant,track,flag)
                        jingles+=1;expected.append('jingle');continue
                    assert got==[track+1,0,variant,preload,flag,fade],(hex(entry),variant,track,flag,got)
                    expected.append(f'{flag} {preload} {fade}')
        for track in range(TRACKS):
            d.call(0x214210,track+1)
            n=directory(track,variant)
            assert d.opened==tuple(f'\\BGM{n}\\BGM{track:02}_{s}.VB;1' for s in 'LR'),(variant,track,d.opened)
            opens+=1
    got=subprocess.run([native,RES,'-','requests'],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True).stdout.split('\n')[:-1]
    assert got==expected,next((i,a,b) for i,(a,b) in enumerate(zip(got,expected)) if a!=b)
    return dict(request_blocks=len(lines),jingle_redirects=jingles,open_names=opens,ee_instructions=d.ee_steps)


def streams(native,tmp):
    """Each stream of both soundtracks through the IRX: the repeating wire period
    against the native decoded period, and the one-shot key-off half."""
    iso=Iso(ISO);out=[];total_iop=0;quirk=[]
    for variant in (0,1):
        for track in range(TRACKS):
            size=iso.by_path[f'/BGM{directory(track,variant)}/BGM{track:02}_L.VB']['size']
            halves=(size+HALF-1)//HALF
            raw=tmp/'stream.raw'
            info=subprocess.run([native,RES,raw,'stream',str(variant),str(track)],capture_output=True,text=True,check=True).stdout.split()
            samples,loop_end,shot_end=map(int,info)
            pcm=array('h');pcm.frombytes(raw.read_bytes())
            assert samples==halves*HALF//16*28 and loop_end==samples
            assert shot_end==samples-(HALF//16*28 if halves>2 else 0)
            for repeat in (1,0):
                d=MusicDriver(iso);d.ee.write(0x43d056,variant,1)
                d.call(0x214060,track,repeat)
                for _ in range(40):
                    d.call(0x2142c0);d.service()
                    if d.state()==0x5000:break
                assert d.state()==0x5000 and d.switches[-1]==(0x1501,3)
                if repeat:
                    while len(d.transfers)<2*(2*halves+2):d.service()
                    for n,side in enumerate('LR'):
                        address=0x1e0000+n*65536
                        wire=bytearray().join(b for dest,b in d.transfers if dest in (address,address+HALF))
                        wire[1::16]=bytes(len(wire)//16)
                        period=wire[:halves*HALF]
                        assert decoded(period)==pcm[n*samples:(n+1)*samples],(variant,track,side)
                        if halves==2:
                            # No EOF test after the initial upload: one half of the
                            # disc after the file, then the ordinary period.
                            path=f'/BGM{directory(track,variant)}/BGM{track:02}_{side}.VB'
                            after=bytearray(iso.read_at(iso.by_path[path]['lba']*iso.block+size,HALF));after[1::16]=bytes(HALF//16)
                            assert wire[2*HALF:3*HALF]==after and wire[3*HALF:]==(period*3)[:len(wire)-3*HALF],(variant,track,side)
                            quirk.append(f'{variant}/{track}/{side}')
                        else:assert wire==(period*3)[:len(wire)],(variant,track,side)
                else:
                    while d.state()==0x5000:d.service()
                    # The IRX keys off once the last uploaded half is due: one
                    # half of the stream is never heard (except a two-half stream).
                    assert d.state()==0x6000 and len(d.transfers)==2*max(halves-1,2),(variant,track,len(d.transfers))
                total_iop+=d.iop_steps
            out.append(dict(variant=variant,track=track,bytes=size,halves=halves,samples=samples))
    return dict(streams=len(out),iop_instructions=total_iop,two_half_repeat_overrun=quirk,detail=out)


def timelines(native):
    """EE request machine, fade and IOP key events per visit, against the native player."""
    iso=Iso(ISO);report={}
    scenarios={
        'play_then_play':[('P',2,1),40,('P',5,1),45],
        'gallery_then_gallery':[('G',2,1),40,('G',5,1),70],
        'gallery_then_stop':[('G',2,1),40,('S',),40],
        'play_then_gallery':[('P',2,1),40,('G',7,1),45],
    }
    offsets=set()
    for name,script in scenarios.items():
        d=MusicDriver(iso);lines=[];rows=[]
        for step in script:
            if isinstance(step,tuple):
                op,*args=step
                if op=='P':d.call(0x213ff0,*args)
                elif op=='G':d.call(0x214060,*args)
                else:d.call(0x1e7ad0)
                lines.append(' '.join(map(str,step)));continue
            for _ in range(step):
                switches=len(d.switches)
                d.call(0x2142c0);d.service()
                ee=d.ee.read(0x1553b44,4) if d.ee.read(0x1553b40,4) else -1
                keys=[s[0] for s in d.switches[switches:]]
                rows.append((min(ee,6),d.ee.read(0x1553b4c,4) if d.ee.read(0x1553b50,4) else 0,
                             'off' if 0x1601 in keys else 'on' if 0x1501 in keys else ''))
                lines.append('T')
        got=[tuple(x.split(' ')) for x in subprocess.run([native,RES,'-','timeline'],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True).stdout.split('\n')[:-1]]
        assert len(got)==len(rows)
        native_on=[i for i,g in enumerate(got) if g[2]=='on'];original_on=[i for i,r in enumerate(rows) if r[2]=='on']
        for i,(r,g) in enumerate(zip(rows,got)):
            state,level,event=int(g[0]),int(g[1]),g[2]
            # States 6/7 hand the request to the IOP; natively it is loading.
            assert (state if state>=0 else -1,level)==(r[0] if r[0]<6 else -1,r[1]),(name,i,r,g)
            if r[2]=='off':assert event=='off',(name,i,r,g)
        assert len(native_on)==len(original_on)
        offsets.update(a-b for a,b in zip(native_on,original_on))
        report[name]=dict(visits=len(rows),key_on=original_on,native_key_on=native_on,fade_visits=sum(1 for r in rows if r[1]))
    assert len(offsets)==1,offsets
    report['key_on_offset_visits']=offsets.pop()
    return report


CPP=r"""
#include "combat_audio.hpp"
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
int main(int argc,char**argv) {
    const std::string mode=argc>3?argv[3]:"";
    if(mode=="requests") {
        // One fresh request per line through the mixer's entry mapping.
        char op;int variant,track,flag;
        while(std::cin>>op>>variant>>track>>flag) {
            ss6::CombatAudio audio(argv[1]);
            using E=ss6::CombatAudio::MusicEntry;
            audio.requestMusic(op=='P'?E::Play:op=='G'?E::Gallery:E::Preload,variant,track,flag,0x3200);
            const auto& m=audio.music();
            if(m.requestState()<0)std::cout<<"jingle\n";
            else std::cout<<m.pending().repeat<<' '<<m.pending().preload<<' '<<m.pending().fadeStop<<'\n';
        }
        return 0;
    }
    if(mode=="stream") {
        ss6::CombatMusic music(argv[1]);
        std::ofstream out(argv[2],std::ios::binary);
        const int variant=std::atoi(argv[4]),track=std::atoi(argv[5]);
        music.request({variant,track,true,false,false},0x3200);
        const unsigned loop=music.endSample();
        music.request({variant,track,false,false,false},0x3200);
        const auto& t=music.track();
        for(const auto& side:t.sides)out.write(reinterpret_cast<const char*>(side.pcm.data()),std::streamsize(2*t.samples));
        std::cout<<t.samples<<' '<<loop<<' '<<music.endSample()<<'\n';
        return 0;
    }
    if(mode=="timeline") {
        // The IOP answers 213db0 with a non-zero volume while a keyed stream runs.
        ss6::CombatMusic music(argv[1]);
        bool streaming=false;std::string op;
        while(std::cin>>op) {
            if(op=="P"||op=="G") {int track,flag;std::cin>>track>>flag;music.request({0,track,flag!=0,false,op=="G"},0x3200);}
            else if(op=="S")music.stop(streaming);
            else {
                const auto e=music.tick(streaming);
                const char* name="";
                if(e==ss6::CombatMusic::Event::KeyOn){streaming=true;name="on";}
                else if(e==ss6::CombatMusic::Event::Silence){streaming=false;name="off";}
                else if(e==ss6::CombatMusic::Event::Fade)name="fade";
                const int level=music.fadeActive()?music.fadeLevel():0;
                std::cout<<music.requestState()<<' '<<level<<' '<<name<<'\n';
            }
        }
        return 0;
    }
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
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',SOURCE,src,SOURCE/'combat_audio.cpp',SOURCE/'combat_music.cpp',SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
        subprocess.run([exe,RES,raw],input='\n'.join(commands)+'\n',text=True,check=True)
        got=raw.read_bytes()
        request_report=requests(exe)
        stream_report=streams(exe,tmp)
        timeline_report=timelines(exe)
    if got!=expected:
        for i,(a,b) in enumerate(zip(struct.iter_unpack('<2h',got),struct.iter_unpack('<2h',expected),strict=True)):
            if a!=b:raise AssertionError(('PCM divergence',i,a,b))
        raise AssertionError('Unequal PCM lengths')
    report=dict(status='passed',select02=select_report,stage05=stage_report,winner24=victory_report,stage_samples=len(stage[0]),
        winner_keyoff_samples=end,frames_compared=len(expected)//4,pcm_sha256=sha(expected),
        requests=request_report,all_streams=stream_report,request_timelines=timeline_report,
        catalogue_sha256=sha((RES/'music_streams.bin').read_bytes()),
        source_sha256={s:sha((SOURCE/s).read_bytes()) for s in ('combat_audio.cpp','combat_music.cpp','combat_sound_bank.cpp')},
        scope='Original EE service, ISO file catalog, IOP CD reads, SPU register writes and actual stereo DMA through wrap/EOF. PCM compares the two dry hardware voices and synchronous SE against an independent model. Device-ready optical and DMA fixtures; the 100 ms per initial CD read is observed in the IOP. No optical seek variation or physical DAC measurement. Every entry point 213ff0/214060/2140b8 x soundtrack x track 0..27 x flag: request block 1553b40/44/54/58, 5a9e80/84 and the 213ff0 track-23 jingle redirect; 214210 OPEN names; all 56 streams through the IRX (repeating wire period equals the native decoded period incl. the post-EOF half; one-shot key-off half count); EE request state, 214438 fade level and IOP key-off/key-on visits for immediate and 214060 fade-out stops. The fixture does not wait the two DelayThread(100000) reads, so native key-on visits trail by the one constant offset reported.')
    OUT.write_text(json.dumps(report,indent=2)+'\n')
    print(OUT,report['frames_compared'],report['pcm_sha256'])


if __name__=='__main__':main()
