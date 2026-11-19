#!/usr/bin/env python3
"""Whole149bc0 request dispatch and its system/alternate/character routes."""
import collections,hashlib,itertools,json,random,struct,subprocess
from validate_permission_stage import Oracle,extended,encoded,ROOT
from validate_input_permissions import BASE,BODIES,BATTLE,OBJECTS,context
from validate_input_features import PADS,LATCHES
from validate_action_selection import sparse
from extract_collision_tables import SOURCE_HASH
from mips_probe import signed
ROUTE_FIELDS=['flags240','controlKind','controlMode','controlFlags','aliasRequest','aliasPendingTable','aliasPendingIndex','dx','ax','dy','ay','request','pendingTable','pendingIndex','variant','pendingFE','flags24c','auxTimer','auxFrame','auxPending','pendingCharacter']
ROUTE_OFFSETS=[0x240,0xa20,0xc8,0xb4,0x19c,0x1a0,0x1a2,None,None,None,None,0x18c,0x190,0x192,0xa48,None,0x24c,None,None,None,0x254]
def actor():
 a=extended();a.update(dict.fromkeys(ROUTE_FIELDS,0));a.update(state194=0,aliasRequest=19,aliasPendingTable=-2,aliasPendingIndex=-3,pendingTable=-4,pendingIndex=-5,variant=-6,dx=7,ax=-8,dy=9,ay=-10,vx=11,vy=-12,auxTimer=13,auxFrame=17,auxPending=-19,pendingCharacter=251)
 return a
