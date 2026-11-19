#!/usr/bin/env python3
"""Original normal0 selection and unchanged-idle continuity, projected fields."""
import hashlib,itertools,json,subprocess
from round_entry_oracle import fixture,ROOT
from mips_probe import signed

def main():
 p,a,o,b=fixture();ctx=0x1e02000;p.write(ctx,a,4)
 commands=[];expected=[];instructions=0
 def original(address,args=()):
  nonlocal instructions
  value,count=p.run(address,args,limit=200000);instructions+=count;return value
 for player,rage,life,armed,mode,setting,time in itertools.product(
     [0,1],[-1,0,1,2,3,4],[48,49,100,200],[0,1],[0,1,2],[0,1,2,3],[-1,0,30,31]):
  p.write(a+0xa24,player,4);p.write(a+0xa30,life,4);p.write(a+0x120,rage,4)
  p.write(a+0x23c,armed*0x1000,4);p.write(a+0xa3c,-1,4)
  p.write(o+0x24,999,4);p.write(o+0x104,0x200,4)
  p.write(0x123a0c0,mode,1);p.write(0x1373948+4*player,setting,4)
  p.write(b+0x13c,3 if time==-1 else 0,4)
  #1407d0 uses90*256 per displayed unit (180*256 in mode2).
  p.write(b+0x114,max(0,time)*(46080 if mode==2 else 23040),4)
  remaining=signed(original(0x1407d0),32)
  assert remaining==time
  original(0x169d10,[ctx])
  commands.append(f'idle {life} {rage} {armed} {remaining} {int(mode==1)} {setting}')
  expected.append([p.read(a+0xa3c,4)])
 choice_cases=len(commands);actor_visits=0
 #Live ordinary meter integration currently admits0/1. Other states are
 #covered above at the selector boundary, not forced through that runtime.
 for life,rage,nextLife,nextRage in itertools.product([48,49,200],range(2),[48,49,200],range(2)):
  p,a,o,b=fixture();original(0x149008,[a,0]);original(0x149918,[a]);original(0x11d8e0,[o])
  p.write(a+0xa30,life,4);p.write(a+0x120,rage,4)
  states=[]
  for tick,state in enumerate([2,0,0,0,0,0,0,2,0]):
   if tick==2:p.write(a+0xa30,nextLife,4);p.write(a+0x120,nextRage,4)
   original(0x11d730,[o]);original(0x11d6c8,[o])
   #Explicit direct-state requests match ContactTrial's present boundary.
   #14ff80/1491e0 reject redundant state0, preserving the existing clip.
   original(0x14ff80,[a+0x18c,0,state]);original(0x149d08,[a]);actor_visits+=1
   original(0x149918,[a]);original(0x11d8e0,[o])
   states += [p.read(o+off,4) for off in [0x24,0x28,0x2c,0xc0]]
  commands.append(f'idle-flow {life} {rage} {nextLife} {nextRage}');expected.append(states)
 binary=ROOT/'work/ss6/build-native/ss6-ordinary-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for command,got,want in zip(commands,actual,expected):assert got==want,(command,got,want)
 report=dict(status='passed_for_projected_fields',choice_cases=choice_cases,continuity_cases=len(commands)-choice_cases,
  whole149d08_visits=actor_visits,original_instructions=instructions,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole169d10 action-choice projection with both players/weapons,rage-1..4,life48/49/100/200,mode0/1/2,practice rage0..3,time infinite/0/30/31;1407d0 executed unchanged.36 direct-state trajectories compare action/step/fraction/end after whole149d08 and body wrappers:idle keeps its clip after gauge/life changes and reselects on re-entry. Native integration uses ordinary armed/system0,rage0/1,infinite time; training/time modes not exposed. Explicit gauge/life fixtures are not full battle producers or pad parsing. Color/audio/GS excluded.')
 (ROOT/'outputs/ss6-feasibility/idle_choice_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
