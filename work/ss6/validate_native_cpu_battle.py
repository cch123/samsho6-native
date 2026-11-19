"""Compare the opening of two autonomous native fights with the original CPU actor."""
import argparse
import struct
import subprocess
import tempfile
from pathlib import Path

from cpu_fight_oracle import cpu_actor
from validate_haohmaru_special import ContactOracle
from mips_probe import signed
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest

DRIVER=r'''
#include "native_match.hpp"
#include "cpu_decision.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
static const NativeMatch* match;
static unsigned seat,visits;
void snapshot(const StateEntryActor& a,const PlayerObject& body) {
    auto& c=body.timeline.clock();
    std::cout<<a.controlC4<<' '<<a.controlMotion38[1]<<' '<<a.controlMotion38[2]<<' '
             <<a.controlMotion38[3]<<' '<<a.controlMotion38[9]<<' '<<a.control88<<' '<<a.control8c<<' '
             <<a.state194<<' '<<body.timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '
             <<std::bit_cast<uint32_t>(a.x)<<' '<<std::bit_cast<uint32_t>(a.y)<<' '
             <<a.cpuRange168<<' '<<a.cpuRange16a<<' '<<a.cpuRange16c<<' '
             <<a.cpuSituation180<<' '<<a.cpuSituation182<<' '<<a.cpuSituation184;
}
void printContact(const NativeMatch& fight,unsigned tick) {
    std::cout<<"contact "<<tick<<" 0 0";
    for(unsigned i=0;i<2;++i) {
        const auto& f=fight.fighter(i);const auto& t=f.body.timeline;
        std::cout<<' '<<f.actor.stateTable()<<' '<<f.actor.stateIndex()<<' '<<t.action().id()<<' '<<t.clock().step
                 <<' '<<int(t.motion().x)<<' '<<int(t.motion().y)<<' '<<f.actor.fieldA30
                 <<' '<<f.hits<<' '<<f.guards<<' '<<fight.battle().match.players[i].wins;
    }
    for(unsigned i=0;i<2;++i) {
        const auto& f=fight.fighter(i);const auto& a=f.actor;
        const auto& t=f.body.timeline;const auto c=t.clock();
        std::cout<<' '<<std::bit_cast<uint32_t>(t.motion().x)<<' '<<std::bit_cast<uint32_t>(t.motion().y)
                 <<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '<<a.flags23c<<' '<<a.flags240
                 <<' '<<a.flags244<<' '<<a.flags248<<' '<<unsigned(a.flags24c)<<' '<<unsigned(a.effectiveFlags())
                 <<' '<<a.timers[6]<<' '<<a.controlModeC8<<' '<<f.input.sampledFeatures[0xfc/4]
                 <<' '<<f.input.sampledFeatures[0xd8/4]<<' '<<f.input.sampledFeatures[0xd4/4]
                 <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138
                 <<' '<<unsigned(a.previousReaction)<<' '<<a.heavyReaction<<' '<<a.fieldA50
                 <<' '<<unsigned(a.field250)<<' '<<unsigned(a.field251)<<' '<<unsigned(a.contactKind252);
    }
    std::cout<<'\n';
}
namespace ss6 {
void observeCpuStart(const StateEntryActor& a,const StateEntryActor& e,const CpuDecisionFrame& f,const GameRandom& r) {
    if(!visits) {
        std::cout<<"start "<<r.mode<<' '<<r.gameSeed<<' '<<r.librarySeed<<' '<<a.controlCC<<' '
                 <<f.difficulty<<' '<<f.level100<<' '<<f.clockValue<<' '<<f.roundIndex<<' '<<f.battleMode
                 <<' '<<f.cameraLeft<<' '<<f.cameraRight<<' '<<e.state194<<' '
                 <<a.fieldA30<<' '<<e.fieldA30<<' '<<a.flags23c<<' '<<a.conditions15c[1]<<' '
                 <<std::bit_cast<uint32_t>(e.x)<<' ';
        snapshot(a,match->fighter(seat).body);std::cout<<'\n';
    }
    ++visits;
}
}
int main(int argc,char** argv) {
    seat=std::stoul(argv[2]);unsigned length=std::stoul(argv[3]);
    NativeMatch fight(argv[1]);match=&fight;fight.enableCpu(seat,3);
    unsigned ticks=0;
    for(unsigned t=0;t<800 && ticks<length;++t) {
        fight.tick({});
        if(!visits)continue;
        const auto& f=fight.fighter(seat);
        std::cout<<"tick ";snapshot(f.actor,f.body);std::cout<<'\n';printContact(fight,ticks);++ticks;
    }
    return ticks!=length;
}
'''
FIELDS=('mode','sequence','cursor','opcode','callback','mask','slot','state','body action','frame','time','x','y',
        'range','defense range','air range','situation','defense situation','air situation')

