#!/usr/bin/env python3
"""Whole149918 queue drain; body clip remains unchanged until its own pass."""
import hashlib,itertools,json,subprocess
from round_entry_oracle import ROOT,fixture
from mips_probe import signed

def main():
 commands=[];checks=[];instructions=0;cases=0
 for player,mirror,queued,flags in itertools.product(range(2),range(2),[-1,0,2,189,190,195,196,492,495,497,499,501],[0,0x1000,0x81234567,0xffffffff]):
  p,a,o,b=fixture(player)
  p.run(0x149008,[a,0],limit=200000);p.run(0x149918,[a]);p.run(0x11d8e0,[o])
  p.write(o+0x38,0x10000000|(mirror<<19),4)
  commands += [f'reset {player} {mirror} 280 400','queues',f'queued-action {queued} {flags}']
  p.write(a+0xa3c,queued,4);p.write(a+0x248,flags,4)
  for repeat in range(2):
   before_actor=bytearray(p.memory[a:a+0xf2c]);before_body=bytearray(p.memory[o:o+0x200])
   _,n=p.run(0x149918,[a]);instructions+=n
   for off in [0x248,0xa3c]:before_actor[off:off+4]=p.memory[a+off:a+off+4]
   for off in [0xc0,0xc4,0x104]:before_body[off:off+4]=p.memory[o+off:o+off+4]
   assert before_actor==p.memory[a:a+0xf2c]
   assert before_body==p.memory[o:o+0x200]
   commands.append('commit-actor')
   #The native probe retains its existing complete state projection. Only
   #four published fields can change in149918; assert the rest is untouched.
   expected={7:p.read(a+0x248,4),57:p.read(o+0xc0,4),59:p.read(o+0x104,4),
             -2:signed(p.read(a+0xa3c,4),32),-1:signed(p.read(o+0xc4,4),32)}
   checks.append((len(commands)-1,expected,(player,mirror,queued,flags,repeat)))
  cases+=1
 binary=ROOT/'work/ss6/build-native/ss6-ground-state-probe'
 digest=hashlib.sha256(binary.read_bytes()).hexdigest()
 run=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',capture_output=True,text=True)
 assert run.returncode==0,run.stderr
 rows=[list(map(int,line.split())) for line in run.stdout.splitlines()]
 assert len(rows)==len(commands)
 for at,values,label in checks:
  wanted=rows[at-1].copy()
  for field,value in values.items():wanted[field]=value
  assert rows[at]==wanted,(label,[(j,x,y) for j,(x,y) in enumerate(zip(rows[at],wanted)) if x!=y])
  assert rows[at][54]==0,'149918 must not commit the new body clip'
 assert digest==hashlib.sha256(binary.read_bytes()).hexdigest()
 report=dict(status='passed',cases=cases,whole149918_visits=len(checks),snapshots=len(rows),original_instructions=instructions,
  elf_sha256=hashlib.sha256((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()).hexdigest(),native_sha256=digest,
  scope='Whole149918: pending/same-action/no-action/forced requests on both players/facings,drain twice,idempotence,preservation of all other projected fields and untouched original actor/body bytes. Explicit actor queue fixtures; no claim of complete149008 round initialization.')
 (ROOT/'outputs/ss6-feasibility/actor_action_queue_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
