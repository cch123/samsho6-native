"""Compare whole original 15f638 visits, including callbacks, RNG and sequence state."""
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_cpu_decision import world
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest

DRIVER=r'''
#include "cpu_execution.hpp"
#include <iostream>
#include <bit>
int main(int argc,char** argv) {
    ss6::InputBindings bindings(argv[1]);ss6::ActionSelection selection(argv[1]);
    unsigned character,spirit,trait,level,wall;
    while(std::cin>>character>>spirit>>trait>>level>>wall) {
        ss6::CpuTactics tactics(argv[1],character);ss6::InputSystemConfig config{spirit,character};
        ss6::StateEntryActor a;a.character=character;
        ss6::GameRandom random;
        std::cin>>random.mode>>random.gameSeed>>random.librarySeed>>a.flags23c>>a.state194>>a.state1a4
                >>a.flags244>>a.flags248>>a.bodyAction24>>a.bodyFlags104>>a.controlModeC8>>a.controlCounterC0>>a.timers[0];
        for(auto& x:a.conditions15c)std::cin>>x;
        std::cin>>a.cpuTimerDelta08>>a.controlTimers0c[0]>>a.controlFlagsB4>>a.controlFlagsBC>>a.control88>>a.control8c;
        for(auto& x:a.controlMotion38)std::cin>>x;
        for(auto& x:a.controlMotion60)std::cin>>x;
        uint32_t x,y;std::cin>>x>>y>>a.velocityY5c;
        a.x=std::bit_cast<float>(x);a.y=std::bit_cast<float>(y);
        ss6::StateEntryActor enemy;ss6::SelectionThreat threat;unsigned ox;
        std::cin>>ox>>a.bodyFlags38>>a.cpuRange168>>a.conditionWord17c>>threat.distance
                >>enemy.character>>enemy.state194>>enemy.state1a4>>enemy.flags23c>>enemy.bodyAction24>>enemy.bodyFlags104
                >>enemy.stateCharacter198>>enemy.aliasCharacter1a8>>enemy.auxiliaryState128>>enemy.auxiliaryFlag134
                >>a.controlE4>>a.controlE8>>a.cpuRange16a>>a.cpuRange16e>>a.controlTimers0c[2]>>a.controlTimers0c[3];
        a.opponentX=std::bit_cast<float>(ox);int count;
        for(auto& n:a.cpuTechnique98)std::cin>>n;
        std::cin>>count;for(int i=0;i<count;++i){int k;std::cin>>k;threat.opponentObjectKinds[i]=k;}
        try {
            ss6::executeCpuInstruction(a,{config,bindings,tactics,random,uint8_t(trait),int(level),wall,&enemy,threat.distance,selection.opponentThreat(a,enemy,threat)});
            std::cout<<random.gameSeed<<' '<<random.librarySeed<<' '<<a.controlTimers0c[0]<<' '<<a.controlFlagsB4
                     <<' '<<a.controlFlagsBC<<' '<<a.control88<<' '<<a.control8c;
            for(auto x:a.controlMotion38)std::cout<<' '<<x;
            for(auto x:a.controlMotion60)std::cout<<' '<<x;
            std::cout<<' '<<a.cpuRange16e<<' '<<a.controlTimers0c[2]<<' '<<a.controlTimers0c[3];
            for(auto n:a.cpuTechnique98)std::cout<<' '<<n;std::cout<<'\n';
        } catch(const std::exception& e) {std::cout<<"ERROR "<<e.what()<<'\n';}
    }
}
'''
def technique(s):
    state=list(struct.unpack_from('<6I',s.p.memory,s.a+0x98))
    if state[5]:state[5]=(state[5]-0x4da788)//12+1
    return state


def input_row(s):
    p,a,o=s.p,s.a,s.o
    u=a+8;r=p.read(0x5d1bf8,4)
    w=lambda pos:p.read(pos,4)
    e=s.other;eo=w(e);aux=w(e+4)
    kinds=[]
    for i in range(48):
        t=w(s.b+0x29c+(1-s.player)*0x108+i*4)
        if t:kinds.append(w(w(t+0x1c)+0xcc))
    return [w(a+0xa10),w(a+0x10c),p.read(0x4e5420+w(a+0xa10),1),w(u+0x100),w(a+0x178),
            w(0x443150),w(0x3d2e80),p.read(r+0xa8,8),w(a+0x23c),w(a+0x194),w(a+0x1a4),
            w(a+0x244),w(a+0x248),w(o+0x24),w(o+0x104),w(a+0xc8),w(a+0xc0),w(a+0x1b0),
            *struct.unpack_from('<3I',p.memory,a+0x15c),w(u),w(u+4),w(a+0xb4),w(a+0xbc),w(a+0x88),
            w(a+0x8c),*struct.unpack_from('<20I',p.memory,a+0x38),w(o+0x40),w(o+0x44),struct.unpack_from('<i',p.memory,o+0x5c)[0],
            w(eo+0x40),w(o+0x38),p.read(a+0x168,2),w(a+0x17c),w(s.b+0x144),
            w(e+0xa10),w(e+0x194),w(e+0x1a4),w(e+0x23c),w(eo+0x24),w(eo+0x104),p.read(e+0x198,2),
            p.read(e+0x1a8,2),w(aux+0x128) if aux else 0,w(aux+0x134) if aux else 0,w(a+0xe4),w(a+0xe8),p.read(a+0x16a,2),p.read(a+0x16e,2),w(a+0x14),w(a+0x18),*technique(s),len(kinds),*kinds]