def compile_probe(temp):
    src=Path(temp)/'probe.cpp';exe=Path(temp)/'probe';src.write_text(DRIVER)
    source=(ROOT/'src/cpu_decision.cpp').read_text()
    target='    const int mode=decideMode(a,enemy,f,rng);'
    assert source.count(target)==1
    instrument=Path(temp)/'cpu_decision.cpp'
    instrument.write_text(source.replace(target,'    extern void observeCpuStart(const StateEntryActor&,const StateEntryActor&,const CpuDecisionFrame&,const GameRandom&);\n    observeCpuStart(a,enemy,f,rng);\n'+target))
    subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',src,instrument,
                    ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
    return exe

def original(seat,start,count):
    mode,game,library,variant,difficulty,level,clock,round_index,battle_mode,left,right,enemy_state,hp,enemy_hp,flags,conditions,enemy_x,*opening=start
    assert (level,difficulty,battle_mode)==(3,4,3)
    assert clock==-1 and enemy_state==0 and hp==enemy_hp==200,(clock,enemy_state,hp,enemy_hp)
    s=cpu_actor(seat,character=0,difficulty=level);p,a,b,o,e=s.p,s.a,s.b,s.o,s.other
    w=lambda at:p.read(at,4)
    p.write(0x43d05c,difficulty,1);p.write(0x4c3808,battle_mode,4)
    p.write(b+0x14,round_index,4);p.write(e+0xfc,1-seat,4)
    p.write(b+0x44,left,4);p.write(b+0x48,right,4)
    p.write(a+0xcc,variant,4);p.write(e+0xa30,enemy_hp,4)
    p.write(o+0x40,opening[11],4);p.write(o+0x1040,enemy_x,4)
    p.write(e+0x194,enemy_state,4)
    # The original frame loop advances the body before its input visit.
    # The fight starts in the cycling idle ACT, at the phase left by the intro.
    # Prime only its idle animation until it reaches the captured phase.
    assert opening[7]==0 and opening[8]==0 and opening[12]==0,opening
    start_clock=(opening[9],opening[10])
    for _ in range(256):
        prev=bytes(p.memory[o:o+0x140]);s.run(0x11d730,o);s.run(0x11d6c8,o)
        if (w(o+0x28),w(o+0x2c))==start_clock:
            p.memory[o:o+0x140]=prev
            break
    else:raise AssertionError(('could not synchronize idle phase',seat,start_clock))
    s.run(0x145ef0);s.run(0x146348)
    # Seed the independent PS2 PRNG once, at the first tactical visit. The
    # remainder of the fight advances it naturally; no later input is injected.
    first=True
    def watch(pc):
        nonlocal first
        if pc==0x15af80 and first:
            p.write(0x443150,mode,4);p.write(0x3d2e80,game,4)
            p.write(w(0x5d1bf8)+0xa8,library,8);first=False
    run=p.run
    def run_watched(*args,**kwargs):return run(*args,**kwargs,observe=watch)
    p.run=run_watched
    rows=[]
    def half(at):return signed(p.read(at,2),16)
    for _ in range(count):
        first_x=struct.unpack_from('<f',p.memory,o+0x40)[0]
        second_x=struct.unpack_from('<f',p.memory,o+0x1040)[0]
        p.write(b+0x144,int(abs(first_x-second_x)),4)
        s.run(0x145ef0);s.run(0x146348)
        s.frame(0)
        rows.append([*[w(a+j) for j in (0xc4,0x3c,0x40,0x44,0x5c,0x88,0x8c,0x194)],
                     *[w(o+j) for j in (0x24,0x28,0x2c,0x40,0x44)],
                     *[half(a+j) for j in (0x168,0x16a,0x16c,0x180,0x182,0x184)]])
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--frames',type=int,default=26);args=ap.parse_args()
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        exe=compile_probe(temp)
        for seat in (0,1):
            out=subprocess.run([exe,ASSETS,str(seat),str(args.frames)],text=True,capture_output=True,check=True)
            lines=[line.split() for line in out.stdout.splitlines()]
            assert lines[0][0]=='start' and len(lines)==2*args.frames+1
            start=list(map(int,lines[0][1:]))
            actual=[list(map(int,r[1:])) for r in lines if r[0]=='tick']
            contacts=[r[1:] for r in lines if r[0]=='contact']
            # The isolated actor owns animation and input. From the first hit
            # onward the fight world takes over timing via contact hitstop.
            # Run the PS2 hit collector and damage handler at that boundary.
            events=ContactOracle().contacts(contacts,seat)
            assert len(events)==1,(seat,events,contacts[-1][:23])
            contact=events[0]
            first=contact['frame']
            expected=original(seat,start,first)
            for i,(want,got) in enumerate(zip(expected,actual)):
                assert want==got,(seat,i,[(k,v,z) for k,v,z in zip(FIELDS,want,got) if v!=z],start)
            moves=sorted({r[8] for r in actual if r[7]&65535==1})
            assert moves,(seat,'no attack within observation window',actual[-1])
            print(f'P{seat+1}: {len(expected)} independent controller and actor visits to first contact, '
                  f'attack ACTs {moves}, PS2 hit on visit {first+1}, damage {contact["damage"]}, '
                  f'target state 2/{contact["target_state"]}',flush=True)
if __name__=='__main__':main()
