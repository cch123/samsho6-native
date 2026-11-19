#!/usr/bin/env python3
"""Persistent player object wrappers, using original whole functions as oracle."""
import hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import idle_fixture,signed
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 p,o=idle_fixture(raw,(ASSETS/'aid_00.bin').read_bytes(),(ASSETS/'act_00.bin').read_bytes())
 p.write(o+0xc8,1,4);p.write(o+0x104,0x200,4);p.run(0x120390,[o,0]);p.run(0x11dda0,[o]);p.run(0x11de10,[o]);p.run(0x11e1c0,[o])
 commands,expected=[],[]
 fields=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4]+list(range(0x4c,0x64,4))+[0x40,0x44]
 def command(op,*vs):
  commands.append(' '.join(map(str,[op,*vs])))
  if op=='flags':
   for off,v in zip([0x38,0x104,0x108],vs):p.write(o+off,v,4)
  elif op=='request':p.run(0x11d908,[o,vs[0],0,vs[1]])
  elif op=='commit':p.run(0x11d8e0,[o])
  elif op=='pending':p.write(o+0xfe,vs[0],2)
  elif op=='stop':p.run(0x11d990,[o])
  elif op=='rewind':
   p.write(o+0x28,0,4);p.write(o+0x2c,0,4);p.run(0x11d850,[o])
  elif op in ['animate','move']:
   p.write(o+0x30,vs[0],4);p.run(0x11d730 if op=='animate' else 0x11d6c8,[o])
  elif op=='motion':
   for off,v in zip(range(0x4c,0x64,4),vs[:6]):p.write(o+off,v,4)
   for off,v in zip([0x40,0x44],vs[6:]):p.write(o+off,struct.unpack('<I',struct.pack('<f',v))[0],4)
  expected.append([signed(p.read(o+off,4),32) if 0x4c<=off<0x64 else p.read(o+off,4) for off in fields]+[p.read(o+0xfe,2)])
 rng=random.Random(140270)
 actions=[141,186,362,0,2,4,6,8,10,12,185,278,282,286,288,290,292,338,344,350,368,143,189,190,191,192,195,196,342,348,354,360,366,372,
          48,49,50,51,52,53,54,55,382,383,384,385,400,401,402,403,492,493,494,495,496,497,498,499,500,501]
 for action in actions:
  for freeze in [0,0x10,0x20,0x30]:
   for delta in [128,256,512]:
    command('flags',0x10000000|(rng.randrange(2)<<19),0x6000200,0)
    command('motion',0,-1008*256,144*256,0,0,0,16,0)
    command('pending',freeze//8)
    command('request',action,1);command('commit')
    for i in range(40):
     command('animate',delta);command('move',delta)
    command('flags',p.read(o+0x38,4),p.read(o+0x104,4)&~0x30,p.read(o+0x108,4)|0x800)
    for i in range(40):command('animate',delta);command('move',delta)
 # Repeated requests, deferred commits, phase changes and a held action.
 for _ in range(800):
  op=rng.randrange(6)
  if op<2:command('request',rng.choice(actions),op)
  elif op==2:command('commit')
  elif op==3:command('stop')
  else:command('animate' if op==4 else 'move',256)
 # A landing callback releases the duration-zero hold with 0x11d990.
 # Reassert the damage-callback flag each tick to exercise terminal jump
 # suppression, including both bounce holds and already-completed frames.
 for action in [382,383,384,385,400,401,402,403]:
  for delta in [128,256,512]:
   command('flags',0x10000000,0x200,0)
   command('motion',0,0,0,0,0,0,320,0)
   command('pending',1);command('request',action,1);command('commit')
   holds=0
   for _ in range(180):
    command('flags',p.read(o+0x38,4),p.read(o+0x104,4)|0x2000,p.read(o+0x108,4))
    command('animate',delta);command('move',delta)
    y=struct.unpack('<f',struct.pack('<I',p.read(o+0x44,4)))[0]
    if p.read(o+0x104,4)&0x100 and y<=0:
     command('stop');holds+=1
   assert holds==2,(action,delta,holds)
   assert p.read(o+0x24,4)==action and p.read(o+0xc0,4)==1
 #FE100 toggles facing on deferred commit, including a forced same-action
 #restart. Rewinding a held/end record must retain motion and completion.
 for mirror in [0,1]:
  for pending in [0x100,0x101,0x106,0x708]:
   command('flags',0x10000000|(mirror<<19),0x200,0)
   command('pending',pending);command('request',384,1);command('commit')
   command('animate',256);command('move',256);command('rewind')
   command('pending',pending);command('request',384,1);command('commit')
 for action in [48,49,50,51]:
  command('flags',0x10000000,0x200,0);command('request',action,1);command('commit')
  for _ in range(35):
   command('flags',p.read(o+0x38,4),p.read(o+0x104,4)|0x2000,p.read(o+0x108,4));command('animate',256)
  assert p.read(o+0xc0,4)
  command('pending',0x10);command('rewind');command('animate',128);command('rewind');command('pending',0)
 binary=ROOT/'work/ss6/build-native/ss6-player-object-probe'
 run=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,row.split())) for row in run.stdout.splitlines()]
 assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):
  assert a==e,(i,commands[max(0,i-4):i+1],[(hex(off) if n<len(fields) else 'fe',x,y) for n,(off,x,y) in enumerate(zip(fields+[0xfe],a,e)) if x!=y])
 report=dict(status='passed',states=len(expected),actions=actions,elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scope='Whole original 0x11d908, 0x11d8e0/0x11dbf0, 0x11d730 and 0x11d6c8; deferred action requests, JDG object flags, consumption reset, freeze and retreat clamp; ordinary player objects, muted audio, exact finite FP')
 (ROOT/'outputs/ss6-feasibility/player_object_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
