#!/usr/bin/env python3
"""Whole clear/charge helpers and explicitly bounded1494f0 input slices."""
import collections,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_input_features import FEATURES,LATCHES,HELD,PRESSED,PADS
from validate_input_pipeline import encoded
from round_entry_oracle import buffered_stdout
ROOT=Path(__file__).resolve().parents[2]
ACTOR=0x1b00000;OTHER=ACTOR+0x1000;BODY=0x1b03000;OWNER=ACTOR+0x2c4;BATTLE=0x1b04000
AFIELDS=['character','flags','controlFlags','locked','controlKind','controlMode','state','bodyFlags','delta','level']

class Boundary:
 def __init__(self,*addresses):self.addresses=addresses;self.seen=set();self.stopped=None
 def __contains__(self,pc):
  self.seen.add(pc)
  if pc in self.addresses:self.stopped=pc;return True
  return False

def actor():return dict(character=9,flags=0x1000,controlFlags=0,locked=0,controlKind=0,controlMode=0,state=0,bodyFlags=0,delta=256,level=173,timers=[0]*35)
def encode_actor(a):return [*[a[k] for k in AFIELDS],*a['timers']]
def frame():return dict(player=0,facing=0,index=-1,mode=0,state=4,field18=0,allowed=1)
def encode_frame(f):return [f[k] for k in ['player','facing','index','mode','state','field18','allowed']]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 quick='--quick' in sys.argv
 p=Probe(raw);rng=random.Random(0x179708);commands=[];expected=[];calls=collections.Counter();instructions=0;routes=collections.Counter()
 def run(pc,args=(),stops=()):
  nonlocal instructions
  _,n=p.run(pc,args,limit=300000,stop_before=stops);instructions+=n;calls[hex(pc)]+=1
 def put_actor(a,f=None):
  p.memory[ACTOR:ACTOR+0x3000]=bytes(0x3000);p.write(ACTOR,BODY,4)
  p.memory[BODY:BODY+0x1000]=bytes(0x1000)
  for key,off,size in [('character',0xa10,4),('flags',0x23c,4),('controlFlags',0x240,4),('locked',0x24c,1),('controlKind',0xa20,4),('controlMode',0xc8,4),('state',0x194,4),('delta',0x1ac,4),('level',0xf18,1)]:p.write(ACTOR+off,a[key],size)
  p.write(BODY+0x38,a['bodyFlags'],4);p.memory[ACTOR+0x1b0:ACTOR+0x23c]=struct.pack('<35i',*a['timers'])
  if f is not None:
   p.write(ACTOR+0xa24,f['player'],4);p.write(ACTOR+0xa08,f['facing'],4);p.write(ACTOR+0x2c0,f['index'],4)
   p.write(0x4c38a8,f['mode'],4);put_battle(f['state'],f['field18'])
 def put_battle(state,field):
  p.write(0x4d3d00,BATTLE,4);p.write(BATTLE,state,4);p.write(BATTLE+0x18,field,4)
 def actor_output():return [p.read(ACTOR+0xf18,1),*struct.unpack_from('<35i',p.memory,ACTOR+0x1b0)]
 def make_input(case):
  start=[-1,0,14,955][case%4];count=[-1,0,1,7,31,32][case%6]
  result=dict(start=start,count=count,enabled=int(start!=-1),features=[rng.getrandbits(32) for _ in range(171)],priority=[rng.randrange(256) for _ in range(32)],slots=[])
  for _ in range(63):result['slots'].append([rng.choice([-1,*range(273)]),rng.randrange(2),rng.getrandbits(32),rng.getrandbits(32),rng.randrange(14),rng.choice([0,7,11,12,255]),rng.choice([0,51,52,5999,6000]),rng.choice([0,1,4,10,33,255])])
  return result
 def put_input(i):
  p.memory[OWNER:OWNER+0x744]=bytes([0xa5])*0x744
  p.write(OWNER+0x5c0,i['start'],4);p.write(OWNER+0x5bc,i['count'],4)
  p.memory[OWNER:OWNER+684]=struct.pack('<171I',*i['features']);p.memory[OWNER+0x428:OWNER+0x448]=bytes(i['priority'])
  for slot,s in enumerate(i['slots']):
   special=slot>=31;index=slot-31 if special else slot
   definition,alternate,recognized,cancel,*progress=s
   for off,value,size in [(0x644 if special else 0x4c4,definition,2),(0x5c4 if special else 0x448,alternate,4),(0x328 if special else 0x2ac,recognized,4)]:p.write(OWNER+off+index*size,value,size)
   if special:p.write(OWNER+0x3a8+index*4,cancel,4)
   address=OWNER+(0x684 if special else 0x502)+index*6;p.memory[address:address+6]=struct.pack('<BBHBB',*progress,0xa5)
 def encode_input(i):return [i['enabled'],i['start'],i['count'],*encoded(i['features']),*i['priority'],*[v for slot in i['slots'] for v in slot]]
 def input_output(i):
  out=[i['enabled'],signed(p.read(OWNER+0x5c0,4),32),signed(p.read(OWNER+0x5bc,4),32),*struct.unpack_from('<171I',p.memory,OWNER),*p.memory[OWNER+0x428:OWNER+0x448]]
  for slot,s in enumerate(i['slots']):
   special=slot>=31;index=slot-31 if special else slot;address=OWNER+(0x684 if special else 0x502)+index*6
   out += [signed(p.read(OWNER+(0x644 if special else 0x4c4)+index*2,2),16),p.read(OWNER+(0x5c4 if special else 0x448)+index*4,4),p.read(OWNER+(0x328 if special else 0x2ac)+index*4,4),p.read(OWNER+0x3a8+index*4,4) if special else s[3],*struct.unpack_from('<BBHB',p.memory,address)]
   assert p.read(address+5,1)==0xa5
  return out
 def bound_input(system,character,d,player):
  p.memory[ACTOR+0x10c:ACTOR+0x120]=struct.pack('<5I',system,player,character,0,0)
  p.memory[0x12d2308+player*128:0x12d2308+player*128+16]=bytes(d)
  run(0x179258,[OWNER,ACTOR+0x10c])
  result=dict(start=signed(p.read(OWNER+0x5c0,4),32),count=signed(p.read(OWNER+0x5bc,4),32),enabled=1,features=list(struct.unpack_from('<171I',p.memory,OWNER)),priority=list(p.memory[OWNER+0x428:OWNER+0x448]),slots=[])
  for special,count in [(False,31),(True,32)]:
   for slot in range(count):
    address=OWNER+(0x684 if special else 0x502)+slot*6
    result['slots'].append([signed(p.read(OWNER+(0x644 if special else 0x4c4)+slot*2,2),16),p.read(OWNER+(0x5c4 if special else 0x448)+slot*4,4),p.read(OWNER+(0x328 if special else 0x2ac)+slot*4,4),p.read(OWNER+0x3a8+slot*4,4) if special else 0,*struct.unpack_from('<BBHB',p.memory,address)])
  return result
 def sampler():
  features=[rng.getrandbits(32) for _ in range(171)];latches=[rng.choice([0,1,4,255]) for _ in range(12)];seed=rng.randrange(65536)
  p.memory[FEATURES:FEATURES+684]=struct.pack('<171I',*features);p.memory[LATCHES:LATCHES+12]=bytes(latches)
  p.memory[HELD:HELD+1200]=struct.pack('<600H',*[(seed+n*137)&65535 for n in range(600)])
  p.memory[PRESSED:PRESSED+1200]=struct.pack('<600H',*[(seed^(n*7919))&65535 for n in range(600)])
  return [*encoded(features),*latches,seed]
 def sampler_output():return [*struct.unpack_from('<171I',p.memory,FEATURES),*p.memory[LATCHES:LATCHES+12],*struct.unpack_from('<600H',p.memory,HELD),*struct.unpack_from('<600H',p.memory,PRESSED)]
 def pads():
  out=[]
  for player in range(2):
   held,pressed=rng.randrange(65536),rng.randrange(65536)
   normal=[1<<n for n in (range(8,16) if player==0 else reversed(range(8,16)))];mode6=list(reversed(normal))
   p.write(PADS+player*12,held,4);p.write(PADS+player*12+4,pressed,4)
   for address,values in [(0x4eaac0,normal),(0x12d32d8,mode6)]:p.memory[address+player*32:address+player*32+32]=struct.pack('<8I',*values)
   out += [held,pressed,*normal,*mode6]
  return out
 def append(values,want):commands.append(' '.join(str(int(v)) if isinstance(v,bool) else str(v) for v in values));expected.append(want)
 for kind,case in itertools.product(range(3),range(2 if quick else 128)):
  i=make_input(case);i['enabled']=case%2 #Clearing intentionally ignores this separate native flag.
  put_input(i);shared=sampler();run([0x1797a8,0x179708,0x178920][kind],[case%2 if kind==2 else OWNER])
  append(['clear',kind,case%2,*encode_input(i),*shared],[0,*input_output(i),*sampler_output()])
 thresholds=[-2147483648,-1,0,1,255,2147483647]+[n*256+delta for n in [60,180,360,1200,4800,5940] for delta in [-1,0,1]]
 for case in range(8 if quick else 3072):
  a=actor();a.update(character=9 if case%8 else 0,controlKind=case%3,controlMode=[0,35,36,37][case%4],state=77<<16|1 if case%13==0 else 0,delta=rng.choice([-1,0,1,128,256,2147483647]),level=case%256)
  a['timers']=[rng.randrange(-999,999) for _ in range(35)];a['timers'][19]=thresholds[case%len(thresholds)]
  held=rng.choice([0,0,1,0x80000000]);state=rng.choice([-1,0,3,4,5]);field=rng.choice([-1,0,0,1])
  put_actor(a);put_battle(state,field);p.write(ACTOR+0x37c,held,4);run(0x14bcc8,[ACTOR])
  append(['charge',*encode_actor(a),held,state,field],[0,*actor_output()])
 for case in range(8 if quick else 512):
  a=actor();a.update(character=[0,9,24,25][case%4],controlKind=(case//4)%3,controlMode=[0,35,36,37][(case//12)%4],controlFlags=(case//3)%16,flags=0x1000|[0,0x10000000,0x20000000,0x30000000][case%4]|(0x100000 if case%3==0 else 0),locked=(case//7)%2,bodyFlags=0x80000 if case%2 else 0)
  a['timers'][0]=rng.choice([-1,0,1,256]);a['timers'][19]=60*256;a['timers'][20]=rng.choice([-1,0,1]);a['timers'][31]=257
  f=frame();f.update(player=case%2,facing=(case//2)%2,index=[-1,0,599,600,719][case%5],mode=6 if case%3==0 else 0,state=[0,4][case%2],field18=rng.choice([-1,0,1]),allowed=(case//5)%2)
  put_actor(a,f);pad=pads();opponent=0x08000000 if (case//9)%2 else 0;p.write(OTHER+0x23c,opponent,4)
  i=make_input(case);put_input(i);shared=sampler();p.put(16,f['allowed']);p.put(17,ACTOR);p.put(18,OTHER)
  boundary=Boundary(0x149768,0x1497fc,0x1498b0);run(0x1495e8,stops=boundary)
  assert boundary.stopped is not None
  route=3 if boundary.stopped==0x1498b0 else 0 if 0x179530 in boundary.seen else 1 if 0x149620 in boundary.seen else 2
  locked=-1 if route==3 else int(boundary.stopped==0x149768);routes[str(route)]+=1
  append(['sample',*encode_actor(a),*encode_frame(f),*pad,opponent,*encode_input(i),*shared],[route,locked,*actor_output(),*input_output(i),*sampler_output()])
 requestOutcomes=collections.Counter();requestRoutes=collections.Counter()
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 fixtures=itertools.product([*range(42),*range(43,49)],range(9),range(2))
 if quick:fixtures=itertools.islice(fixtures,8)
 for case,(character,system,variant) in enumerate(fixtures):
  a=actor();a.update(character=character,state=(case%64)<<16,controlFlags=(case//9)%16,locked=case%7==0,flags=0x1000|(0x100000 if variant else 0)|(0x400000 if case%3==0 else 0),bodyFlags=0x80000 if variant else 0)
  a['timers'][0]=case%3-1;a['timers'][4]=257;a['timers'][19]=60*256;a['timers'][20]=case%3-1;a['timers'][31]=a['timers'][32]=256
  f=frame();f.update(player=variant,facing=variant,index=[-1,0,599,600,719][case%5],mode=6,state=3 if case%3 else 4,allowed=case%5!=0)
  put_actor(a,f);pad=pads();opponent=0x08001000 if case%11==0 else 0x1000
  #The sampling prefix holds an opponent pointer, while request helpers
  #repeat1400a8's actor-array lookup. Both must refer to the same fixture.
  otherAddress=ACTOR+(0xf2c if f['player']==0 else -0xf2c)
  p.memory[otherAddress:otherAddress+0xf2c]=bytes(0xf2c);p.write(otherAddress,BODY+0x400,4);p.write(otherAddress+4,BODY+0x800,4)
  p.write(otherAddress+0x23c,opponent,4);p.write(0x4d3d08,ACTOR-f['player']*0xf2c,4);p.write(ACTOR+4,BODY+0xc00,4);p.write(ACTOR+0xfc,f['player'],4)
  p.write(BODY+0xcc4,-1,4)
  for offset in [0x190,0x192,0x1a0,0x1a2]:p.write(ACTOR+offset,-1,2)
  p.write(BATTLE+0x144,300,4);p.write(0x4c3808,3,4);p.write(0x132c4bc,-1,4);p.memory[0x132c398:0x132c39c]=struct.pack('<f',160)
  d=descriptors[case%8].copy();d[4]=18;d[13]=42;d[14]=44
  i=bound_input(system,character,d,f['player'])
  #Seed unfinished motions and completion buffers after real binding. This
  #also exercises consumption without replacing recognition with results.
  for slot in i['slots']:
   slot[4:]=[rng.randrange(3),rng.randrange(4),rng.choice([0,51,52]),rng.choice([0,0,1,4])]
  put_input(i);shared=sampler();buffered_stdout(p);p.put(16,f['allowed']);p.put(17,ACTOR);p.put(18,otherAddress)
  boundary=Boundary(0x149770,0x1498b0);run(0x1495e8,stops=boundary)
  assert boundary.stopped==0x149770
  route=0 if 0x179530 in boundary.seen else 1;locked=int(0x14bb48 in boundary.seen);requestRoutes[f'{route}:{locked}']+=1
  pending=[signed(p.read(ACTOR+off,2),16) for off in [0x190,0x192]];requestOutcomes[f'{pending[0]}:{pending[1]}']+=1
  writes=[p.read(ACTOR+0x18c,4),*pending,p.read(ACTOR+0x19c,4),*[signed(p.read(ACTOR+off,2),16) for off in [0x1a0,0x1a2]],*[p.read(ACTOR+off,4) for off in [0x23c,0x244,0x248]],*[p.read(BODY+off,4) for off in [0x38,0x104,0x128]],signed(p.read(ACTOR+0xa48,4),32),p.read(ACTOR+0xb4,4),*[p.read(BODY+0xc00+off,4) for off in [0x134,0x130,0xc0]],signed(p.read(BODY+0xcc4,4),32),p.read(BODY+0xd04,4),p.read(ACTOR+0x254,1),*p.memory[ACTOR+0xf14:ACTOR+0xf22]]
  stream=p.read(p.read(0x5d1bf8,4)+8,4);end=p.read(stream,4);logs=bytes(p.memory[0x1a00000:end]);assert all(line in [b'DUMP:---------- !! MIKIRI !! -----------',b'DUMP:--------!!!!!TURN!!!!!--------'] for line in logs.splitlines()),logs
  writes += [logs.count(b'TURN!!!!!'),logs.count(b'MIKIRI')]
  append(['requests',*encode_actor(a),*encode_frame(f),*pad,opponent,*encode_input(i),*shared,system,*d],[route,locked,*actor_output(),*writes,*input_output(i),*sampler_output()])
 for case in range(8 if quick else 512):
  a=actor();a['controlFlags']=case%16;a['timers'][31]=rng.choice([-1,0,1,256]);f=frame()
  f.update(player=case%2,index=rng.choice([-2147483648,-721,-1,0,598,599,600,718,719,720,2147483647]),mode=6 if case%3==0 else 0,state=rng.choice([-1,0,3,4,5]),field18=rng.choice([-1,0,1]))
  put_actor(a,f);pad=pads();p.put(17,ACTOR)
  #This slice starts after the actor callbacks. Seed its saved return address
  #only; it reaches the real14bdf0 tail call and returns without skipped calls.
  p.write(0x1fff000+0x38,0x1ffff00,8);run(0x149790)
  append(['tail',*encode_actor(a),*encode_frame(f),*pad],[signed(p.read(ACTOR+0x2c0,4),32),*actor_output()])
 binary=ROOT/'work/ss6/build-native/ss6-input-lifecycle-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr,commands[min(len(result.stdout.splitlines()),len(commands)-1)][:500])
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for index,(got,want) in enumerate(zip(actual,expected)):assert got==want,(index,commands[index][:600],[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y][:30],len(got),len(want))
 if quick:print(json.dumps(dict(quick_cases=len(expected),status='passed_quick_fixture_check')));return
 report=dict(status='passed_input_lifecycle_boundaries',cases=len(expected),original_calls=calls,original_instructions=instructions,sampling_routes=routes,sampling_to_requests_cases=864,request_routes=requestRoutes,request_outcomes=requestOutcomes,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole1797a8/179708/178920 clear helpers and3072 whole14bcc8 charge cases.512 explicit1495e8 sampling slices stop before149768/1497fc or AI1498b0.864 additional slices start1495e8 and continue through sampling,recognition,permissions/forced/ordinary requests or locked14bb48,stopping before149770 actor callbacks;48 actual binding blocks/systems0..8 and both facing directions. Reached callees run whole,without skips.512 explicit149790 finish slices execute141820 and14bdf0 normally. Full171 features,63 definitions/progress/results,priorities,12 latches,1200 recording words,35 timers and request-side writes compared. Includes disabled owners,dynamic24/25 bindings,pad swap,owner/opponent gates,buffer-aging pause,negative/overflow counters and600-record/720-wrap mismatch. Not whole1494f0; AI,state callbacks,state-entry consumption ordering and live battle remain pending.')
 (ROOT/'outputs/ss6-feasibility/input_lifecycle_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
