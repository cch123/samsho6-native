#!/usr/bin/env python3
"""Compare whole entry/cleanup helpers against unmodified source instructions.

The native codec supplies only field locations. Expected values are obtained
by executing the ELF; untouched actor/body bytes and entire pools are checked.
"""
import collections,hashlib,itertools,json,random,re,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout

ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/'work/ss6/build-native/ss6-state-transition-probe'
ASSETS=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
BASE=0x1c00000;BODY=0x1d00000;AUX=0x1d01000;LINK=0x1d02000;STACK=0x1d10000
TASKS=0x122f040;OBJECTS=0x456900
MASK=0xffffffff

def fnv(data):
 h=14695981039346656037
 for byte in data:h=((h^byte)*1099511628211)&0xffffffffffffffff
 return h
def object_pointer(handle):return OBJECTS+(handle-1)*320 if handle else 0
def object_handle(pointer):
 if not pointer:return 0
 assert OBJECTS<=pointer<OBJECTS+256*320 and (pointer-OBJECTS)%320==0,hex(pointer)
 return (pointer-OBJECTS)//320+1
def stack_pointer(handle):return STACK+(handle-1)*16 if handle else 0
def stack_handle(pointer):
 if not pointer:return 0
 assert STACK<=pointer<STACK+256*16 and (pointer-STACK)%16==0,hex(pointer)
 return (pointer-STACK)//16+1