def encode_actor(a):return encoded(a)+[a[k] for k in ROUTE_FIELDS]
def inputs():return dict(count=32,priority=list(reversed(range(32))),normal=[0]*31,special=[0]*32,cancel=[1]*32,features=[0]*171)
def encode_input(i):return [i['count'],*i['priority'],*i['normal'],*i['special'],*i['cancel'],*sparse(i['features'])]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 oracle=Oracle(raw);p=oracle.p;rng=random.Random(0x149bc0);commands=[];expected=[];outcomes=collections.Counter()
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 custom=descriptors[0].copy();custom[4]=18
 special=bytes(p.memory[0x4eb1e0:0x4eb1e0+972*12]);blocks={}
 for index in range(972):
  character=special[index*12]
  if character!=255 and character not in blocks:
   count=0
   while count<32 and struct.unpack_from('<h',special,(index+count)*12+2)[0]!=-1:count+=1
   blocks[character]=(index,count)
 def put_actor(player,a,c):
  address=BASE+player*0xf2c;body=BODIES+player*0x1000
  for key,off in zip(ROUTE_FIELDS,ROUTE_OFFSETS):
   if off is not None:p.write(address+off,a[key],1 if off in [0x24c,0x254] else 2 if off in [0x190,0x192,0x1a0,0x1a2] else 4)
  for off,key in [(0x4c,'dx'),(0x54,'ax'),(0x58,'dy'),(0x60,'ay')]:p.write(body+off,a[key],4)
  p.write(body+0xfe,a['pendingFE'],2)
  for off,key in [(0x530,'auxTimer'),(0x4c0,'auxFrame'),(0x4c4,'auxPending')]:p.write(body+off,a[key],4)
  system,character,*d=c;p.memory[address+0x10c:address+0x120]=struct.pack('<5I',system,player,character,0,0)
  p.memory[0x12d2308+player*128:0x12d2308+player*128+16]=bytes(d)
  return address,body
 def put_input(address,i):
  owner=address+0x2c4;p.memory[owner:owner+0x744]=bytes([0xa5])*0x744
  p.write(owner+0x5bc,i['count'],4);p.memory[owner+0x428:owner+0x448]=bytes(i['priority'])
  p.memory[owner:owner+684]=struct.pack('<171I',*i['features'])
  p.memory[owner+0x2ac:owner+0x428]=struct.pack('<95I',*i['normal'],*i['special'],*i['cancel'])
  return bytes(p.memory[owner:owner+0x744])
 def run(kind,a=None,b=None,inp=None,other=None,system=6,d=custom,otherSystem=6,otherD=custom,owner=0,pressed=0,mask=16,distance=300,objects=(),battleState=3):
  a=actor() if a is None else a;b=actor() if b is None else b;inp=inputs() if inp is None else inp;other=inputs() if other is None else other
  player=len(expected)%2;config=[system,a['character'],*d];otherConfig=[otherSystem,b['character'],*otherD]
  oracle.setup(a,b,context(),config,player);address,body=put_actor(player,a,config);otherAddress,otherBody=put_actor(1-player,b,otherConfig)
  originalInputs=[put_input(address,inp),put_input(otherAddress,other)]
  if kind==7:
   owner=player;p.write(BATTLE,battleState,4);p.memory[LATCHES:LATCHES+12]=bytes(range(1,13))
  if kind==6:
   p.write(address+0x884,blocks[a['character']][0],4);originalInputs[0]=bytes(p.memory[address+0x2c4:address+0xa08])
  p.write(address+0xfc,1-player if owner else player,4)
  p.write(PADS+player*12+4,pressed,4);p.write(0x4eaac0+player*32+16,mask,4)
  p.write(BATTLE+0x144,distance,4);pool=BATTLE+0x29c+(1-player)*0x108;p.memory[pool:pool+48*4]=bytes(48*4)
  for slot,kindObject in objects:
   node=OBJECTS+0x20000+slot*0x400;p.write(pool+slot*4,node,4);p.write(node+0x1c,node+0x100,4);p.write(node+0x1cc,kindObject,4)
  entry=[0x14c0d0,0x14ce28,0x209840 if a['character']==45 else 0x1ec4c8,0x14ca28,0x149bc0,0x149980,0x14a1b8,0x14bb48][kind]
  if kind==6:
   oracle.run(0x14a1b8,[address])
   if not oracle.run(0x149980,[address]):oracle.run(0x149bc0,[address])
   value=0
  else:
   value=oracle.run(entry,[address]);value=value if kind in [0,3,5] else -1
  for start,before in [(address,originalInputs[0]),(otherAddress,originalInputs[1])]:
   after=p.memory[start+0x2c4:start+0x2c4+0x744]
   for i,(old,new) in enumerate(zip(before,after)):
    clearedBuffer=kind==7 and start==address and (i in range(0x506,0x506+31*6,6) or i in range(0x688,0x688+32*6,6))
    if not clearedBuffer and not 0x2ac<=i<(0x428 if kind==6 else 0x3a8):assert old==new,(hex(entry),hex(i),old,new)
  #Compare all downstream-visible route writes, including both state request
  #channels, six motion words, all35 timers and the control-owner results.
  words=[p.read(address+off,4) for off in [0x18c]]+[signed(p.read(address+off,2),16) for off in [0x190,0x192]]
  words += [p.read(address+0x19c,4)]+[signed(p.read(address+off,2),16) for off in [0x1a0,0x1a2]]
  words += [p.read(address+0x244,4),p.read(address+0x248,4),p.read(body+0x38,4),p.read(body+0x104,4),p.read(address+0xb4,4),signed(p.read(address+0xa48,4),32)]
  words += list(struct.unpack_from('<6i',p.memory,body+0x4c))+list(struct.unpack_from('<35i',p.memory,address+0x1b0))+list(p.memory[address+0xf14:address+0xf22])
  words += [p.read(body+0x534,4),p.read(body+0x530,4),p.read(body+0x4c0,4),signed(p.read(body+0x4c4,4),32),p.read(body+0x504,4),p.read(address+0x254,1)]
  words += list(struct.unpack_from('<95I',p.memory,address+0x570))+list(struct.unpack_from('<31I',p.memory,otherAddress+0x570))
  if kind==7:
   words += [p.read(address+0x23c,4)]
   for start,count in [(0x502,31),(0x684,32)]:
    for slot in range(count):words += list(struct.unpack_from('<BBHB',p.memory,address+0x2c4+start+slot*6))
   words += list(p.memory[LATCHES:LATCHES+12])
  stream=p.read(p.read(0x5d1bf8,4)+8,4);end=p.read(stream,4);assert 0x1a00000<=end<=0x1a10000
  logs=bytes(p.memory[0x1a00000:end]);assert all(line in [b'DUMP:---------- !! MIKIRI !! -----------',b'DUMP:--------!!!!!TURN!!!!!--------'] for line in logs.splitlines()),logs
  if kind==6:value=logs.count(b'TURN!!!!!')
  append=['route',kind,*encode_actor(a),*encode_actor(b),*config,*otherConfig,*encode_input(inp),*encode_input(other),distance,len(objects),*[v for pair in objects for v in pair],owner,pressed,mask]
  if kind==7:append += [battleState]
  commands.append(' '.join(map(str,append)));expected.append([value,logs.count(b'MIKIRI'),*words]);outcomes[f'{"composed" if kind==6 else hex(entry)}:{value}']+=1
 #Character result rewrites ignore count; nonboolean publication is preserved
 #except the explicit character25 slot3->4 canonicalization.
 for character,flags,pattern in itertools.product(range(51),[0,0x1000,0x100000,0x101000],range(8)):
  a=actor();a.update(character=character,flags23c=flags);i=inputs();i['count']=-1 if pattern%2 else 0
  i['special']=[0 if (slot+pattern)%3==0 else 0x80000000 if pattern%2 else 1 for slot in range(32)];run(1,a,inp=i)
 #Alias fallback must increment timer23 even when no alias state may act.
 #The new timer value controls42-tick exit; request18c remains untouched.
 for character,table,timer,delta,pattern in itertools.product([0,1,45],[0,1,2],[-1,0,0x29ff,0x2a00,0x1733ff,0x173400,2147483647,-2147483648],[0,1,256,-1],range(12)):
  a=actor();a.update(character=character,state1a4=table,flags23c=[0x200000,0x201000,0x301000][pattern%3],timerDelta=delta,request=23);a['timers'][23]=timer
  i=inputs()
  if pattern<9:i['features'][[6,7,8,9,57,55,56,64,62][pattern]]=1
  if pattern==10:
   for index in [6,7,8,9,55,57]:i['features'][index]=0x80000000
  run(2,a,inp=i)
 #System cancel: two windows, third-window veto, input and AI bit consumption.
 #Separate owner snapshots catch accidental writes to the requesting actor.
 for case in range(4096):
  a=actor();b=actor();i=inputs();other=inputs();table=case%3;state=rng.choice([0,1,2,3,5,6,55,56,57,58,59,60,63])
  a.update(state194=state<<16|table,controlKind=case%3,controlMode=rng.choice([34,35,36]),controlFlags=rng.choice([0,0x4000,0x8000,0xc000,0xffffffff]),flags23c=rng.choice([0x1000,0x1010,0x201000]))
  a['state1a4']=rng.randrange(3);a['timers'][31:34]=[rng.choice([-1,0,1,255,256]) for _ in range(3)]
  for slot in range(24,31):i['normal'][slot]=rng.choice([0,0,1,0x80000000])
  b['state194']=rng.choice([0,56<<16,58<<16]);bad=custom.copy();bad[4]=17
  run(0,a,b,i,other,owner=case%2,pressed=rng.choice([0,1,16,0x80000000]),mask=rng.choice([1,16,0x80000000]),otherSystem=0 if case%5==0 else 6,otherD=bad if case%7==0 else custom)
 for system,byte in itertools.product(range(9),range(256)):
  a=actor();a['timers'][32]=1;i=inputs();i['normal'][24]=1;d=custom.copy();d[4]=byte
  run(0,a,inp=i,system=system,d=d)
 #Whole alternate dispatch and149bc0, including competing recognized inputs.
 for kind,case in itertools.product([3,4],range(6144)):
  a=actor();b=actor();i=inputs();other=inputs();table=case%3;state=rng.randrange(64)
  a.update(character=rng.randrange(51),state194=state<<16|table,state1a4=(rng.randrange(3)<<16)|rng.randrange(3),flags23c=rng.choice([0,0x1000,0x100000,0x200000,0x201000,0x300000,0x800000,0x801000,0x901000]),flags244=rng.choice([0,2,4,6,8,10,12,14,0x2000,0x4000]),flags248=rng.getrandbits(32),flags24c=rng.choice([0,2,4,6]),controlKind=case%3,controlMode=rng.choice([0,35,36,37]),controlFlags=0xc000,body38=rng.choice([0,0x80000]),body104=rng.choice([0,0x40000,0x80000,0xc0000]),body108=rng.choice([0,0x20,0x60]),request=0 if case%8 else 1,pendingFE=rng.choice([0,0x100]),x=rng.choice([160.5,160.75]))
  a['timers'][23]=rng.choice([0,0x2900,0x29ff,0x2a00]);a['timers'][31:34]=[rng.choice([0,0,256]) for _ in range(3)];a['bytes']=[case%256]*14
  b.update(character=rng.randrange(51),state194=(rng.randrange(96)<<16)|rng.randrange(3),flags23c=rng.choice([0x1000,0x1010]),x=rng.choice([160.5,160.75]),aux128=case%48,auxFlag134=case%2,action=rng.choice([0,189,537,599]))
  #System requests beat specials; specials beat ordinary attacks. Sparse
  #patterns also force the later routes to run instead of always winning early.
  if case%4==0:i['normal'][case%31]=1
  elif case%4==1:i['special'][case%32]=1
  elif case%4==2:
   i['normal']=[rng.choice([0,0,0,1]) for _ in range(31)];i['special']=[rng.choice([0,0,0,1]) for _ in range(32)]
  for index in [6,7,8,9,*range(49,66),91,92]:i['features'][index]=rng.choice([0,0,0,1])
  i['cancel']=[rng.choice([0,1,0x80000000]) for _ in range(32)];rng.shuffle(i['priority']);i['count']=rng.choice([-1,0,7,31,32]);objects=[] if case%3 else [(0,6),(47,2 if case%2 else 5)]
  d=descriptors[case%8].copy()
  if case%3==0:d[4]=18
  if case%5==0:d[14]=44
  run(kind,a,b,i,other,system=case%9,d=d,owner=case%2,pressed=16,distance=rng.choice([239,240,300]),objects=objects)
 #Forced KO/rage/weapon/auxiliary branches, including writes on false return.
 for character,flags,table,rage,variant in itertools.product([0,16,48],[0,0x10,0x80,0x90,0x1000,0x1080],range(3),[-1,0,1,2],range(4)):
  a=actor();a.update(character=character,flags23c=flags,state194=table,flags244=[0,2,0x200000,0x200002][variant],rageState=rage,flags248=variant&2)
  a['timers'][21]=variant%2;i=inputs();i['special'][15]=1
  run(5,a,inp=i,system=1 if variant%2 else 6)
 for character,state,amount,active,same in itertools.product([0,16],[0,9<<16|2,16<<16|2,54<<16,55<<16],[0,1,2,127,255],[0,1],[0,1]):
  a=actor();a.update(character=character,state194=state,auxFlag134=active,auxAction=605+amount if same else 0);a['bytes'][1]=amount;i=inputs();i['special'][15]=1
  run(5,a,inp=i)
 for system,byte in itertools.product(range(9),range(256)):
  a=actor();a['rageState']=1;d=custom.copy();d[8]=byte;run(5,a,system=system,d=d)
 #Actual post-recognition composition: unmodified original functions are
 #called in1494f0 order. This is not a claim of whole1494f0 or complete frames.
 for case,(character,system,variant) in enumerate(itertools.product(blocks,range(9),range(4))):
  a=actor();b=actor();i=inputs();i['count']=blocks[character][1]
  a.update(character=character,state194=[0,7<<16|1,3<<16|2,0][variant],flags23c=[0x1000,0x1010,0x1000,0x201000][variant],state1a4=0,flags244=0,flags248=0,rageState=variant%3,systemState=2,systemMeter=10240,fieldA30=1)
  a['timers'][4]=257;a['timers'][31]=256;a['bytes']=[1]*14
  i['normal']=[rng.choice([0,0,1]) for _ in range(31)];i['special']=[rng.choice([0,0,1]) for _ in range(32)]
  for index in [6,7,8,9,*range(49,66)]:i['features'][index]=rng.choice([0,0,1])
  d=descriptors[case%8].copy();d[4]=18;d[8]=32
  run(6,a,b,i,system=system,d=d,pressed=16)
 #The locked branch still permits custom descriptor13==42 restricted normal
 #selection, then character11 mode toggles consume latches/buffers only.
 for case in range(2048):
  a=actor();b=actor();i=inputs();a.update(character=11 if case%3 else 0,state194=(case%64)<<16,flags23c=0x1000|(0x400000 if case%2 else 0),flags244=2 if case%17==0 else 0,body38=0x80000 if case%2 else 0)
  a['request']=case%2;i['count']=[-1,0,32][case%3]
  i['normal']=[rng.choice([0,0,0,1]) for _ in range(31)];i['special'][9]=case%4;i['special'][21]=(case//4)%4
  for index in range(49,66):i['features'][index]=rng.choice([0,0,1])
  d=custom.copy();d[13]=[0,41,42,43][(case//5)%4]
  run(7,a,b,i,system=6 if case%5 else 0,d=d,battleState=[2,3,3,4][(case//7)%4])
 binary=ROOT/'work/ss6/build-native/ss6-input-permissions-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
 report=dict(status='passed_whole_input_request_routes',cases=len(expected),original_calls=oracle.calls,original_instructions=oracle.instructions,outcomes=outcomes,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  composed_permission_forced_request_cases=1728,
  scope='Whole14c0d0 including15ae30/15aee0/179020,14ce28,1ec4c8/209840,14ca28,149bc0 ordered request dispatch and149980 forced requests including1f7638/11d908 auxiliary queueing.1728 composed cases execute whole14a1b8 then149980 and,if allowed,149bc0 in original order,not whole1494f0.2048 whole14bb48 locked-input cases include restricted14bf30 and14bba8 latch/buffer consumption while preserving partial motions/results. Real pad words,mappings,control-owner lookup,descriptor pools,opponent object lists and buffered libc. Compare both state request channels,all motion/timer words,character/auxiliary writes and both input owners; other input bytes unchanged. Supplied recognized features/commands and actor snapshots; full sampling/state-entry and live battle pending. No skipped callees.')
 (ROOT/'outputs/ss6-feasibility/input_routes_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
