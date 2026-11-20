"""Compare the two fight-world AI observation passes before controller dispatch."""
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
int main(int argc,char**argv) {
    StateEntryRules rules(argv[1]);
    unsigned character;
    while(std::cin>>character) {
        CpuTactics t(argv[1],character);StateEntryActor a,b;
        int dist;uint32_t x,y;std::cin>>dist>>a.cpuRange168;
        for(auto p:{&a,&b}) {
            std::cin>>p->character>>p->state194>>p->flags23c>>p->stateCharacter198>>p->state1a4
                    >>p->aliasCharacter1a8>>p->bodyFlags38>>p->velocityX50>>x>>y;
            p->x=std::bit_cast<float>(x);p->y=std::bit_cast<float>(y);
        }
        observeCpuDistances(a,b,dist,t);observeCpuSituation(a,b,t,rules);
        std::cout<<a.cpuRange168<<' '<<a.cpuRange16a<<' '<<a.cpuRange16c<<' '<<a.cpuPrevious174<<' '
                 <<a.cpuWall178<<' '<<a.conditionWord17c<<' '<<a.cpuSituation180<<' '<<a.cpuSituation182<<' '
                 <<a.cpuSituation184<<' '<<a.cpuSituation186<<' '<<a.cpuSituation188<<' '<<a.cpuSituation18a<<'\n';
    }
}
'''
def samples(char,seat):
    enemy=(char+1)%4;s=cpu_actor(seat=seat,character=char,opponent_character=enemy)
    p,a,e,b=s.p,s.a,s.other,s.b;own,other=s.o,s.o+0x1000
    p.write(e+0xa10,enemy,4);p.write(e+0xfc,1-seat,4)
    word=lambda pos:p.read(pos,4)
    half=lambda pos:signed(p.read(pos,2),16)
    rng=random.Random(0x145ef0+char);rows=[]
    for i in range(420):
        table=i%3;index=rng.randrange((64,96,112)[table])
        p.write(e+0x194,table|(index<<16),4)
        p.write(e+0x198,i%4,2);p.write(e+0x23c,rng.choice((0x1000,0x1008,0x1010,0x1018)),4)
        p.write(a+0x23c,0x1000 if i%5 else 0,4)
        p.write(e+0x1a4,1|(rng.randrange(4)<<16),4)
        p.write(e+0x1a8,rng.randrange(4),2)
        if i%29==0:p.write(e+0x23c,word(e+0x23c)|0x200000,4)
        p.write(own+0x38,(i%2)<<19,4);p.write(other+0x50,rng.choice([-1000,0,1000]),4)
        dist=i if i<320 else rng.randrange(620)
        dx=(dist+rng.choice([0,.125,.5,.875]))*(-1 if i%2 else 1)
        p.write(b+0x144,dist,4)
        struct.pack_into('<ff',p.memory,own+0x40,320,10.5)
        struct.pack_into('<ff',p.memory,other+0x40,320+dx,rng.uniform(0,65))
        row=[char,dist,half(a+0x168)]
        for actor,body in ((a,own),(e,other)):
            row.extend([word(actor+0xa10),word(actor+0x194),word(actor+0x23c),half(actor+0x198),
                        word(actor+0x1a4),half(actor+0x1a8),word(body+0x38),signed(word(body+0x50),32),
                        word(body+0x40),word(body+0x44)])
        s.run(0x145ef0);s.run(0x146348)
        rows.append((row,[*(half(a+j) for j in (0x168,0x16a,0x16c,0x174)),word(a+0x178),word(a+0x17c),
                          *(half(a+j) for j in range(0x180,0x18c,2))]))
    return rows

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'test.cpp';exe=Path(tmp)/'test';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,ROOT/'src/cpu_decision.cpp',
                        ROOT/'src/cpu_tactics.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        for char in range(4):
            for seat in range(2):
                rows=samples(char,seat)
                out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r,_ in rows),
                                   capture_output=True,text=True,check=True)
                lines=out.stdout.splitlines();assert len(lines)==len(rows)
                for i,(line,(raw,expected)) in enumerate(zip(lines,rows)):
                    got=list(map(int,line.split()));assert got==expected,(char,seat,i,raw,got,expected)
                print(f'P{seat+1} character {char}: {len(rows)} complete PS2 world observations matched',flush=True)
if __name__=='__main__':main()
