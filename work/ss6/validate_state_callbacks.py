#!/usr/bin/env python3
"""Whole normal/attack registration and rage gain, without executing handlers."""
import collections,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout

ROOT=Path(__file__).resolve().parents[2];BINARY=ROOT/'work/ss6/build-native/ss6-state-callbacks-probe'
ACTOR=0x1c00000;BODY=0x1c02000;BATTLE=0x1c04000;TASKS=0x1d00000;OBJECTS=0x1d10000
MASK=0xffffffff

def main():
 quick='--quick' in sys.argv;raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x172eb0);layout=[]
 for line in subprocess.check_output([str(BINARY),'--layout'],text=True).splitlines():
  off,size,name=line.split();layout.append((int(off),int(size),name))
 positions={off:i for i,(off,_,_) in enumerate(layout)};covered=set()
 for off,size,_ in layout:covered.update(range(off,off+size))
 calls=collections.Counter();groups=collections.Counter();coverage=collections.Counter();handlers=collections.Counter()
 commands=[];expected=[];labels=[];instructions=0;total=0
 class Trace:
  def __init__(self):self.fp=False;self.rage=False
  def __contains__(self,pc):
   if pc==0x14efb8:self.rage=True
   if pc==0x14f040:self.fp=True
   return False
 def run(pc,args,trace):
  nonlocal instructions
  result,n=p.run(pc,[signed(v,32) for v in args],limit=10000,stop_before=trace)
  instructions+=n;calls[hex(pc)]+=1;return result&MASK
 def fixture(case,character=0,index=0,variant=0):
  values=[rng.getrandbits(size*8) for _,size,_ in layout]
  def setv(off,value):values[positions[off]]=value&((1<<(8*layout[positions[off]][1]))-1)
  for off,v in [(0xa10,character),(0xa18,character),(0x194,index<<16|1),(0x1a4,0),
                (0x198,variant),(0x1a8,variant),(0x23c,rng.getrandbits(32)&~0x200000),
                (0x120,[0,0,0,1,2,3,-1][case%7]),(0x124,[0,1,0xb700,0xb7ff,0xb800,0x7fffffff,0xffffffff][(case//7)%7])]:setv(off,v)
  slots=[0]*48;objects={}
  if case%5:
   for handle in range(1,7):objects[handle]=[[3,3,2,-1,3,5][handle-1],rng.getrandbits(32)]
   for slot,handle in zip([0,2,7,12,30,47],[4,5,3,1,6,5]):slots[slot]=handle
   if case%5==2:slots[0]=2 #A different first match; repeated handle5 remains live.
   if case%5==3:
    for obj in objects.values():obj[0]=2 #No matching object, despite live registrations.
  descriptor=[rng.randrange(64) for _ in range(16)];descriptor[0]=[0,2,3,4][case%4];descriptor[2]=[0,7,8,9][(case//4)%4]
  return dict(values=values,player=case%2,system=case%9,meterCharacter=(character+case)%51,d=descriptor,
              amount=0,marker=rng.getrandbits(32),slots=slots,objects=objects)
 def setv(f,off,value):f['values'][positions[off]]=value&((1<<(8*layout[positions[off]][1]))-1)
 def check(op,f,label):
  p.memory[ACTOR:ACTOR+0xf2c]=bytes([0xa5])*0xf2c;p.memory[BODY:BODY+0x140]=bytes([0x5a])*0x140
  p.memory[BATTLE:BATTLE+0x600]=bytes([0x69])*0x600
  for (off,size,_),v in zip(layout,f['values']):p.write(ACTOR+off,v,size)
  p.write(ACTOR,BODY,4);p.write(ACTOR+0xa24,f['player'],4);p.write(0x4d3d00,BATTLE,4)
  p.write(0x4d3d08,ACTOR-f['player']*0xf2c,4)
  p.memory[ACTOR+0x10c:ACTOR+0x120]=struct.pack('<5I',f['system'],f['player'],f['meterCharacter'],0,0)
  p.write(0x4c38a8,6,4);p.memory[0x12d2308+f['player']*128:0x12d2308+f['player']*128+16]=bytes(f['d'])
  p.write(0x12d2300,f['marker'],4)
  table=BATTLE+0x29c+f['player']*0x108
  for i,handle in enumerate(f['slots']):p.write(table+i*4,TASKS+handle*52 if handle else 0,4)
  for handle,(kind,d4) in f['objects'].items():
   p.memory[TASKS+handle*52:TASKS+(handle+1)*52]=bytes([0x3c])*52;p.write(TASKS+handle*52+0x1c,OBJECTS+handle*320,4)
   p.memory[OBJECTS+handle*320:OBJECTS+(handle+1)*320]=bytes([0x7e])*320
   p.write(OBJECTS+handle*320+0xcc,kind,4);p.write(OBJECTS+handle*320+0xd4,d4,4)
  if op==5:
   flags,phases,scale,seed=f['effects']
   for i in range(2):p.write(0x46a918+i*4,flags[i],4);p.write(0x46a910+i*4,phases[i],4)
   p.write(0x1239d84,scale,4)
   p.memory[0x3ebf30:0x3ec730]=struct.pack('<1024H',*[(seed+i*137)&65535 for i in range(1024)])
  before=bytes(p.memory[ACTOR:ACTOR+0xf2c]);body=bytes(p.memory[BODY:BODY+0x140]);battle=bytes(p.memory[BATTLE:BATTLE+0x600])
  object_before={h:bytes(p.memory[OBJECTS+h*320:OBJECTS+(h+1)*320]) for h in f['objects']}
  task_before={h:bytes(p.memory[TASKS+h*52:TASKS+(h+1)*52]) for h in f['objects']}
  buffered_stdout(p);p.memory[0x1a00000:0x1a10000]=bytes(65536)
  p.finite_model=op in [1,3,4];trace=Trace()
  if op==4:run(0x14b798,[ACTOR],trace)
  pc,args={0:(0x172d68,[ACTOR]),1:(0x172eb0,[ACTOR]),2:(0x14cc10,[ACTOR]),3:(0x14efb8,[ACTOR+0x10c,f['amount']]),4:(0x172eb0,[ACTOR]),
           5:(0x11e548,[f['player']]),6:(0x1732b0,[ACTOR,f['meterCharacter'],f['amount']]),7:(0x14eb78,[ACTOR+0x10c])}[op]
  original_result=run(pc,args,trace)
  result=original_result if op in [0,1,4,6] else int(original_result!=0) if op==7 else 0
  if op==7:assert original_result in [0,ACTOR+0x13c]
  coverage['finite_arithmetic_reached' if trace.fp else 'integer_only']+=1
  if trace.rage:coverage['rage_helper_reached']+=1
  if op in [0,1,4]:handlers[hex(result)]+=1
  want=[result,p.read(0x12d2300,4),*[p.read(ACTOR+off,size) for off,size,_ in layout]]
  for i in range(48):
   address=p.read(table+i*4,4);assert address==0 or (address-TASKS)%52==0
   want.append((address-TASKS)//52 if address else 0)
  for handle in sorted(f['objects']):want += [handle,p.read(OBJECTS+handle*320+0xcc,4),p.read(OBJECTS+handle*320+0xd4,4)]
  if op==5:want += [*[p.read(0x46a918+i*4,4) for i in range(2)],*[p.read(0x46a910+i*4,4) for i in range(2)],p.read(0x1239d84,4),*struct.unpack_from('<1024H',p.memory,0x3ebf30)]
  for off,(old,new) in enumerate(zip(before,p.memory[ACTOR:ACTOR+0xf2c])):assert old==new or off in covered,(label,'unrepresented actor write',hex(off))
  assert body==p.memory[BODY:BODY+0x140] and battle==p.memory[BATTLE:BATTLE+0x600],label
  for h,old in object_before.items():
   for off,(a,b) in enumerate(zip(old,p.memory[OBJECTS+h*320:OBJECTS+(h+1)*320])):assert a==b or 0xd4<=off<0xd8,(label,'object',h,hex(off))
  for h,old in task_before.items():assert old==p.memory[TASKS+h*52:TASKS+(h+1)*52],(label,'task',h)
  log=bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0];assert not log,(label,log)
  encoded=[op,f['player'],f['system'],f['meterCharacter'],*f['d'],f['amount']&MASK,f['marker'],*f['values'],*f['slots'],len(f['objects'])]
  for handle,obj in sorted(f['objects'].items()):encoded += [handle,*[v&MASK for v in obj]]
  if op==5:encoded += [*f['effects'][0],*f['effects'][1],f['effects'][2],f['effects'][3]]
  commands.append(' '.join(map(str,encoded)));expected.append(want);labels.append(label)
 def flush(group):
  nonlocal total
  result=subprocess.run([str(BINARY),str(ROOT/'work/ss6/extracted/resources')]+(['--task-pools'] if '--task-pools' in sys.argv else []),input='\n'.join(commands)+'\n',text=True,capture_output=True)
  assert result.returncode==0,(group,result.stderr,len(result.stdout.splitlines()))
  actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
  for n,(got,want) in enumerate(zip(actual,expected)):
   assert got==want,(group,labels[n],[(i,layout[i-2] if 2<=i<2+len(layout) else None,a,b) for i,(a,b) in enumerate(zip(got,want)) if a!=b][:12],commands[n][:300])
  total+=len(expected);groups[group]+=len(expected);print(group,len(expected),'passed',flush=True)
  commands.clear();expected.clear();labels.clear()

 for case,(index,alias) in enumerate(itertools.product(range(4 if quick else 64),range(2))):
  f=fixture(case,index=index);setv(f,0x194,index<<16);setv(f,0x1a4,index<<16);setv(f,0x23c,0x200000 if alias else 0)
  check(0,f,('normal',index,alias))
 flush('normal_registration')
 for case in range(8 if quick else 612):
  f=fixture(case,character=case%51);setv(f,0x23c,[0,0x200000,0xffffffff][(case//51)%3]);check(2,f,('alias',case))
 flush('alias_registration')
 gains=[-2147483648,-1,0,1,2,184,255,0x800000,2147483647]
 for case,(character,system,boundary) in enumerate(itertools.product(range(2 if quick else 51),range(9),range(2 if quick else 16))):
  f=fixture(case,character=character);f.update(system=system,meterCharacter=character,amount=gains[boundary%len(gains)])
  setv(f,0x120,[0,0,0,0,0,0,0,1,2,-1,0,0,0,0,0,0][boundary]);setv(f,0x124,[-1,0,1,0xb6ff,0xb700,0xb7ff,0xb800,0xb801,2147483647,-2147483648,0xb800-256,0xb800-257,0xb800-255,0,0,1][boundary])
  check(3,f,('rage',character,system,boundary))
 flush('rage_gain')
 for case,(amount,gain) in enumerate(itertools.product([-2147483648,-1,0,0xb7ff,0xb800,2147483647],gains)):
  f=fixture(case,character=case%51);f['amount']=gain;setv(f,0x120,0);setv(f,0x124,amount)
  check(3,f,('rage_wrap',amount,gain))
 flush('rage_wrap')
 for case,(character,variant,index) in enumerate(itertools.product(range(2 if quick else 51),range(4),range(96))):
  f=fixture(case,character,index,variant);check(1,f,('attack',character,variant,index))
  if (case+1)%2048==0:flush('attack_registration')
 if commands:flush('attack_registration')
 configurations=[(s,[0]*16) for s in range(9) if s!=6]
 for first,second in itertools.product([0,2,3,4],[0,7,8,9]):
  d=[0]*16;d[0]=first;d[2]=second;configurations.append((6,d))
 case=0
 for character in ([0] if quick else [0,1,11,24,32,45,48,50]):
  categories=p.memory[0x4e5c50+character*5:0x4e5c50+character*5+5]
  indices=sorted({64,65,95,*[64+s for s in categories if s<32]})
  for index,(system,d) in itertools.product(indices,configurations):
   f=fixture(case,character,index);f.update(system=system,d=d.copy());setv(f,0x120,0);setv(f,0x124,0xb7ff)
   check(1,f,('system_gates',character,index,system,d[0],d[2]));case+=1
 flush('system_gates')
 for case in range(16 if quick else 1536):
  character=[0,1,11,24,32,45,48,50][(case//4)%8];index=(case//32)%96;f=fixture(case,character,index)
  f.update(system=(case//16)%9);setv(f,0x23c,[0,0x1000,0x200000,0x201000][case%4]);setv(f,0x244,0x4000 if (case//4)%2 else 0)
  setv(f,0x1a4,((case//8)%4)<<16|1);setv(f,0x1a8,(case//32)%4)
  check(4,f,('metadata_attack',case,character,index))
 flush('metadata_then_attack')
 case=0
 for character,enabled,source,index in itertools.product([0,32,33,34,48],[0,1],[0,12,13,35,50],[-2147483648,-2,-1,*range(112),2147483647]):
  if quick and case%211:case+=1;continue
  f=fixture(case,character);f.update(meterCharacter=source,amount=index);setv(f,0x244,0xffffffff if enabled else 0xffdfffff)
  check(6,f,('drop_predicate',character,enabled,source,index));case+=1
  if len(commands)>=2048:flush('damage_weapon_decision')
 if commands:flush('damage_weapon_decision')
 configurations=[(s,[0]*16) for s in range(9) if s!=6]
 for third,fifth in itertools.product([0,13,14,15],[0,23,24,25,26]):
  d=[0]*16;d[3]=third;d[5]=fifth;configurations.append((6,d))
 for case,((system,d),player,own,other) in enumerate(itertools.product(configurations,range(2),range(2),range(2))):
  f=fixture(case);f.update(system=system,d=d.copy(),player=player);check(7,f,('effect_available',system,d[3],d[5]))
  #11e548's caller has already obtained a non-null14eb78 mode state.
  #Testing the invalid null dereference would not describe a game state.
  if system==4 or (system==6 and (d[3]==14 or d[5] in [24,25])):
   flags=[rng.getrandbits(32)&~1,rng.getrandbits(32)&~1];flags[player]|=own;flags[1-player]|=other
   f['effects']=(flags,[rng.getrandbits(32),rng.getrandbits(32)],rng.getrandbits(32),rng.randrange(65536))
   check(5,f,('effect_exit',case,system,player,own,other))
 flush('system_effect_exit')
 report=dict(status='passed_callback_registration_and_rage_gain',cases=total,groups=groups,coverage=coverage,
             original_calls=calls,original_instructions=instructions,handlers=handlers,elf_sha256=SOURCE_HASH,
             native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
             scope='Whole172d68 normal registration,14cc10 alternate handler registration,172eb0 attack registration,14efb8 rage gain,1732b0 damage weapon-drop predicate,14eb78 mode availability and11e548 system-effect exit;1536 composed14b798->172eb0 fixtures in the full suite. Original callees execute unchanged with no skipped calls or early stops. All51 character descriptors,4 variants,96 attack indices;9 systems,selected custom descriptors,integer wrap/threshold edges,ordered48-slot object registrations with holes/shared identities. Compare callback words,flags,gauges,metadata,objectD4,system-effect globals/1024 halfword flags and preserved unrepresented actor/body/battle/task/object bytes. Float cases explicitly use finite ScalarFloat model,not EE hardware proof. Handler identities are registered but their move bodies are NOT executed. Actual weapon-object creation,full173108 damage registration,14aec8 and149d08 remain pending; no new playable moves.')
 report['native_object_storage']='task_registry_and_shared_pool' if '--task-pools' in sys.argv else 'explicit_object_identity_map'
 if not quick:(ROOT/'outputs/ss6-feasibility'/('state_callbacks_task_pools_validation.json' if '--task-pools' in sys.argv else 'state_callbacks_validation.json')).write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
