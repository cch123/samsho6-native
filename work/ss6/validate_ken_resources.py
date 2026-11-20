#!/usr/bin/env python3
"""Validate factory limit, Full Guard cost, secret-technique gain and recharge."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile

from validate_shin_meters import ROOT,ASSETS,PLAYER,OBJECT,BATTLE,Probe,SOURCE_HASH
from validate_ten_explosion_meter import CPP as ROUND_DRIVER

CPP=ROUND_DRIVER[:ROUND_DRIVER.index(' ss6::BattleRoundState b;')]+r"""
 ss6::BattleRoundState b;ss6::DamageTables rules(argv[1]);int op,side,sourceMode,strength,raw;
 int reserve,phase,wait,rage,amount,sword,swordMax,hp,stance,attackSystem;
 while(std::cin>>op>>side>>sourceMode>>strength>>raw>>reserve>>phase>>wait>>rage>>amount>>sword>>swordMax>>hp>>stance>>attackSystem) {
  auto& a=actors[side];auto& g=b.gauges;actors={};configs[side].system=5;configs[1-side].system=0;
  b.requestedState=b.currentState=4;b.field08=0;b.timers={};
  for(auto& f:actors){f.swordCurrent134=f.swordMaximum138=95*256;}
  a.bonusState14c=phase;a.bonusTime150=wait;a.systemMeter158=reserve;a.bonusRate154=256;
  a.swordCurrent134=sword;a.swordMaximum138=swordMax;a.fieldA30=hp;
  a.rageState120=rage;a.rageAmount124=amount;a.rageDecay128=78;
  if(op==4) {
   b.gauges={};a.state194=uint32_t(raw)<<16|1;
   b.timers.values[0]=770;b.timers.delta=256;b.timers.values[5]=strength==1?300:0;b.timers.values[6]=strength==2?300:0;
   ss6::RoundControl::advanceBattleClock(b,refs);
   std::cout<<b.timers.values[0]<<' '<<b.timers.delta<<' '<<b.gauges.scale1239d88<<'\n';continue;
  }
  if(op==0 || op==1){
   ss6::DamageActor source,target;source.system=attackSystem;source.swordCurrent=source.swordMaximum=25600;
   source.attackStrength=strength;target.system=5;target.life=hp;target.armed=stance;
   rules.gainKenSecret(raw,source,target,sourceMode,a);
  } else if(op==2)ss6::DamageTables::spendKenGuard(a);
  else gauges.task(b,refs);
  std::cout<<a.bonusState14c<<' '<<a.bonusTime150<<' '<<a.bonusRate154<<' '<<a.systemMeter158
           <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138<<'\n';
 }
}
"""

def main():
    raw=(ASSETS.parent/'SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
    p=Probe(raw,finite_model=True);p.write(0x4d3d08,PLAYER,4);p.write(0x4d3d00,BATTLE,4)
    p.write(0x43d069,91,1);p.write(0x43d06c,92,1);p.run(0x1113e8,[0x43d058])
    assert [p.read(0x43d069+i*3,1) for i in range(2)]==[32,32]
    fields=(0x14c,0x150,0x154,0x158,0x120,0x124,0x134,0x138)
    rng=random.Random(0x1a4708);cmd=[];expected=[];counts=Counter();steps=0
    for side in range(2):
        a=PLAYER+0xf2c*side;b=PLAYER+0xf2c*(1-side)
        for op in range(5):
            for t in range(230):
                mode=(0,1,2)[t%3];strength=t%3;aux=rng.choice((0,1,8,10,16,26,39,60))
                if op==4:aux=(8,21,69,77,78,79,80)[t%7]
                reserve=rng.choice((0,1,8191,8192,25599,25600,25601,51199,51200,rng.randrange(51200)))
                phase=t%2;wait=rng.choice((0,1,2,149,150));rage=t%2
                amount=rng.choice((0,39*256,10239,10240,10241,47103,47104))
                sword=rng.choice((0,18000,95<<8,100<<8));cap=100<<8
                hp=rng.choice((1,19,20,32,100,200));armed=t%2;system=rng.randrange(6)
                for i in range(2):
                    at=PLAYER+i*0xf2c;ob=OBJECT+i*0x1000
                    p.memory[at:at+0xf2c]=bytes(0xf2c);p.write(BATTLE+0x24c+i*4,at,4)
                    for off,value in ((0,ob),(0x10c,5 if i==side else system),(0x110,i),(0xa24,i),
                               (0xa30,hp),(0x23c,(armed if i==side else 1)*0x1000),(0x134,25600),(0x138,25600)):
                        p.write(at+off,value,4)
                for off,v in zip(fields,(phase,wait,256,reserve,rage,amount,sword,cap)):p.write(a+off,v,4)
                p.write(a+0x128,78,4);p.write(b+0x19a,(0,2,4)[strength],1)
                p.write(BATTLE,4,4);p.write(BATTLE+4,4,4);p.write(BATTLE+8,0,4)
                cmd.append((op,side,mode,strength,aux,reserve,phase,wait,rage,amount,sword,cap,hp,armed,system))
                if op==4:
                    p.write(a+0x194,aux<<16|1,4);p.write(BATTLE+0x114,770,4);p.write(BATTLE+0x110,256,4)
                    p.write(BATTLE+0x128,300 if strength==1 else 0,4);p.write(BATTLE+0x12c,300 if strength==2 else 0,4)
                    _,n=p.run(0x1421b0,[BATTLE],limit=20000);steps+=n;counts["0x1421b0"]+=1
                    expected.append([p.read(BATTLE+0x114,4),p.read(BATTLE+0x110,4),p.read(0x1239d88,4)])
                    continue
                if op<=1:fn=0x1a4708;args=[aux,b,a,mode]
                elif op==2:fn=0x1a4a00;args=[a]
                else:fn=0x11e760;args=[side]
                _,n=p.run(fn,args,limit=100000);steps+=n;counts[hex(fn)]+=1
                expected.append([p.read(a+off,4) for off in fields])
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);cpp=folder/'probe.cpp';cpp.write_text(CPP);exe=folder/'probe'
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',cpp,ROOT/'src/damage.cpp',ROOT/'src/battle_gauges.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r in cmd),text=True,capture_output=True,check=True)
    rows=[list(map(int,r.split())) for r in out.stdout.splitlines()]
    assert len(rows)==len(expected)
    for inp,actual,want in zip(cmd,rows,expected):assert actual==want,(inp,actual,want)
    report=dict(status='passed',sha256=SOURCE_HASH,actor_slots=[0,1],checks=len(rows),sources=dict(counts),original_instructions=steps,
                factory_secret_limit=32,full_guard_cost=40,scope='SLPS_255.59 default versus bytes, attack against image, both sides of the 100-point taper and 200-point clamp, Full Guard at 39/40/41 and overfull sword, secret recharge wait/fast completion, both seats and mixed attack styles.')
    (ROOT/'outputs/ss6-feasibility/ken-resource-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
