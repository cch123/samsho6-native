#!/usr/bin/env python3
"""Whole original96 condition dispatcher and14af48 filtering, no skips."""
import collections,hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
ROOT=Path(__file__).resolve().parents[2]
BASE=0x1c00000;BODIES=0x1d00000;BATTLE=0x1b00000;OBJECTS=0x1e00000;CONTEXT=0x1c03000;RESULTS=0x1c04000;CATEGORIES=0x1c05000;REQUIREMENTS=0x1c05100
FIELDS=['flags23c','flags244','flags248','state194','state1a4','character','stateFlags','aliasFlags','body38','body104','body108','action','body128','auxAction','aux128','aux12c','button9','rageState','rageAmount','systemState','systemMeter','fieldA30','x','y']
OFFSETS=[0x23c,0x244,0x248,0x194,0x1a4,0xa10,0x19a,0x1aa]
def actor():
 a=dict.fromkeys(FIELDS,0);a.update(flags23c=0x1000,state194=64<<16|1,character=23,body108=0x40,body104=0xc0000,body128=0xaabbccdd,x=160.5,y=0)
 a['timers']=[0]*35;a['bytes']=[0]*14;return a
def encode(a):return [a[k] for k in FIELDS]+a['timers']+a['bytes']
def context():return dict(mode=3,stageIndex=-1,stageX=160,own=[],battle=[])
def encode_context(c):return [c['mode'],c['stageIndex'],c['stageX'],len(c['own']),*[v for o in c['own'] for v in o],len(c['battle']),*[v for o in c['battle'] for v in o]]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x1798f0);commands=[];expected=[];counts=collections.Counter();outcomes=collections.Counter();instructions=0
 p.write(0x4d3d08,BASE,4);p.write(0x4d3d00,BATTLE,4);p.write(0x4c38a8,6,4)
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 def put_actor(player,a):
  address=BASE+player*0xf2c;body=BODIES+player*0x1000
  p.write(address,body,4);p.write(address+4,body+0x400,4);p.write(address+0xa24,player,4);p.write(BATTLE+0x24c+player*4,address,4)
  for i,off in enumerate(OFFSETS):p.write(address+off,a[FIELDS[i]],1 if i>=6 else 4)
  for off,key in [(0x38,'body38'),(0x104,'body104'),(0x108,'body108'),(0x24,'action'),(0x128,'body128'),(0x424,'auxAction'),(0x528,'aux128'),(0x52c,'aux12c')]:p.write(body+off,a[key],4)
  for off,key in [(0x2e8,'button9'),(0x120,'rageState'),(0x124,'rageAmount'),(0x13c,'systemState'),(0x158,'systemMeter'),(0xa30,'fieldA30')]:p.write(address+off,a[key],4)
  p.memory[body+0x40:body+0x48]=struct.pack('<2f',a['x'],a['y']);p.memory[address+0x1b0:address+0x23c]=struct.pack('<35i',*a['timers']);p.memory[address+0xf14:address+0xf22]=bytes(a['bytes'])
  p.write(address+0x1ac,256,4)
  return address,body
 def put_context(c,player):
  p.write(0x4c3808,c['mode'],4);p.write(0x132c4bc,c['stageIndex'],4);p.memory[0x132c398:0x132c39c]=struct.pack('<f',c['stageX'])
  for pool,count,objects,objectBase in [(BATTLE+0x29c+player*0x108,48,c['own'],OBJECTS),(BATTLE+0x14c,64,c['battle'],OBJECTS+0x10000)]:
   p.memory[pool:pool+count*4]=bytes(count*4)
   for slot,kind,subtype,action,flags,x in objects:
    node=objectBase+slot*0x400;body=node+0x100;p.write(pool+slot*4,node,4);p.write(node+0x1c,body,4)
    for off,value in [(0xcc,kind),(0xd0,subtype),(0x24,action),(0x108,flags)]:p.write(body+off,value,4)
    p.memory[body+0x40:body+0x44]=struct.pack('<f',x)
 def setup(a,b,config,c,player):
  address,body=put_actor(player,a);put_actor(1-player,b);put_context(c,player)
  system,character,*d=config;p.memory[address+0x10c:address+0x120]=struct.pack('<5I',system,0,character,0,0);p.memory[0x12d2308:0x12d2318]=bytes(d)
  p.write(CONTEXT,address,4);buffered_stdout(p);return address,body
 def original(entry,args):
  nonlocal instructions
  result,n=p.run(entry,args,limit=100000);instructions+=n;counts[hex(entry)]+=1;return signed(result,32)
 def effects(address,body):
  stream=p.read(p.read(0x5d1bf8,4)+8,4);end=p.read(stream,4);assert 0x1a00000<=end<=0x1a10000
  diagnostic=bytes(p.memory[0x1a00000:end]).count(b'TURN!!!!!')
  return [p.read(address+0x244,4),p.read(body+0x128,4),diagnostic,*struct.unpack_from('<35i',p.memory,address+0x1b0)]
 def condition(id,a,b,config,c,player=0):
  address,body=setup(a,b,config,c,player);value=original(0x1798f0,[CONTEXT,id]);want=[value,*effects(address,body)]
  commands.append(' '.join(map(str,['condition',id,*encode(a),*encode(b),*config,*encode_context(c)])));expected.append(want);outcomes[f'{id}:{value}']+=1
 def available(key,c,player=0):
  address,_=setup(actor(),actor(),[0,0,*descriptors[0]],c,player);value=original(0x179d10,[CONTEXT,key])
  commands.append(' '.join(map(str,['available',key,*encode_context(c)])));expected.append([value])
 def filter(kind,start,count,a,b,config,c,categories,requirements,recognized,player=0):
  address,body=setup(a,b,config,c,player)
  p.memory[RESULTS:RESULTS+4*count]=struct.pack(f'<{count}I',*recognized);p.memory[CATEGORIES:CATEGORIES+52]=struct.pack('<13I',*categories);p.memory[REQUIREMENTS:REQUIREMENTS+36]=struct.pack('<9I',*requirements)
  table=(0x4eb1e0 if kind else 0x4eb068)+start*12
  original(0x14af48,[address,RESULTS,count,table,CATEGORIES,REQUIREMENTS]);want=effects(address,body)+list(struct.unpack_from(f'<{count}I',p.memory,RESULTS))
  commands.append(' '.join(map(str,['filter',kind,*encode(a),*encode(b),*config,*encode_context(c),start,count,*categories,*requirements,*recognized])));expected.append(want)
 #Every callback, all raw attack state numbers, both contact outcomes and
 #table/alias disagreements. Callbacks may mutate even when they return0.
 for id,case in itertools.product(range(96),range(256)):
  a=actor();b=actor();c=context();a['state194']=(case%96)<<16|1;a['body108']=0x40 if case<192 else 0
  if case>=96:
   a['state194']=(case%96)<<16|rng.randrange(4);a['state1a4']=(rng.randrange(5)<<16)|rng.randrange(4)
   a['flags23c']=rng.choice([0,0x1000,0x100000,0x200000,0x400000,0x800000,0xa01000]);a['flags244']=rng.getrandbits(32);a['flags248']=rng.getrandbits(32)
   a['stateFlags']=rng.randrange(256);a['aliasFlags']=rng.randrange(256);a['body104']=rng.choice([0,0x40000,0x80000,0xc0000]);a['body38']=rng.choice([0,0x80000]);a['character']=rng.randrange(51)
   a['timers']=[rng.choice([-1,0,1,1024,1025]) for _ in range(35)];a['bytes']=[rng.randrange(256) for _ in range(14)]
   a['rageState']=rng.choice([-2147483648,-1,0,1,2,3,2147483647]);a['rageAmount']=rng.choice([-1,0,10239,10240,10241]);a['systemState']=rng.randrange(5);a['systemMeter']=rng.choice([-1,0,255,256,257,65536]);a['fieldA30']=rng.choice([-1,0,1,2,256])
   a['x']=rng.choice([-0.25,0,0.25,160.5,240.25]);a['y']=rng.choice([-1,0,47.75,48,48.25,479.75,480]);a['button9']=rng.choice([0,1,0x80000000]);c['mode']=case%4
  a['action']=rng.choice([0,467,565,569,572,599,602,657,658,666,667,673,674,749,750]);a['auxAction']=rng.choice([0,781,782,783,784,786]);a['aux128']=case%3;a['aux12c']=case%24
  b['state194']=(case%96)<<16|case%3;b['character']=case%51;b['flags23c']=rng.choice([0,0x10,0x1000,0x1010,0x200000]);b['stateFlags']=case%256;b['timers'][25]=case%3-1;b['x']=rng.choice([160.5,180.5,240.25]);b['y']=rng.choice([0,16.5,48.25,100])
  if case%4:c['own']=[(rng.randrange(48),rng.choice([2,4,5]),rng.choice([0,160,161]),rng.choice([0,467]),rng.choice([0,0x400000,0x800000]),rng.choice([136.5,160.5,184.5]))]
  if case%8:c['battle']=[(rng.randrange(64),5,rng.randrange(4),rng.choice([0,76,133]),0,rng.choice([124.5,160.5,196.5]))]
  c['stageIndex']=rng.choice([-1,0,7]);c['stageX']=rng.choice([124.5,160.5,196.5])
  condition(id,a,b,[case%9,a['character'],*descriptors[case%8]],c,case%2)
 condition(255,actor(),actor(),[0,0,*descriptors[0]],context())
 #Branches whose prerequisites are unlikely to coincide in random snapshots.
 for system in [4,6]:
  a=actor();a.update(rageState=1,systemState=2);d=descriptors[0].copy();d[3]=14
  condition(4,a,actor(),[system,23,*d],context())
 for system in [1,5,6]:
  a=actor();a['bytes'][13]=255;a.update(systemMeter=256,fieldA30=1)
  d=descriptors[0].copy();d[2]=9;condition(79,a,actor(),[system,23,*d],context())
 for state in [80,81,82,83,86,87]:
  a=actor();a['character']=4;b=actor();b['state194']=state<<16|2
  condition(56,a,b,[0,4,*descriptors[0]],context())
 for count in range(4):
  c=context();c['own']=[(i*15,2,160+i%2,0,0,0) for i in range(count)]
  condition(75,actor(),actor(),[0,23,*descriptors[0]],c)
 for state,button,contact in itertools.product([72,73,74,75,76],[0,1,0x80000000],[0,0x40]):
  a=actor();a.update(state194=state<<16|1,button9=button,body108=contact)
  condition(65,a,actor(),[0,23,*descriptors[0]],context())
 #The first matching object wins even if a later one has the wanted action.
 for id,firstAction,stage in itertools.product([0,1],[0,76,133,467],[-1,0]):
  a=actor();c=context();c['stageIndex']=stage;c['stageX']=500
  c['battle' if id==0 else 'own']=[(0,5 if id==0 else 4,0,firstAction,0,500),(31,5 if id==0 else 4,0,76 if id==0 else 467,0,a['x'])]
  condition(id,a,actor(),[0,23,*descriptors[0]],c)
 #Every character-dependent air rectangle at its edges and just outside,
 #including negative/fractional origin and mirror. No approximate hitboxes.
 for character,mirror,x in itertools.product(range(51),[0,0x80000],[-0.25,160.5]):
  r=struct.unpack_from('<4h',p.memory,0x4e5d50+character*8)
  left,right=(int(x-r[0]),int(x-r[1])) if mirror else (int(x+r[1]),int(x+r[0]))
  for ox,oy in [(left, r[3]),(right,r[2]),(left-0.25,r[3]),(right+0.25,r[2]),(left,r[3]-0.25),(right,r[2]+0.25)]:
   a=actor();b=actor();a.update(character=character,body38=mirror,x=x);b.update(flags23c=0x10,state194=0,x=ox,y=oy)
   condition(16,a,b,[0,character,*descriptors[0]],context())
 #Character throw range: exact inclusive bound, truncation below/above it,
 #all source/target keys and armed/unarmed target columns.
 for character,target,armed in itertools.product(range(51),range(51),[0,0x1000]):
  bound=signed(p.read(0x4e5ee8+character*36+24,2),16)+signed(p.read(0x4e5ab8+target*8+(4 if armed else 6),2),16)
  a=actor();b=actor();a.update(character=character,x=0);b.update(character=target,flags23c=armed)
  for distance in [bound+0.75,bound+1.0]:
   b['x']=distance;condition(59,a,b,[0,character,*descriptors[0]],context())
 #Custom descriptor branches, low-five-bit use count, byte flag predicates.
 for byte in range(256):
  a=actor();a['bytes']=[byte]*14;b=actor();d=descriptors[0].copy()
  for field in [2,3,5,6]:d[field]=byte
  a.update(rageState=2,systemState=3,systemMeter=256,fieldA30=1)
  for id in [2,4,5,6,7,8,27,28,30,31,39,40,41,42,43,44,78,79]:condition(id,a,b,[6,23,*d],context())
 #Raw subtype key and grouped keys250..255, with kind filtering and holes.
 for key in range(256):
  for subtype in [key-1,key,key+1]:
   c=context();c['own']=[(0,5,key,0,0,0),(47,2,subtype,0,0,0)];available(key,c,key%2)
 for key,subtype in itertools.product(range(250,256),range(256)):
  c=context();c['own']=[(0,2,subtype,0,0,0)];available(key,c)
 #Every shipped record, then multi-record filtering with preserved nonboolean
 #results and earlier callbacks' writes visible to later conditions.
 for kind,total in [(0,31),(1,972)]:
  for start in range(total):
   a=actor();b=actor();c=context();a['state194']=((start%96)<<16)|1
   filter(kind,start,1,a,b,[start%9,23,*descriptors[start%8]],c,[1]*13,[1]*9,[0x80000000],start%2)
 for case in range(1024):
  kind=case%2;count=31 if not kind else 32;start=0 if not kind else rng.randrange(941)
  a=actor();b=actor();c=context();a.update(flags244=rng.getrandbits(32),state194=(rng.randrange(96)<<16)|1,button9=1);a['bytes']=[case%256]*14
  c['own']=[(0,2,rng.randrange(256),0,0,0),(47,2,rng.randrange(256),0,0x400000,0)]
  filter(kind,start,count,a,b,[case%9,23,*descriptors[case%8]],c,[rng.choice([0,1,1]) for _ in range(13)],[rng.choice([0,1,1,1]) for _ in range(9)],[rng.choice([0,1,0x80000000]) for _ in range(count)],case%2)
 binary=ROOT/'work/ss6/build-native/ss6-input-permissions-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,commands[i],got,want)
 for id in range(83):
  assert outcomes[f'{id}:0']>0,id
  if id!=65:assert outcomes[f'{id}:1']>0,id
 report=dict(status='passed_whole_input_permissions',cases=len(expected),original_calls=counts,original_instructions=instructions,condition_outcomes=outcomes,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole1798f0 for all96 callbacks and255,179d10 object availability and14af48 filtering of all31 normal/972 special records plus multi-record sequences. No callee skips; callback74 executes real libc logger into initialized FILE. Compare return/results,flags244,body128,all35 timers and diagnostic event count. Actor/meter/auxiliary/object snapshots and category13/requirement9 words supplied; caller producers, consumption and live battle remain separate. Geometry cases use exactly representable finite arithmetic; no full EE hardware floating-point claim.')
 (ROOT/'outputs/ss6-feasibility/input_permissions_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='condition_outcomes'},indent=2))

if __name__=='__main__':main()
