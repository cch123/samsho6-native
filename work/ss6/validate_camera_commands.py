#!/usr/bin/env python3
"""Whole original camera queue/target/update functions, explicit finite FP."""
import hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from validate_stage_camera import bits
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw,finite_model=True)
 b=0x1b00000;c=b+0x34;p.write(0x4d3d00,b,4);rng=random.Random(0x146bc0)
 offsets=[0,4,8,12,16,20,28,32,36,40,44,48,52];float_indices={1,2,3,7,8,9}
 projection=[0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68]
 commands=[];expected=[];cases=[]
 def snapshot():
  fields=[p.read(c+o,4) if i in float_indices else signed(p.read(c+o,4),32) for i,o in enumerate(offsets)]
  fields += [p.read(a,4) for a in projection]
  count=p.read(c+0x4c,4);done=p.run(0x146b00,[c])[0];fields += [done,count]
  for i in range(count):fields += [p.read(c+0x50+i*8,1),signed(p.read(c+0x54+i*8,4),32)]
  return fields
 for case in range(192):
  mode=case%4;elapsed=[256,128,85,0][mode]
  camera=[256,rng.randrange(180*8,460*8)/8,rng.randrange(120*8,280*8)/8,rng.randrange(320*8,444*8)/8,
          160,480,240,320,120,320,0,0,0]
  xy=[rng.randrange(40*8,600*8)/8,rng.randrange(0,280*8)/8,rng.randrange(40*8,600*8)/8,rng.randrange(0,280*8)/8]
  if case<44:queue=[(case%11,[-1,0,1,30][case//11]),(0,0)]
  elif case<60:queue=[(2,case%2),(3,30),(2,case%2),(0,0)];xy=[240,0,400,0]
  else:queue=[(rng.randrange(1,11),rng.choice([-1,0,1,2,30,0x800000])) for _ in range(case%15)]+[(0,0)]
  p.memory[b:b+0x800]=bytes(0x800);p.write(b+0x140,mode,4)
  for i,(off,value) in enumerate(zip(offsets,camera)):p.write(c+off,bits(value) if i in float_indices else value,4)
  for address,v in zip(projection,[320,120,-400,0,-120]):p.write(address,bits(v),4)
  for kind,param in queue:p.run(0x146b30,[c,kind,param])
  steps=120;commands.append('queue '+' '.join(map(str,[*camera,len(queue),*[v for q in queue for v in q],steps,elapsed,*xy])))
  expected.append(snapshot())
  for tick in range(steps):
   p.floats[12:16]=list(map(bits,xy));p.run(0x146460,[c]);p.run(0x1463d0,[c,0]);expected.append(snapshot())
  cases.append(dict(mode=mode,queue=queue,updates=steps,completed=bool(expected[-1][18])))
 binary=ROOT/'work/ss6/build-native/ss6-stage-camera-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=[list(map(int,row.split())) for row in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(i,commands[i//121],i%121,[(j,x,y) for j,(x,y) in enumerate(zip(a,e)) if x!=y])
 report=dict(status='passed_under_explicit_finite_model',scenarios=len(cases),camera_and_queue_states=len(expected),
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole146b30 append,146b00 completion,146460 target,1463d0 update including146bc0/146d10 queue consumption,146750 movement and146870 projection.11 command kinds; global elapsed256/128/85/0, word-wrapped parameters, up to16 queued commands. No logger patch, shake, full battle scheduler or hardware FP/GS claim.',cases=cases)
 (ROOT/'outputs/ss6-feasibility/camera_commands_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='cases'},indent=2))
if __name__=='__main__':main()
