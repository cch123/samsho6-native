#!/usr/bin/env python3
"""Compare complete original effect updates including their queued snapshots.

Original 1235f8 calls 123648,123800/1207e8,1239b8 and record entry; no
callee is replaced. Floating point uses the explicit finite model, not GS/EE
hardware validation. Global effect pause is separate from battle pause.
"""
import hashlib,itertools,json,struct,subprocess
from pathlib import Path
from mips_probe import Probe

ROOT=Path(__file__).resolve().parents[2]
OFFSETS=[0x28,0x2c,0x30,*range(0x4c,0x64,4),0x74,0x78,0x7c,0x8c,*range(0x90,0xb0,4)]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw,finite_model=True)
 assets=ROOT/'work/ss6/extracted/resources'
 for bank,name in [(1,'01HitFlash.bin'),(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
  b=(assets/name).read_bytes();addr=0x4a4810+(bank-1)*0x3da0;p.memory[addr:addr+len(b)]=b
 obj=0x1e00000;commands=[];expected=[];cases=[];instructions=0
 # The queue copy uses unaligned merge instructions. Their byte count must
 # not overwrite the runner's instruction counter or disable its limit.
 p.write(0x4a2250,0,4)
 try:p.run(0x1207e8,[obj,1],limit=100)
 except RuntimeError as error:assert 'instruction budget' in str(error)
 else:raise AssertionError('Original instruction budget was not enforced')
 def state(a):return [p.read(a+o,4) for o in OFFSETS]
 def alive():return int(p.run(0x1233a0,[obj])[0]!=0)
 admitted=[(1,18),*[(5,a) for a in range(32)],*[(6,a) for a in range(6)],*[(7,a) for a in [*range(18),24,25,26]]]
 visits=210
 for (bank,action),flags,paused in itertools.product(admitted,[0,0x80000,0x100000,0x1c0000],[0,1,2]):
  p.memory[obj:obj+0x138]=bytes(0x138)
  for f,v in [(12,280),(13,0),(14,0),(15,1)]:p.put_exact_float(f,v)
  _,n=p.run(0x123330,[obj,bank,action,flags]);instructions+=n
  expected.append([alive(),*state(obj),0]);commands.append(f'run {bank} {action} {flags} {visits} {paused}')
  end=None;draws=0
  for t in range(visits):
   p.write(0x46a924,int(paused==1 or (paused==2 and t%3==0)),4)
   p.write(0x4a2250,0,4)
   _,n=p.run(0x1235f8,[obj],limit=20000);instructions+=n
   count=p.read(0x4a2250,4);assert count in (0,1)
   row=[alive(),*state(obj),count]
   if count:
    assert p.read(0x479250+0x144,4)==1
    row+=state(0x479250);draws+=1
   if not row[0] and end is None:end=t+1
   expected.append(row)
  cases.append(dict(bank=bank,action=action,flags=flags,pause_mode=paused,ended_update=end,draws=draws))
 binary=ROOT/'work/ss6/build-native/ss6-effect-probe'
 result=subprocess.run([str(binary),str(assets)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,r.split())) for r in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):
  assert a==e,(i,commands[i//(visits+1)],i%(visits+1),[(n,x,y) for n,(x,y) in enumerate(zip(a,e)) if x!=y],a,e)
 report=dict(status='passed',cases=len(cases),object_and_queue_states=len(expected),original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  instruction_budget_check='Unmodified1207e8 correctly exceeds100 instructions despite LDL/LDR/SDL/SDR copy loop',
  scope=f'Whole unmodified123330 and1235f8 including record entry, integration, render-queue copy and clock. Exact integer fields; explicit finite FP model. All{len(admitted)} admitted effect actions, four flag combinations and running/frozen/interleaved effect pause. Not original scheduler/task allocator, GS, sound or hardware comparison.',traces=cases)
 (ROOT/'outputs/ss6-feasibility/effect_runtime_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='traces'},indent=2))
if __name__=='__main__':main()
