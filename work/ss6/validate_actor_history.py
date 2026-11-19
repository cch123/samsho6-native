#!/usr/bin/env python3
"""Whole original history and resource00 afterimage callback comparisons."""
import hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 actor,body=0x1c00000,0x1e00000;images=[body+0x200*(i+1) for i in range(3)]
 p.write(0x4d3d08,actor,4);p.write(actor,body,4)
 for i,o in enumerate(images):
  for off,value in [(0xcc,10),(0x128,(i+1)*5),(0x12c,144-i*48),(0x130,i+1),(0x104,0x400300)]:p.write(o+off,value,4)
 rng=random.Random(0x147b60);commands=[];expected=[];instructions=0
 actions=[0,10,185,186,495,497,499,501,549,550,551,568,569,570,612,264]
 for visit in range(2048):
  reset=visit%67==0;flags=rng.getrandbits(32);action=rng.choice(actions);step=rng.randrange(32)
  x,y=[struct.unpack('<I',struct.pack('<f',rng.randrange(-2048,2049)/4))[0] for _ in range(2)]
  delta=rng.choice([-512,-1,0,1,127,128,255,256,257,512,1024]);table=rng.randrange(3)
  for off,value in [(0x38,flags),(0x24,action),(0x28,step),(0x40,x),(0x44,y),(0x30,delta)]:p.write(body+off,value,4)
  p.write(actor+0x194,table,4)
  instructions+=p.run(0x14ae70 if reset else 0x14b6a0,[actor])[1]
  out=[p.read(actor+0xa5c,1)]+[p.read(actor+0xa60+off,4) for off in range(0,60*20,4)]
  for o in images:
   instructions+=p.run(0x147b60,[o])[1]
   out += [p.read(o+off,4) for off in [0x38,0x24,0x28,0x40,0x44,0x8c,0x104,0xb0]]
  commands.append(' '.join(map(str,['reset' if reset else 'tick',flags,action,step,x,y,delta,table])))
  expected.append(out)
 binary=ROOT/'work/ss6/build-native/ss6-actor-history-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(i,commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(a,e)) if x!=y][:12])
 report=dict(status='passed',states=len(actual),original_callback_cases=len(actual)*3,original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unmodified14ae70/14b6a0 and147b60 including169138,11d990. Resource00,60samples,all3lags,positive/zero/negative/large deltas,seven169138 eligible actions plus264 exception and ordinary hidden paths,damage-table suppression. Original object history data compared bitwise. Visible trail rendering and full actor dispatch excluded.')
 (ROOT/'outputs/ss6-feasibility/actor_history_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
