#!/usr/bin/env python3
"""Normal31 through whole149d08, real ACT emission/drop, shared lock control.

The harness composes explicit phase boundaries, not the unported1494f0 loop.
No original instruction/callee is patched, skipped or replaced.
"""
import collections, hashlib, itertools, json, random, struct, subprocess, sys
from pathlib import Path
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import handle, digest, TASKS, OBJECTS
from validate_scheduled_opening import DRAW_OFFSETS
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
BINARY=ROOT/'work/ss6/build-native/ss6-weapon-lock-actor-probe'
B,A,O,OWNERS=0x1b00000,0x1c00000,0x1e00000,0x3d2e88
ACT=[0x1400000,0x1500000,0x1600000]
th=lambda a:handle(a,TASKS,52);oh=lambda a:handle(a,OBJECTS,320);hh=lambda a:handle(a,OWNERS,8)
bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 native_pin=hashlib.sha256(BINARY.read_bytes()).hexdigest();validator_pin=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 p=Probe(raw,finite_model=True);rng=random.Random(0x152368);quick='--quick' in sys.argv;unified='--unified' in sys.argv;object_frames=unified or '--objects' in sys.argv;raw_draw=False
 commands=[];expected=[];labels=[];counts=collections.Counter();instructions=snapshots=draws=0;traces=[];drop_events=[]
 def words(at,values):
  vs=list(values);p.memory[at:at+4*len(vs)]=struct.pack(f'<{len(vs)}I',*[v&0xffffffff for v in vs])
 def readwords(at,n):return list(struct.unpack_from(f'<{n}I',p.memory,at))
 def run(fn,args=()):
  nonlocal instructions
  value,n=p.run(fn,args,limit=2000000);instructions+=n;counts[f'whole{fn:06x}']+=1;return value
 for slot,resource in enumerate([0,0,51]):
  aid=(ASSETS/f'aid_{resource:02}.bin').read_bytes();act=(ASSETS/f'act_{resource:02}.bin').read_bytes()
  p.memory[0x46a9b0+slot*0x1800:0x46a9b0+(slot+1)*0x1800]=aid
  p.memory[ACT[slot]:ACT[slot]+len(act)]=act;p.write(0x4751b0+slot*4,ACT[slot],4);p.write(0x46a9a0+slot*4,resource,4)
 for bank,name in [(2,'02Guard.bin'),(3,'03etc.bin'),(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
  data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0;p.memory[base:base+len(data)]=data
 def fixture(seed,positions=(280,400),mirrors=(0,1),mode=3):
  nonlocal raw_draw
  raw_draw=False
  if unified:p.memory[0x4a2258:0x4a2258+2048]=bytes(2048)
  buffered_stdout(p)
  if object_frames:p.memory[0x479250:0x479250+511*328]=bytes(511*328);p.write(0x46a99c,0,4);p.write(0x4c380c,0,4)
  for at,size in [(B,0x1000),(A,2*0xf2c),(O,0x4000),(OWNERS,512*4),(OBJECTS,256*320),(TASKS,256*52),(0x1232440,258*4),(0x3d3698,257*4)]:p.memory[at:at+size]=bytes(size)
  run(0x1123a8);run(0x112570);run(0x11e290)
  words(0x4c3510,range(1,33));words(0x4c3658,((seed+i)%4 for i in range(44)));words(0x439a48,(seed+i*17 for i in range(72)))
  p.write(0x345188,0,4);p.write(0x123a0c0,0,1);p.write(0x4a2250,0,4);p.write(0x12d2300,0,4)
  game=rng.getrandbits(32);library=rng.getrandbits(64)
  p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(p.read(0x5d1bf8,4)+0xa8,library,8)
  p.write(0x4d3d00,B,4);p.write(0x4d3d08,A,4);p.write(0x4c3808,3,4);p.write(0x4c38a8,0,4)
  words(B,[4,4,1,0]);p.write(B+0x13c,3,4)
  for off,v in [(0,256),(4,bits(320)),(8,bits(120)),(12,bits(320)),(16,160),(20,480),(28,240),(32,bits(320)),(36,bits(120)),(40,bits(320))]:p.write(B+0x34+off,v,4)
  for addr,v in zip([0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68],[320,120,-400,0,-120]):p.write(addr,bits(v),4)
  data=[seed,mode&0xffffffff,game,library]
  for i in range(2):
   a,o=A+i*0xf2c,O+i*0x1000;p.write(B+0x24c+i*4,a,4);p.write(a,o,4);p.write(a+0xa24,i,4)
   for off,value in [(0x190,0xffffffff),(0x1a0,0xffffffff),(0x1a4,0xffffffff),(0x23c,0x1000),(0x1ac,256),
                     (0x134,25600),(0x138,25600),(0xa30,200),(0xa34,200),(0xa3c,0xffffffff),(0xa58,0xffffffff)]:p.write(a+off,value,4)
   p.write(a+0x255,255,1)
   for off,value in [(0xc,i),(0xcc,i),(0xc8,1),(0x104,0x200),(0x30,256),(0x70,bits(1)),(0x8c,0xff808080)]:p.write(o+off,value,4)
   run(0x120390,[o,0]);run(0x11dda0,[o]);run(0x11de10,[o]);run(0x11e1c0,[o])
   for off,value in [(0x38,0x10000000|(mirrors[i]<<19)),(0x104,0x40000200),(0x108,0x40),(0x40,bits(positions[i])),(0x44,0)]:p.write(o+off,value,4)
   data += [mirrors[i],bits(positions[i]),0]
  commands.append('fixture '+' '.join(map(str,data)))
 def snapshot():
  row=[signed(p.read(B+8,4),32),signed(p.read(B+12,4),32),p.read(B+0x138,4),signed(p.read(B+0x144,4),32),p.read(0x12d2300,4)]
  for i in range(2):
   a,o=A+i*0xf2c,O+i*0x1000
   row += [p.read(a+off,4) for off in [0x194,0x18c]]
   row += [signed(p.read(a+off,2),16)&0xffffffff for off in [0x190,0x192,0x198]]+[p.read(a+0x19a,1)]
   row += [p.read(a+off,4) for off in [0x23c,0x244,0x248]]+[p.read(a+0x24c,1)]
   row += [p.read(a+off,4) for off in [0xc0,0xb8,0x130,0xa3c,0xa54,0xa58]]+[p.read(B+0x254+i*0x108+0x30,4)]
   row += [p.read(a+off,4) for off in [0xa28,0xa2c,0x1ac]]+readwords(a+0x15c,3)+readwords(a+0x260,7)+readwords(a+0x1b0,35)+readwords(a+0x27c,4)
   row += list(p.memory[a+0x250:a+0x258])+readwords(a+0x258,2)+[digest(readwords(a+0x2c4,171))]
   row += [p.read(o+off,4) for off in [0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,*range(0x4c,0x64,4),0x40,0x44]]
   row += [p.read(o+0xfe,2)]+[p.read(o+off,4) for off in [0x8c,0x20,0x30]]+readwords(o+0x10c,3)
   row.append(digest(map(th,readwords(B+0x29c+i*0x108,48))))
  tasks=readwords(TASKS,256*13);objects=readwords(OBJECTS,256*80)
  for i in range(256):
   tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+6]=hh(tasks[i*13+6]);tasks[i*13+7]=oh(tasks[i*13+7])
   ref=tasks[i*13+8]
   if ref:
    assert ref in [0x4a2b30+id*108 for id in [12,36]],hex(ref)
    tasks[i*13+8]=0x100+(ref-0x4a2b30)//108
   objects[i*80]=oh(objects[i*80]);objects[i*80+1]=th(objects[i*80+1]);objects[i*80+78]=oh(objects[i*80+78])
   ref=objects[i*80+0xbc//4]
   if ref:
    for base in ACT:
     if base<=ref<base+0x100000:objects[i*80+0xbc//4]=ref-base+1;break
    else:raise AssertionError(hex(ref))
   owner=objects[i*80+0x118//4]
   if owner:
    assert owner in [A,A+0xf2c],hex(owner)
    objects[i*80+0x118//4]=(owner-A)//0xf2c+1
  row += [p.read(0x3d3690,4),p.read(0x3d3688,4),th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),
          th(p.read(0x1232840,4)),p.read(0x3d3a98,4),digest(tasks),digest(objects),digest(map(th,readwords(0x1232440,256))),digest(readwords(0x3d3698,256)),
          digest(readwords(OWNERS,512)),digest(readwords(0x439a48,72)),digest(readwords(0x4c3510,32)),digest(readwords(0x4c3658,44)),
          signed(p.read(0x443150,4),32),p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8),digest(map(th,readwords(B+0x14c,64)))]
  count=0 if raw_draw and not unified else p.read(0x4a2250,4)
  effect_indices=[i for i in range(count) if not unified or p.read(0x479250+i*0x148+0x144,4)]
  row.append(len(effect_indices))
  for i in effect_indices:
   obj=0x479250+i*0x148;record=run(0x1233a0,[obj]);assert record
   row += list(struct.unpack_from('<30H',p.memory,record))+[p.read(obj+off,4) for off in DRAW_OFFSETS]
  if object_frames:
   count=p.read(0x4a2250,4) if raw_draw or unified else 0;row += [p.read(0x46a99c,4),count]
   for i in range(count):
    obj=readwords(0x479250+i*0x148,82);obj[0]=oh(obj[0]);obj[1]=th(obj[1])
    ref=obj[0xbc//4]
    if ref:
     for base in ACT:
      if base<=ref<base+0x100000:obj[0xbc//4]=ref-base+1;break
     else:raise AssertionError(hex(ref))
    owner=obj[0x118//4]
    if owner:assert owner in [A,A+0xf2c];obj[0x118//4]=(owner-A)//0xf2c+1
    row += obj
  if unified:
   pointers=readwords(0x4a2258,512)
   for i,address in enumerate(pointers):
    if address:assert 0x479250<=address<0x479250+511*328 and (address-0x479250)%328==0;pointers[i]=(address-0x479250)//328+1
   row.append(digest(pointers))
  return row
 def visit(i):
  a,o=A+i*0xf2c,O+i*0x1000;armed=bool(p.read(a+0x23c,4)&0x1000);before=(p.read(o+0x24,4),p.read(o+0x28,4),p.read(o+0x104,4))
  run(0x149d08,[a])
  if armed and not p.read(a+0x23c,4)&0x1000:drop_events.append([i,*before,p.read(a+0x260,4)])
 def features(i,mask):words(A+i*0xf2c+0x2c4+24,((mask>>j)&1 for j in range(3)))
 def effects(paused):
  nonlocal raw_draw
  raw_draw=False;p.write(0x4a2250,0,4);p.write(0x46a924,paused,4);run(0x112838)
 def execute(command,label=None):
  nonlocal draws,raw_draw
  op,*vs=command.split();vs=list(map(int,vs))
  if op in ['object-update','object-visit','object-draw']:
   if op=='object-draw':
    raw_draw=True
    if not unified:run(0x1207d8)
   fn={'object-update':0x147028,'object-visit':0x146ef8,'object-draw':0x1470a8}[op]
   for reg,count in [(B+0x29c,48),(B+0x3a4,48),(B+0x14c,64)]:run(fn,[reg,count])
   if unified and op=='object-draw':run(0x122bc0)
  elif op=='enter':run(0x1449c0,[B])
  elif op=='update':run(0x144b28,[B])
  elif op=='features':features(*vs)
  elif op=='distance':p.write(B+0x144,vs[0],4)
  elif op=='bounds':words(B+0x44,vs)
  elif op=='posture':
   a=A+vs[0]*0xf2c
   for off,value in zip([0x23c,0x244,0x194],vs[1:]):p.write(a+off,value,4)
  elif op=='position':words(O+vs[0]*0x1000+0x40,vs[1:])
  elif op=='callback-words':words(A+vs[0]*0xf2c+0x26c,vs[1:])
  elif op in ['phase','timer','delta','queue']:p.write(A+vs[0]*0xf2c+{'phase':0xa54,'timer':0x1e4,'delta':0x1ac,'queue':0xa3c}[op],vs[1],4)
  elif op=='body-flags':words(O+vs[0]*0x1000+0x104,vs[1:])
  elif op=='visit':visit(vs[0])
  elif op=='commit-actor':run(0x149918,[A+vs[0]*0xf2c])
  elif op=='commit-body':run(0x11d8e0,[O+vs[0]*0x1000])
  elif op in ['animate','move']:
   o=O+vs[0]*0x1000;p.write(o+0x30,vs[1],4);run(0x11d730 if op=='animate' else 0x11d6c8,[o])
  elif op=='stage':run(0x1426d8,[B])
  elif op=='separate':run(0x147f48,[A,A+0xf2c,vs[0],1])
  elif op=='effects':effects(vs[0])
  elif op=='common-commit':
   for task in readwords(B+0x14c,64):
    if task:run(0x11d958,[p.read(task+28,4)])
  elif op=='drop':
   context=0x1b10000;words(context,[A+vs[0]*0xf2c,A+(1-vs[0])*0xf2c,0xffffffff]);run(0x16ffb0,[context])
  elif op=='step':
   first,delta,mask0,mask1,paused=vs
   for i in range(2):
    a,o=A+i*0xf2c,O+i*0x1000;p.write(o+0x30,delta,4);run(0x11d730,[o]);run(0x11d6c8,[o]);p.write(a+0x1ac,delta,4)
   run(0x1426d8,[B]);visit(first);visit(1-first)
   for i in [first,1-first]:run(0x149918,[A+i*0xf2c])
   for i in [first,1-first]:run(0x11d8e0,[O+i*0x1000])
   features(0,mask0);features(1,mask1)
   if p.read(B+8,4)==1:run(0x144b28,[B])
   effects(paused)
  elif op!='snapshot':raise AssertionError(op)
  commands.append(command);expected.append(snapshot());labels.append(label or command);draws+=p.read(0x4a2250,4)
 def flush():
  nonlocal snapshots
  assert hashlib.sha256(BINARY.read_bytes()).hexdigest()==native_pin,'Native changed during comparison'
  result=subprocess.run([str(BINARY),str(ASSETS)]+(['--unified'] if unified else ['--objects'] if object_frames else []),input='\n'.join(commands)+'\n',capture_output=True,text=True)
  if result.returncode:
   (ROOT/'work/ss6/lock-actor-failed-input.txt').write_text('\n'.join(commands)+'\n')
   raise AssertionError((result.stderr,len(result.stdout.splitlines()),labels[min(len(result.stdout.splitlines()),len(labels)-1)]))
  actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected),(len(actual),len(expected))
  for i,(got,want) in enumerate(zip(actual,expected)):
   if got!=want:
    (ROOT/'work/ss6/lock-actor-failed-input.txt').write_text('\n'.join(commands)+'\n')
    raise AssertionError((i,labels[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20],len(got),len(want)))
  snapshots+=len(expected);print(f'verified {snapshots} snapshots',flush=True);commands.clear();expected.clear();labels.clear()
 #Observe each boundary separately before exercising continuous compositions.
 fixture(1);execute('snapshot');execute('enter');execute('common-commit')
 for i in range(2):execute(f'visit {i}');execute(f'commit-actor {i}');execute(f'commit-body {i}')
 for d in [120,49,48]:
  execute(f'distance {d}')
  for i in range(2):execute(f'visit {i}')
 for i in range(2):
  execute(f'callback-words {i} 305419896 2271560481 5 4294967294');execute(f'visit {i}');execute(f'commit-actor {i}');execute(f'commit-body {i}')
 for i in range(2):execute(f'phase {i} {2+i}');execute(f'visit {i}');execute(f'visit {i}');execute(f'commit-actor {i}');execute(f'commit-body {i}')
 for tick in range(75):execute(f'step 0 256 0 0 0',('boundary-recover',tick))
 flush()
 #The hold return must survive a queued action or body-pending bit. A
 #missing weapon still releases the callback without allocating/RNG draws.
 for case in range(4):
  fixture(500+case,(280,320));execute('enter')
  for i in range(2):execute(f'visit {i}');execute(f'commit-actor {i}');execute(f'commit-body {i}')
  execute('distance 48');execute('visit 0');execute('visit 0');execute('commit-actor 0');execute('commit-body 0')
  execute('callback-words 0 123 456 7 789')
  execute('timer 0 2147483520');execute('delta 0 256');execute('visit 0')
  execute('phase 0 4294967295');execute('visit 0');execute('visit 0');execute('commit-actor 0');execute('commit-body 0')
  for tick in range(4):execute('animate 0 256')
  assert p.read(O+0x24,4)==140 and p.read(O+0x28,4)==2 and p.read(O+0x104,4)&0x100
  if case&1:execute('queue 0 137')
  if case&2:execute(f'body-flags 0 {p.read(O+0x104,4)|1} {p.read(O+0x108,4)}')
  if case==3:execute('posture 0 0 0 2031616')
  free=p.read(0x46a904,4);game=p.read(0x3d2e80,4);library=p.read(p.read(0x5d1bf8,4)+0xa8,8)
  execute('visit 0',('hold-conditions',case))
  assert p.read(A+0x260,4)==0x169a50 and not p.read(O+0x104,4)&0x100
  assert free-p.read(0x46a904,4)==(0 if case==3 else 1)
  if case==3:assert (game,library)==(p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8))
  flush()
 #Force1 anchor positioning, including coincident/fractional/reversed bodies,
 #odd remainders, shrinkage, walls and positive-only damage wall propagation.
 positions=[(280,400),(400,280),(280.75,280.25),(280.25,280.75),(280.5,280.5),(12.25,42.75),(599.5,620.25),(-20.25,30.5)]
 for case,(xy,gap) in enumerate(itertools.product(positions,[0,1,49,79,80,81,121,-1,-81])):
  if quick and case>3:break
  fixture(10+case,xy);execute('bounds 0 640')
  for i in range(2):
   table=2 if case%3==i else 0;state=case%80 if table==2 else 31
   execute(f'posture {i} 4096 {0x20000 if case%5==i else 0} {table|(state<<16)}')
  execute(f'separate {gap&0xffffffff}',('separate',xy,gap));flush()
 #Real controller decisions (human feature edges supplied at input boundary),
 #not manually assigned A54 phases, release the loser hold and recover idle.
 layouts=[(280,400),(400,280),(200.125,240.875),(400.5,440.25),(280.25,280.75),(280.5,280.5)]
 for case,(outcome,first,delta) in enumerate(itertools.product(range(4),range(2),[128,256,512])):
  if quick and case>0:break
  fixture(100+case,layouts[case%len(layouts)],(case%2,1-case%2),case%3)
  start_drops=len(drop_events);execute('enter');execute('common-commit')
  max_steps=760 if delta==128 else 500 if delta==256 else 360
  seen=set();finished=False
  for tick in range(max_steps):
   mask0=7 if outcome==0 or outcome==2 else 0;mask1=7 if outcome==1 or outcome==2 else 0
   if object_frames:execute('object-update',('objects-before-body',case,tick))
   execute(f'step {first} {delta} {mask0} {mask1} {int(tick%19<2)}',('trace',case,tick))
   if object_frames:execute('object-visit',('objects-callbacks',case,tick));execute('object-draw',('objects-draw',case,tick))
   seen.update(p.read(O+i*0x1000+0x24,4) for i in range(2))
   if p.read(B+8,4)==0 and all(p.read(A+i*0xf2c+0x194,4)==0 and p.read(O+i*0x1000+0x24,4) in [0,1] for i in range(2)):
    finished=True;break
  assert finished,('did not recover',case,[p.read(A+i*0xf2c+0x260,4) for i in range(2)],seen)
  expected_armed=[outcome==0,outcome==1]
  assert [bool(p.read(A+i*0xf2c+0x23c,4)&0x1000) for i in range(2)]==expected_armed,(case,expected_armed)
  assert len(drop_events)-start_drops==2-sum(expected_armed)
  for event in drop_events[start_drops:]:assert event[1]==140 and event[2]==2 and event[3]&0x100 and event[4]==0x169a50,event
  assert {137,138,140}.issubset(seen) and ((139 in seen)==(outcome<2)),(case,seen)
  recovery_steps=tick+1
  for tick in range(180 if object_frames else 85):
   execute('effects 0',('particle-drain',case,tick))
   if object_frames:
    execute('object-update',('objects-drain-update',case,tick));execute('object-visit',('objects-drain-visit',case,tick));execute('object-draw',('objects-drain-draw',case,tick))
  if object_frames:
   assert not any(readwords(B+0x14c,64)),('common effect not reclaimed',case)
   landed=[]
   for i in range(2):
    tasks=readwords(B+0x29c+i*0x108,48)
    for task in tasks:
     if task:
      obj=p.read(task+28,4);assert p.read(obj+0x24,4)==467 and p.read(obj+0x44,4)==0 and p.read(task,4)==0x147540
      landed.append(i)
   assert len(landed)==2-sum(expected_armed),(case,landed)
  assert not any(p.read(OWNERS+i*8,4)&1 for i in range(256))
  traces.append(dict(case=case,outcome=outcome,first=first,delta=delta,steps=recovery_steps,actions=sorted(seen),drops=len(drop_events)-start_drops))
  flush()
 report=dict(status='passed',quick=quick,snapshots=snapshots,draw_snapshots=draws,original_instructions=instructions,functions=dict(counts),traces=traces,drop_events=drop_events,
  elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,
  scope='Whole unmodified149d08 normal31 callbacks137..140,147f48(force1),1449c0/144b28,11d958 and body11d730/11d6c8/149918/11d8e0,1426d8 and112838/124898 with actual ACT world12/36 and16ffb0 weapon births. Shared256 pools,owners,registries,residency,RNG,body and actor fields,ordered particle draws. Explicit input features and phase composition; common-kind7 and dropped-weapon animation/task phases are not advanced. Not whole1494f0,live play,GS pixels or hardware FP. Real buffered libc,muted body audio,finite scalar model; no original code changed or skipped.')
 if object_frames:
  report['scope']='Whole original normal31/controller/body/effect functions plus147028/146ef8/1470a8,145e30,1701c0 and every reached callee. Shared256 pools and actual actor-produced dropped weapons, resource51/action135 common animation,146ef8 callbacks/free, raw auxiliary drawing. Both winners,ties,timeouts,actor orders,128/256/512 body deltas; object base speed remains actual battle140=0. Complete weapon landings/action467 and common reclamation asserted after natural actor recovery. Particle and auxiliary draws checked at distinct explicit phase boundaries; no claim of their merged global draw-budget/order,whole140270/1494f0,live input/trigger,GS pixels or SPU audio. Body mute bit; auxiliary sound selection runs before original global playback-off gate. Finite scalar model; no original code patched/skipped.'
 target=('weapon_lock_object_quick_validation.json' if quick else 'weapon_lock_object_validation.json') if object_frames else ('weapon_lock_actor_quick_validation.json' if quick else 'weapon_lock_actor_validation.json')
 if unified:
  report['scope']=f'Whole original normal31/controller/body/effects and147028/146ef8/1470a8/122bc0. Shared pools and a SINGLE511-slot raw draw queue, particle snapshots before advance/free, auxiliary append, stable descending48+b0 sorting with retained pointer-table tail. Particle render decoding from queued snapshots compared with original1233a0 after object/owner reclamation.{len(traces)}natural outcome/order/bodydelta traces and{len(drop_events)}total real callback drop events; full landing andcommon reclamation.Explicit phase composition; not whole140270/1494f0,actual hardware scheduler order/liveinput/GS/audio. Capacity stress and fractional/tied sort belong to the separate mixed_draw_validation.json matrix; this natural matrix does not reach511.Full source functions execute unchanged;finite scalar model,buffered libc,muted backend.'
  target='weapon_lock_unified_quick_validation.json' if quick else 'weapon_lock_unified_validation.json'
 (ROOT/'outputs/ss6-feasibility'/target).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
