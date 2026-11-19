"""Compare scripted technique starts, polls and row transitions to the Japanese CPU."""
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from mips_probe import signed

BASE=0x4da788
CONTEXT=0x1810000
CALLBACKS=(0x15e428,0x15e508,0x15e7c8)
DRIVER=r'''
#include "cpu_technique_script.hpp"
#include <string_view>
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char**argv){
    InputBindings bind(argv[1]);CpuTactics tables(argv[1],0);
    if(argc>2 && std::string_view(argv[2])=="definitions") {
        int character;unsigned ordinal;
        while(std::cin>>character>>ordinal) {
            if(auto row=tables.techniqueDefinition(character,ordinal))for(auto x:*row)std::cout<<unsigned(x)<<' ';
            std::cout<<'\n';
        }
        return 0;
    }
    int script;
    while(std::cin>>script) {
        StateEntryActor a,b;InputSystemConfig config;GameRandom random;int round,delta;
        std::cin>>round>>delta>>random.mode>>random.gameSeed>>random.librarySeed;
        for(auto p:{&a,&b}) {
            uint32_t x,y;std::cin>>p->character>>p->state194>>p->velocityX50>>p->velocityY5c
               >>p->accelerationY60>>p->bodyFlags38>>x>>y;
            p->x=std::bit_cast<float>(x);p->y=std::bit_cast<float>(y);
        }
        int flag;std::cin>>a.bodyFlags104>>a.bodyFlags108>>a.bodyAction24>>flag>>a.controlModeC8
                         >>a.rageState120>>a.cpuTimerDelta08;
        a.characterBytesF14[9]=flag;config.character=a.character;
        std::cin>>config.system>>a.flags23c>>a.controlMotion38[3]>>a.controlMotion38[4]>>a.controlFlagsB4;
        auto fields=[&](auto apply){
            apply(a.flags244);apply(a.control88);apply(a.control8c);apply(a.controlFlagsBC);apply(a.controlTimers0c[0]);
            apply(a.controlMotion38[0]);apply(a.controlMotion38[9]);apply(a.controlMotion60[3]);
            for(auto& v:a.cpuTechnique98)apply(v);
        };
        fields([](auto& x){std::cin>>x;});
        CpuExecutionFrame frame{config,bind,tables,random,0,3,0,&b,0,false,round,delta};
        try {
            if(script==-200)executeCpuInstruction(a,frame);
            else if(script!=-100)beginCpuTechniqueScript(a,frame,script);
            if(script==-100||(script!=-200 && a.controlMotion38[9]==0x15e428))visitCpuTechniqueScript(a,frame);
            std::cout<<random.gameSeed<<' '<<random.librarySeed;
            std::cout<<' '<<a.controlFlagsB4<<' '<<a.controlMotion38[4];
            fields([](auto& x){std::cout<<' '<<x;});std::cout<<'\n';
        }catch(const std::exception& err){std::cout<<"error "<<err.what()<<'\n';}
    }
}
'''
def setup(char=1):
    s=cpu_actor(character=char);s.run(0x15f5d8,CONTEXT,s.a+8)
    return s

def capture(s,script):
    p,a=s.p,s.a;w=lambda pos:p.read(pos,4)
    rand=[w(0x443150),w(0x3d2e80),p.read(w(0x5d1bf8)+0xa8,8)]
    result=[script,signed(w(s.b+0x14),32),w(s.o+0x30),*rand]
    for pl in (a,s.other):
        o=w(pl);result.extend([w(pl+0xa10),w(pl+0x194),*[signed(w(o+j),32) for j in (0x50,0x5c,0x60)],
                              w(o+0x38),w(o+0x40),w(o+0x44)])
    result.extend([w(s.o+0x104),w(s.o+0x108),w(s.o+0x24),p.read(a+0xf1d,1),w(a+0xc8),w(a+0x120),w(a+8)])
    state=[w(a+j) for j in (0x244,0x88,0x8c,0xbc,0xc,0x38,0x5c,0x6c,*range(0x98,0xb0,4))]
    if state[-1]:state[-1]=1+(state[-1]-BASE)//12
    result.extend([w(a+0x10c),w(a+0x23c),w(a+0x44),w(a+0x48),w(a+0xb4)])
    return result+state,rand[1:]+[w(a+0xb4),w(a+0x48)]+state

def starts():
    s=setup();p,a=s.p,s.a;rows=[]
    data=(ASSETS/'cpu_technique_steps.bin').read_bytes()
    ids=sorted(set(k[0] for k in struct.iter_unpack('<h10x',data)))+[7777]
    for ri in (0,2,10):
        for script in ids:
            p.write(s.b+0x14,ri,4)
            p.write(a+0x5c,0,4)
            for state in (0,0x280001,0x470001):
                p.write(a+0x194,state,4)
                row=capture(s,script)[0];s.run(0x15e370,CONTEXT,script);rows.append((row,capture(s,script)[1]))
    return rows

