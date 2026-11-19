"""Compare the ordinary fight tactics dispatcher with whole 15af80 in SLPS_255.59."""
import collections
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from mips_probe import signed

DRIVER=r'''
#include "cpu_decision.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){
    unsigned key;
    while(std::cin>>key) {
        int directSequence;std::cin>>directSequence;
        StateEntryActor a,b;CpuDecisionFrame f;GameRandom r;InputSystemConfig config;
        a.character=key;config.character=key;
        std::cin>>config.system>>f.level100>>f.clockValue>>f.roundIndex>>f.difficulty>>f.battleMode
                >>f.cameraLeft>>f.cameraRight>>r.mode>>r.gameSeed>>r.librarySeed;
        for(auto actor:{&a,&b}) {
            uint32_t x,y;
            std::cin>>actor->character>>actor->state194>>actor->state1a4>>actor->flags23c
                    >>actor->rageState120>>actor->rageAmount124>>actor->fieldA30>>x>>y
                    >>actor->velocityY5c>>actor->bodyAction24;
            actor->x=std::bit_cast<float>(x);actor->y=std::bit_cast<float>(y);
        }
        std::cin>>a.conditions15c[1]>>a.conditionWord17c>>a.cpuTimerDelta08;
        std::cin>>a.cpuRange168>>a.cpuRange16a>>a.cpuRange16c>>a.cpuRange16e>>a.cpuRange170
                >>a.cpuPrevious174>>a.cpuSituation180>>a.cpuSituation182>>a.cpuSituation184;
        auto control=[&](auto apply) {
            apply(a.controlTimers0c[0]);apply(a.control88);apply(a.control8c);apply(a.controlFlagsB4);
            apply(a.flagsB8);apply(a.controlFlagsBC);apply(a.controlCounterC0);apply(a.controlC4);apply(a.controlModeC8);
            apply(a.controlCC);apply(a.controlD0);apply(a.controlDC);apply(a.controlE4);apply(a.controlE8);
            apply(a.controlEC);apply(a.controlF0);apply(a.controlFieldF4);apply(a.controlF8);
            for(auto& word:a.controlMotion38)apply(word);
        };
        control([](auto& value){std::cin>>value;});
        for(auto ptr:{&f.kind2,&f.kind3}) {
            int exists;std::cin>>exists;
            if(exists){CpuObservedObject o;uint32_t x;std::cin>>o.idD0>>o.moveD4>>o.resource14>>x;
                       o.x=std::bit_cast<float>(x);*ptr=o;}
        }
        std::cin>>f.kind3Active;
        try {
            CpuTactics t(argv[1],key);
            if(directSequence>=0)beginCpuSequence(a,config,f,t,r,directSequence);
            else decideCpuAction(a,b,config,f,t,r);
            std::cout<<r.gameSeed<<' '<<r.librarySeed<<' '<<a.cpuRange16e<<' ';
            control([](auto& value){std::cout<<value<<' ';});std::cout<<'\n';
        } catch(const std::exception& e){std::cout<<"ERROR "<<e.what()<<'\n';}
    }
}
'''
HALVES=(0x168,0x16a,0x16c,0x16e,0x170,0x174,0x180,0x182,0x184)
WORDS=(0xc,0x88,0x8c,0xb4,0xb8,0xbc,0xc0,0xc4,0xc8,0xcc,0xd0,0xdc,0xe4,0xe8,0xec,0xf0,0xf4,0xf8,*range(0x38,0x60,4))
def world(src):
    p=src.p
    return [signed(p.run(address,limit=20000)[0],32) for address in (0x1407d0,0x1418f8)]

def capture(src,time,objects=(None,None),active=False):
    p,a,b=src.p,src.a,src.b
    word=lambda i:p.read(i,4)
    r=word(0x5d1bf8)
    rng=[word(0x443150),word(0x3d2e80),p.read(r+0xa8,8)]
    frame=[word(a+0xa10),-1,word(a+0x10c),word(a+0x108),*time,p.read(0x43d05c,1),word(0x4c3808),
           signed(word(b+0x44),32),signed(word(b+0x48),32),*rng]
    for actor in (a,src.other):
        o=word(actor)
        frame.extend([word(actor+i) for i in (0xa10,0x194,0x1a4,0x23c,0x120,0x124,0xa30)])
        frame.extend([word(o+0x40),word(o+0x44),signed(word(o+0x5c),32),signed(word(o+0x24),32)])
    frame.extend([word(a+0x160),word(a+0x17c),word(a+8)])
    halves=[signed(p.read(a+i,2),16) for i in HALVES]
    words=[word(a+i) for i in WORDS]
    words[16]=signed(words[16],32)
    row=frame+halves+words
    for obj in objects:
        row.append(int(bool(obj)))
        if obj:row.extend([signed(word(obj+0xd0),32),signed(word(obj+0xd4),32),word(obj+0x14),word(obj+0x40)])
    row.append(int(active))
    return row,[*rng[1:],halves[3],*words]

def live(seat,perception=False):
    s=cpu_actor(seat=seat);p=s.p;time=world(s);rows=[];original=p.run
    def watch(pc):
        if pc==0x15af80:rows.append([capture(s,time)[0],None])
        if pc==0x158a8c:rows[-1][1]=capture(s,time)[1]
    def run(*args,**kwargs):return original(*args,**kwargs,observe=watch)
    p.run=run
    p.write(s.other+0xfc,1-seat,4)
    for _ in range(110):
        if perception:
            s.run(0x145ef0);s.run(0x146348)
        s.frame(0)
    assert len(rows)>50 and all(post is not None for _,post in rows)
    if not perception:assert rows[0][1][3+19]==141 and rows[0][1][3+21]==121
    if perception:print('P',seat+1,'with world observations, first sequence / opcode:',rows[0][1][22],rows[0][1][24])
    return rows

