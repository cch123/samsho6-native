#!/usr/bin/env python3
"""Compare represented round reset state with WHOLE original149008."""
import hashlib,json,random,subprocess
from round_entry_oracle import fixture,ROOT
from mips_probe import signed
def main():
 rng=random.Random(0x149008);commands=[];expected=[];instructions=0;logs=[]
 for case in range(256):
  player=case%2;first=case//128;p,a,o,b=fixture(player)
  table,state,action=rng.choice([(0,41,495),(0,41,497),(2,15,48),(0,52,493)])
  flags=[rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32)]
  object_flags=[0x10000000|rng.randrange(2)*0x80000,rng.choice([0x400000,0x400200,0x400300,0x402000]),rng.choice([0,0x40,0xe00])]
  pending=rng.choice([0,1]);meters=[case%4,rng.randrange(1000),rng.randrange(100),rng.randrange(21),rng.randrange(46081),25600]
  timers=[128]+[rng.randrange(60001) for _ in range(35)]
  p.run(0x120390,[o,action]);p.write(a+0x194,table|(state<<16),4)
  for off,v in zip([0x23c,0x240,0x244,0x248],flags):p.write(a+off,v,4)
  for off,v in zip([0x38,0x104,0x108],object_flags):p.write(o+off,v,4)
  p.write(o+0xfe,pending,2)
  for off,v in zip([0x14,0x18,0x1c,0x24,0x28,0x2c],meters):p.write(a+0x10c+off,v,4)
  for i,v in enumerate(timers):p.write(a+0x1ac+i*4,v,4)
  instructions+=p.run(0x149008,[a,first],limit=100000)[1]
  log=bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0].decode();assert 'ASSERT' not in log,log
  logs.append(log)
  out=[p.read(a+off,4) for off in [0xa30,0xa34,0xa38,0x23c,0x240,0x244,0x248]]
  out += [p.read(a+0x24c,1),p.read(a+0x194,2),p.read(a+0x196,2),p.read(a+0x19a,1),p.read(a+0x160,4),p.read(a+0xa3c,4)]
  out += [p.read(a+0x10c+off,4) for off in [0x14,0x18,0x1c,0x24,0x28,0x2c]]
  out += [signed(p.read(a+0x1ac+i*4,4),32) for i in range(36)]
  out += [p.read(o+off,4) for off in [0x24,0x28,0x38,0x104,0x108]]+[p.read(o+0xfe,2)]
  out += [signed(p.read(o+off,4),32) for off in range(0x4c,0x64,4)]+[p.read(o+0x40,4),p.read(o+0x44,4),p.read(a+0xa5c,1)]
  out += [p.read(a+0xa60+off,4) for off in range(0,60*20,4)]
  commands.append(' '.join(map(str,[player,action,first,table,state,*flags,*object_flags,pending,*meters,*timers])));expected.append(out)
 binary=ROOT/'work/ss6/build-native/ss6-round-entry-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(i,commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(a,e)) if x!=y][:20])
 report=dict(status='passed',cases=len(actual),original_instructions=instructions,
  elf_sha256=hashlib.sha256((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  example_original_log=logs[0],scope='Whole149008, no patched/skipped calls. Resident resource00, initialized task/object pools, buffered libc stdout; no ASSERTs. Ordinary mode3,no-time-limit, both first/subsequent rounds,system0 rage0..3 reset semantics,both players,four previous ending states. Compare represented life/posture/state/conditions/meters/timers/body/pending-action/history fields. Extra-object allocation executes originally; native afterimage callback separately verified. Full13fd80,replay/audio/input and all-character initialization excluded.')
 (ROOT/'outputs/ss6-feasibility/round_entry_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
