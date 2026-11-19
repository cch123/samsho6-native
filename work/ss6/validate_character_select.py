#!/usr/bin/env python3
"""Japanese factory VS character/spirit/arena selection, through the face-off request."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json
import struct
import subprocess
import tempfile

from mips_probe import Probe, signed
from validate_dash_motion import ELF, PIN, ROOT, digest

REPORT = ROOT/'outputs/ss6-feasibility/character_select_validation.json'
DRIVER = r'''
#include "character_select.hpp"
#include <iostream>
int main(int n,char**v){
    ss6::CharacterSelect a; a.stageOwner=std::stoi(v[1]); a.random.librarySeed=std::stoull(v[2]);
    if(std::stoi(v[3])){a.stageOption=1;a.seats[0].palette=0x50003;a.seats[1].palette=0x60002;}
    std::array<ss6::NormalizedPadSample,2> pads{};
    unsigned x,y;while(std::cin>>x>>y){
        const unsigned next[]{x,y};
        for(int j=0;j<2;++j){pads[j].pressed=next[j]&~pads[j].held;pads[j].held=next[j];}
        a.tick(pads);
        auto put=[](auto x){std::cout<<x<<' ';};
        put(a.frame);put(a.remaining);put(a.firstChooser);put(a.spiritRequested);put(a.complete);
        put(a.characterDirectorVisible?a.drawFrame:-1);put(a.spiritDirectorVisible?a.spiritDrawFrame:-1);
        put(a.stageCursor);put(a.stageOption);put(a.random.librarySeed);
        for(unsigned j=0;j<2;++j){
            auto& c=a.seats[j];auto& s=a.spirits[j];
            for(auto x:{c.phase,c.count,c.cell,c.selected,c.palette,int(c.committed),c.drawPhase,c.drawCount,int(c.drawPortrait),int(c.controls)})put(x);
            for(auto x:{s.phase,s.count,s.choiceCount,s.cursor,s.progress,s.secondary,s.drawPhase,s.drawCount,s.drawCursor,s.drawProgress,s.progress?a.seats[j].spirit:0})put(x);
        }
        put(a.audio.size());for(auto s:a.audio){put(s.bank);put(s.tone);}std::cout<<'\n';
    }
}
'''
# External boundaries. The actor/selection dispatchers, input, geometry's phase
# completion returns, both task pools, timer/PRNG and selection tables execute
# from the ELF. Graphics code is validated separately against the CS/GS assets.
LEAVES = (
    0x109f08,0x10add8,0x112f08,0x112f30,0x1132c0,0x113f98,0x1142d8,
    0x1145c0,0x1148f0,0x114d88,0x1159d0,0x115ae0,0x116200,0x116268,
    0x1163c0,0x116478,0x1170d8,0x117170,0x117de8,0x118320,0x118420,
    0x11c248,0x11d668,0x11d908,0x1207d8,0x122e98,0x122eb8,0x1252f0,
    0x129cf8,0x12d188,0x12ee68,0x135300,0x1353a0,0x152988,0x17e038,
    0x1c2420,0x1e79c8,0x1e7b70,0x1e7ba0,0x1e7c00,0x1e7d60,0x318358,0x323050)
class Source:
    def __init__(self,owner,seed,reselect=False):
        self.p=p=Probe(ELF.read_bytes(),finite_model=True)
        for pc in LEAVES:
            p.memory[pc:pc+8]=struct.pack('<II',0x03e00008,0x0000102d)
        p.run(0x1113e8,[0x43d058])
        for pc in (0x1123a8,0x112570,0x11e290,0x127eb0):
            p.run(pc,limit=200000)
        p.write(0x443150,1,4);p.write(0x4c3808,6,4);p.write(0x4c38a8,2,4)
        p.write(0x4c3818,owner,4);self.seed=p.read(0x5d1bf8,4)+0xa8
        if reselect:
            p.write(0x4c3828,1,4)
            for j,col in enumerate((0x50003,0x60002)):p.write(0x456894+j*48,col,4)
        p.write(self.seed,seed,8);p.run(0x128008,limit=500000)
        self.last=[0,0];self.requested=0;self.complete=0;self.visits=0
        self.drawSpirit=[[0,0,5,0] for _ in range(2)]
        self.grid=[p.read(0x4c82a8+i*4,4) for i in range(42)]
    def observe(self,pc):
        p=self.p;r=p.registers
        if pc==0x12a418:
            self.drawChar[r[4]]=[*r[5:9]]
        elif pc==0x1309a8:
            s=r[4];self.drawSpirit[s]=[*r[5:7],p.read(0x4c8d40+s*52,4),p.read(0x4c8d44+s*52,4)]
        elif pc==0x1129c8 and r[4]==0x12eee8:self.requested=1
        elif pc==0x1252f0:
            assert r[4:8]==[1,1,0x12f800,0x125e10];self.complete=1
        elif pc==0x128470:self.charFrame=p.read(0x4c8290,4)
        elif pc==0x12f100:self.spiritFrame=p.read(0x4c8290,4)
        elif pc in (0x1e7b70,0x1e7ba0):
            self.audio.extend((signed(r[4],64),r[5]))
    def step(self,pads):
        p=self.p;self.drawChar=[[0]*4 for _ in range(2)];self.audio=[]
        self.charFrame=self.spiritFrame=-1
        for s,h in enumerate(pads):
            p.write(0x443568+4*s,h,4);p.write(0x443570+4*s,self.last[s],4);p.run(0x117fd8,[s])
        self.last=list(pads);_,count=p.run(0x112838,limit=400000,observe=self.observe)
        self.visits+=count
        # Before 12eee8/12f8e8 the public cursor defaults describe the incoming
        # factory page; its visible flag and choiceCount remain zero.
        age=p.read(0x4c8d18,4)
        stage=p.read(0x4c8d80,4) if self.requested and (age or p.read(0x4c8288,4)==1200) else 10
        a=[p.read(0x4c8290,4),p.read(0x4c8288,4)-p.read(0x4c8280,4),
           signed(p.read(0x4c38a4,4),32),self.requested,self.complete,
           self.charFrame,self.spiritFrame,stage,p.read(0x4c3828,4),p.read(self.seed,8)]
        for s in range(2):
            ss=s*4; data=0x456890+s*48;sp=0x4c8d18+s*52
            commit=p.read(data+16,4);progress=p.read(sp+44,4);n=p.read(sp,4)
            a += [p.read(0x1239e28+ss,4),p.read(0x1239e20+ss,4),p.read(0x4c82a0+ss,4),
                  p.read(data,4) if commit else -1,p.read(data+4,4),commit,*self.drawChar[s],
                  p.read(0x1239e78+ss,4),p.read(0x1239e70+ss,4),n,p.read(sp+40,4) if n else 5,
                  progress,p.read(sp+48,4),*self.drawSpirit[s],p.read(data+8,4)]
        return a+[len(self.audio)//2,*self.audio]

def make_case(name):
    owner,seed=0,1
    inputs=[[0,0] for _ in range(420)]
    def key(seat,t,word):inputs[t-1][seat]=word
    if name in ('opposite','reselect'):
        # P1: Haohmaru. P2: Nakoruru. P2 makes the first confirmation.
        owner=1;key(0,66,32)
        for t,word in ((65,64),(76,64),(88,16),(90,16),(92,512)):
            key(1,t,word)
        key(0,99,1024)
    elif name=='random-mirror':
        seed=455
        # Both random tiles are distinct cells with the same random lookup.
        for s in range(2):
            key(s,64,64 if not s else 128);key(s,78,16);key(s,80,16)
            if s:key(s,82,16)
            key(s,87,0x400000|0x80000|0x100000)
    elif name=='all-cells':
        inputs=[[0,0] for _ in range(790)]
        tick=65
        for col in range(7):
            for seat in range(2):
                for row in range(6):key(seat,tick+row*2,32)
                if col<6:key(seat,tick+12,128 if not seat else 64)
            tick+=25
        for seat in range(2):key(seat,tick,0x80000|4)
    elif name=='stages':
        inputs=[[0,0] for _ in range(750)]
        for s in (0,1):key(s,72,1024)
    elif name=='palette':
        for s in range(2):key(s,70,32);key(s,74,2)
    elif name=='repeat':
        for s in range(2):
            for t in range(62,103):key(s,t,128|32)
            key(s,125,0x100000|4)
    else:raise ValueError(name)
    shift=220 if name=='all-cells' else 0
    steps={'opposite':(2,-2),'reselect':(2,-2),'palette':(0,1),'random-mirror':(3,-1),'repeat':(-1,0),'all-cells':(-3,-2),'stages':(1,-1)}[name]
    for s,n in enumerate(steps):
        for k in range(abs(n)):key(s,shift+224+s*7+k*15,128 if n>0 else 64)
        key(s,shift+274+s*9,1024)
    for t,w in ((310,128),(313,64),(316,128),(320,2),(339,128),(375,4)):
        if name!='stages' or t<339:key(owner,shift+t,w)
    if name=='stages':
        for n in range(11):key(owner,339+31*n,128)
        key(owner,684,1024)
    return owner,seed,inputs

def check(args):
    exe,name=args
    owner,seed,inputs=make_case(name)
    src=Source(owner,seed,name=='reselect')
    stream=''.join(f'{a} {b}\n' for a,b in inputs)
    rows=subprocess.check_output([exe,str(owner),str(seed),str(int(name=='reselect'))],input=stream,text=True).splitlines()
    history=[];last=None;visited=[set(),set()];stages=set()
    for frame,(pads,line) in enumerate(zip(inputs,rows),1):
        expected=src.step(pads);row=list(map(int,line.split()))
        if row!=expected:
            differences=[(j,b,a) for j,(a,b) in enumerate(zip(expected,row)) if a!=b]
            raise AssertionError((name,frame,pads,differences,'native',row,'ELF',expected))
        for j in (0,1):visited[j].add(row[12+21*j])
        if row[20+21*owner] in (20,22,23,24,25):stages.add(row[7])
        state=tuple(row[i] for i in (10,20,31,41))
        if state!=last:history.append([frame,*state]);last=state
        if src.complete:
            if name=='all-cells':assert [len(c) for c in visited]==[42,42]
            if name=='stages':assert stages==set(range(11))
            return dict(stage_cells=sorted(stages),visited_cells=[len(c) for c in visited],name=name,owner=owner,seed=seed,frames=frame,executed_instructions=src.visits,
                        characters=[row[13],row[34]],palettes=[row[14],row[35]],spirits=[row[30],row[51]],
                        stage=row[7],stage_option=row[8],state_changes=history)
    raise AssertionError('Face-off handoff missing: '+name)

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        test=Path(temp)/'select.cpp';test.write_text(DRIVER);exe=Path(temp)/'select'
        subprocess.run(['c++','-std=c++20','-O2','-I'+str(ROOT/'src'),str(test),str(ROOT/'src/character_select.cpp'),
                        str(ROOT/'src/game_random.cpp'),str(ROOT/'src/scalar_float.cpp'),'-o',str(exe)],check=True)
        names=['opposite','palette','random-mirror','repeat','all-cells','stages','reselect']
        with ProcessPoolExecutor(4) as pool:
            results=list(pool.map(check,[(str(exe),name) for name in names]))
    REPORT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,
        cpp_sha256=digest(ROOT/'src/character_select.cpp'),header_sha256=digest(ROOT/'src/character_select.hpp'),
        scope='Factory local VS, Japanese SLPS-25559. Full original scheduler 112838 with 128008 and nested births, 117fd8 raw pad sampling, character/spirit/setting/stage controls, all reached draw-phase completion decisions and ordered SE requests; external graphics, platform I/O, and audio driver submitted at fixture boundaries. Stops at original 1252f0(1,1,12f800,125e10); the face-off and fight are separate scenes.', cases=results),indent=2)+'\n')
    print(f'{len(results)} original/native selection sequences, {sum(c["frames"] for c in results)} scheduler visits through face-off')
if __name__=='__main__':main()
