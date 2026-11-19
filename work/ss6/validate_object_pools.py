#!/usr/bin/env python3
"""Native allocation/order compared with whole unmodified original helpers."""
import collections,hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/'work/ss6/build-native/ss6-object-pool-probe'
TASKS=0x122f040;OBJECTS=0x456900;REGISTRY=0x1b00000
def pointer(handle,base,stride):return base+(handle-1)*stride if handle else 0
def handle(address,base,stride):
 if not address:return 0
 assert base<=address<base+256*stride and (address-base)%stride==0,hex(address)
 return (address-base)//stride+1
def digest(rows):
 h=14695981039346656037
 for v in rows:
  #One full-word hash still observes every payload bit and record position.
  h=((h^v)*1099511628211)&0xffffffffffffffff
 return h

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x1471a8);commands=[];expected=[];labels=[];groups=collections.Counter();instructions=0
 tp=lambda h:pointer(h,TASKS,52);op=lambda h:pointer(h,OBJECTS,320)
 th=lambda a:handle(a,TASKS,52);oh=lambda a:handle(a,OBJECTS,320)
 guards=[(TASKS-16,16),(TASKS+256*52,16),(OBJECTS-16,16),(OBJECTS+256*320+8,16),(REGISTRY-16,16),(REGISTRY+192,16)]
 def setup(task_head=0,object_head=0,count=0,registry=None,dense=False):
  tasks={};objects={}
  for i in range(256) if dense else [0,1,17,127,254,255]:
   t=[rng.getrandbits(32) for _ in range(13)];t[3]=rng.randrange(257);t[7]=rng.randrange(257);tasks[i]=t
   o=[rng.getrandbits(32) for _ in range(80)];o[78]=rng.randrange(257);objects[i]=o
  reg=registry if registry is not None else [0]*48
  data=['P',task_head,object_head,count,len(tasks)]
  p.memory[TASKS:TASKS+256*52]=bytes(256*52);p.memory[OBJECTS:OBJECTS+256*320]=bytes(256*320)
  for i,row in tasks.items():
   data.extend([i,*row]);mapped=row.copy();mapped[3]=tp(mapped[3]);mapped[7]=op(mapped[7])
   p.memory[TASKS+i*52:TASKS+(i+1)*52]=struct.pack('<13I',*mapped)
  data.append(len(objects))
  for i,row in objects.items():
   data.extend([i,*row]);mapped=row.copy();mapped[78]=op(mapped[78]);p.memory[OBJECTS+i*320:OBJECTS+(i+1)*320]=struct.pack('<80I',*mapped)
  data.extend(reg);commands.append(' '.join(map(str,data)))
  p.write(0x1232844,tp(task_head),4);p.write(0x46a900,op(object_head),4);p.write(0x46a904,count,4)
  p.memory[REGISTRY:REGISTRY+192]=struct.pack('<48I',*[tp(v) for v in reg])
  for address,size in guards:p.memory[address:address+size]=bytes([0xa5])*size
 def snapshot(result):
  tasks=list(struct.unpack('<3328I',p.memory[TASKS:TASKS+256*52]));objects=list(struct.unpack('<20480I',p.memory[OBJECTS:OBJECTS+256*320]))
  for i in range(256):tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+7]=oh(tasks[i*13+7]);objects[i*80+78]=oh(objects[i*80+78])
  return [result,th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),digest(tasks),digest(objects),*[th(p.read(REGISTRY+i*4,4)) for i in range(48)]]
 def run(code,*args,group='helpers'):
  nonlocal instructions
  pc={'t':0x112570,'p':0x1125e0,'a':0x112608,'c':0x112670,'b':0x1129c8,
      'o':0x11e290,'j':0x11e2e8,'f':0x11e350,'s':0x11d528,'g':0x1471a8,'x':0x11e3a0}[code]
  original=list(args)
  if code=='b':original[1]=op(original[1])
  if code in ['f','s']:original[0]=op(original[0])
  if code=='g':original.insert(0,REGISTRY)
  result,n=p.run(pc,[signed(v&0xffffffff,32) for v in original],limit=20000);instructions+=n
  value=th(result&0xffffffff) if code in ['p','a','c','b','g'] else oh(result&0xffffffff) if code=='j' else 0
  commands.append(' '.join(map(str,[code,*[v&0xffffffff for v in args]])));expected.append(snapshot(value));labels.append((group,code,args));groups[group]+=1
  for address,size in guards:assert p.memory[address:address+size]==bytes([0xa5])*size,(code,hex(address))
  return value
 #Initializer differences and destructive reinitialization with nonzero data.
 for i in range(12):
  setup(i,256-i,rng.getrandbits(32),dense=True);run('t',group='initializers');run('o',group='initializers')
  run('s',1+i,group='reset_payload');run('o',group='initializers');run('t',group='initializers')
 #All slots, then exhaustion: low-level allocation returns null and preserves
 #all records. The popped-only helper must not clear the record it returns.
 for kind in ['p','a','c','b']:
  setup(dense=True);run('t',group='task_capacity')
  for i in range(258):
   args={'p':[],'a':[rng.getrandbits(32),rng.getrandbits(32)],
         'c':[i%256,rng.getrandbits(32),rng.getrandbits(32),rng.getrandbits(32)],
         'b':[rng.getrandbits(32),i%257]}[kind]
   run(kind,*args,group='task_capacity')
 setup(dense=True);run('o',group='object_capacity');allocated=[]
 for i in range(258):
  h=run('j',rng.getrandbits(32),group='object_capacity')
  if h:allocated.append(h)
 rng.shuffle(allocated)
 for h in allocated:run('f',h,group='object_recycle')
 for i in range(256):run('j',i,group='object_recycle')
 #1471a8 scans the caller's prefix; holes/duplicates survive except the first
 #empty slot. A full prefix returns null without looking at pool capacity.
 for count in [0,1,3,48]:
  for hole in range(count+1):
   reg=[(i%7)+1 for i in range(48)]
   if hole<count:reg[hole]=0
   if hole+2<count:reg[hole+2]=0
   setup(registry=reg);run('t',group='registration_setup');run('o',group='registration_setup')
   run('g',count,rng.getrandbits(32),0 if hole%2 else 0x1701c0,group='registration')
   run('g',count,rng.getrandbits(32),0,group='registration')
 for count in [0,1,48]:
  setup(registry=[1]*48);run('g',count,0x1390,0,group='full_registration_empty_pools')
 #Composition with previously ported tag cleanup and wraparound counters.
 for count in [0,0xffffffff,1,256]:
  setup(object_head=256,count=count);run('j',0x12341b5b,group='counter_wrap');run('f',256,group='counter_wrap')
 setup();run('t',group='mixed_lifecycle');run('o',group='mixed_lifecycle')
 for i in range(48):run('g',48,0x1390+i%3,0 if i%2 else 0x1701c0,group='mixed_lifecycle')
 for tag in [0,0x1390,0x1391,0x1392]:run('x',tag,group='mixed_lifecycle')
 for i in range(64):run('j',i,group='mixed_lifecycle')
 #Explicit native safety boundary: unlike primitive allocations,1471a8 has
 #no source null guard. No original equivalence is claimed for these cases.
 native_rejections=0
 for task_head,object_head in [(0,0),(1,0),(0,1)]:
  setup(task_head,object_head,1);commands.append('e 48 5008 0');expected.append(snapshot(1));labels.append(('native_rejection',));native_rejections+=1
 result=subprocess.run([str(BINARY)],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[[int(v) for v in line.split()] for line in result.stdout.splitlines()]
 assert len(actual)==len(expected),(len(actual),len(expected))
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,labels[i],[(j,a,b) for j,(a,b) in enumerate(zip(got,want)) if a!=b][:12])
 report=dict(status='passed',cases=sum(groups.values()),native_fail_fast_cases=native_rejections,groups=dict(groups),original_instructions=instructions,
  elf_sha256=SOURCE_HASH,native_probe_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Whole112570,1125e0,112608,112670,1129c8,11e290,11e2e8,11e350,11d528,1471a8 and composed11e3a0. No patched/skipped callees. Integer-only, every word of both256-slot pools normalized/hashed plus all48 registry slots, free heads/count, pool/registry canaries. Successful registration and full registry included;1471a8 pool-exhaustion null dereferences explicitly excluded and native fail-fast checked separately. Scheduler dispatch/coroutines, stack allocation, body initialization and gameplay integration excluded.')
 (ROOT/'outputs/ss6-feasibility/object_pool_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
