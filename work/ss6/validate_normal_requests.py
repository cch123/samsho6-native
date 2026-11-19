#!/usr/bin/env python3
"""Whole14bf30,151428,151478 and14cca0 with real object-list fixtures."""
import collections,hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_action_selection import sparse
ROOT=Path(__file__).resolve().parents[2]
BASE=0x1c00000;BODIES=0x1d00000;BATTLE=0x1a00000;OBJECTS=0x1b00000

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x14bf30);commands=[];expected=[];counts=collections.Counter();outcomes=collections.Counter();instructions=0
 p.write(0x4d3d08,BASE,4);p.write(0x4d3d00,BATTLE,4);p.write(0x4c38a8,6,4)
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 def original(entry,args):
  nonlocal instructions
  result,n=p.run(entry,args,limit=30000);counts[hex(entry)]+=1;instructions+=n;return signed(result,32)
 def put_actor(player,a):
  address=BASE+player*0xf2c;body=BODIES+player*0x1000
  p.write(address,body,4);p.write(address+4,body+0x400,4);p.write(address+0xa24,player,4)
  for off,v,size in [(0x23c,a[0],4),(0x244,a[1],4),(0x248,a[2],4),(0x24c,a[3],1),(0x194,a[4],4),(0x1a4,a[5],4),(0xa10,a[6],4),(0xa48,a[7],4)]:p.write(address+off,v,size)
  p.write(body+0x38,a[8],4);p.write(body+0xfe,a[9],2);p.memory[body+0x40:body+0x44]=struct.pack('<f',a[10]);return address,body
 def actor(state=0,table=0):return [0x1000,0,0x02000010,2,(state<<16)|table,0,0,-9,0x80000,0,160.5,160.75]
 def run(a,extra,other,otherExtra,distance,objects,c,f,r,restricted=False,player=0):
  address,body=put_actor(player,a);_,otherBody=put_actor(1-player,other)
  for off,value,size in [(0x240,extra[0],4),(0xa20,extra[1],4),(0xc8,extra[2],4),(0x18c,extra[3],4),(0x190,extra[4],2),(0x192,extra[5],2)]:p.write(address+off,value,size)
  for off,value in [(0x24,otherExtra[0]),(0x528,otherExtra[1]),(0x534,otherExtra[2])]:p.write(otherBody+off,value,4)
  p.write(BATTLE+0x144,distance,4)
  pool=BATTLE+0x29c+(1-player)*0x108;p.memory[pool:pool+48*4]=bytes(48*4)
  for slot,kind in objects:
   node=OBJECTS+slot*0x400;p.write(pool+slot*4,node,4);p.write(node+0x1c,node+0x100,4);p.write(node+0x1cc,kind,4)
  system,character,*d=c;p.memory[address+0x10c:address+0x120]=struct.pack('<5I',system,0,character,0,0);p.memory[0x12d2308:0x12d2318]=bytes(d)
  inp=address+0x2c4;features=struct.pack('<171I',*f);recognized=struct.pack('<31I',*r)
  p.memory[inp:inp+684]=features;p.memory[inp+0x2ac:inp+0x328]=recognized
  allowed=original(0x151428,[address]);threat=original(0x151478,[address]);queued=original(0x14bf30,[address,int(restricted)])
  assert p.memory[inp:inp+684]==features and p.memory[inp+0x2ac:inp+0x328]==recognized
  want=[allowed,threat,queued,p.read(body+0x38,4),p.read(address+0x248,4),p.read(address+0x18c,4),signed(p.read(address+0x190,2),16),signed(p.read(address+0x192,2),16)]
  commands.append(' '.join(map(str,['normal_request',*a,*extra,*other,*otherExtra,distance,len(objects),*[v for pair in objects for v in pair],*c,*sparse(f),*sparse(r),int(restricted)])));expected.append(want)
  outcomes[f'guardAllowed={allowed}']+=1;outcomes[f'threat={threat}']+=1;outcomes[f'request:queued={queued}']+=1
  if queued:outcomes[f'next={want[-1]}']+=1
 #Every normal state, single recognized command and raw direction followed
 #by conflicting inputs; both ordinary and descriptor-filtered selectors.
 for state,case in itertools.product(range(64),range(80)):
  a=actor(state,rng.choice([0,0,1,2]));a[0]=rng.choice([0,0x1000,0x800000,0x801000,0x200000,0x201010]);a[1]=rng.choice([0,1,2,0x2000,0x2002]);a[3]=rng.choice([0,2,4,6])
  a[5]=(rng.randrange(5)<<16)|rng.randrange(4);a[6]=rng.choice([0,1,25,41,45,50]);a[9]=rng.choice([0,0x100]);a[10:12]=rng.choice([(160.5,160.75),(160.75,160.5),(160.5,160.5)])
  other=actor(rng.choice([0,1,57,58,64]),rng.randrange(4));other[6]=rng.randrange(51);other[10:12]=[a[11],a[10]]
  otherExtra=[rng.choice([0,537,599,189,190,195,196,211,214]),rng.randrange(48),rng.choice([0,1,0x80000000])]
  f=[0]*171;r=[0]*31
  if case<31:r[case]=1
  elif case<44:f[49+case-31]=1
  else:
   f=[rng.choice([0,0,1,0x80000000]) for _ in range(171)];r=[rng.choice([0,0,1,0x80000000]) for _ in range(31)]
  extra=[rng.choice([0,4]),rng.choice([0,1,2]),rng.choice([0,35,36,37]),23,-3,-7]
  objects=[] if case%4==0 else [(rng.randrange(48),rng.choice([-1,0,2,5,6]))]
  c=[case%9,a[6],*descriptors[case%8]]
  for restricted in [False,True]:run(a,extra,other,otherExtra,rng.choice([-1,0,239,240,241,300]),objects,c,f,r,restricted,state%2)
 #All51 character keys and auxiliary states. The threat helper's actual
 #jump table has eight special keys; others must remain false here.
 for character,state in itertools.product(range(51),range(64)):
  a=actor();other=actor();other[6]=character;other[10:12]=[a[11],a[10]];f=[0]*171;f[54]=1
  run(a,[0,0,0,17,-1,-1],other,[0,state,state%3],300,[],[0,0,*descriptors[0]],f,[0]*31,False,character%2)
 #Range-exempt threat actions, exact pair matching and both sides of240.
 pairs=list(struct.iter_unpack('<BBh',p.memory[0x4e8120:0x4e8140]))
 for (character,_,action),table,delta,distance in itertools.product(pairs,[0,1,2],[-1,0,1],[239,240,241]):
  a=actor();other=actor(0,table);other[6]=character;other[10:12]=[a[11],a[10]];f=[0]*171;f[53]=1
  run(a,[0,0,0,17,-1,-1],other,[action+delta,0,0],distance,[],[0,0,*descriptors[0]],f,[0]*31)
 #Custom guard byte, with matching and nonmatching objects in edge slots.
 for byte in range(256):
  a=actor();other=actor();other[10:12]=[a[11],a[10]];d=descriptors[0].copy();d[12]=byte;f=[0]*171;f[54]=1
  run(a,[0,1,36,29,1,23],other,[0,0,0],300,[(0,6),(47,2 if byte%2 else 5)],[6,0,*d],f,[0]*31)
 #14cca0 swaps23/24 according to control source, then character rules.
 for character,state,mirror,flags,control in itertools.product(range(51),[22,23,24,36],[0,0x80000],[0,0x100000],[(0,1,0),(0,1,36),(4,1,0),(0,0,0)]):
  a=actor();a[6]=character;a[8]=mirror;a[0]|=flags;address,_=put_actor(0,a)
  for off,value in zip([0x240,0xa20,0xc8],control):p.write(address+off,value,4)
  commands.append(' '.join(map(str,['translate_normal',*a,*control,state])));expected.append([original(0x14cca0,[address,state])])
 binary=ROOT/'work/ss6/build-native/ss6-action-selection-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,commands[i],got,want)
 report=dict(status='passed_whole_normal_request_boundaries',cases=len(expected),original_calls=counts,original_instructions=instructions,outcomes=outcomes,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole14bf30,151428,151478 and14cca0, no skipped callees. Includes original140d78/1473b8 object-list traversal,1a3798 auxiliary dispatch,168fc8 threat-action pairs and custom descriptor lookup. Compare guard/threat booleans, request result, body facing, flags248, pending18c/190/192; original inputs unchanged.51 character keys are helper fixtures, not playable-character implementations. Actor/input/auxiliary/object-registration snapshots supplied; their producers, action commit and live battle integration remain separate.')
 (ROOT/'outputs/ss6-feasibility/normal_request_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
