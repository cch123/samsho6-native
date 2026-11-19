#!/usr/bin/env python3
"""Compare guard dispatch, retreat installation and clamp against original code."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 source,target,os,ot,ctx,battle=0x1c00000,0x1c00f2c,0x1e00000,0x1e01000,0x1e02000,0x1e03000
 p.write(0x4d3d08,source,4);p.write(0x4d3d00,battle,4)
 commands,expected=[],[];counts={}
 for armed,flags,defense,strength in itertools.product([0,1],[0,0x2000000,0x80000,0x2080000],[1,2],range(3)):
  p.memory[source:source+0x2000]=bytes(0x2000);p.memory[os:battle+0x500]=bytes(battle+0x500-os)
  for actor,obj,slot in [(source,os,0),(target,ot,1)]:
   for off,v in [(0,obj),(0xa24,slot),(0x190,-1),(0xa3c,-1)]:p.write(actor+off,v,4)
   p.write(obj+0xcc,slot,4)
  p.write(source+0x194,1,4);p.write(target+0x23c,armed*0x1000,4);p.write(target+0x244,flags,4)
  #Distinct nonzero sentinels expose unexpected timer writes and prove
  #that refused guards retain timer32, while accepted guards replace it.
  timer_values=[0x12340000+slot*257+i*263 for slot in range(2) for i in range(35)]
  for slot,actor in enumerate([source,target]):
   for i in range(35):p.write(actor+0x1b0+4*i,timer_values[slot*35+i],4)
  p.run(0x14d5a0,[target,os,defense,strength])
  applied=p.read(target+0x18c,4)
  result=[applied,p.read(target+0x244,4),signed(p.read(target+0x190,2),16),signed(p.read(target+0x192,2),16),applied]
  result += [p.read(actor+off,4) for actor in [source,target] for off in [0x1b0,0x1b4]]
  if applied:
   p.write(ctx,target,4);p.write(ctx+4,source,4)
   p.run(0x1705a8,[ctx,strength,defense==2]);result.append(p.read(target+0xa3c,4))
  else:result.append(0)
  result += [signed(p.read(actor+0x1b0+4*i,4),32) for actor in [source,target] for i in range(35)]
  commands.append(' '.join(map(str,['guard-timers',armed*0x1000,flags,defense,strength,*timer_values])));expected.append(result)
 counts['guard']=len(commands)
 rng=random.Random(175070)
 for operation in ['retreat','clamp']:
  count=0
  for i in range(1024):
   p.memory[source:source+0x2000]=bytes(0x2000);p.memory[os:battle+0x500]=bytes(battle+0x500-os)
   # States 8 and 80+ have special character branches outside this subset.
   state=rng.choice([0,1,2,3,4,5,32,33,34,35,36,37,38,39,40,43,44,46,47,49])
   flags=rng.getrandbits(32);other=rng.randrange(-2,5)
   values=[rng.randrange(-500000,500000) for _ in range(6)];values[1]=rng.choice([-1,0,1,values[1]])
   y=rng.choice([-3.,0.,17.])
   p.write(target,ot,4);p.write(target+0xa24,1,4);p.write(ot+0x108,flags,4)
   p.write(battle+0x254+0xc,other,4)
   for j,v in enumerate(values):p.write(ot+0x4c+j*4,v,4)
   p.memory[ot+0x44:ot+0x48]=struct.pack('<f',y)
   p.run(0x151728 if operation=='retreat' else 0x11deb0,[target,state] if operation=='retreat' else [ot])
   result=[p.read(ot+0x108,4)]+[signed(p.read(ot+0x4c+j*4,4),32) for j in range(6)]
   result.append(struct.unpack_from('<f',p.memory,ot+0x44)[0])
   commands.append(' '.join(map(str,[operation,state,flags,other,*values,y])));expected.append(result);count+=1
  counts[operation]=count
 binary=ROOT/'work/ss6/build-native/ss6-reaction-control-probe'
 actual=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 lines=[[float(x) for x in line.split()] for line in actual.stdout.splitlines()]
 assert len(lines)==len(expected)
 for cmd,a,e in zip(commands,lines,expected):assert a==e,(cmd,a,e)
 report=dict(status='passed',cases=counts,elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scope='Whole 0x14d5a0 + 0x1705a8 ordinary guard, 0x151728 ordinary retreat, 0x11deb0 clamp. Guard compares all35 timers on both actors, seeded nonzero, including timer32=3 on acceptance and preservation on refusal. Unpatched original functions; exact finite arithmetic only. Not a full-frame comparison.')
 (ROOT/'outputs/ss6-feasibility/reaction_control_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
