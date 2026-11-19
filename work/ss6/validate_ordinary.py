#!/usr/bin/env python3
"""Original range helper, descriptors and recoil request vs native port."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_input_lifecycle import Boundary
ROOT=Path(__file__).resolve().parents[2]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);commands,expected=[],[]
 for a,b,distance,armed,target in itertools.product(range(2),range(2),range(-4,325),range(2),range(2)):
  far,_=p.run(0x168c58,[a,b,distance,armed,target])
  descriptor,_=p.run(0x172e08,[0,2 if far else 0,0])
  commands.append(f'range-matchup {a} {b} {distance} {armed} {target}');expected.append([far,p.read(descriptor,1)])
 range_cases=len(commands);rng=random.Random(0x14d070);a=0x1c00000
 for _ in range(2048):
  flags=rng.getrandbits(32);table=rng.randrange(3);state=rng.choice([0,1,21,25,39]);strength=rng.randrange(3);clash=rng.randrange(2)
  p.memory[a:a+0x300]=bytes(0x300);p.write(a+0x23c,flags,4);p.write(a+0x194,table|(state<<16),4)
  p.run(0x14d070,[a,strength,clash])
  commands.append(f'clash {flags} {table} {state} {strength} {clash}')
  expected.append([p.read(a+0x23c,4),signed(p.read(a+0x190,2),16),signed(p.read(a+0x192,2),16)])
 clash_cases=len(commands)-range_cases
 #The ordinary stage converts x-other before abs. Include the half-pixel
 #322.5/400 regression, signed coordinates, swapped players and both sides
 #of the inclusive78 threshold; do not provide an integer distance by hand.
 distance_cases=0;distance_instructions=0;objects=[0x1e00000,0x1e01000];battle=0x1e03000
 for x,offset,swap,armed,target in itertools.product([-400,-78.25,-0.25,0,0.25,322.5,400],[-78.25,-78,-77.75,-77.5,0,77.5,77.75,78,78.25],range(2),range(2),range(2)):
  positions=[x,x+offset]
  if swap:positions.reverse()
  for obj,value in zip(objects,positions):p.memory[obj+0x40:obj+0x44]=struct.pack('<f',value)
  p.put(11,objects[0]);p.put(14,objects[1]);p.put(18,battle)
  boundary=Boundary(0x142918)
  _,n=p.run(0x1428f4,[],stop_before=boundary);distance_instructions+=n
  assert boundary.stopped==0x142918
  distance=p.read(battle+0x144,4);far,_=p.run(0x168c58,[0,0,distance,armed,target])
  commands.append(' '.join(map(str,['distance',*positions,armed,target])));expected.append([distance,far]);distance_cases+=1
 p.write(0x4d3d08,a,4);objects=[0x1e00000,0x1e01000];event=0x1e02000
 for _ in range(2048):
  x=rng.choice([319.75,320.,320.25,rng.randrange(0,640*256)/256]);other=rng.choice([x,rng.randrange(0,640*256)/256])
  ys=[rng.randrange(0,80*4)/4 for _ in range(2)];flags=[rng.getrandbits(32) for _ in range(2)];width=rng.randrange(0,100)
  p.memory[a:a+0x2000]=bytes(0x2000);p.memory[objects[0]:event+0x100]=bytes(event+0x100-objects[0])
  for i,obj in enumerate(objects):
   p.write(obj+0xc,i,4);p.write(obj+0xcc,i,4);p.write(a+i*0xf2c+0x248,flags[i],4)
   p.memory[obj+0x40:obj+0x48]=struct.pack('<ff',[x,other][i],ys[i])
  p.write(event+0x40,objects[0],4);p.write(event+0x68,objects[1],4);p.write(event+0x14,width,4)
  p.run(0x154bd0,[event])
  commands.append('push '+' '.join(map(str,[x,ys[0],flags[0],other,ys[1],flags[1],width])))
  expected.append([struct.unpack_from('<f',p.memory,obj+0x40)[0] for obj in objects]+[p.read(a+i*0xf2c+0x248,4) for i in range(2)])
 binary=ROOT/'work/ss6/build-native/ss6-ordinary-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(float,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for command,got,want in zip(commands,actual,expected):assert got==want,(command,got,want)
 report=dict(status='passed',range_cases=range_cases,clash_request_cases=clash_cases,distance_slice_cases=distance_cases,distance_slice_instructions=distance_instructions,push_cases=len(commands)-range_cases-clash_cases-distance_cases,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Unpatched complete 0x168c58, 0x172e08, 0x14d070 and ordinary 0x154bd0, plus explicit1428f4..142918 distance slices with fractional/signed positions and swapped players at both sides of78. Resource00/01 ranges, armed and disarmed on both sides; standing armed-light descriptor flags; recoil request flags/state; ordinary push including coincident positions. Does not cover full stage,route8,effects/audio or recoil actor callback.')
 (ROOT/'outputs/ss6-feasibility/ordinary_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
