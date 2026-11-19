#!/usr/bin/env python3
"""Scoped original helpers for ordinary KO dispatch and winner readiness.

The printf-producing fallback branches are checked as static decision cases,
not by patching their logger or claiming the whole dispatcher was executed.
"""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 actor,obj,battle=0x1c00000,0x1e00000,0x1d00000
 p.write(0x4d3d08,actor,4);p.write(0x4d3d00,battle,4)
 commands,expected=[],[];rng=random.Random(0x151b00);counts={}
 def add(op,vs,want):commands.append(' '.join(map(str,[op,*vs])));expected.append(want)
 def reset():
  p.memory[actor:actor+0x2000]=bytes(0x2000);p.memory[obj:obj+0x1000]=bytes(0x1000)
  p.write(actor,obj,4);p.write(actor+0xf2c,obj+0x400,4)
  p.write(actor+0xa3c,-1,4);p.write(actor+0x190,-1,4)
 for _ in range(2048):
  reset();flags=rng.getrandbits(32);posture=rng.choice([0,0x1000,0x1080,0x1090])
  table=rng.randrange(3);state=rng.choice([0,7,25,30,31,32,52,63,64]);desc=rng.randrange(256)
  of=rng.getrandbits(32);timer=rng.choice([-1,0,1,768]);distance=rng.choice([0,77,78,200])
  p.write(actor+0x23c,posture,4);p.write(actor+0x244,flags,4)
  p.write(actor+0x194,table|(state<<16),4);p.write(actor+0x19a,desc,1)
  p.write(obj+0x108,of,4);p.write(actor+0x1c4,timer,4);p.write(battle+0x144,distance,4)
  p.write(actor+0xf2c+0x23c,0x1000,4)
  far,_=p.run(0x168c58,[0,0,distance,bool(posture&0x1000),1])
  p.run(0x151b00,[actor]);add('gates',[flags,posture,table,state,desc,of,timer,far],p.read(actor+0x244,4))
 counts['whole_151b00_gate_fields']=len(commands)
 for table,state,air,gate,end,pending,condition in itertools.product([0,1,2],[0,32,52],[0,1],[0,2],[0,1],[0,1],[0,16,32,64,1<<30]):
  reset();posture=0x1000|air*16;p.write(actor+0x23c,posture,4);p.write(actor+0x244,gate,4)
  p.write(actor+0x194,table|(state<<16),4);p.write(obj+0xc0,end,4);p.write(obj+0x104,pending,4)
  p.write(actor+(0x17c if condition==1<<30 else 0x160),condition,4)
  p.memory[obj+0x40:obj+0x44]=struct.pack('<f',280)
  p.memory[obj+0x440:obj+0x444]=struct.pack('<f',344)
  ready,_=p.run(0x145240,[actor,52]);queued=p.read(actor+0x190,4)==52<<16
  add('victory',[posture,gate,table,state,int(end and not pending),int(bool(condition))],2 if ready else 1 if queued else 0)
 counts['whole_145240']=len(commands)-sum(counts.values())
 for state in [0,4,5,6,7,10]:
  for lock,flags in itertools.product([0,1,2],range(256)):
   p.write(battle+4,state,4);p.write(battle+12,lock,4);p.write(actor+0x24c,flags,1)
   p.run(0x143390,[battle]);add('lock',[flags,state,lock],p.read(actor+0x24c,1))
 counts['whole_143390']=len(commands)-sum(counts.values())
 # Unlocked KO request on table2 avoids the unconditional normal/attack
 # fallback. Run all of149980 and then all of14b880 at the small timer.
 for state,air,gate,ko in itertools.product([15,30,31,32,44,61],[0,1],[0,2],[0,1]):
  reset();posture=0x1000|air*16|ko*128
  p.write(actor+0x23c,posture,4);p.write(actor+0x244,gate,4);p.write(actor+0x194,2|(state<<16),4)
  p.run(0x149980,[actor]);p.run(0x14b880,[actor])
  add('ko',[posture,gate,2,state,0,0],signed(p.read(actor+0x192,2),16))
 counts['whole_149980_14b880_no_logger']=len(commands)-sum(counts.values())
 static=0
 for table,state,timer,lock in itertools.product([0,1,2],[0,15,16,30,31,32,61],[0,0x257ff,0x25800],[0,1]):
  protected=table==2 and state in [15,16,30,31,61]
  add('ko',[0x1080,2,table,state,timer,lock],31 if table<2 or (timer>0x257ff and not protected) else -1);static+=1
 binary=ROOT/'work/ss6/build-native/ss6-round-rules-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=list(map(int,result.stdout.split()));assert len(actual)==len(expected)
 for command,a,e in zip(commands,actual,expected):assert a==e,(command,a,e)
 report=dict(status='passed',original_function_cases=counts,static_fallback_cases=static,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unmodified original helpers on ordinary resource00 fixtures;151b00 comparison covers244 gates only.145240 includes condition254 and action-pending bit.14b880 printf branches are static cases only, not whole-function execution. No whole frame, UI task, time-slow, full round or hardware claim.')
 (ROOT/'outputs/ss6-feasibility/round_rules_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
