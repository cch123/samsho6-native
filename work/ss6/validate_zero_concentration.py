#!/usr/bin/env python3
"""Compare both combatant slots' Mu accounting with Japanese original functions."""
import collections
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile

from validate_shin_meters import ASSETS, ROOT, PLAYER, OBJECT, BATTLE, Probe, SOURCE_HASH
from validate_ten_explosion_meter import CPP as TEN_DRIVER

CPP=TEN_DRIVER[:TEN_DRIVER.index(' ss6::BattleRoundState b;')]+r"""
 ss6::BattleRoundState b;
 int op,side,phase,reserve,remaining,decay,rage,amount,hp,wins,other,force,meditate,state,transition;
 while(std::cin>>op>>side>>phase>>reserve>>remaining>>decay>>rage>>amount>>hp>>wins>>other>>force>>meditate>>state>>transition){
  b.gauges={};b.field08=transition;b.requestedState=b.currentState=4;b.timers={};
  auto& g=b.gauges;g.scale1239d84=64;g.scale1239d88=256;g.paletteTones.fill(7);
  for(int i=0;i<2;++i){
   actors[i]={};configs[i].system=i==side?4:0;
   auto& a=actors[i];a.fieldA30=hp;a.swordCurrent134=a.swordMaximum138=25600;
   a.state194=state;a.rageState120=rage;a.rageAmount124=amount;a.rageDecay128=130;
   a.flags23c=0x1000+(meditate?0x8000:0);a.flags248=force?0x10000:0;
   b.match.players[i].wins=wins;b.match.players[i].requiredWins=2;
  }
  auto& a=actors[side];
  a.systemState13c=phase;a.systemAmount140=reserve;a.systemTime144=remaining;a.systemDecay148=decay;
  g.words910[side]=op==1?5:6;g.words910[1-side]=other;g.words910[2+side]=3;g.words910[3-side]=other==5||other==6;
  if(op==5){
   g.delta46a908=remaining;b.timers.values[0]=770;b.timers.delta=256;
   for(auto& fighter:actors)fighter.flags23c|=force?0x10000000:0;
   ss6::RoundControl::advanceBattleClock(b,refs);
   std::cout<<b.timers.values[0]<<' '<<b.timers.delta;
   for(unsigned i=0;i<3;++i)std::cout<<' '<<ss6::resolveObjectDelta(256,i,g);
   for(unsigned i=0;i<2;++i)std::cout<<' '<<g.words910[10+i];
   std::cout<<'\n';continue;
  }
  if(op==0)gauges.beginConcentration(b,side);
  else if(op==1)gauges.releaseConcentration(b,refs);
  else if(op==2)gauges.endConcentration(b,a,side);
  else if(op==3)gauges.startExplosion(b,a,side,4);
  else gauges.task(b,refs);
  for(int v:{a.systemState13c,a.systemAmount140,a.systemTime144,a.systemDecay148,a.rageState120,a.rageAmount124,
            a.rageDecay128,a.swordCurrent134,a.swordMaximum138})std::cout<<v<<' ';
  for(int i=0;i<4;++i)std::cout<<g.words910[i]<<' ';
  std::cout<<g.scale1239d84<<' '<<g.paletteTones[511]<<' '<<g.paletteTones[512]<<' '<<g.paletteTones[1023]<<'\n';
 }
}
"""