def polls():
    s=setup();p,a=s.p,s.a;rows=[];rng=random.Random(0x15e7c8);w=lambda i:p.read(i,4)
    data=(ASSETS/'cpu_technique_steps.bin').read_bytes()
    start=0
    for i,(key,move,trigger,param,chance,flags,num,command,pad) in enumerate(struct.iter_unpack('<hBBhBBhBB',data)):
        if key:start=i
        for cb in CALLBACKS:
            for variant in range(3):
                if i+1==len(data)//12 and not flags&1:continue
                p.write(a+0x5c,cb,4);p.write(a+0x98,i-start,4);p.write(a+0x9c,i-start,4)
                p.write(a+0xa0,move+1,4);p.write(a+0xa4,rng.randrange(0,30)<<8,4);p.write(a+0xa8,7,4)
                p.write(a+0xac,BASE+12*start,4);p.write(a+0x6c,move,4)
                p.write(a+0xa10,rng.choice((0,1,3,9,20,45,48)),4);p.write(a+0xf1d,1,1)
                p.write(a+0xc8,35 if variant<2 else 4,4)
                own=0x280001 if not command else ((move+(0 if flags&4 else 64))<<16)|1
                p.write(a+0x194,0 if variant==0 else own,4)
                p.write(s.o+0x108,64 if variant else 0,4);p.write(s.o+0x104,0x40000,4)
                p.write(s.o+0x24,0x23b,4);p.write(s.o+0x38,(i%2)<<19,4)
                p.write(s.other+0x194,0x80002,4)
                for actor in (a,s.other):
                    o=w(actor)
                    p.write(o+0x30,128 if variant==2 else 256,4)
                    for j in (0x50,0x5c,0x60):p.write(o+j,rng.randint(-32768,64000),4)
                    struct.pack_into('<ff',p.memory,o+0x40,240+rng.uniform(-50,50),80+rng.uniform(-75,75))
                p.write(a+0xc,rng.randrange(4)<<8,4)
                row=capture(s,-100)[0];s.run(cb,CONTEXT);rows.append((row,capture(s,-100)[1]))
    return rows

def actor_script(char,op,spirit,seed):
    s=cpu_actor(character=char,spirit=spirit);p,a=s.p,s.a
    first=True;active=False;rows=[];waiting=False;start=None;states=set()
    def watch(pc):
        nonlocal first,active,waiting,start
        if first and pc==0x158a8c:
            # Select the opcode once at the strategy/executor boundary.
            # From here the original actor runs real permission, input,
            # animation and callbacks on each consecutive visit.
            p.write(a+0x44,op,4);p.write(a+0x4c,op,4);first=False;active=True
            if spirit==3:p.write(p.read(0x5d1bf8,4)+0xa8,seed,8)
        if active and pc==0x15f638:
            if p.read(a+0x44,4)!=op:active=False;return
            rows.append([capture(s,-200)[0],None]);waiting=True
        if active and pc==0x158aa0 and waiting:
            rows[-1][1]=capture(s,-200)[1];waiting=False
            if p.read(a+0xac,4):start=(p.read(a+0xac,4)-BASE)//12
            if p.read(a+0x38,4):active=False
    saved=p.run
    def run(*args,**kwargs):return saved(*args,observe=watch,**kwargs)
    p.run=run
    for _ in range(110):
        s.frame(0);states.add(p.read(a+0x194,4))
        if not first and not active:break
    assert rows and start is not None,(char,op,spirit,seed,states)
    return rows,start

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',src,ROOT/'src/cpu_technique_script.cpp',
                        ROOT/'src/cpu_tactics.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        s=setup();p=s.p;identities=[];expected=[]
        for character in range(54):
            count=p.run(0x15f558,[character],limit=25000)[0]
            for ordinal in range(count):
                record=p.run(0x15f518,[character,ordinal],limit=25000)[0]
                assert record
                expected.append(bytes(p.memory[record:record+12]));identities.append(f'{character} {ordinal}')
        result=subprocess.run([exe,ASSETS,'definitions'],input='\n'.join(identities)+'\n',
                              capture_output=True,text=True,check=True)
        assert [bytes(map(int,line.split())) for line in result.stdout.splitlines()]==expected
        print(len(expected),'PS2 technique definitions matched',flush=True)
        groups=[('script starts',starts()),('script callbacks',polls())]
        for op,start in [(183,53),(184,55),(185,57)]:
            rows,base=actor_script(1,op,0,1);assert base==start
            groups.append((f'Nakoruru opcode {op}',rows))
        chosen={}
        for seed in range(1,16):
            rows,base=actor_script(0,132,3,seed)
            chosen.setdefault(base,rows)
            if len(chosen)==4:break
        assert set(chosen)=={0,4,8,12},chosen.keys()
        groups.extend((f'System command 16, script {990+i//4}',rows) for i,rows in sorted(chosen.items()))
        for name,rows in groups:
            out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r,_ in rows),text=True,capture_output=True,check=True)
            lines=out.stdout.splitlines();assert len(lines)==len(rows)
            for index,(line,(row,want)) in enumerate(zip(lines,rows)):
                assert not line.startswith('error'),(name,index,line,row)
                got=list(map(int,line.split()));assert got==want,(name,index,row,[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
            print(name,len(rows),'whole original calls matched',flush=True)
if __name__=='__main__':main()
