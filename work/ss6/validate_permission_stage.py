#!/usr/bin/env python3
"""Original permission producers and whole14a1b8, with no callee skips."""
import collections,hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from finite_float import value,square_root
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_input_permissions import BASE,BODIES,BATTLE,OBJECTS,CONTEXT,FIELDS,OFFSETS,actor,encode,context,encode_context
ROOT=Path(__file__).resolve().parents[2]
EXTRA=['vx','vy','auxFlags104','auxFlag134','auxX','auxY','timerDelta']
def extended():
 a=actor();a.update(vx=0,vy=0,auxFlags104=0xaabbffff,auxFlag134=0,auxX=110.5,auxY=120,timerDelta=256)
 return a
def encoded(a):return encode(a)+[a[k] for k in EXTRA]

class Oracle:
 def __init__(self,raw):
  self.p=Probe(raw);self.calls=collections.Counter();self.instructions=0;self.models=collections.Counter()
  self.p.write(0x4d3d08,BASE,4);self.p.write(0x4d3d00,BATTLE,4);self.p.write(0x4c38a8,6,4)
 def actor(self,player,a):
  p=self.p;address=BASE+player*0xf2c;body=BODIES+player*0x1000
  p.write(address,body,4);p.write(address+4,body+0x400,4);p.write(address+0xa24,player,4);p.write(BATTLE+0x24c+player*4,address,4)
  for i,off in enumerate(OFFSETS):p.write(address+off,a[FIELDS[i]],1 if i>=6 else 4)
  for off,key in [(0x38,'body38'),(0x104,'body104'),(0x108,'body108'),(0x24,'action'),(0x128,'body128'),(0x424,'auxAction'),(0x528,'aux128'),(0x52c,'aux12c'),(0x50,'vx'),(0x5c,'vy'),(0x504,'auxFlags104'),(0x534,'auxFlag134')]:p.write(body+off,a[key],4)
  for off,key in [(0x2e8,'button9'),(0x120,'rageState'),(0x124,'rageAmount'),(0x13c,'systemState'),(0x158,'systemMeter'),(0xa30,'fieldA30')]:p.write(address+off,a[key],4)
  p.memory[body+0x40:body+0x48]=struct.pack('<2f',a['x'],a['y']);p.memory[body+0x440:body+0x448]=struct.pack('<2f',a['auxX'],a['auxY'])
  p.memory[address+0x1b0:address+0x23c]=struct.pack('<35i',*a['timers']);p.memory[address+0xf14:address+0xf22]=bytes(a['bytes'])
  p.write(address+0x1ac,a['timerDelta'],4)
  return address,body
 def setup(self,a,b,c,config,player):
  p=self.p;address,body=self.actor(player,a);self.actor(1-player,b)
  p.write(0x4c3808,c['mode'],4);p.write(0x132c4bc,c['stageIndex'],4);p.memory[0x132c398:0x132c39c]=struct.pack('<f',c['stageX'])
  for pool,count,objects,objectBase in [(BATTLE+0x29c+player*0x108,48,c['own'],OBJECTS),(BATTLE+0x14c,64,c['battle'],OBJECTS+0x10000)]:
   p.memory[pool:pool+count*4]=bytes(count*4)
   for slot,kind,subtype,action,flags,x in objects:
    node=objectBase+slot*0x400;obj=node+0x100;p.write(pool+slot*4,node,4);p.write(node+0x1c,obj,4)
    for off,v in [(0xcc,kind),(0xd0,subtype),(0x24,action),(0x108,flags)]:p.write(obj+off,v,4)
    p.memory[obj+0x40:obj+0x44]=struct.pack('<f',x)
  system,character,*d=config;p.memory[address+0x10c:address+0x120]=struct.pack('<5I',system,0,character,0,0);p.memory[0x12d2308:0x12d2318]=bytes(d)
  p.write(CONTEXT,address,4);buffered_stdout(p)
  return address,body
 def run(self,entry,args,model=False):
  self.p.finite_model=model
  result,n=self.p.run(entry,args,limit=200000);self.instructions+=n;self.calls[hex(entry)]+=1;self.models['finite_model' if model else 'exact_finite']+=1
  return signed(result,32)

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 oracle=Oracle(raw);p=oracle.p;rng=random.Random(0x14a1b8);commands=[];expected=[];outcomes=collections.Counter()
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 def append(values,want):commands.append(' '.join(map(str,values)));expected.append(want)
 def gate(op,id,a,start=0,model=False):
  address,body=oracle.setup(a,extended(),context(),[0,a['character'],*descriptors[0]],len(expected)%2)
  p.write(address+0x884,start,4)
  entry={'category':0x179e68,'requirement':0x17a150,'cancel':0x179968}[op]
  result=oracle.run(entry,[CONTEXT,id],model)
  append([op,id,*encoded(a),*([start] if op=='cancel' else [])],[result,p.read(body+0x504,4),*struct.unpack_from('<35i',p.memory,address+0x1b0)])
  outcomes[f'{op}:{id}:{result}']+=1
 def apply(a,b,config,c,start,count,seed,recognized,cancels,model=False):
  address,body=oracle.setup(a,b,c,config,seed%2);owner=address+0x2c4
  #Seed every byte, including padding: only the documented result arrays
  #may change. The native probe separately checks all represented metadata.
  p.memory[owner:owner+0x744]=bytes([seed%256])*0x744
  features=[(seed+i)&0xffffffff for i in range(171)];features[9]=a['button9'];p.memory[owner:owner+684]=struct.pack('<171I',*features)
  p.write(owner+0x5bc,count,4);p.write(owner+0x5c0,start,4);p.memory[owner+0x428:owner+0x448]=bytes((seed+i)%256 for i in range(32))
  for kind,size in [(0,31),(1,32)]:
   for i in range(size):
    n=(seed+i)&0xffffffff
    for off,v,sz in [(0x644 if kind else 0x4c4,i,2),(0x5c4 if kind else 0x448,i%2,4),(0x328 if kind else 0x2ac,recognized[kind][i],4)]:p.write(owner+off+i*sz,v,sz)
    off=owner+(0x684 if kind else 0x502)+i*6;p.memory[off:off+5]=struct.pack('<BBHB',n%14,n%256,n%65536,n%11)
    if kind:p.write(owner+0x3a8+i*4,cancels[i],4)
  before=bytes(p.memory[owner:owner+0x744]);oracle.run(0x14a1b8,[address],model)
  after=p.memory[owner:owner+0x744]
  for i,(old,new) in enumerate(zip(before,after)):
   if not 0x2ac<=i<0x428:assert old==new,(hex(i),old,new)
  stream=p.read(p.read(0x5d1bf8,4)+8,4);end=p.read(stream,4);assert 0x1a00000<=end<=0x1a10000
  diagnostics=bytes(p.memory[0x1a00000:end]).count(b'TURN!!!!!')
  want=[p.read(address+0x244,4),p.read(body+0x128,4),diagnostics,*struct.unpack_from('<35i',p.memory,address+0x1b0),p.read(body+0x504,4),*struct.unpack_from('<95I',p.memory,owner+0x2ac)]
  append(['apply',*encoded(a),*encoded(b),*config,*encode_context(c),seed,(seed//2)%2,start,count,*recognized[0],*recognized[1],*cancels],want)
 #State categories: raw/effective alias disagreement, timer boundaries,
 #signed vertical speed and all13 dispatch entries (plus out-of-range).
 for case in range(512):
  a=extended();a.update(flags23c=rng.choice([0,0x10,0x100,0x110,0x200000,0x200010,0x200100]),state194=(case%96)<<16|case%3,state1a4=(case%4)<<16|case%3,stateFlags=case%16,aliasFlags=(case//4)%16,character=45 if case%7==0 else 0)
  a['timers'][8]=case%3-1;a['timers'][27]=(case//3)%3-1;a['vx']=rng.choice([-2147483648,-1,0,1,2147483647]);a['vy']=rng.choice([-2147483648,-262145,-262144,-1,0,1,262144,262145,2147483647]);a['y']=rng.choice([-1,0,47.75,48,48.25])
  for id in range(14):gate('category',id,a,model=id==8 and a['vx']==2147483647)
 for state,timer8,timer27,flags in itertools.product([0,1,2,9,10,22,23,24],[-1,0,1],[-1,0,1],[0,0x100]):
  a=extended();a.update(state194=state<<16,flags23c=flags);a['timers'][8]=timer8;a['timers'][27]=timer27
  for id in [2,3]:gate('category',id,a)
 for vy,y,vx in itertools.product([-2147483648,-262145,-262144,-1,0,1,262144,262145,2147483647],[47.75,48,48.25],[-1,0,1]):
  a=extended();a.update(flags23c=0x10,vy=vy,y=y,vx=vx)
  for id in [5,6,7,8]:gate('category',id,a)
 for id,case in itertools.product(range(10),range(128)):
  a=extended();a.update(flags23c=rng.getrandbits(32),rageState=rng.choice([-1,0,1,2,3]),character=case%51,aux128=case%33,aux12c=case%35,auxFlag134=case%2)
  a['bytes'][1]=case%2;gate('requirement',id,a,model=True)
 #All auxiliary-dispatch keys and signed state values. Cases with sqrt use
 #the explicit finite model; separate exact cases below retain the strict mode.
 for character,state in itertools.product(range(51),[-2147483648,-1,*range(35),2147483647]):
  a=extended();a.update(character=character,aux128=state&0xffffffff,aux12c=state&0xffffffff);a['bytes'][1]=1
  gate('requirement',3,a,model=True)
 for character,mirror,dx,y in itertools.product([4,19,34],[0,0x80000],[-80.25,-80,-79.75,-32.25,-32,-31.75,0,31.75,32,32.25,79.75,80,80.25],[-0.25,0,0.25]):
  a=extended();offset={4:-68,19:-40,34:-28}[character];a.update(character=character,body38=mirror,auxX=a['x']+(-offset if mirror else offset)-dx,auxY=y)
  gate('requirement',3,a)
 for character,mirror,dx,dy in itertools.product([1,45],[0,0x80000],[0,6,18,23.75,24,24.25],[-24,-18,0,18,24]):
  a=extended();a.update(character=character,body38=mirror,auxX=a['x']+(50 if mirror else -50)-dx,auxY=120-dy)
  gate('requirement',3,a,model=True)
 for character,dx,dy in itertools.product([1,45],[-25,-24,-23,0,23,24,25],[0]):
  a=extended();a.update(character=character,auxX=a['x']-50-dx,auxY=120-dy);gate('requirement',3,a)
 #Every original record's cancel classification and all character/current
 #special categories, including the character32/48 exceptional states.
 for index,variant in itertools.product(range(972),range(3)):
  a=extended();a.update(state194=(0 if variant==0 else 64+index%32)<<16|variant%2,character=index%51);a['timers'][4]=variant-1
  gate('cancel',index,a,start=max(0,index-index%20))
 for character,state in itertools.product(range(51),range(96)):
  a=extended();a.update(character=character,state194=state<<16|1);gate('cancel',25,a)
 for slot,flags,action,timer in itertools.product(range(14),[0,0x100000],[563,564,565],[-1,0,1]):
  a=extended();a.update(character=22,flags23c=flags,action=action,state194=0);a['timers'][4]=timer;gate('cancel',slot,a,start=0)
 #179968's flag80 branch consumes timer4 using14d010. Include signed wrap,
 #OLD-value truth and several matching candidates sharing one timer visit.
 timedRecords=[i for i in range(972) if p.read(0x4eb1e0+i*12+6,2)&0x80 and p.read(0x4eb1e0+i*12+4,1)==255]
 assert timedRecords
 for index,delta,timer in itertools.product(timedRecords,[0,1,128,256,-1,2147483647],[-2147483648,-1,0,1,127,128,255,256,257,2147483647]):
  a=extended();a.update(state194=0,timerDelta=delta);a['timers'][4]=timer;gate('cancel',index,a)
 #Whole permission stage across each explicit binding block and all systems.
 special=bytes(p.memory[0x4eb1e0:0x4eb1e0+972*12]);blocks={}
 for i in range(972):
  character=special[i*12]
  if character!=255 and character not in blocks:
   count=0
   while count<32 and struct.unpack_from('<h',special,(i+count)*12+2)[0]!=-1:count+=1
   blocks[character]=(i,count)
 assert len(blocks)==48
 for case,(character,system,variant) in enumerate(itertools.product(blocks,range(9),range(4))):
  a=extended();b=extended();c=context();start,count=blocks[character]
  a.update(character=character,state194=[0,64<<16|1,73<<16|1,54<<16][variant],flags23c=[0x1000,0x1010,0x1000,0x1040][variant],flags244=0x01400000 if variant==2 else 0,button9=1,systemState=2,rageState=1,systemMeter=10240,fieldA30=1)
  a['timers'][4]=1;a['bytes']=[1]*14
  b.update(flags23c=0x10,state194=0,x=a['x'],y=16)
  recognized=[[0x80000000 if variant%2 else 1]*31,[1]*32];cancels=[0xdeadbeef+i for i in range(32)]
  apply(a,b,[system,character,*descriptors[case%8]],c,start,count,case,recognized,cancels,model=True)
 for case in range(512):
  a=extended();b=extended();c=context();character=rng.choice(list(blocks));start,count=blocks[character]
  if case%16==0:start,count=-1,-1
  if case%16==1:count=0
  a.update(character=character,flags23c=rng.choice([0,0x1000,0x10,0x100,0x40,0x80,0x400,0x200000,0x800000]),flags244=rng.getrandbits(32),flags248=rng.getrandbits(32),state194=(rng.randrange(96)<<16)|rng.randrange(3),state1a4=rng.randrange(3),stateFlags=rng.randrange(16),aliasFlags=rng.randrange(16),aux128=rng.randrange(15),aux12c=rng.randrange(35),button9=case%2,auxY=case%3-1,vy=rng.choice([-262144,0,262144]))
  a['bytes']=[rng.randrange(256) for _ in range(14)];a['timers']=[rng.choice([-1,0,1,1024,1025]) for _ in range(35)];c['own']=[(0,2,160,0,0,0),(47,2,161,0,0x400000,0)]
  recognized=[[rng.choice([0,1,0x80000000]) for _ in range(n)] for n in [31,32]];cancels=[rng.getrandbits(32) for _ in range(32)]
  apply(a,b,[case%9,character,*descriptors[case%8]],c,start,count,10000+case,recognized,cancels,model=True)
 #SQRT model: all finite exponents, mantissa endpoints and random normals.
 #Validate the lower/upper neighboring-square property independently too.
 roots=[0,0x80000000]+[(e<<23)|m for e,m in itertools.product(range(1,255),[0,1,0x7fffff])]+[rng.randrange(0x800000,0x7f800000) for _ in range(4096)]
 for bits in roots:
  p.floats[0]=bits;oracle.run(0x1a3b98,[],model=True);root=p.floats[0]
  assert root==square_root(bits)
  if bits&0x7fffffff:assert value(root)**2<=value(bits)<value(root+1)**2
  append(['sqrt',bits],[root])
 for integer in range(129):
  bits=struct.unpack('<I',struct.pack('<f',integer*integer))[0];p.floats[0]=bits;oracle.run(0x1a3b98,[])
  append(['sqrt',bits],[p.floats[0]])
 binary=ROOT/'work/ss6/build-native/ss6-input-permissions-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
 for id in range(12):assert outcomes[f'category:{id}:0'] and outcomes[f'category:{id}:1'],id
 report=dict(status='passed_whole_permission_stage',cases=len(expected),original_calls=oracle.calls,original_instructions=oracle.instructions,arithmetic_scope=oracle.models,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole179e68 categories,17a150 requirements including all1a3700 auxiliary branches,179968 cancel permissions and14a1b8 complete gate/filter/cancel stage. Compare all35 timers, including179968 flag80 decrement/OLD-value check and signed wrap/clamp boundaries; earlier26659-case report omitted timer writes. Real object lists,descriptors and buffered libc diagnostics; no skipped callees. All48 explicit binding blocks/systems0..8 plus empty/disabled/unused slots. Original input-owner bytes outside result arrays and native progress/metadata remain unchanged. Supplied actor/command snapshots; sampling-to-stage integration and move execution pending. The4989 calls at1a3b98 are explicitly the SQRT/return tail,not whole1a3b68; full auxiliary helpers are executed inside17a150/14a1b8. SQRT extension uses explicit rational finite rounding model plus exact-square cases; not EE hardware accuracy.')
 (ROOT/'outputs/ss6-feasibility/permission_stage_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