def main():
 quick='--quick' in sys.argv
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x14a348)
 layout=[]
 for line in subprocess.check_output([str(BINARY),'--layout'],text=True).splitlines():
  area,off,size,name=line.split();layout.append((area,int(off),int(size),name))
 positions={(a,o):i for i,(a,o,_,_) in enumerate(layout)}
 assert len(positions)==len(layout)
 calls=collections.Counter();groups=collections.Counter();instructions=0;diagnostics=[];coverage=collections.Counter()
 commands=[];expected=[];labels=[];total=0
 class Trace:
  def __contains__(self,pc):
   if pc==0x1124b8:
    address=p.registers[4]&MASK
    if address and p.read(address,4)&4:diagnostics.append(stack_handle(address))
   return False
 def run(pc,args):
  nonlocal instructions
  #EE word arguments arrive sign-extended, including unsigned tag words
  #produced by SLL/ADDU. Zero-extending a high-bit fixture breaks LW equality.
  value,n=p.run(pc,[signed(v,32) for v in args],limit=250000,stop_before=Trace());instructions+=n;calls[hex(pc)]+=1;return value&MASK
 def append(command,want,label):
  commands.append(' '.join(map(str,command)));expected.append(want);labels.append(label)
 def flush(group):
  nonlocal total
  result=subprocess.run([str(BINARY),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
  assert result.returncode==0,(group,result.stderr,len(result.stdout.splitlines()))
  actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
  assert len(actual)==len(expected),(group,len(actual),len(expected))
  for case,(got,want) in enumerate(zip(actual,expected)):
   if got!=want:
    diff=[]
    for i,(x,y) in enumerate(zip(got,want)):
     if x!=y:diff.append((i,layout[i-3] if 3<=i<3+len(layout) and len(want)>20 else None,x,y))
    raise AssertionError((group,case,labels[case],len(got),len(want),diff[:20],commands[case][:250]))
  groups[group]+=len(expected);total+=len(expected);print(group,len(expected),'passed',flush=True)
  commands.clear();expected.clear();labels.clear()

 #Every descriptor is resolved through the original helper, not just a
 #second reader of the newly extracted files. Character51 is a null slot.
 for table in range(3):
  specs=([(0,0,i) for i in range(64)] if table==0 else
         [(c,v,i) for c in range(51) for v in range(4) for i in range(64)]+[(c,0,i) for c in range(51) for i in range(64,96)] if table==1 else
         [(0,0,i) for i in range(80)]+[(c,0,i) for c in range(51) for i in range(80,112)])
  if quick:specs=specs[:4]+specs[-4:]
  for c,v,i in specs:
   pc,args=[(0x172d18,[i]),(0x172e08,[c,v,i]),(0x173078,[c,i])][table]
   address=run(pc,args);want=list(p.memory[address:address+(14 if table==2 else 5)])
   append([0,table,i,c,v],want,(table,c,v,i))
 flush('descriptors')
 for c,i in itertools.product(range(2 if quick else 51),range(96)):
  p.write(BASE+0xa10,c,4);value=run(0x14bb08,[BASE,1,i]);append([1,1,i,c,0],[value],(c,i))
 flush('attack_windows')

 def fixture(case,character=None):
  values=[rng.getrandbits(size*8) for _,_,size,_ in layout]
  def setv(area,offset,value):values[positions[area,offset]]=value&((1<<(8*layout[positions[area,offset]][2]))-1)
  for off,v in [(0xa10,case%51 if character is None else character),(0xa18,(case*7)%51),
                (0x194,0),(0x1a4,0),(0x190,0xffff),(0x192,0xffff),(0x18c,0),
                (0x1a0,0xffff),(0x1a2,0xffff),(0x19c,0),(0x1ac,256),
                (0x2b4,7 if case%3 else 0),(0x27c,case%2),
                (0x120,[-1,0,1,2,3,4,2147483647,-2147483648][case%8])]:setv('a',off,v)
  setv('b',0x44,struct.unpack('<I',struct.pack('<f',[-0.0,-32.0,0.0,16.5][case%4]))[0])
  for off in range(0x4c,0x64,4):setv('b',off,rng.choice([-65536,-256,-1,0,1,256,65536]))
  setv('x',0x24,776 if case%2 else 777)
  descriptor=[rng.randrange(64) for _ in range(16)];descriptor[2]=9 if case%2 else 0
  return dict(values=values,player=case%2,system=case%9,d=descriptor,opponent=rng.getrandbits(32),linked=rng.getrandbits(32),marker=rng.getrandbits(32))

 def pools(case,player,tag=None,active=True):
  tags=[((6*4+player)<<16)+0x1b5b,((5*4+player)<<16)+0x1b5b,((6*4+(1-player))<<16)+0x1b5b]
  if tag is not None:tags=[tag,tag^0x10000,tag^1]
  tasks={};objects={};stacks={}
  if active:
   for n,slot in enumerate([0,1,17,127,254,255]):
    task=[rng.getrandbits(32) for _ in range(13)];task[5]=tags[[0,1,0,2,1,0][n]]
    task[6]=[1,2,1,3,0,4][n];tasks[slot]=task
    obj=[rng.getrandbits(32) for _ in range(80)];obj[79]=tags[[0,1,0,2,1,0][n]];obj[78]=[0,13,34,51,75,91][n];objects[slot]=obj
   stacks={1:[4,rng.getrandbits(32)],2:[0,rng.getrandbits(32)],3:[7,rng.getrandbits(32)],4:[0xffffffff,rng.getrandbits(32)]}
  return dict(tasks=tasks,objects=objects,stacks=stacks,freed=[0,7,0xffffffff][case%3],head=[0,100,200][case%3],count=[0,19,0xfffffffe][case%3])

 def check(op,index,case,table=0,f=None,pool=None,label=None):
  if f is None:f=fixture(case)
  if pool is None:pool=pools(case,f['player'],active=op in [4,5,9] and case%4==0)
  actor=BASE+f['player']*0xf2c;other=BASE+(1-f['player'])*0xf2c
  areas={'a':(actor,0xf2c),'b':(BODY,0x140),'x':(AUX,0x140)}
  p.memory[BASE:BASE+2*0xf2c]=bytes([0xa5])*(2*0xf2c)
  p.memory[BODY:BODY+0x3000]=bytes([0x5a])*0x3000
  for area,(address,length) in areas.items():p.memory[address:address+length]=bytes([0xa5 if area=='a' else 0x5a])*length
  for (area,off,size,_),value in zip(layout,f['values']):
   if area=='a' and off==0x2b4:value=LINK if value else 0
   p.write(areas[area][0]+off,value,size)
  p.write(actor,BODY,4);p.write(actor+4,AUX,4);p.write(actor+0xa24,f['player'],4)
  p.write(other+0xb8,f['opponent'],4);p.write(LINK+0x108,f['linked'],4);p.write(0x4d3d08,BASE,4)
  p.write(0x12d2300,f['marker'],4)
  p.memory[actor+0x10c:actor+0x120]=struct.pack('<5I',f['system'],f['player'],f['values'][positions['a',0xa10]],0,0)
  p.write(0x4c38a8,6,4);p.memory[0x12d2308+f['player']*128:0x12d2308+f['player']*128+16]=bytes(f['d'])
  p.memory[TASKS:TASKS+256*52]=bytes(256*52);p.memory[OBJECTS:OBJECTS+256*320]=bytes(256*320)
  for slot,row in pool['tasks'].items():
   data=row.copy();data[6]=stack_pointer(data[6]);p.memory[TASKS+slot*52:TASKS+(slot+1)*52]=struct.pack('<13I',*data)
  for slot,row in pool['objects'].items():
   data=row.copy();data[78]=object_pointer(data[78]);p.memory[OBJECTS+slot*320:OBJECTS+(slot+1)*320]=struct.pack('<80I',*data)
  for handle,header in pool['stacks'].items():
   address=stack_pointer(handle);p.memory[address:address+8]=struct.pack('<2I',*header)
  p.write(0x3d3690,pool['freed'],4);p.write(0x46a900,object_pointer(pool['head']),4);p.write(0x46a904,pool['count'],4)
  buffered_stdout(p);p.memory[0x1a00000:0x1a10000]=bytes(65536)
  p.memory[0x3d2e88:0x3d2e88+12]=b'entry-test\0\0'
  before={area:bytes(p.memory[address:address+size]) for area,(address,size) in areas.items()}
  other_before=bytes(p.memory[other:other+0xf2c]);linked_before=bytes(p.memory[LINK:LINK+0x140])
  diagnostics.clear()
  pc,args={2:(0x16a8f8,[actor,index]),3:(0x151298,[actor+0x15c,index,f['player']]),
           4:(0x14a348,[actor,table,index]),5:(0x1491e0,[actor]),
           6:(0x112a70,[index]),7:(0x11e3a0,[index]),8:(0x124d18,[index,f['player']]),
           9:(0x14cbc8,[actor]),10:(0x14b798,[actor])}[op]
  run(pc,args)
  want=[p.read(other+0xb8,4),p.read(LINK+0x108,4),p.read(0x12d2300,4)]
  covered={area:set() for area in areas}
  for area,off,size,_ in layout:
   value=p.read(areas[area][0]+off,size)
   if area=='a' and off==0x2b4:
    assert value in [0,LINK];value=7 if value else 0
   want.append(value);covered[area].update(range(off,off+size))
  for area,(address,length) in areas.items():
   for off,(old,new) in enumerate(zip(before[area],p.memory[address:address+length])):
    assert old==new or off in covered[area],(op,index,case,'unrepresented write',area,hex(off),old,new)
  for off,(old,new) in enumerate(zip(other_before,p.memory[other:other+0xf2c])):assert old==new or 0xb8<=off<0xbc,(op,case,'opponent',hex(off))
  for off,(old,new) in enumerate(zip(linked_before,p.memory[LINK:LINK+0x140])):assert old==new or 0x108<=off<0x10c,(op,case,'linked',hex(off))
  native_tasks=bytearray(p.memory[TASKS:TASKS+256*52]);native_objects=bytearray(p.memory[OBJECTS:OBJECTS+256*320])
  for slot in range(256):
   struct.pack_into('<I',native_tasks,slot*52+24,stack_handle(p.read(TASKS+slot*52+24,4)))
   struct.pack_into('<I',native_objects,slot*320+312,object_handle(p.read(OBJECTS+slot*320+312,4)))
  want += [p.read(0x3d3690,4),object_handle(p.read(0x46a900,4)),p.read(0x46a904,4),fnv(native_tasks),fnv(native_objects)]
  for handle in sorted(pool['stacks']):want += [handle,p.read(stack_pointer(handle),4),p.read(stack_pointer(handle)+4,4)]
  want += [len(diagnostics),*diagnostics]
  log=bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0]
  assert b'ASSERT' not in log,log
  #The real printf formatter runs, with an ordinary buffered FILE fixture.
  logged=[stack_handle(int(v,16)) for v in re.findall(rb'handleFree:alloc:([0-9a-fA-F]+)',log)]
  if diagnostics:assert logged==diagnostics,(log,logged,diagnostics)
  encoded=[op,table,index,0,0,f['player'],f['opponent'],f['linked'],f['marker'],f['system'],*f['d'],*f['values'],pool['freed'],pool['head'],pool['count']]
  for name in ['tasks','objects']:
   encoded += [len(pool[name])]
   for slot,row in sorted(pool[name].items()):encoded += [slot,*row]
  encoded += [len(pool['stacks'])]
  for handle,row in sorted(pool['stacks'].items()):encoded += [handle,*row]
  append(encoded,want,label or (op,table,index,case));coverage[f'op:{op}']+=1
  coverage['stack_diagnostics']+=len(diagnostics)

 for case,index in enumerate([*range(31),31,255,0xffffffff]*(1 if quick else 4)):check(2,index,case)
 flush('poses')
 for case,(index,velocity) in enumerate(itertools.product(range(4 if quick else 69),[-65536,-1,0,1,65536])):
  f=fixture(case);f['values'][positions['b',0x50]]=velocity&MASK;check(3,index,case,f=f)
 flush('conditions')
 tags=[0,1,0x1b5b,0xffff,0x10000,0x191b5b,0x7fffffff,0x80000000,0xffff1b5b,0xffffffff]
 for op,case in itertools.product([6,7,8],range(4 if quick else 40)):
  f=fixture(case);index=[0,5,6,16383][case%4] if op==8 else tags[case%len(tags)]
  tag=((index*4+f['player'])<<16)+0x1b5b if op==8 else index
  check(op,index,case,f=f,pool=pools(case,f['player'],tag=tag))
 flush('tagged_cleanup')

 def set_field(f,area,off,value):f['values'][positions[area,off]]=value&((1<<(8*layout[positions[area,off]][2]))-1)
 specs=[(0,i) for i in range(64)]+[(1,i) for i in range(96)]+[(2,i) for i in range(112)]+[(3,0),(3,53)]
 for case,(table,index) in enumerate(specs*(1 if quick else 3)):
  if quick and case not in [0,4,23,56,64,85,128,159,160,240,271,272]:continue
  f=fixture(case)
  check(4,index,case,table=table,f=f)
  if (case+1)%274==0:flush('whole_entry')
 if commands:flush('whole_entry')
 for case in range(16 if quick else 512):
  f=fixture(case);table,index=specs[(case*79)%len(specs)]
  oldtable=case%3;oldindex=[0,1,5,6,7,9,17,32,57,58,63][case%11]
  set_field(f,'a',0x194,oldindex<<16|oldtable)
  set_field(f,'a',0x1a4,(case%8)<<16|((case//2)%3))
  set_field(f,'a',0x23c,[0,0x1000,0x200000,0x801000,0xa00000,0xffffffff][case%6])
  set_field(f,'a',0x18c,(case//2)%2)
  if case%8==0:table,index=oldtable,oldindex
  set_field(f,'a',0x190,table if case%13 else 0xffff);set_field(f,'a',0x192,index if case%17 else 0xffff)
  check(5,0,case,f=f,label=('transition',case,oldtable,oldindex,table,index))
 flush('whole_transition')
 for case in range(16 if quick else 576):
  f=fixture(case,character=[0,24,45,48][case%4]);table=(case//4)%4;index=(case//16)%4
  set_field(f,'a',0x23c,[0x200000,0x201000,0xa00000,0,0xffffffff][case%5])
  set_field(f,'a',0x1a4,((index if case%7==0 else (index+1)%4)<<16)|table)
  set_field(f,'a',0x1a0,table if case%13 else 0xffff);set_field(f,'a',0x1a2,index if case%17 else 0xffff)
  set_field(f,'a',0x19c,case%3)
  check(9,0,case,f=f,label=('alias',case,table,index))
 flush('whole_alias_transition')
 for case in range(16 if quick else 768):
  f=fixture(case,character=[0,11,24,45,48,50][case%6]);table,index=specs[(case*47)%len(specs)]
  set_field(f,'a',0x194,index<<16|table);set_field(f,'a',0x1a4,(case%4)<<16|table)
  set_field(f,'a',0x23c,[0,0x1000,0x200000,0x201000][(case//6)%4]);set_field(f,'a',0x244,0x4000 if case%2 else 0)
  check(10,0,case,f=f,label=('metadata',case,table,index))
 flush('whole_metadata')
 report=dict(status='passed_whole_state_transition',cases=total,groups=groups,coverage=coverage,original_calls=calls,original_instructions=instructions,
             elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
             scope='Whole172d18/172e08/173078 descriptor resolution,14bb08 attack windows,16a8f8 poses,151298 conditions,112a70/11e3a0/124d18 pool cancellation,14a348 entry,1491e0 main transitions,14cbc8 alias transitions and14b798 metadata. Original callees execute unchanged; no skipped calls or early stops. Both actor channels,35 timers,body/auxiliary fields,input features/results/progress,linked object,opponent flags,1488e0 marker and full256-slot task/object pools compared; opaque handles normalize addresses. Unrepresented actor/body/auxiliary bytes checked for preservation. Real libc logging uses initialized buffered FILE; diagnostic order compared. Integer/exact finite fixtures only; not full149d08 callbacks,complete actor frames or newly playable moves.')
 if not quick:(ROOT/'outputs/ss6-feasibility/state_transition_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
