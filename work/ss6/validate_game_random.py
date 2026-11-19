#!/usr/bin/env python3
"""Whole original RNG helpers, including state progression and mode changes."""
import collections,hashlib,json,random,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/'work/ss6/build-native/ss6-object-pool-probe'

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x112300);commands=[];expected=[];labels=[];groups=collections.Counter();instructions=0
 reent=0x1b00000;p.write(0x5d1bf8,reent,4)
 assert p.read(0x67ab58,8)==0x5851f42d4c957f2d
 def seed(mode,game,library):
  commands.append(f'R {mode&0xffffffff} {game&0xffffffff} {library}')
  p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(reent+0xa8,library,8)
 def run(kind,bound=3,group='standalone'):
  nonlocal instructions
  start=[0x112290,0x316b90,0x112300][kind]
  result,n=p.run(start,[] if kind<2 else [signed(bound&0xffffffff,32)],limit=1000);instructions+=n
  commands.append(f'r {kind} {bound&0xffffffff}')
  expected.append([result&0xffffffff,p.read(0x3d2e80,4),p.read(reent+0xa8,8)])
  labels.append((group,kind,bound));groups[group]+=1
 edges=[0,1,2,127772,127773,127774,0x7ffffffe,0x7fffffff,0x80000000,0x80000001,0xfffffffe,0xffffffff]
 for value in edges+[rng.getrandbits(32) for _ in range(256)]:
  seed(3,value,rng.getrandbits(64));run(0,group='game_seed_edges')
 for value in [0,1,2,0xffffffff,1<<32,(1<<63)-1,1<<63,(1<<64)-1]+[rng.getrandbits(64) for _ in range(256)]:
  seed(0,rng.getrandbits(32),value);run(1,group='library_seed_edges')
 bounds=[0,1,2,3,7,255,32767,32768,65535,65536,0x7fffffff,0x80000000,0xfffffffd,0xffffffff]
 for mode in [0,-2,1,3,6,-1,-2147483648,2147483647]:
  for value in edges:
   for bound in bounds:
    seed(mode,value,rng.getrandbits(64));run(2,bound,'bounded_modes_edges')
 #Persistent sequences matter: a mode switch must retain the inactive seed.
 #The R codec reloads the current original seeds, never advances either one.
 for sequence in range(24):
  seed(sequence%9-2,rng.getrandbits(32),rng.getrandbits(64))
  for step in range(256):
   if step%17==0:
    seed(rng.choice([0,-2,1,3,6]),p.read(0x3d2e80,4),p.read(reent+0xa8,8))
   run(2 if step%11 else sequence%2,rng.choice(bounds) if step%3 else 3,'persistent_mixed_sequences')
 result=subprocess.run([str(BINARY)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[[int(v) for v in line.split()] for line in result.stdout.splitlines()]
 assert len(actual)==len(expected),(len(actual),len(expected))
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,labels[i],got,want)
 report=dict(status='passed',cases=len(expected),groups=dict(groups),original_instructions=instructions,
  elf_sha256=SOURCE_HASH,native_probe_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Whole112290,316b90,112300 with all reached callees including30ede0, no patched/skipped calls. Integer-only; compare return values and both persistent seeds. Full signed bound and seed edges, zero/negative bounds, overflow,24 mixed256-call sequences and mode switching. No source entropy seeding or gameplay producer integration claimed.')
 (ROOT/'outputs/ss6-feasibility/game_random_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
