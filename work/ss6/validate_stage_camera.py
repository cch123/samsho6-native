#!/usr/bin/env python3
"""Whole original ordinary position/camera phase, under explicit finite FP.
No instruction patching or call hooks. This is not a complete battle oracle.
"""
import hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
def bits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def acc_checks(raw):
 # Hand-authored test instructions in scratch memory, not modifications of
 # original code. Check ACC preservation and fd==fs read-before-write.
 p=Probe(raw);code=0x1f00000
 words=[0x4602081a,0x460410dc,0x4603085c,0x03e00008,0]
 p.memory[code:code+len(words)*4]=struct.pack('<5I',*words)
 p.floats[1:5]=list(map(bits,[2,3,5,7]));p.run(code)
 assert p.float_acc==bits(6) and p.floats[3]==bits(27) and p.floats[1]==bits(60)
 p.floats[1]=bits(1.0000001192092896);p.floats[2]=p.floats[1]
 try:p.run(code)
 except NotImplementedError:pass
 else:raise AssertionError('Exact mode accepted inexact MULA')
 p=Probe(raw,finite_model=True);p.memory[code:code+8]=struct.pack('<2I',0x03e00008,0x4602081a)
 p.floats[1]=p.floats[2]=0x3f800001;p.run(code)
 assert p.float_acc==0x3f800002 # (1+2^-23)^2 rounded toward zero.
 p.memory[code:code+8]=struct.pack('<2I',0x03e00008,0x46020819)
 p.floats[1]=bits(2);p.floats[2]=bits(5);p.run(code);assert p.float_acc==bits(-3)
 return 4
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 acc_cases=acc_checks(raw);p=Probe(raw,finite_model=True);rng=random.Random(0x1426d8)
 battle=0x1b00000;camera=battle+0x34;actors=[0x1c00000,0x1c01000];objects=[0x1e00000,0x1e01000]
 p.write(0x4d3d00,battle,4)
 offsets=[0,4,8,12,16,20,28,32,36,40,44,48,52];float_indices={1,2,3,7,8,9}
 projection=[0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68]
 commands,expected=[],[];counts={}
 def setup(c):
  p.memory[battle:battle+0x800]=bytes(0x800)
  for i,(offset,v) in enumerate(zip(offsets,c)):p.write(camera+offset,bits(v) if i in float_indices else v,4)
  for address,v in zip(projection,[320,120,-400,0,-120]):p.write(address,bits(v),4)
 def read_camera():
  return [p.read(camera+o,4) if i in float_indices else signed(p.read(camera+o,4),32) for i,o in enumerate(offsets)]+[p.read(o,4) for o in projection]
 def random_camera():
  return [rng.choice([0,64,128,256,512]),rng.randrange(120*8,520*8)/8,rng.randrange(100*8,380*8)/8,
   rng.randrange(300*8,460*8)/8,rng.randrange(0,210),rng.randrange(430,641),240,
   rng.randrange(160*8,480*8)/8,rng.randrange(120*8,360*8)/8,rng.randrange(320*8,444*8)/8,
   rng.choice([-0x40000,0,0x40000]),rng.choice([-0x200000,0,0x200000]),rng.choice([-0x20000,0,0x20000])]
 for op in ['target','move','publish','update']:
  for _ in range(384):
   c=random_camera();setup(c);xy=[rng.randrange(-100*8,740*8)/8,rng.randrange(0,500*8)/8,rng.randrange(-100*8,740*8)/8,rng.randrange(0,500*8)/8]
   p.floats[12:16]=list(map(bits,xy))
   if op=='update':p.run(0x146460,[camera]);p.run(0x1463d0,[camera,0])
   else:p.run({'target':0x146460,'move':0x146750,'publish':0x146870}[op],[camera])
   commands.append(op+' '+' '.join(map(str,c+(xy if op in ['target','update'] else []))));expected.append(read_camera())
  counts[op]=384
 for _ in range(384):
  c=random_camera();setup(c);p.run(0x146870,[camera])
  x,y=rng.randrange(0,640*16)/16,rng.randrange(0,400*16)/16
  p.floats[12]=bits(0);p.run(0x122ff0);scale=p.floats[0]
  p.floats[12:15]=[bits(x),bits(y),bits(0)];p.run(0x123020,[0x1e10000])
  commands.append('project '+' '.join(map(str,c+[x,y])));expected.append([p.read(0x1e10000,4),p.read(0x1e10004,4),scale])
 counts['projection']=384
 # Include swapped/equal integer X, fractional wall penetration, both facing
 # bits, airborne exclusion and all 80 original reaction descriptor flags.
 for case in range(2304):
  c=random_camera();setup(c);parts=[]
  shared=rng.randrange(180*16,460*16)/16
  for i,(a,o) in enumerate(zip(actors,objects)):
   p.memory[a:a+0xf2c]=bytes(0xf2c);p.memory[o:o+0x200]=bytes(0x200)
   p.write(battle+0x24c+i*4,a,4);p.write(a,o,4)
   x=rng.choice([shared,shared+.25,rng.randrange(-20*16,660*16)/16])
   y=rng.choice([0,-.009999999776482582,rng.randrange(0,400*8)/8])
   f23c=rng.choice([0,0x1000,0x1010]);f244=rng.choice([0,0x20000]);fobj=rng.choice([0,0x80000]);f24c=rng.randrange(256)
   table=case%3;state=rng.randrange(80);desc=p.read(0x4e90b8+state*14,1)
   for off,v in [(0x23c,f23c),(0x244,f244),(0x194,table|(state<<16))]:p.write(a+off,v,4)
   p.write(a+0x24c,f24c,1);p.write(o+0x38,fobj,4);p.write(o+0x40,bits(x),4);p.write(o+0x44,bits(y),4)
   parts.extend([x,y,f23c,f244,fobj,f24c,table,state,desc])
  p.run(0x1426d8,[battle])
  commands.append('stage '+' '.join(map(str,c+parts)))
  out=read_camera()
  for a,o in zip(actors,objects):out.extend([p.read(o+0x40,4),p.read(a+0x24c,1),p.read(a+0xa08,4)])
  out.extend([p.read(battle+0x144,4),p.read(battle+0x148,4)]);expected.append(out)
 counts['whole_stage_phase']=2304
 binary=ROOT/'work/ss6/build-native/ss6-stage-camera-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for command,got,want in zip(commands,actual,expected):assert got==want,(command,got,want)
 report=dict(status='passed_under_explicit_finite_model',cases=counts,acc_instruction_checks=acc_cases,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Complete unpatched 0x146460, 0x146750, 0x146870/0x122ed8, z=0 projection 0x123020 and ordinary resource00 0x1426d8 with callees. Bitwise camera/projection state, positions, facing flags and distances. No special camera queue/shake, pending camera effect flags, alternate actor state or special character. Finite MUL/ADD/ACC model is not EE hardware proof; not a full battle-frame comparison or GS raster validation.')
 (ROOT/'outputs/ss6-feasibility/stage_camera_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
