"""Feed actual 158990 decisions into the real match. Compare each resulting actor update."""
import struct
import subprocess
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest

DRIVER=r'''
#include "native_match.hpp"
#include <bit>
#include <iostream>
int main(int argc,char** argv) {
    const unsigned side=std::stoul(argv[2]);
    std::array<ss6::CpuSeatDecision,2> cpu;
    bool active=false,eof=false;
    cpu[side]=[&](ss6::MatchFighter&,const ss6::MatchFighter&,ss6::BattleRoundState&) {
        ss6::CpuCommand c;active=true;
        if(!(std::cin>>c.mask>>c.slot))eof=true;
        return c;
    };
    ss6::NativeMatch match(argv[1],0,ss6::VersusMode::FixedMatch,nullptr,{0,0},{},0,cpu);
    for(unsigned tick=0;tick<900&&!eof;++tick) {
        active=false;match.tick({});
        if(active&&!eof) {
            const auto& f=match.fighter(side);const auto& a=f.actor;const auto& clock=f.body.timeline.clock();
            std::cout<<a.state194<<' '<<f.body.timeline.action().id()<<' '<<clock.step<<' '<<clock.fractionalTime
                     <<' '<<std::bit_cast<unsigned>(a.x)<<' '<<std::bit_cast<unsigned>(a.y)<<'\n';
        }
    }
}
'''

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        driver=Path(temp)/'probe.cpp';binary=Path(temp)/'probe'
        driver.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',driver,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',binary],check=True)
        for side,perception in ((0,False),(1,False),(0,True),(1,True)):
            source=cpu_actor(side)
            p,a,o=source.p,source.a,source.o
            struct.pack_into('<f',p.memory,o+0x40,(240,400)[side])
            struct.pack_into('<f',p.memory,o+0x1040,(400,240)[side])
            controls=[];expected=[];actions=set()
            # The single-actor original fixture has no contact resolver. End
            # before the first possible contact with the stationary opponent.
            for _ in range(14 if perception else 16):
                if perception:
                    source.run(0x145ef0);source.run(0x146348)
                source.frame(0)
                mask,slot=struct.unpack_from('<Ii',p.memory,a+0x88)
                controls.append(f'{mask} {slot}')
                expected.append([p.read(a+0x194,4),*(p.read(o+i,4) for i in (0x24,0x28,0x2c,0x40,0x44))])
                actions.add(expected[-1][1])
            result=subprocess.run([binary,ASSETS,str(side)],input='\n'.join(controls)+'\n',
                                  text=True,capture_output=True,check=True)
            rows=[list(map(int,row.split())) for row in result.stdout.splitlines()]
            assert len(expected)==len(rows)
            for tick,(got,want) in enumerate(zip(rows,expected)):assert got==want,(side,tick,got,want)
            assert any(action>=150 for action in actions)
            print(f'P{side+1} {len(rows)} actual CPU input visits, perception={perception}, actions {sorted(actions)}')

if __name__=='__main__':main()