def result(s):
    r=input_row(s)
    return [*r[6:8],*r[22:47],s.p.read(s.a+0x16e,2),s.p.read(s.a+0x14,4),s.p.read(s.a+0x18,4),*technique(s)]

def live(seat,perception=False):
    s=cpu_actor(seat);p=s.p
    rows=[];expected=[];saved=p.run
    def observe(pc):
        if pc==0x15f638:rows.append(input_row(s))
        if pc==0x158aa0:expected.append(result(s))
    def run(*args,**kwargs):return saved(*args,**kwargs,observe=observe)
    p.run=run
    for _ in range(115):
        if perception:
            s.run(0x145ef0);s.run(0x146348)
        s.frame(0)
    if perception:assert rows[0][27+3]==113
    assert len(rows)==len(expected)>50
    return rows,expected

def chains():
    s=cpu_actor();p,a=s.p,s.a
    s.run(0x15f5d8,0x1850000,a+8)
    rows=[];expected=[];rng=random.Random(0x162920);initial=bytes(p.memory[a:a+0xf2c])
    for spirit in (0,3,8):
        for index in range(21):
            for _ in range(5):
                p.memory[a:a+0xf2c]=initial
                # A landed ordinary attack entered its recovery callback
                # with an original chain opportunity still latched.
                for off,v in ((0x10c,spirit),(0x194,(index<<16)|1),(0x44,113),(0x48,113),(0x5c,0x1625b8),
                              (0xb4,0x13004),(0x1b0,0)):p.write(a+off,v,4)
                p.write(s.o+0x104,0xc0000,4);p.write(p.read(0x5d1bf8,4)+0xa8,rng.getrandbits(64),8)
                rows.append(input_row(s));s.run(0x15f638,0x1850000);expected.append(result(s))
    return rows,expected

def direct():
    s=cpu_actor();p,a=s.p,s.a;r=p.read(0x5d1bf8,4)
    s.run(0x15f5d8,0x1850000,a+8)
    rows=[];expected=[];rng=random.Random(0x15f638)
    initial=bytes(p.memory[a:a+0xf2c])
    for op in range(256):
        for seat in (0,1):
            p.memory[a:a+0xf2c]=initial
            p.write(a+0x10c,[1,4][seat],4)
            p.write(a+0x44,op,4);p.write(a+0x48,0xffffffff,4)
            p.write(0x3d2e80,rng.getrandbits(31),4);p.write(r+0xa8,rng.getrandbits(64),8)
            for step in range(35):
                p.write(a+0x244,4 if step%8>=2 else 0,4)
                p.write(a+0x194,(step%15<<16)|(step%8>=3),4)
                p.write(a+0x248,0x40 if step%15==3 else 0,4)
                p.write(a+0x160,rng.getrandbits(32) if step%4==1 else 0,4)
                p.write(a+0x164,rng.getrandbits(32),4)
                p.write(a+8,[0x100,0x80][step%2],4)
                if op in (35,36):
                    p.write(a+0x168,(step<34)+1,2);p.write(a+0x194,0,4)
                    p.write(s.b+0x144,[350,240,110][step//8%3],4)
                    p.write(a+8,4*256,4)
                if 37<=op<=44:
                    p.write(a+0x168,3 if step<10 else 0,2);p.write(a+0x178,step==15,4)
                    p.write(a+0x160,0x8180 if 3<=step<20 else 0,4);p.write(a+0x248,0,4)
                if 20<=op<=33:
                    p.write(a+0x168,(step//2)%4,2);p.write(a+0x17c,int(step%4==1),4)
                if op in (54,64,65,68,69):
                    p.write(s.other+0x23c,0x1000|int(step<8),4)
                    p.write(s.other+0x194,0x40001 if step%3==1 else 0,4)
                    p.write(s.other+0x198,0,2);p.write(s.o+0x1104,0x80000000 if step%8==4 else 0,4)
                    p.write(a+0x194,2 if step==3 else 0,4)
                    p.write(a+0xe4,-1,4)
                if 80<=op<=103 or 140<=op<=175:
                    p.write(a+0x23c,0x1000|(0x10 if 3<=step<(32 if op>=140 else 14) else 0),4)
                    p.write(a+0x244,0x20 if step>=9 else 0,4)
                    p.write(a+0x194,0x160000 if step==14 else 0,4)
                    p.write(a+0x160,0x70 if 2<=step<14 else 0,4)
                    p.write(s.o+0x5c,0x100000-step*0x20000,4)
                    struct.pack_into('<2f',p.memory,s.o+0x40,180 if seat else 400,60)
                rows.append(input_row(s));s.run(0x15f638,0x1850000);expected.append(result(s))
                if p.read(a+0x38,4):break
    return rows,expected

def main():
    assert digest(ELF)==PIN
    groups=[('chain cancels',*chains()),('direct',*direct()),('live P1',*live(0)),('live P2',*live(1)),('P1 with both perception passes',*live(0,True)),('P2 with both perception passes',*live(1,True))]
    with tempfile.TemporaryDirectory() as temp:
        driver=Path(temp)/'probe.cpp';binary=Path(temp)/'probe';driver.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',driver,ROOT/'src/cpu_execution.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',binary],check=True)
        for name,rows,expected in groups:
            out=subprocess.run([binary,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r in rows),
                               text=True,capture_output=True,check=True)
            lines=out.stdout.splitlines();assert len(lines)==len(expected)
            for t,(line,raw,want) in enumerate(zip(lines,rows,expected)):
                assert not line.startswith('ERROR'),(name,t,raw,line)
                got=list(map(int,line.split()))
                assert got==want,(name,t,raw,[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
            print(name,len(rows),'whole CPU instruction callbacks matched')

if __name__=='__main__':main()
