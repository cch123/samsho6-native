#!/usr/bin/env python3
"""Whole14c2d0/14c3b0/14c510, including pending-state writes."""
import collections,hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_action_selection import sparse

ROOT=Path(__file__).resolve().parents[2]
BASE=0x1c00000;BODIES=0x1d00000

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x14c3b0);commands=[];expected=[];counts=collections.Counter();outcomes=collections.Counter();instructions=0
 p.write(0x4d3d08,BASE,4);p.write(0x4c38a8,6,4)
 descriptor=list(p.memory[0x4d7068:0x4d7078])
 def put_actor(player,a):
  address=BASE+player*0xf2c;body=BODIES+player*0x1000
  p.write(address,body,4);p.write(address+0xa24,player,4)
  for off,v,size in [(0x23c,a[0],4),(0x244,a[1],4),(0x248,a[2],4),(0x24c,a[3],1),(0x194,a[4],4),(0x1a4,a[5],4),(0xa10,a[6],4),(0xa48,a[7],4)]:p.write(address+off,v,size)
  p.write(body+0x38,a[8],4);p.write(body+0xfe,a[9],2)
  p.memory[body+0x40:body+0x44]=struct.pack('<f',a[10]);return address,body
 def run(op,a,extra,other,c,f,r,player=0):
  nonlocal instructions
  address,body=put_actor(player,a);put_actor(1-player,other)
  p.write(body+0x104,extra[0],4)
  for off,value,size in [(0x18c,extra[1],4),(0x190,extra[2],2),(0x192,extra[3],2)]:p.write(address+off,value,size)
  system,character,*d=c;p.memory[address+0x10c:address+0x120]=struct.pack('<5I',system,0,character,0,0)
  p.memory[0x12d2308:0x12d2318]=bytes(d)
  inp=address+0x2c4;features=struct.pack('<171I',*f);recognized=struct.pack('<31I',*r)
  p.memory[inp:inp+684]=features;p.memory[inp+0x2ac:inp+0x328]=recognized
  entry={'request_chain':0x14c3b0,'request_attack':0x14c2d0,'request_supplemental':0x14c510,'request_system_only':0x14c510}[op]
  result,n=p.run(entry,[address,int(op=='request_system_only')],limit=30000);instructions+=n;counts[hex(entry)]+=1
  assert p.memory[inp:inp+684]==features and p.memory[inp+0x2ac:inp+0x328]==recognized
  want=[signed(result,32),p.read(body+0x38,4),signed(p.read(address+0xa48,4),32),p.read(address+0x18c,4),signed(p.read(address+0x190,2),16),signed(p.read(address+0x192,2),16)]
  commands.append(' '.join(map(str,[op,*a,*extra,*other,*c,*sparse(f),*sparse(r)])));expected.append(want)
  outcomes[f'{op}:queued={want[0]}']+=1
  if want[0]:outcomes[f'{op}:next={want[-1]}']+=1
 def actor(state=0,table=1):return [0x1000,0,0,0,(state<<16)|table,0,0,-13,0x80000,0,160.5,160.75]
 #Every selector state with raw edges and recognized candidates, both sides.
 #Old request fields deliberately differ from success writes, so refusal must
 #preserve them. Chain recognition lives inside the actor at+2c4.
 for state,case in itertools.product(range(64),range(32)):
  a=actor(state);a[0]=[0,0x1000,0x800000,0x801000][case%4]
  other=actor(57,2);other[10:12]=[a[11],a[10]]
  f=[0]*171;r=[0]*31
  if case<16:
   f[6+case//4]=1;f[63]=case%2;f[51]=(case//2)%2;f[50]=int(case%3==0)
  else:r[[2,3,5,6,14,16,0,30][(case-16)%8]]=0x80000000
  if case>=24:r[5]=1;f[6]=1
  for op in ['request_attack','request_chain','request_supplemental','request_system_only']:run(op,a,[0xc0000,17,-3,-7],other,[8,0,*descriptor],f,r,state%2)
 #Independent gates, including invalid-high states only on paths that reject
 #before indexing; transformed state helpers still execute in the original.
 for case in range(6144):
  a=actor(rng.randrange(64),rng.randrange(4));a[0]=rng.choice([0,0x10,0x1000,0x800000,0x801010,0x200000,0xa01000])
  a[1]=rng.choice([0,4,8,0x400,0x2000,0x2004]);a[2]=rng.choice([0,0x10]);a[3]=rng.choice([0,2,4,6])
  a[5]=(rng.randrange(5)<<16)|rng.randrange(4);a[6]=rng.choice([0,25,32,45,48]);a[8]=rng.getrandbits(32)
  a[10:12]=rng.choice([(160.5,160.75),(160.75,160.5),(160.5,160.5)])
  other=actor(rng.choice([0,57,58,63,64,95]),rng.randrange(4));other[0]=rng.choice([0,0,0x10,0x200000,0x200010]);other[5]=rng.randrange(4)|(rng.randrange(5)<<16);other[6]=rng.choice([0,45]);other[10:12]=[a[11],a[10]]
  d=descriptor.copy();d[15]=rng.choice([0,45,46,47,255]);c=[rng.choice([0,1,2,3,4,5,6,6,8,8]),a[6],*d]
  f=[rng.choice([0,0,0,1,0x80000000]) for _ in range(171)];r=[rng.choice([0,0,0,1,0x80000000]) for _ in range(31)]
  extra=[rng.choice([0,0x40000,0x80000,0xc0000,0x20000,0xffffffff]),rng.getrandbits(32),rng.randrange(-8,8),rng.randrange(-8,80)]
  for op in ['request_attack','request_chain','request_supplemental','request_system_only']:run(op,a,extra,other,c,f,r,case%2)
 #Exhaust custom chain-enable byte and the signed upper state gate.
 for byte,state in itertools.product(range(256),[0,63,64,65]):
  a=actor(state);other=actor(57,2);other[10:12]=[a[11],a[10]];d=descriptor.copy();d[15]=byte
  f=[0]*171;f[6]=1;r=[0]*31;r[16]=1
  run('request_chain',a,[0x40000,23,3,91],other,[6,0,*d],f,r,byte%2)
 binary=ROOT/'work/ss6/build-native/ss6-action-selection-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,commands[i],got,want)
 report=dict(status='passed_whole_attack_request_boundaries',cases=len(expected),original_calls=counts,original_instructions=instructions,outcomes=outcomes,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole14c2d0,14c3b0 and14c510, no callee skips. Compare return, body facing, variantA48 and pending18c/190/192; assert original input words remain unchanged. Covers64 selector states, both player slots, permission flags, transformed aliases, system6 byte15, hit-result bits, opponent damage57/58 and upper state63/64. Inputs and actor states supplied. These are queued requests, not action entry, command consumption or live battle integration.')
 (ROOT/'outputs/ss6-feasibility/attack_request_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
