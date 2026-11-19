#!/usr/bin/env python3
"""Whole original gauge callback vs native ordinary system-0 branch.

Uses the explicit finite FP model documented in damage-model.txt. Original
instructions and internal calls are unmodified; this is not hardware proof.
"""
import hashlib,itertools,json,random,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw,finite_model=True)
 actor,obj,battle=0x1c00000,0x1e00000,0x1e01000
 p.write(0x4d3d08,actor,4);p.write(0x4d3d00,battle,4)
 # Normal system 0 has no auxiliary gauge, charge, or explosion. The global
 # battle-freeze gates are open. The per-actor hitstop flag remains varied.
 p.write(0x46a940,0,4)
 commands,expected=[],[];rng=random.Random(0x11e760)
 cases=[]
 for current,wait,table,flag in itertools.product(
   [0,1,17919,17920,17921,24575,25597,25598,25599,25600,30000],
   [0,1,20],range(3),[0,0x10]):
  cases.append((current,25600,wait,0,0,0,table,0,0,0,flag,0))
 for amount,decay,table,transition in itertools.product([0,1,61,62,63,0xb800],[0,1,62],range(3),range(2)):
  cases.append((46080,46080,0,1,amount,decay,table,0,0,0,0,transition))
 for _ in range(2048):
  rage=rng.randrange(2);maximum=46080 if rage else 25600
  cases.append((rng.randrange(maximum+256),maximum,rng.choice([0,0,0,1,20]),rage,
                rng.randrange(0xb801),rng.randrange(1,129),rng.randrange(3),rng.choice([0,0,21]),
                rng.randrange(3),rng.choice([0,0x30,0x40000,0x80000,0xc0030]),
                rng.choice([0,0x10,0x210,0xe10]),rng.randrange(2)))
 max_steps=0
 for row in cases:
  current,maximum,wait,rage,amount,decay,table,state,strength,f104,f108,transition=row
  p.memory[actor:actor+0x2000]=bytes(0x2000);p.memory[obj:battle+0x800]=bytes(battle+0x800-obj)
  p.write(battle,4,4);p.write(battle+8,transition,4)
  for off,value in [(0,obj),(0x130,wait),(0x134,current),(0x138,maximum),(0x120,rage),
                    (0x124,amount),(0x128,decay),(0x194,table|(state<<16)),(0x23c,0x1000)]:
   p.write(actor+off,value,4)
  p.write(actor+0x19a,[0,2,4][strength],1)
  p.write(obj+0x104,f104,4);p.write(obj+0x108,f108,4)
  before_actor=bytes(p.memory[actor:actor+0xf2c]);before_obj=bytes(p.memory[obj:obj+0x200])
  _,steps=p.run(0x11e760,[0]);max_steps=max(max_steps,steps)
  expected.append([signed(p.read(actor+off,4),32) for off in [0x134,0x138,0x130,0x120,0x124,0x128]]+[p.read(obj+0x108,4)])
  # Ensure this admitted branch has no silently omitted actor/object effects.
  mutable={j for off in [0x120,0x124,0x130,0x134,0x138] for j in range(off,off+4)}
  assert all(v==before_actor[j] or j in mutable for j,v in enumerate(p.memory[actor:actor+0xf2c]))
  assert all(v==before_obj[j] or 0x108<=j<0x10c for j,v in enumerate(p.memory[obj:obj+0x200]))
  commands.append(' '.join(map(str,row)))
 binary=ROOT/'work/ss6/build-native/ss6-meter-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for command,a,e in zip(commands,actual,expected):assert a==e,(command,a,e)
 report=dict(status='passed_under_explicit_model',cases=len(cases),max_original_steps=max_steps,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unpatched 0x11e760, resource00/system0 ordinary rage and sword; includes complete callee execution and actor/object write coverage.',
  scheduler_evidence={'gauge_registration':'0x11e520: priority5 -> 0x11e708 -> 0x11e760 for both players',
                      'battle_registration':'0x139648: priority50 -> coroutine0x138f48 -> 0x140270',
                      'order':'0x112838/0x1128c4 visits ascending priority buckets; gauges before battle'},
  limitations=['Finite FP model, not EE hardware verification.','No rage explosion, charge or other systems.','Full game scheduling not exercised by this function probe.'])
 (ROOT/'outputs/ss6-feasibility/meter_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
