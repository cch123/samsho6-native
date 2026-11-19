#!/usr/bin/env python3
"""Round UI ownership/callbacks against the unchanged original scheduler.

The fixture supplies already-loaded textures, an owner and free object pool.
1249c8's allocation/file/audio setup is excluded;124620,112838,124898 and
all three completion callbacks execute unchanged, without skipped callees.
"""
import hashlib,itertools,json,struct,subprocess
from pathlib import Path
from mips_probe import Probe
from validate_effect_runtime import OFFSETS

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'work/ss6/extracted/resources'
TASKS=range(0x122f040,0x1232440,0x34)
OWNER=0x1e00000

def fixture(raw,label):
 p=Probe(raw,finite_model=True)
 for bank,name in [(5,'Display.bin'),(6,'Display2.bin')]:
  data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0
  p.memory[base:base+len(data)]=data
 p.run(0x112570,limit=30000)
 # The real loader has already installed these textures by battle entry.
 # Supply residency only;1240c0's reference counts still run unchanged.
 for i in range(32):p.write(0x4c3510+i*4,i+1,4)
 for i in range(100):
  p.write(0x1d00000+i*0x140+0x138,0x1d00000+(i+1)*0x140 if i<99 else 0,4)
 p.write(0x46a900,0x1d00000,4);p.write(0x46a904,100,4)
 p.write(0x345188,0,4) # Original audio-disabled option, not a patched callee.
 p.write(OWNER,0xc,4);p.write(OWNER+4,label,4)
 p.run(0x116200,[10,11])
 for descriptor in ([2,1] if label==1 else [label+2]):
  for f,v in [(12,320),(13,240),(14,-50 if descriptor==2 else -60),(15,1)]:p.put_exact_float(f,v)
  p.run(0x124620,[0x4a3e30+descriptor*0x6c,0x100000,OWNER,0],limit=20000)
 return p

def snapshot(p):
 tasks=[(p.read(a+0x20,4)-0x4a3e30)//0x6c for a in reversed(TASKS) if p.read(a+4,4)]
 count=p.read(0x4a2250,4)
 row=[p.read(OWNER,4)&1,len(tasks),*tasks,count]
 for i in range(count):
  o=0x479250+i*0x148
  assert p.read(o+0x144,4)==1
  rec=p.run(0x1233a0,[o])[0]
  row+=list(struct.unpack_from('<30H',p.memory,rec))
  row+=[p.read(o+offset,4) for offset in OFFSETS]
 return row

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 binary=ROOT/'work/ss6/build-native/ss6-round-intro-probe'
 cases=[];states=draws=instructions=0
 for label,mode in itertools.product(range(1,11),range(3)):
  visits=[210,32,310][mode];p=fixture(raw,label)
  result=subprocess.run([str(binary),str(ASSETS)],input=f'{label} {visits} {mode}\n',text=True,capture_output=True,check=True)
  actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
  assert len(actual)==visits+1
  ended=None;transitions=[];previous=None
  for visit in range(visits+1):
   if visit:
    p.write(0x46a924,int(mode==1 or (mode==2 and visit%3==1)),4)
    p.write(0x4a2250,0,4)
    _,n=p.run(0x112838,limit=100000);instructions+=n
   expected=snapshot(p)
   assert actual[visit]==expected,(label,mode,visit,[(i,a,b) for i,(a,b) in enumerate(zip(actual[visit],expected)) if a!=b],len(actual[visit]),len(expected))
   if not expected[0] and ended is None:ended=visit
   tasks=expected[2:2+expected[1]]
   if tasks!=previous:transitions.append(dict(visit=visit,descriptors=tasks));previous=tasks
   states+=1;draws+=p.read(0x4a2250,4)
  assert ended==([200 if label==1 else 110,None,300 if label==1 else 165][mode])
  #116200/116268 reserve/release palette10 only: the upper bound11 is
  # exclusive. The owner is released by descriptor13, not by its background.
  assert p.read(0x439b08+p.read(0x5dd628+10*4,4)*4,4)==int(mode==1)
  assert p.read(0x46a904,4)==(100 if ended else 100-(7 if label==1 else 4 if label==10 else 5))
  cases.append(dict(label=label,pause_mode=mode,ended_visit=ended,transitions=transitions))
 report=dict(status='passed',cases=len(cases),scheduler_states=states,queued_draws=draws,original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unmodified124620 allocation,112838 scheduler,124898 update/free and124b48/124bf0/124cc0 completion callbacks after fixture setup; all10 labels and running/frozen/interleaved effect pause. Ordered draws include every raw record and21 object fields, including final draws on owner release. Exact integers and explicit finite FP model. Initial1249c8 owner allocation, texture I/O, enabled audio, GS and battle controller are excluded.',traces=cases)
 (ROOT/'outputs/ss6-feasibility/round_intro_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='traces'},indent=2))
if __name__=='__main__':main()
