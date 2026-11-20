#!/usr/bin/env python3
"""Exercise the Japanese sound RPC and its original ADPCMST.IRX, then compare PCM."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_combat_sound_bank import ISO
from inspect_iso import Iso
from mips_probe import Probe,signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ROOT,ELF,PIN

SOURCE=ROOT/'src'
RES=ROOT/'work/ss6/extracted/resources'
REPORT=ROOT/'outputs/ss6-feasibility/combat_audio_validation.json'
PHASE_SHA='8c6eae12a42efeba4cc2d46bfdc4aa82ee9a044de48144cf46d01c1ce3707ea0'
HW_MODEL='https://github.com/PCSX2/pcsx2/tree/master/pcsx2/SPU2'
sha=lambda data:hashlib.sha256(data).hexdigest()

def coefficients():
    raw=[]
    for n in range(512):
        x=n+.5
        t=math.cos(math.pi*x*2/1023)-1
        u=math.cos(math.pi*x*4/1023)-1
        raw.append(math.sin(math.pi*x*2.048/1024)*(1+t*.5+u*.08)/x)
    norm=32640*128/sum(raw)
    scaled=[x*norm for x in reversed(raw)]
    out=[]
    for i in reversed(range(256)):
        row=[scaled[n] for n in (i,i+256,511-i,255-i)]
        out.append([round(x+(32640-sum(row))/4) for x in row])
    # Independent, pinned 256x4 SPU interpolation table, ordered as in the
    # published PCSX2 table. Reject even a one-LSB floating-point variation.
    assert sha(b''.join(struct.pack('<4h',*row) for row in out))==PHASE_SHA
    return out

class Key:
    def __init__(self,data,pitch,volume):
        self.values=[];self.pitch=pitch;self.volume=volume
        self.cursor=self.fetched=self.level=self.count=self.phase=0
        prev1=prev2=0
        for start in range(0,len(data),16):
            header,flag=data[start:start+2]
            a,b=((0,0),(60,0),(115,-52),(98,-55),(122,-60))[header>>4]
            for byte in data[start+2:start+16]:
                for nib in (byte%16,byte//16):
                    pcm=(signed(nib,4)*4096>>(header%16))+((a*prev1+b*prev2+32)//64)
                    prev2,prev1=prev1,max(-32768,min(32767,pcm))
                    self.values.append(prev1)
            if flag&1:
                assert flag==1
                break
        else:raise AssertionError('No terminating ADPCM packet')

    def next(self,table):
        at=self.cursor//4096
        if self.fetched-at<=12:self.fetched+=4
        if self.fetched==len(self.values):return None
        # ADSR1/2 are verified against the IRX register calls. Derive the
        # per-tick register effects from their shift/step fields.
        shift=(0,0,31,0)[self.phase]
        step=(7,-8,4,-8)[self.phase] << max(0,11-shift)
        if self.phase==1:step=step*self.level//32768
        self.count+=max(1,32768>>max(0,shift-11))
        if self.count>=32768:
            self.count=0;self.level=max(0,min(32767,self.level+step))
        if (self.phase==0 and self.level==32767) or self.phase==1:self.phase+=1
        if self.phase==3 and not self.level:return None
        taps=table[(self.cursor>>4)%256]
        value=sum(weight*sample//32768 for weight,sample in zip(taps,self.values[at:at+4],strict=True))
        self.cursor+=self.pitch
        return (value*self.level//32768)*(2*self.volume)//32768

class OriginalDriver:
    ee_boundaries=(0x3242b0,0x320960,0x320940)

    def __init__(self,iso):
        self.ee=Probe(ELF.read_bytes());buffered_stdout(self.ee)
        irx=iso.read('/IRX/ADPCMST.IRX')
        self.irx_hash=sha(irx);self.iop=Probe(irx)
        self.spu=bytearray(2*1024*1024)
        self.registers={};self.voices={};self.ops=Counter();self.calls=Counter()
        self.ee_steps=self.iop_steps=self.keys=0;self.pcm=bytearray();self.table=coefficients()
        self.ee.write(0x345188,1,4)
        self.iop.write(0x4114,0x80000,4)
        self.ee.write(0x5a9e74,0x80000,4)
        self.ee.write(0x59d018,50,4)
        for group,base in [('BVOICE1',0x59d028),('BVOICE2',0x5a0a98),('NAL',0x5a89c8)]:
            header=iso.read('/VOICE/'+group+'.MSH')
            self.ee.memory[base:base+len(header)]=header
            file=iso.by_path['/VOICE/'+group+'.MSB']
            def payload(index,stride):
                sector,_,size,_=struct.unpack_from('<4I',header,index*stride)
                return iso.read_at((file['lba']+sector)*iso.block,size)
            if group=='BVOICE2':
                for idx,addr in ((50,0x5010),(0,0x5b010),(0,0xb1010)):
                    data=payload(idx,0x250);self.spu[addr:addr+len(data)]=data
            if group=='BVOICE1':
                data=payload(0,0x110);at=0x1466980
                self.ee.memory[at:at+len(data)]=data
                data=payload(49,0x110);self.spu[0x146010:0x146010+len(data)]=data
            if group=='NAL':
                data=payload(0,0x210);at=0x1373980
                self.ee.memory[at:at+len(data)]=data
        self.call(0x213d28,16)
        self.rpc(0x50001,[0x3fff3fff])
        assert self.iop.read(0x40fc,4)==0x21ff

    def sdk(self,pc):
        p=self.iop;r=p.registers
        if pc==0x38bc:p.put(2,1) # LIBSD transfer completed
        elif pc==0x38b4:
            count=p.read(r[29]+16,4);source,dest=r[6:8]
            self.spu[dest:dest+count]=p.memory[source:source+count]
            p.put(2,count)
        elif pc in (0x3894,0x38a4):
            reg,value=r[4:6];self.registers[reg]=value
        elif pc==0x389c:
            reg,mask=r[4:6]
            if reg==0x1501:
                for ch in range(24):
                    if not mask&(1<<ch):continue
                    v=1+2*ch;src=self.registers[v|0x2040]
                    assert self.registers[v]==self.registers[0x100|v]
                    assert (self.registers[v|0x300],self.registers[v|0x400])==(15,0x1fc0)
                    self.voices[ch]=Key(memoryview(self.spu)[src:],self.registers[v|0x200],self.registers[v])
                    self.keys+=1
            elif reg==0x1601:
                for ch,key in self.voices.items():
                    if mask&(1<<ch):key.phase=3;key.count=0

    def rpc(self,op,words):
        p=self.iop;area=0x60000
        for i,v in enumerate(words):p.write(area+4*i,v,4)
        out,n=p.run(0x2eb4,[op,area,64],limit=50000,observe=self.sdk)
        self.iop_steps+=n;self.ops[hex(op)]+=1
        return p.read(out,4)

    def call(self,start,*args):
        p=self.ee;pc=start;saved=None;self.calls[hex(start)]+=1
        while True:
            ee_boundaries=self.ee_boundaries
            class Boundary:
                at=None
                def __contains__(self,addr):
                    if addr in ee_boundaries:
                        self.at=addr;return True
                    return False
            boundary=Boundary()
            def resume(_):
                nonlocal saved
                if saved:
                    p.put(29,saved[0]);p.put(31,saved[1]);saved=None
            result,n=p.run(pc,args,limit=40000,stop_before=boundary,observe=resume)
            self.ee_steps+=n
            if boundary.at is None:return signed(result,32)
            r=p.registers
            if boundary.at==0x3242b0:
                result=self.rpc(r[5],[p.read(r[7]+i*4,4) for i in range(3)])
                p.write(r[9],result,4);p.put(2,0)
            elif boundary.at==0x320960:
                source,dest,count=struct.unpack_from('<3I',p.memory,r[4])
                self.iop.memory[dest:dest+count]=p.memory[source:source+count];p.put(2,1)
            elif boundary.at==0x320940:p.put(2,-1)
            else:self.ee_library(boundary.at)
            saved=(r[29],r[31]);pc=r[31];args=()

    def render(self,frames):
        for _ in range(frames):
            output=0
            for ch,v in list(self.voices.items()):
                s=v.next(self.table)
                if s is None:del self.voices[ch]
                else:output+=s
            output=max(-32768,min(32767,output))*32766//32768
            self.pcm.extend(struct.pack('<2h',output,output))

DRIVER=r'''
#include "combat_audio.hpp"
#include <fstream>
#include <iostream>
#include <vector>
int main(int argc,char** argv) {
    ss6::CombatAudio mixer(argv[1]);std::ofstream file(argv[2],std::ios::binary);
    char op;int a,b,value;
    while(std::cin>>op) {
        value=0;
        if(op=='S'){std::cin>>a>>b;value=mixer.play(a,b);}
        if(op=='J'){std::cin>>a>>b;value=mixer.playResidentJingle(a,b);}
        if(op=='V'){std::cin>>a>>b;value=mixer.playVoice(a,b);}
        if(op=='G'){std::cin>>a;mixer.stopGroup(a);}
        if(op=='K'){std::cin>>a;mixer.stop(a);}
        if(op=='T')mixer.tick();
        if(op=='R'){std::cin>>a;std::vector<int16_t> frames(2*a);mixer.render(frames);
            file.write(reinterpret_cast<const char*>(frames.data()),frames.size()*2);}
        std::cout<<value<<'\n';
    }
}
'''
def main():
    assert sha(ELF.read_bytes())==PIN
    o=OriginalDriver(Iso(ISO));commands=[];expected=[];scenarios=Counter()
    def step(op,*args):
        commands.append(' '.join(map(str,[op,*args])));scenarios[op]+=1
        value=0
        if op=='S':value=o.call(0x212fa0,*args)
        elif op=='J':
            tone,code=args
            # Code 0 is also reachable with positive nonzero raw music volume.
            o.ee.write(0x5a9e78,max(1,code*512),4)
            value=o.call(0x212d80,tone)
        elif op=='V':value=o.call(0x213378,*args)
        elif op=='G':o.call(0x213be8,*args)
        elif op=='K':o.call(0x213bc8,*args)
        elif op=='T':o.call(0x213660)
        elif op=='R':o.render(args[0])
        expected.append(value)
    for bank,count in ((0,70),(1,49),(2,49)):
        for tone in range(count):
            step('S',bank,tone);step('R',157)
    for tone in range(13):step('V',50,tone);step('R',211)
    for volume in (0,1,7,14,15,16,25):
        step('J',12,volume);step('R',841)
    for tone in range(15):
        step('V',0,tone)
        for _ in range(3):step('T');step('R',233)
    for tone in (0,1,2,*range(44,89)):
        step('V',49,tone)
        for _ in range(3):step('T');step('R',31)
    for ch in (0,1,2,3,4,14,16,18,21):step('K',ch);step('R',7)
    for i in range(10):step('S',0,i);step('V',0,i)
    for i in range(22):
        if i in (0,2,3,9):step('G',(i+1)%4)
        step('T');step('R',121)
    step('G',3);step('R',1000);step('S',0,12);step('R',19000)
    step('G',3);step('V',0,0)
    for _ in range(3):step('T')
    step('R',67500)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);source=tmp/'driver.cpp';source.write_text(DRIVER)
        exe=tmp/'audio';pcm=tmp/'audio.raw'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',SOURCE,source,SOURCE/'combat_audio.cpp',SOURCE/'combat_music.cpp',SOURCE/'combat_sound_bank.cpp','-o',exe],check=True)
        result=subprocess.run([exe,RES,pcm],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
        returns=list(map(int,result.stdout.split()))
        for idx,(got,want) in enumerate(zip(returns,expected,strict=True)):
            assert got==want,(idx,commands[idx],got,want)
        data=pcm.read_bytes()
        if data!=o.pcm:
            for i,(a,b) in enumerate(zip(struct.iter_unpack('<2h',data),struct.iter_unpack('<2h',o.pcm),strict=True)):
                if a!=b:raise AssertionError(('PCM first difference',i,a,b))
            raise AssertionError('PCM size mismatch')
    report=dict(status='passed',ee_sha256=PIN,iop_sha256=o.irx_hash,source_sha256=sha((SOURCE/'combat_audio.cpp').read_bytes()),bank_sha256=sha((RES/'combat_sound_bank.bin').read_bytes()),ee_instructions=o.ee_steps,iop_instructions=o.iop_steps,game_calls=dict(o.calls),original_rpc_calls=dict(o.ops),operations=dict(scenarios),key_ons=o.keys,frames=len(data)//4,pcm_sha256=sha(data),interpolation_coefficients_sha256=PHASE_SHA,
       scope='Raw Japanese disc samples. Execute EE game functions plus the ADPCMST.IRX dispatcher and register programming. SIF DMA/bus and LIBSD register/transfer boundaries use ready-memory fixtures. PCM compared against a separate SPU2 model; no physical console waveform. Fixed local Haohmaru mirror, default language, 48 kHz dry stereo, cue timing rounded to each 60 Hz update.',
       hardware_model=HW_MODEL)
    REPORT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
