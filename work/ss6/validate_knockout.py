#!/usr/bin/env python3
"""Ordinary KO entry/playback against unmodified original helper functions.

The first landing's effect-task allocation is outside this fixture. Its event
boundary is explicit: original landing predicate + stop + callback install;
we do not patch or stub the original effect allocator and claim a whole call.
"""
import hashlib,itertools,json,struct,subprocess
from pathlib import Path
from mips_probe import idle_fixture,signed

ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 p,o=idle_fixture(raw,(ASSETS/'aid_00.bin').read_bytes(),(ASSETS/'act_00.bin').read_bytes())
 actor,ctx=0x1c00000,0x1e02000
 fields=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,0xfe]+list(range(0x4c,0x64,4))+[0x40,0x44]
 callbacks={0:0,0x172be8:1,0x172c50:2,0x172cb0:3,0x169a50:4}
 commands,expected,scenarios=[],[],[]
 def command(op,*vs):
  commands.append(' '.join(map(str,[op,*vs])));dust=0
  if op=='reset':
   p.memory[o:o+0x200]=bytes(0x200);p.memory[actor:actor+0xf2c]=bytes(0xf2c)
   p.write(actor,o,4);p.write(ctx,actor,4);p.write(actor+0xa3c,-1,4);p.write(actor+0x23c,0x1080,4)
   p.write(o+0xc8,1,4);p.write(o+0x104,0x200,4)
   for addr,args in [(0x120390,[o,0]),(0x11dda0,[o]),(0x11de10,[o]),(0x11e1c0,[o])]:p.run(addr,args)
  elif op=='flags':
   for off,v in zip([0x38,0x104,0x108],vs):p.write(o+off,v,4)
  elif op=='motion':
   for off,v in zip(range(0x4c,0x64,4),vs[:6]):p.write(o+off,v,4)
   for off,v in zip([0x40,0x44],vs[6:]):p.write(o+off,struct.unpack('<I',struct.pack('<f',v))[0],4)
  elif op=='begin':
   p.write(actor+0x23c,vs[0],4);p.run(0x172b38,[ctx,vs[1]]);p.run(0x149918,[actor])
  elif op=='commit':p.run(0x11d8e0,[o])
  elif op in ('animate','move'):
   p.write(o+0x30,vs[0],4);p.run(0x11d730 if op=='animate' else 0x11d6c8,[o])
  elif op=='callback':
   callback=p.read(actor+0x260,4)
   p.run(0x168aa0,[ctx])
   if callback==0x172be8:
    p.run(0x173970,[ctx])
    if p.registers[2]:
     # Explicit presentation boundary, not a whole 0x172be8 comparison.
     p.run(0x1697d0,[ctx]);p.run(0x1522a0,[actor+0x260,0x172c50,2,-1]);dust=1
    else:p.run(callback,[ctx])
   else:p.run(callback,[ctx])
  phase=callbacks[p.read(actor+0x260,4)]
  expected.append([p.read(actor+0x23c,4),phase,dust]+[
   signed(p.read(o+off,4),32) if 0x4c<=off<0x64 else p.read(o+off,2 if off==0xfe else 4) for off in fields])
 for armed,air,variant,mirror,delta in itertools.product([0,1],[0,1],range(3),[0,1],[128,256,512]):
  command('reset');command('flags',0x10000000|mirror*0x80000,0x340,0)
  command('motion',4096,12345,256,8192,-16384,-512,320,64 if air else -2)
  command('begin',0x80|armed*0x1000|air*0x10|0xe0b,variant);command('commit')
  transitions=[];previous=1;dusts=0
  for tick in range(200):
   command('animate',delta);command('move',delta);command('callback')
   phase=expected[-1][1];dusts+=expected[-1][2]
   if phase!=previous:transitions.append([tick+1,phase]);previous=phase
  assert previous==4 and dusts==1,(armed,air,variant,delta,transitions,dusts)
  assert p.read(o+0xc0,4)==1 and p.read(o+0x24,4) in [382,383,400,401,402,403]
  scenarios.append(dict(armed=armed,airborne=air,variant=variant,mirror=mirror,delta=delta,transitions=transitions))
 binary=ROOT/'work/ss6/build-native/ss6-knockout-probe'
 run=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=[list(map(int,row.split())) for row in run.stdout.splitlines()]
 assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):
  assert a==e,(i,commands[max(0,i-4):i+1],a,e)
 report=dict(status='passed',states=len(expected),scenarios=scenarios,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Exact finite FP. Whole 172b38 + 149918 entry, player wrappers, 173970 landing predicate, 1697d0 stop, 172c50 second landing, 172cb0 finish, 169a50 case7. First-landing effect29 allocation/rendering is an explicit excluded event boundary. No full actor scheduler or round-controller claim.')
 (ROOT/'outputs/ss6-feasibility/knockout_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='scenarios'},indent=2));print('scenarios',len(scenarios))
if __name__=='__main__':main()