def direct(char):
    s=cpu_actor(character=char);p,a,b=s.p,s.a,s.b;seed=random.Random(0x15af80+char)
    time=world(s);rows=[];r=p.read(0x5d1bf8,4)
    initial=bytes(p.memory[a:a+0xf2c])
    for i in range(256):
        p.memory[a:a+0xf2c]=initial
        put=lambda k,v:p.write(k,v,4)
        mode=i%8
        put(a+0xc4,mode);put(a+0xbc,seed.choice((0,0,0,1,2,4,8,0x40,0x80)))
        put(a+0xb8,seed.choice((0,0,2,2,0x20,0x22)))
        put(a+0xcc,i%2);put(a+0xc,seed.choice((0,0,128,256,512)))
        put(a+0x160,seed.choice((0,0,0,0x10,0x100,0x200)));put(a+0x17c,0)
        put(a+0xe4,0xffffffff);put(a+0xe8,0xffffffff)
        put(a+0x120,seed.randrange(4));put(s.other+0x120,seed.randrange(4))
        put(a+0xa30,seed.randrange(200));put(s.other+0xa30,seed.randrange(200))
        put(a+0x194,seed.choice((0,0,0,0x10001,0x330000,0x360000)))
        put(s.other+0x194,seed.choice((0,0,0x20000,0x400001,0x170001)))
        for off,upper in zip(HALVES,(4,4,2,4,5,4,6,7,5)):p.write(a+off,seed.randrange(upper),2)
        put(0x443150,i%2);put(0x3d2e80,seed.randrange(2**32));p.write(r+0xa8,seed.randrange(2**64),8)
        p.write(0x43d05c,i%8,1);put(0x4c3808,1)
        row=capture(s,time)[0]
        s.run(0x15af80,a+8)
        rows.append((row,capture(s,time)[1]))
    return rows

def objects():
    rows=[]
    for seat in (0,1):
        s=cpu_actor(seat,character=1,opponent_character=1);p,a,e=s.p,s.a,s.other
        p.write(e+0xa10,1,4)
        time=world(s);registry=s.b+0x29c+(1-seat)*0x108
        p.memory[registry:registry+192]=bytes(192)
        handlers=(0x1840100,0x1840140);obj=(0x1840300,0x1840600)
        for kind,(task,body) in enumerate(zip(handlers,obj),2):
            p.write(task+0x1c,body,4);p.write(body+0xcc,kind,4);p.write(body+0xd0,0x50+kind,4)
            p.write(body+0x14,1,4)
        for i in range(128):
            active=bool(i&4)
            p.write(p.read(e+4,4)+0x128,6 if active else 0,4)
            p.write(a+0xc4,1,4);p.write(a+0xb8,(0,2,0x20,0x22)[i%4],4)
            p.write(e+0x194,0x400001 if i%5==0 else 0,4)
            enabled=[obj[n] if i&(1<<n) else None for n in range(2)]
            for n,body in enumerate(obj):
                p.write(registry+n*4,handlers[n] if enabled[n] else 0,4)
                p.write(body+0xd4,[-1,0,19,32,74][(i//4+n)%5],4)
                struct.pack_into('<f',p.memory,body+0x40,float(i*3-100))
            row=capture(s,time,enabled,active)[0]
            s.run(0x15af80,a+8)
            rows.append((row,capture(s,time,enabled,active)[1]))
    return rows

def sequence_starts():
    s=cpu_actor();p,a=s.p,s.a;time=world(s);rows=[]
    reent=p.read(0x5d1bf8,4)
    for i in range(768):
        p.write(a+0x10c,(0,8,5)[i//256],4)
        p.write(a+0xc4,2 if i%3 else 1,4)
        p.write(0x43d05c,i%8,1);p.write(0x4c3808,int(i%5!=0),4)
        p.write(0x443150,i%2,4)
        p.write(reent+0xa8,i+1,8);p.write(0x3d2e80,i+1,4)
        row=capture(s,time)[0];row[1]=i%256
        s.run(0x15d5b0,a+0x38,i%256,s.player)
        rows.append((row,capture(s,time)[1]))
    return rows

def main():
    assert digest(ELF)==PIN
    groups={'live P1':live(0),'live P2':live(1)}
    groups.update({f'P{i+1} world perceptions':live(i,True) for i in (0,1)})
    groups['enemy throws and companions']=objects()
    groups['sequence initialization']=sequence_starts()
    for c in (0,1,2,3):groups[f'dispatch char {c}']=direct(c)
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',src,ROOT/'src/cpu_decision.cpp',
                        ROOT/'src/cpu_tactics.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        for group,rows in groups.items():
            out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r,_ in rows),
                               capture_output=True,text=True,check=True)
            lines=out.stdout.splitlines();assert len(lines)==len(rows),(group,len(lines),len(rows))
            modes=collections.Counter()
            for i,(line,(row,post)) in enumerate(zip(lines,rows)):
                assert not line.startswith('ERROR'),(group,i,line)
                got=list(map(int,line.split()))
                assert got==post,(group,i,row,[(n,g,w) for n,(g,w) in enumerate(zip(got,post)) if g!=w])
                modes[post[10]]+=1
            print(group,len(rows),'PS2 dispatch snapshots matched',dict(modes),flush=True)
if __name__=='__main__':main()