def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True);p.write(0x4d3d08,PLAYER,4);p.write(0x4d3d00,BATTLE,4)
    rand=random.Random(0x11ef90);rows=[];expected=[];instructions=0
    offsets=(0x13c,0x140,0x144,0x148,0x120,0x124,0x128,0x134,0x138)
    for op,side in itertools.product(range(6),range(2)):
        for t in range(260):
            phase=t%5;reserve=rand.choice((0,1,5120,16694,16695,16696,25599,25600,25601,51199,51200,rand.randrange(51200)))
            remaining=rand.choice((0,1,105,106,107,108,2048));decay=rand.choice((106,107))
            rage=rand.choice((0,0,0,1,2,3));amount=rand.choice((0,1,6,7,299,300,301,47104))
            hp=rand.choice((0,1,20,65,100,200));wins=t%2;other=rand.randrange(7)
            force=rand.randrange(2);meditate=rand.randrange(2);state=rand.choice((0,0x250001,0x240001,0x120002))
            transition=rand.randrange(2);a=PLAYER+side*0xf2c
            if op==5:remaining=(0,64,128,256)[t%4]
            for i in range(2):
                at=PLAYER+i*0xf2c;obj=OBJECT+i*0x1000
                p.memory[at:at+0xf2c]=bytes(0xf2c);p.memory[obj:obj+320]=bytes(320)
                for off,v in ((0,obj),(0xa24,i),(0x110,i),(0x10c,4 if side==i else 0),(0xa30,hp),(0x138,25600),
                              (0x134,25600),(0x120,rage),(0x124,amount),(0x128,130),(0x194,state),
                              (0x23c,0x1000+meditate*0x8000+(0x10000000 if force and op==5 else 0)),(0x248,force*0x10000)):
                    p.write(at+off,v,4)
                p.write(BATTLE+0x24c+i*4,at,4)
                p.write(BATTLE+0x27c+i*0x108,wins,4);p.write(BATTLE+0x280+i*0x108,2,4)
            for key,v in zip(offsets,(phase,reserve,remaining,decay,rage,amount,130,25600,25600)):p.write(a+key,v,4)
            p.write(0x46a910+side*4,5 if op==1 else 6,4);p.write(0x46a910+(1-side)*4,other,4)
            p.write(0x46a918+side*4,3,4);p.write(0x46a918+(1-side)*4,other in (5,6),4)
            for addr,v in ((BATTLE,4),(BATTLE+4,4),(BATTLE+8,transition),(0x1239d84,64),(0x1239d88,256)):p.write(addr,v,4)
            p.memory[0x3ebf30:0x3ec730]=b'\x07\0'*1024
            args=[op,side,phase,reserve,remaining,decay,rage,amount,hp,wins,other,force,meditate,state,transition]
            rows.append(args)
            if op==5:
                p.write(0x46a908,remaining,4);p.write(BATTLE+0x110,256,4);p.write(BATTLE+0x114,770,4)
                _,count=p.run(0x1421b0,[BATTLE],limit=30000);instructions+=count
                deltas=[]
                for i in range(3):
                    value,n=p.run(0x11f450,[256,i]);instructions+=n;deltas.append(value)
                expected.append([p.read(BATTLE+0x114,4),p.read(BATTLE+0x110,4),*deltas,
                                 p.read(0x46a938,4),p.read(0x46a93c,4)])
                continue
            _,count=p.run([0x11ef30,0x11ef90,0x11e548,0x11f248,0x11e708][op],[side],limit=35000);instructions+=count
            expected.append([*[p.read(a+v,4) for v in offsets],*[p.read(0x46a910+4*i,4) for i in range(4)],p.read(0x1239d84,4),
                             *[p.read(0x3ebf30+2*i,2) for i in (511,512,1023)]])
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);cpp=folder/'test.cpp';exe=folder/'test';cpp.write_text(CPP)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/battle_gauges.cpp',ROOT/'src/damage.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        proc=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r in rows),text=True,capture_output=True,check=True)
    values=[list(map(int,line.split())) for line in proc.stdout.splitlines()]
    assert len(values)==len(rows)
    for row,want,got in zip(rows,expected,values):
        assert got==want,(row,want,got)
    report=dict(status='passed',elf_sha256=SOURCE_HASH,original_instructions=instructions,comparisons=len(rows),
                cases_per_function=dict(zip(('11ef30','11ef90','11e548','11f248','11e708','1421b0+11f450'),collections.Counter(r[0] for r in rows).values())),
                scope='Ordinary/forced release, simultaneous phase ordering and scale, fixed Zero explosion, meditation, decay boundaries and exclusion during 1/37, per-seat score gating, palette restoration and retained reserve.')
    (ROOT/'outputs/ss6-feasibility/zero-concentration-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)

if __name__=='__main__':main()
