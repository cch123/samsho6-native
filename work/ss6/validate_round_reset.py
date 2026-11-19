#!/usr/bin/env python3
"""Compare cross-round flags, timers and ordinary system0 meter resets."""
import hashlib,json,random,subprocess
from pathlib import Path
from mips_probe import Probe,signed
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 addr=0x1c00000;rng=random.Random(0x149008);commands=[];expected=[]
 p.write(0x4c3808,3,4);p.write(0x4c38a8,0,4);p.write(0x123a0c0,0,1)
 p.write(0x43d068,0,1);p.write(0x43d06b,0,1)
 for _ in range(512):
  values=[signed(rng.getrandbits(32),32) for _ in range(36)]
  for i,v in enumerate(values):p.write(addr+i*4,v,4)
  p.run(0x14cf80,[addr]);out=[signed(p.read(addr+i*4,4),32) for i in range(36)]
  commands.append('timers '+' '.join(map(str,values)));expected.append(out)
 for _ in range(1024):
  values=[rng.getrandbits(32) for _ in range(4)]+[rng.randrange(256)]
  for i,v in enumerate(values):p.write(addr+i*4,v,1 if i==4 else 4)
  p.run(0x14fe10,[addr]);out=[p.read(addr+i*4,1 if i==4 else 4) for i in range(5)]
  commands.append('flags '+' '.join(map(str,values)));expected.append(out)
 offsets=[0x14,0x18,0x1c,0x24,0x28,0x2c]
 for _ in range(512):
  p.memory[addr:addr+0x80]=bytes(0x80);p.write(addr+4,rng.randrange(2),4)
  values=[rng.randrange(4),rng.randrange(0xb801),rng.randrange(129),rng.randrange(21),rng.randrange(46081),rng.choice([25600,46080])]
  for off,v in zip(offsets,values):p.write(addr+off,v,4)
  before=bytes(p.memory[addr:addr+0x80]);p.run(0x14ec80,[addr])
  # Complete meter helper, including all callees: confirm it did not mutate
  # any unrepresented meter fields, not just the six reported values.
  mutable={i for off in offsets for i in range(off,off+4)}
  assert all(v==before[i] or i in mutable for i,v in enumerate(p.memory[addr:addr+0x80]))
  out=[signed(p.read(addr+off,4),32) for off in offsets]
  commands.append('meters '+' '.join(map(str,values)));expected.append(out)
 binary=ROOT/'work/ss6/build-native/ss6-round-reset-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[[int(v) for v in line.split()] for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for command,a,e in zip(commands,actual,expected):assert a==e,(command,a,e)
 report=dict(status='passed',cases={'whole14cf80_timer_reset':512,'whole14fe10_flag_reset':1024,'whole14ec80_system0_meters':512},
  total=len(actual),elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unmodified helpers with exact integer comparisons. Timer19 and selected cross-round flag preservation. System0 ordinary configuration, both player indices, rage0..3; complete meter write coverage. New-round149008 dispatcher, actor/JDG reset, intro, UI, other systems and forced gauge options excluded. Rage2/3 reset semantics do not admit explosion gameplay in ContactTrial.')
 (ROOT/'outputs/ss6-feasibility/round_reset_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
