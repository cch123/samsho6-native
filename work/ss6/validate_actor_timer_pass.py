#!/usr/bin/env python3
"""Whole151eb0 including timer4's original registered-object flag release."""
import hashlib,itertools,json,random,struct,subprocess
from round_entry_oracle import ROOT
from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe,signed

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x151eb0)
 actor,battle,tasks,objects=0x1c00000,0x1b00000,0x1d00000,0x1d10000
 p.write(0x4d3d00,battle,4)
 commands=[];expected=[];instructions=0;release_count=0
 edges=[-0x80000000,-257,-1,0,1,127,128,255,256,257,767,768,2816,0x1733ff,0x173400,0x7fffffff]
 for player,alias,table,air,back_d8,back_100 in itertools.product(range(2),range(2),range(3),range(2),range(2),range(2)):
  for n in range(12):
   main=rng.choice([0,1,0x170000,0x360000,0x80001,0x100002,0x1f0002])
   if not alias:main=(main&0xffff0000)|table
   delta=[0,1,128,256,300,512,65535,0x7fffffff][n%8]
   values=[rng.choice(edges) for _ in range(35)]
   #Consecutive values on either side of zero are essential: all branches
   #use the old timer, even after subtraction reaches zero or wraps signed.
   values[0]=[-1,0,1,256][n%4];values[4]=[-1,0,1,256][(n//3)%4]
   p.memory[actor:actor+0xf2c]=bytes([0xa5])*0xf2c
   for off,v in [(0x194,main),(0x1a4,table),(0x23c,(alias<<21)|(air<<4)),(0x39c,back_d8),(0x3c4,back_100),(0xa24,player),(0x1ac,delta)]:p.write(actor+off,v,4)
   p.memory[actor+0x1b0:actor+0x23c]=struct.pack('<35i',*values)
   p.memory[battle+0x29c:battle+0x4ac]=bytes(0x210)
   for slot,h in [(0,1),(7,2),(12,1)]:p.write(battle+0x29c+player*0x108+slot*4,tasks+h*52,4)
   for h in [1,2]:
    p.write(tasks+h*52+0x1c,objects+h*320,4);p.write(objects+h*320+0xcc,3,4)
    p.write(objects+h*320+0x108,0x202042,4)
   before=bytes(p.memory[actor:actor+0xf2c])
   _,count=p.run(0x151eb0,[actor],limit=10000);instructions+=count
   after=bytes(p.memory[actor:actor+0xf2c]);assert before[:0x1b0]==after[:0x1b0] and before[0x23c:]==after[0x23c:]
   released=p.read(objects+320+0x108,4)==0x2042
   for h in [1,2]:assert p.read(objects+h*320+0x108,4)==(0x2042 if released else 0x202042)
   release_count+=released
   commands.append('actor '+' '.join(map(str,[main,table,air,back_d8,back_100,delta,*values])))
   expected.append([int(released),*struct.unpack_from('<35i',p.memory,actor+0x1b0)])
 binary=ROOT/'work/ss6/build-native/ss6-actor-state-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
 report=dict(status='passed',cases=len(actual),original_instructions=instructions,object_release_cases=release_count,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole151eb0 and all reached callees,including140de0 with holes/duplicate registered objects;both players,ordinary/alias effective tables0/1/2,airborne,previous inputD8/100,35timers with signed overflow/zero edges and8deltas. Native exposes object-release event for caller to apply;timer values and original object flags compared,unrepresented actor bytes checked unchanged. No original frame or live battle integration claim.')
 (ROOT/'outputs/ss6-feasibility/actor_timer_pass_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
