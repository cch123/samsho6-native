#!/usr/bin/env python3
"""Compare Ten explosion activation with the Japanese 11f248 and world-4 release."""
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from validate_shin_meters import ASSETS, ROOT, PLAYER, FIELDS, Probe, SOURCE_HASH

CPP=r'''
#include "round_control.hpp"
#include <iostream>
int main(int argc,char** argv){
 ss6::ActionBank bank(argv[1],true);ss6::BattleGauges gauges(argv[1]);
 std::array<ss6::PlayerObject,2> bodies{ss6::PlayerObject(bank,0),ss6::PlayerObject(bank,0)};
 std::array<ss6::StateEntryActor,2> actors;
 std::array<ss6::ActorCommandInput,2> inputs;
 std::array<ss6::InputSystemConfig,2> configs;std::array<ss6::RoundActorStorage,2> storage;
 std::array<ss6::CallbackContext,2> contexts;
 const std::array<ss6::RoundPlayerRef,2> refs{{
  {bodies[0],actors[0],inputs[0],configs[0],storage[0],contexts[0]},
  {bodies[1],actors[1],inputs[1],configs[1],storage[1],contexts[1]}}};
 ss6::BattleRoundState b;int op,side,hp,phase0,phase1;
 while(std::cin>>op>>side>>hp>>phase0>>phase1){
  if(op==2){
    b.gauges={};b.timers={};b.currentState=side;b.field08=hp;b.timers.values[0]=770;b.timers.delta=256;
    for(unsigned i=0;i<2;++i){
      int mode=i?phase1:phase0;auto& a=actors[i];
      a.rageState120=mode==5?2:mode==4?0:mode;a.state194=mode==4?0x240001:mode==5?0x260001:0;
      a.flags23c=0x1000;a.flags244=0;a.flags248=0;configs[i].system=3;
    }
    ss6::RoundControl::advanceBattleClock(b,refs);
    std::cout<<b.timers.values[0]<<' '<<b.timers.delta<<'\n';continue;
  }
  b.gauges={};auto& g=b.gauges;g.scale1239d84=32;
  for(unsigned i=0;i<2;++i){
   auto& a=actors[i];a.fieldA30=static_cast<int>(i)==side?hp:100;a.rageState120=1;a.rageAmount124=24567;
   a.rageDecay128=42;a.swordCurrent134=9999;a.swordMaximum138=24320;
   g.words910[i]=i?phase1:phase0;g.words910[i+2]=8;
  }
  if(op)gauges.releaseExplosion(b,refs);else gauges.startExplosion(b,actors.at(side),side);
  std::cout<<g.scale1239d84;
  for(unsigned i=0;i<2;++i){auto& a=actors[i];
   std::cout<<' '<<g.words910[i]<<' '<<g.words910[i+2]<<' '<<a.rageState120<<' '
    <<a.rageAmount124<<' '<<a.rageDecay128<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138;
  }
  std::cout<<'\n';
 }
}
'''
def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True);p.write(0x4d3d08,PLAYER,4)
    cases=[(0,side,hp,4,4) for side,hp in itertools.product(range(2),range(201))]
    cases.extend(itertools.product((0,1),range(2),(1,2,100,199,200),range(7),range(7)))
    expected=[];instructions=0
    for op,side,hp,phase0,phase1 in cases:
        for i,phase in enumerate((phase0,phase1)):
            a=PLAYER+0xf2c*i
            for off,v in ((0xa24,i),(0xa30,hp if i==side else 100),(0x10c,3),
                          (0x120,1),(0x124,24567),(0x128,42),(0x134,9999),(0x138,24320)):
                p.write(a+off,v,4)
            p.write(0x46a910+4*i,phase,4);p.write(0x46a918+4*i,8,4)
        p.write(0x1239d84,32,4)
        _,count=p.run(0x11f1c8 if op else 0x11f248,[side]);instructions+=count
        row=[p.read(0x1239d84,4)]
        for i in range(2):
            row+=[p.read(addr+4*i,4) for addr in (0x46a910,0x46a918)]
            row+=[p.read(PLAYER+i*0xf2c+off,4) for off in FIELDS[:5]]
        expected.append(row)
    # 1421b0 is the complete battle-clock callback. 141cf8 stops the
    # countdown during startup even before phase 2 has been published.
    clock_cases=list(itertools.product((2,),(3,4,5),(0,1),range(6),range(6)))
    battle=0x1e02000
    p.write(0x4d3d00,battle,4)
    for op,combat,transition,p0,p1 in clock_cases:
        for i,mode in enumerate((p0,p1)):
            a=PLAYER+i*0xf2c;body=0x1d00000+i*0x1000
            p.write(battle+0x24c+4*i,a,4);p.write(a,body,4)
            p.write(a+0x120,(0 if mode==4 else 2 if mode==5 else mode),4)
            p.write(a+0x194,(0x240001 if mode==4 else 0x260001 if mode==5 else 0),4)
            p.write(a+0x23c,0x1000,4)
        p.memory[0x46a910:0x46a944]=bytes(0x34)
        for off,value in ((0,combat),(4,combat),(8,transition),(0x108,0),(0x110,256),(0x114,770)):
            p.write(battle+off,value,4)
        _,steps=p.run(0x1421b0,[battle],limit=30000);instructions+=steps
        expected.append([p.read(battle+0x114,4),p.read(battle+0x110,4)])
    cases.extend(clock_cases)
    with tempfile.TemporaryDirectory() as td:
        path=Path(td);cpp=path/'probe.cpp';exe=path/'probe';cpp.write_text(CPP)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,ROOT/'src/battle_gauges.cpp',
                        ROOT/'src/damage.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        result=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,c))+'\n' for c in cases),text=True,capture_output=True,check=True)
    actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(actual)==len(expected)
    for c,a,e in zip(cases,actual,expected):assert a==e,(c,a,e)
    report=dict(status='passed',elf_sha256=SOURCE_HASH,original_instructions=instructions,cases=len(cases)-len(clock_cases),clock_updates=len(clock_cases),
                hp_range=[0,200],slot_phase_range=[0,6],samples={hp:expected[hp][3:8] for hp in (0,1,2,3,100,199,200)},
                scope='Original 11f248 and 11f1c8 on both slots from every HP and the full P1/P2 phase matrix. Also executes the full 1421b0 battle countdown for both actors and every transition between neutral, startup, rage, explosion, Issen and exhaustion. Compares scale, flags, phases, rage amount/decay and sword. For positive zero divided by positive zero and CVT.W.S 0x7fffffff, the test interpreter uses captured PS2 instruction vectors.',
                hardware_vectors=['https://github.com/unknownbrackets/ps2autotests/blob/master/tests/cpu/ee_fpu/'+f+'.expected' for f in ('muldiv','convert')])
    (ROOT/'outputs/ss6-feasibility/ten-explosion-meter-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'activation/release comparisons',instructions,'original instructions')

if __name__=='__main__':main()
