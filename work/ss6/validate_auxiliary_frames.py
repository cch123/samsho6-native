#!/usr/bin/env python3
"""Actual auxiliary update/callback/draw functions; no original code patches.

The three phases are composed explicitly. This is not a whole140270 frame,
original trigger proof, or a native GS/audio backend validation.
"""
import collections, hashlib, itertools, json, random, struct, subprocess, sys, tempfile
from pathlib import Path
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import digest, handle, pointer, TASKS, OBJECTS
from validate_scheduled_opening import DRAW_OFFSETS
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
BIN=ROOT/'work/ss6/build-native/ss6-auxiliary-frame-probe'
B,A,O,Q=0x1b00000,0x1c00000,0x1e00000,0x479250
ACT=[0x1400000,0x1500000,0x1600000]
bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
tp=lambda v:pointer(v,TASKS,52);optr=lambda v:pointer(v,OBJECTS,320)
th=lambda v:handle(v,TASKS,52);oh=lambda v:handle(v,OBJECTS,320)
def main():
 quick='--quick' in sys.argv;mixed='--mixed' in sys.argv;raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 native_pin=hashlib.sha256(BIN.read_bytes()).hexdigest();validator_pin=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 p=Probe(raw,finite_model=True);rng=random.Random(0x147028);instructions=total=0;counts=collections.Counter();groups=collections.Counter();traces=[]
 commands=[];expected=[];labels=[];written=set();result=0
 def words(at,vs):
  vs=[v&0xffffffff for v in vs];p.memory[at:at+len(vs)*4]=struct.pack(f'<{len(vs)}I',*vs)
 def read(at,n):return list(struct.unpack_from(f'<{n}I',p.memory,at))
 def run(fn,args=()):
  nonlocal instructions
  value,n=p.run(fn,[signed(v,32) for v in args],limit=2000000);instructions+=n;counts[hex(fn)]+=1;return value&0xffffffff
 def reg(i):return B+0x14c if i==2 else B+0x29c+i*0x108
 def size(i):return 64 if i==2 else 48
 def normalize(row,tail=True):
  row=list(row);row[0]=oh(row[0]);row[1]=th(row[1])
  if tail:row[78]=oh(row[78])
  ref=row[0xbc//4]
  if ref:
   for base in ACT:
    if base<=ref<base+0x100000:row[0xbc//4]=ref-base+1;break
   else:raise AssertionError(('ACT',hex(ref)))
  owner=row[0x118//4]
  if owner:assert owner in [A,A+0xf2c];row[0x118//4]=(owner-A)//0xf2c+1
  return row
 def snapshot():
  ts=read(TASKS,256*13);os=[]
  for i in range(256):
   ts[i*13+3]=th(ts[i*13+3]);ts[i*13+7]=oh(ts[i*13+7]);os+=normalize(read(OBJECTS+i*320,80))
   if mixed:
    ts[i*13+6]=handle(ts[i*13+6],0x3d2e88,8)
    ref=ts[i*13+8]
    if ref:
     if ref in [0x4a2b30+id*108 for id in [12,36]]:ts[i*13+8]=0x100+(ref-0x4a2b30)//108
     else:
      assert 0x4a3e30<=ref<0x4a3e30+20*108 and (ref-0x4a3e30)%108==0
      ts[i*13+8]=(ref-0x4a3e30)//108
  draws=read(Q,511*82)
  for i in written:draws[i*82:i*82+78]=normalize(draws[i*82:i*82+78],False)
  owners=[]
  for i in range(2):
   a=A+i*0xf2c;owners += [p.read(a+0x23c,4),p.read(a+0xa2c,4),signed(p.read(a+0x194,2),16)]
  row=[result,p.read(0x46a99c,4),th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),digest(ts),digest(os),
   digest(read(O,80)+read(O+0x1000,80)),digest([th(x) for i in range(2) for x in read(reg(i),48)]),digest(map(th,read(reg(2),64))),
   p.read(0x4a2250,4),digest(draws),p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8),signed(p.read(0x585224,4),32),signed(p.read(0x58524c,4),32),*owners,*os[-320:]]
  if mixed:
   order=read(0x4a2258,512)
   for i,ref in enumerate(order):
    if Q<=ref<Q+511*328 and (ref-Q)%328==0:order[i]=(ref-Q)//328+1
   row += [digest(read(0x3d2e88,512)),p.read(0x3d3690,4),p.read(0x3d3688,4),th(p.read(0x1232840,4)),p.read(0x3d3a98,4),
           digest(map(th,read(0x1232440,256))),digest(read(0x3d3698,256)),digest(read(0x439a48,72)),digest(read(0x4c3510,32)),digest(read(0x4c3658,44)),digest(order)]
   decoded=[]
   for i in range(p.read(0x4a2250,4)):
    at=Q+i*328
    if p.read(at+0x144,4):
     record=run(0x1233a0,[at]);assert record
     decoded+=list(struct.unpack_from('<30H',p.memory,record))+[p.read(at+off,4) for off in DRAW_OFFSETS]
   assert len(decoded)%56==0
   row += [len(decoded)//56,digest(decoded)]
  return row
 def draw(which):
  before=p.read(0x4a2250,4);run(0x1470a8,[reg(which),size(which)]);written.update(range(before,p.read(0x4a2250,4)))
 def cmd(name,*args):
  nonlocal result,written,instructions
  commands.append(' '.join(map(str,[name,*[v&0xffffffff for v in args]])))
  if name=='reset':
   seed,stage=args;result=0;written=set();buffered_stdout(p)
   for at,n in [(B,0x1000),(A,2*0xf2c),(O,0x2000),(TASKS,256*52),(OBJECTS,256*320),(0x1232440,258*4),(0x3d3698,257*4)]:p.memory[at:at+n]=bytes(n)
   if mixed:
    words(0x3d2e88,[0]*512);run(0x1123a8)
    words(0x4a2258,(0xabc000+seed+i*13 for i in range(512)))
    words(0x4c3510,range(1,33));words(0x4c3658,((seed+i)%4 for i in range(44)));words(0x439a48,(seed+i*17 for i in range(72)))
    p.write(0x123a0c0,0,1)
   run(0x112570);run(0x11e290);words(Q,(seed+i*997+j*17 for i in range(511) for j in range(82)))
   for addr,v in [(0x4d3d00,B),(0x4d3d08,A),(0x4a2250,0),(0x46a99c,0),(0x345188,0),(0x4c3808,3),(0x4c380c,stage),
                  (0x443150,3),(0x3d2e80,seed),(0x46a908,256)]:p.write(addr,v,4)
   words(0x46a910,[0]*13);p.write(p.read(0x5d1bf8,4)+0xa8,42,8)
   table=(ASSETS/'sound_selection.bin').read_bytes();p.write(0x585224,struct.unpack_from('<I',table,36)[0],4);p.write(0x58524c,struct.unpack_from('<I',table,76)[0],4)
   for i in range(2):
    a,o=A+i*0xf2c,O+i*0x1000;p.write(a,o,4);p.write(a+0xa24,i,4);p.write(a+0x23c,0x1000,4);p.write(B+0x24c+i*4,a,4)
    for off,v in [(0xc,i),(0xcc,i),(0x30,256),(0xc8,1),(0x38,0x10000000|(i<<19)),(0x70,bits(1)),(0x40,bits(280+80*i)),(0x8c,0xffffffff)]:p.write(o+off,v,4)
  elif name=='parent':p.write(O+args[0]*0x1000+args[1],args[2],4)
  elif name=='actor':
   i,flags,posture,table=args;a=A+i*0xf2c;p.write(a+0x23c,flags,4);p.write(a+0xa2c,posture,4);p.write(a+0x194,table,2);p.write(a+0x1a4,table,2)
  elif name=='gauge':p.write([0x46a940,0x46a908][args[0]] if args[0]<2 else 0x46a910+(args[0]-2)*4,args[1],4)
  elif name=='speed':p.write(B+0x140,args[0],4)
  elif name=='jump':p.write(0x46a99c,args[0],4)
  elif name=='whirlwind':
   i,strength=args;a=A+i*0xf2c;body=O+i*0x1000
   p.write(a+0x194,1|((64+strength)<<16),4);p.write(a+0x28c,0,4);p.write(a+0x2b8,0x4df060,4);p.write(a+0x26c,strength,4)
   result=oh(run(0x16d9c8,[a]))
  elif name=='flask':
   i,=args;a=A+i*0xf2c
   p.write(a+0x194,1|(77<<16),4);p.write(a+0x28c,0,4);p.write(a+0x2b8,0x4df100,4);p.write(a+0x26c,0,4)
   result=oh(run(0x16d9c8,[a]))
  elif name=='reflect':
   h,team=args;event=B+0x2000;source=B+0x2100
   p.write(event+0x40,source,4);p.write(event+0x68,optr(h),4);p.write(source+0x10,team,4)
   # The original tail calls the clash spark/sound. Stop at the real branch
   # boundary to compare the reflected object and its subsequent playback.
   from validate_input_lifecycle import Boundary
   stop=Boundary(0x157f80)
   _,steps=p.run(0x155780,[event],stop_before=stop)
   instructions+=steps;counts[hex(0x155780)]+=1
   assert stop.stopped==0x157f80
  elif name=='rising-trail':
   i,state=args;a=A+i*0xf2c;running=state>=71
   p.write(a+0x194,1|(state<<16),4);p.write(a+0x28c,0,4);p.write(a+0x2b8,0x4df0b0 if running else 0x4df088,4)
   p.write(a+0x26c,state-(71 if running else 68),4);result=oh(run(0x16d9c8,[a]))
  elif name=='actor-attachment':
   i,=args;result=oh(run(0x16d9c8,[A+i*0xf2c]))
  elif name=='slash-effect':
   i,=args;a=A+i*0xf2c
   p.write(a+0x194,1|(80<<16),4);p.write(a+0x28c,0,4);p.write(a+0x2b8,0x4df150,4)
   result=oh(run(0x16d9c8,[a]))
  elif name=='projectile-pause':
   h,first,second=args;ticks=run(0x151948,[first,second]);run(0x11db00,[optr(h),ticks])
  elif name=='spawn':
   kind,i=args
   if kind==7:result=oh(run(0x140a78,[O,0x1396,7,0]))
   else:words(B+0x2000,[A+i*0xf2c,A+(1-i)*0xf2c,0xffffffff]);result=oh(run(0x16ffb0,[B+0x2000]))
  elif name=='object':
   h,offset,v=args
   if offset==4:v=tp(v)
   elif offset==0x118:v=A+(v-1)*0xf2c if v else 0
   p.write(optr(h)+offset,v,4)
  elif name=='task':
   h,offset,v=args
   if offset==28:v=optr(v)
   p.write(tp(h)+offset,v,4)
  elif name=='registry':p.write(reg(args[0])+args[1]*4,tp(args[2]),4)
  elif name=='request':h,action,flags=args;run(0x11d908,[optr(h),action,flags&1,(flags>>1)&1])
  elif name=='animate':run(0x11d730,[optr(args[0])])
  elif name=='move':run(0x11d6c8,[optr(args[0])])
  elif name=='delta':result=run(0x11f450,args)
  elif name in ['update','visit']:run(0x147028 if name=='update' else 0x146ef8,[reg(args[0]),size(args[0])])
  elif name=='draw':draw(args[0])
  elif name=='world':
   p.floats[12:16]=args[3:];run(0x124430,args[:3])
  elif name=='opening':result=handle(run(0x1249c8,args),0x3d2e88,8)
  elif name=='ending':
   p.floats[12:16]=list(map(bits,[320,240,-50,1]));result=handle(run(0x124548,[args[0],0x100000,0]),0x3d2e88,8)
  elif name=='effects':
   before=p.read(0x4a2250,4);run(0x112838);written.update(range(before,p.read(0x4a2250,4)))
  elif name=='repeat-draw':
   for _ in range(args[1]):draw(args[0])
  elif name=='sort':run(0x122bc0)
  elif name=='begin':run(0x1207d8)
  elif name=='draw-count':p.write(0x4a2250,args[0],4)
  elif name=='tick':
   run(0x1207d8)
   for i in range(3):run(0x147028,[reg(i),size(i)])
   for i in range(3):run(0x146ef8,[reg(i),size(i)])
   for i in range(3):draw(i)
  elif name=='snapshot':pass
  else:raise AssertionError(name)
 def check(label):
  commands.append('snapshot');expected.append(snapshot());labels.append(label);groups[str(label[0] if isinstance(label,tuple) else label)]+=1
 def flush():
  nonlocal total
  assert hashlib.sha256(BIN.read_bytes()).hexdigest()==native_pin
  native=subprocess.run([str(BIN),str(ASSETS)]+(['--mixed'] if mixed else []),input='\n'.join(commands)+'\n',text=True,capture_output=True)
  actual=[list(map(int,line.split())) for line in native.stdout.splitlines()]
  if native.returncode or len(actual)!=len(expected):
   (ROOT/'work/ss6/auxiliary-frame-failed-input.txt').write_text('\n'.join(commands)+'\n')
   raise AssertionError((native.stderr,len(actual),len(expected),labels[min(len(actual),len(labels)-1)]))
  for i,(got,want) in enumerate(zip(actual,expected)):
   if got!=want:
    (ROOT/'work/ss6/auxiliary-frame-failed-input.txt').write_text('\n'.join(commands)+'\n')
    (ROOT/'work/ss6/auxiliary-frame-failed-expected.json').write_text(json.dumps(want))
    raise AssertionError((i,labels[i],[(j,hex(x),hex(y)) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:30]))
  total+=len(expected);print('auxiliary frames',total,'passed',flush=True);commands.clear();expected.clear();labels.clear()
 for slot,c in enumerate([0,0,51]):
  aid=(ASSETS/f'aid_{c:02}.bin').read_bytes();act=(ASSETS/f'act_{c:02}.bin').read_bytes()
  p.memory[0x46a9b0+slot*0x1800:0x46a9b0+(slot+1)*0x1800]=aid;p.memory[ACT[slot]:ACT[slot]+len(act)]=act
  p.write(0x4751b0+slot*4,ACT[slot],4);p.write(0x46a9a0+slot*4,c,4)
 if '--victory-attachment' in sys.argv:
  from mips_probe import idle_fixture
  aid=(ASSETS/'aid_00.bin').read_bytes();act=(ASSETS/'act_00.bin').read_bytes()
  source,body=idle_fixture(raw,aid,act);source.write(body+0xc8,1,4);source.write(body+0x104,0x200,4)
  source.run(0x120390,[body,502]);source.write(body+0x30,256,4)
  for _ in range(6):
   assert source.read(body+0x10c,4)==0
   source.run(0x120ac8,[body])
  assert source.read(body+0x28,4)==1 and source.read(body+0x104,4)&0x18000==0x8000
  decoded=tuple(source.read(body+off,4) for off in (0x10c,0x110,0x114))
  for side in range(2):
   cmd('reset',side+1,0);cmd('actor',side,0x1000,0,0)
   start=struct.unpack_from('<h',aid,502*2)[0]
   record=ACT[side]+(start+1)*60
   assert p.read(record,4)&0x400
   action,dx,dy=struct.unpack_from('<3h',p.memory,record+0x2e)
   assert (action,dx,dy)==decoded==(508,0,0)
   # Pass the request published by the original body clock to the actor-owned registry.
   for off,v in [(0x10c,action),(0x110,dx),(0x114,dy),(0x104,0x8000)]:cmd('parent',side,off,v)
   cmd('actor-attachment',side);check(('birth',side));assert result
   cmd('draw',side);check(('commit',side));child=optr(result)
   assert p.read(child+0x24,4)==508 and p.read(child+0xcc,4)==6
   steps={0};last=0
   for t in range(400):
    cmd('tick')
    if not p.read(reg(side),4):check(('retired',side));break
    step=p.read(child+0x28,4);steps.add(step)
    if step!=last:check(('record',side,step));last=step
   else:raise AssertionError('Victory effect failed to retire')
   assert len(steps)==27
   traces.append(dict(player=side+1,source_record=start+1,action=action,records=len(steps),updates=t+1));flush()
  with tempfile.TemporaryDirectory() as tmp:
   exe=Path(tmp)/'live';library=BIN.parent/'libss6-runtime.a'
   subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',Path(__file__).with_name('cpu_victory_attachment_probe.cpp'),library,'-o',exe],check=True)
   first,last,count,n,ticks,wins,losses,visible,maxPixels=map(int,subprocess.check_output([exe,ASSETS],text=True).split())
  report=dict(status='passed',cases=traces,snapshots=total,original_instructions=instructions,
              live_level3_cpu_set=dict(first=first,last=last,draws=count,records=n,ticks=ticks,score=[wins,losses],visible_poses=visible,max_changed_pixels=maxPixels),
              runtime_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
              original_elf_sha256=SOURCE_HASH,native_probe_sha256=native_pin,
              scope='Original 120390/120ac8 body playback through Haohmaru ACT502 entry 1, 16d9c8 and 16dcc0 nonzero personal attachment allocation, complete original object clocks/callbacks/draws to retirement. Full object and submitted draw records at every one of ACT508’s 27 poses. Owner placement sampled for both seats.')
  (ROOT/'outputs/ss6-feasibility/victory-attachment-validation.json').write_text(json.dumps(report,indent=2)+'\n')
  print(total,'victory attachment snapshots');return
 if '--slash-effect' in sys.argv:
  traces=[]
  for slot,interrupted in itertools.product(range(2),(False,True)):
   cmd('reset',slot+1,0);cmd('actor',slot,0x1000,0,1)
   cmd('parent',slot,0x10c,593);cmd('parent',slot,0x104,0x8000)
   cmd('slash-effect',slot);check(('birth',slot));assert result
   cmd('draw',slot);check(('commit',slot));assert p.read(optr(result)+0x24,4)==593
   for tick in range(120):
    cmd('parent',slot,0x40,bits(280+40*slot+tick))
    if interrupted and tick==2:cmd('actor',slot,0x1000,0,2)
    cmd('tick');check(('tick',slot,interrupted,tick))
    if not p.read(reg(slot),4):break
   assert tick<119
   traces.append(dict(slot=slot,interrupted=interrupted,updates=tick+1));flush()
  report=dict(status='passed',cases=traces,snapshots=total,original_instructions=instructions,
              scope='Original nonzero ACT593 attachment from 16d9c8, allocation, movement, expiry and queued draw records.')
  (ROOT/'outputs/ss6-feasibility/slash_attachment_validation.json').write_text(json.dumps(report,indent=2)+'\n')
  print(total,'slash attachment snapshots');return
 if '--rising-trail' in sys.argv:
  cases=[]
  for state,slot,interrupted in itertools.product(range(68,74),range(2),(False,True)):
   cmd('reset',state*2+slot,0);cmd('actor',slot,0x1000,0,1);cmd('parent',slot,0x104,0x8000)
   cmd('rising-trail',slot,state);check(('birth',state,slot));assert result==256
   cmd('draw',slot);check(('commit',state,slot));action=p.read(optr(result)+0x24,4)
   assert action==(555+state-68 if state<71 else 571+state-71)
   for tick in range(160):
    # A living slash follows its owner's new position and action speed.
    # Original kind6 also vanishes immediately when that owner takes a hit.
    cmd('parent',slot,0x40,bits(290.25+tick));cmd('parent',slot,0x44,bits(tick/2))
    cmd('parent',slot,0x30,128 if 2<=tick<=5 else 256)
    if interrupted and tick==8:cmd('actor',slot,0x1000,0,2)
    cmd('tick');check(('tick',state,slot,interrupted,tick))
    if not p.read(reg(slot),4):break
   assert tick<159 and (not interrupted or tick==8)
   cases.append(dict(state=state,player=slot+1,interrupted=interrupted,ticks=tick+1,action=action));flush()
  report=dict(status='passed',cases=cases,snapshots=total,original_instructions=instructions,sha256=SOURCE_HASH,
   scope='Original 16d9c8 and original allocation, 147028, 146ef8, 1470a8. All raw task, object and submitted draw records for rising-slash trails in both directions, three strengths, standing/running, with normal completion or interrupted owner.')
  (ROOT/'outputs/ss6-feasibility/rising_slash_trails_validation.json').write_text(json.dumps(report,indent=2)+'\n')
  print(total,'original/native rising-slash trail snapshots');return
 if '--flask' in sys.argv:
  cases=[]
  for slot,ending in itertools.product(range(2),('whiff','hit','guard','clash','reflect-whirlwind')):
   cmd('reset',102+slot,0);cmd('actor',slot,0x1000,0,1);cmd('parent',slot,0x104,0x8000)
   cmd('parent',slot,0x110,11);cmd('parent',slot,0x114,-2)
   if ending=='reflect-whirlwind':cmd('whirlwind',slot,1)
   else:cmd('flask',slot)
   check(('birth',slot,ending));assert result==256
   cmd('draw',slot);check(('commit',slot,ending));actions=set()
   for tick in range(135):
    if tick==5:
     if ending=='clash':cmd('object',result,0x100,2)
     elif ending=='reflect-whirlwind':cmd('reflect',result,1-slot);check(('reflected',slot))
     elif ending in ('hit','guard'):
      cmd('object',result,0x104,p.read(optr(result)+0x104,4)|(0x40000 if ending=='hit' else 0x80000))
      if ending=='guard':cmd('projectile-pause',result,4,8)
    cmd('tick');check(('tick',slot,ending,tick));actions.add(p.read(optr(result)+0x24,4))
    if not p.read(reg(slot),4):break
   assert tick<134 and (ending=='reflect-whirlwind' or (601 in actions)==(ending!='whiff')),(slot,ending,actions)
   cases.append(dict(player=slot+1,ending=ending,ticks=tick+1,actions=sorted(actions)));flush()
  report=dict(status='passed',cases=cases,snapshots=total,original_instructions=instructions,sha256=SOURCE_HASH,
   scope='Complete original 16d9c8, 147028, 146ef8 and 1470a8. Raw task/object/registry/draw arrays agree for both facings, staged hits, block, clash and whiff, including freezes and object retirement. Reflection runs 155780 up to (excluding) its 157f80 spark and sound, then checks the real reflected whirlwind to retirement.')
  (ROOT/'outputs/ss6-feasibility/flask_objects_validation.json').write_text(json.dumps(report,indent=2)+'\n');return
 if '--whirlwind' in sys.argv:
  cases=[]
  for strength,slot,ending in itertools.product(range(3),range(2),('whiff','hit','guard','clash')):
   cmd('reset',101+strength,0);cmd('actor',slot,0x1000,0,1);cmd('parent',slot,0x104,0x8000)
   cmd('parent',slot,0x110,11);cmd('parent',slot,0x114,0)
   cmd('whirlwind',slot,strength);check(('birth',strength,slot,ending));assert result==256
   cmd('draw',slot);check(('commit',strength,slot,ending));actions=set();last_hp=0
   for tick in range(95):
    if tick==9 and ending!='whiff':
     obj=optr(result)
     if ending=='clash':cmd('object',result,0x100,2)
     else:cmd('object',result,0x104,p.read(obj+0x104,4)|(0x40000 if ending=='hit' else 0x80000))
     if ending=='guard':cmd('projectile-pause',result,4,8)
    cmd('tick');check(('tick',strength,slot,ending,tick));actions.add(p.read(optr(result)+0x24,4))
    if not p.read(reg(slot),4):break
   assert tick<94 and 532+strength in actions and (535 if ending=='hit' else 538) in actions,(strength,slot,ending,actions)
   cases.append(dict(strength=strength,slot=slot,ending=ending,ticks=tick+1));flush()
  report=dict(status='passed',cases=cases,snapshots=total,original_instructions=instructions,sha256=SOURCE_HASH,
   scope='16d9c8 on original phase marker, then real registry clock, motion, callbacks, commit, drawing and destruction. Both owners, three slash strengths, signed anchors, whiff/hit/guard/clash marks. Every raw task, object and submitted draw record. Contact and victim takeover are separate replay fixtures.')
  (ROOT/'outputs/ss6-feasibility/whirlwind_objects_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(total,'original/native whirlwind object snapshots');return
 if mixed:
  for bank,name in [(2,'02Guard.bin'),(3,'03etc.bin'),(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
   data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0;p.memory[base:base+len(data)]=data
  def world(id,slot=0,z=-10,flags=0):cmd('world',id,flags,slot,*map(bits,[280.125,80.25,z,1]))
  #Real groups/captions and a common object share pool and queue across
  #every update. Reversing submission phases catches cross-type ordering.
  for case in range(1 if quick else 8):
   cmd('reset',5000+case,case%12);cmd('spawn',7,0);cmd('request',256,135,3)
   cmd('object',256,0x48,bits(-10));cmd('opening',1 if case%2 else 10)
   for tick in range(270):
    cmd('begin');cmd('gauge',7,int(tick%13<3));cmd('gauge',4,(case+tick)%8);cmd('gauge',5,(case*3+tick)%8)
    if tick in [0,4,8,64,100,180]:world(12 if tick%8==0 else 36,case%3,[-10,-50,-60][case%3],(case%4)<<18)
    if tick==120:cmd('ending',15+case%5)
    cmd('update',2);cmd('visit',2)
    if case%2:cmd('draw',2);cmd('effects')
    else:cmd('effects');cmd('draw',2)
    cmd('sort');check(('mixed-lifecycle',case,tick))
   assert p.read(0x46a904,4)==255,('unreleased effect objects',case)
   flush()
  #Queue capacity is filled by real1470a8 submissions. Update/clock and
  #owner reclamation still execute when1207e8 discards excess draws.
  for case,(prefill,first) in enumerate(itertools.product([0,1,490,500,510,511],range(2))):
   if quick and case>1:break
   cmd('reset',6000+case,0);cmd('spawn',7,0);cmd('request',256,135,3)
   world(12);world(36,1);cmd('begin')
   if first:cmd('effects');cmd('repeat-draw',2,prefill)
   else:cmd('repeat-draw',2,prefill);cmd('effects')
   cmd('draw',2);cmd('sort');check(('capacity',prefill,first))
   assert p.read(0x4a2250,4)<=511
   if prefill>=510:assert p.read(0x4a2250,4)==511
   for tick in range(80):
    cmd('begin');cmd('effects');cmd('draw',2);cmd('sort');check(('capacity-drain',case,tick))
   assert p.read(0x46a904,4)==255
   flush()
  #Standalone ordering uses actual submitted snapshots, varying both Z
  #and B0 with rounding ties, signed zero, and retained pointer-table tail.
  values=[(0,0),(-0.0,0),(0.5,-0.5),(1,-1),(-10,0),(-10,0),(-50,40),
          (16777216,1),(16777216,0),(-16777216,-1),(-16777216,0),(1.5,0.25)]
  for case in range(6 if quick else 64):
   cmd('reset',7000+case,0);cmd('spawn',7,0);cmd('request',256,135,3)
   count=[0,1,2,7,19,64,127,511][case%8];cmd('begin')
   for i in range(count):
    z,offset=values[(i+case)%len(values)] if case%3 else (rng.randrange(-4000,4000)/8,rng.randrange(-1000,1000)/16)
    cmd('object',256,0x48,bits(z));cmd('object',256,0xb0,bits(offset));cmd('draw',2)
   cmd('sort');check(('sort',case,count))
   cmd('begin');cmd('draw',2);cmd('sort');check(('sort-tail-retention',case))
   flush()
  #This assertion requires a final particle snapshot after its source
  #object and owner have already returned to their pools in the samevisit.
  cmd('reset',8000,0);world(36);last_draw=False
  for tick in range(90):
   cmd('begin');cmd('effects');cmd('sort');check(('final-frame',tick))
   if p.read(0x46a904,4)==256 and p.read(0x4a2250,4)>0:last_draw=True
  assert last_draw,'Final queued particle frame was not exercised';flush()
  report=dict(status='passed',quick=quick,snapshots=total,original_instructions=instructions,groups=dict(groups),functions=dict(counts),
   elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,
   scope='Whole original112838/124898 particle/caption tasks,124430/1249c8/124548 allocation and completion,147028/146ef8/1470a8 auxiliary phases,1207e8 copy/capacity,122bc0 stable depth sort,1233a0 draw decoding. Shared256 pools/owners,RNG,residency/palettes,complete511 raw slots and512 sort pointers including retained tails. Actual world12/36,all5ending captions,opening callbacks/common135; both submission orders,full511 capacity,clocks and reclamation after discarded draws,final draw afterfree,rounded/tied/negativeZ+B0. Explicit phase composition,not whole hardware mainloop/GS/audio. All reached original callees unchanged,buffered libc,finite FPmodel.')
  target='mixed_draw_quick_validation.json' if quick else 'mixed_draw_validation.json'
  (ROOT/'outputs/ss6-feasibility'/target).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
 #Whole resolver: independent globals, both borrowing branches, common
 #selector2 adjacency, signed multiply overflow and the zero-factor64rule.
 for case in range(60 if quick else 900):
  cmd('reset',case,0)
  for i in range(14):cmd('gauge',i,0 if i==0 and case%9 else rng.choice([0,0,0,1,5,0xffffffff]))
  cmd('gauge',1,rng.choice([0,64,85,128,256,512,0x7fffffff,0xffffffff]))
  cmd('delta',rng.choice([0,1,128,256,512,0x7fffffff,0xffffffff]),case%3);check(('delta',case))
  if case%100==99:flush()
 flush()
 #Natural loops and dropped weapons: all real spawn/landing callees run
 #with audioenabled objects, and global playback disabled after selection.
 for case,(mode,player) in enumerate(itertools.product([0,1,2],range(2))):
  if quick and case>0:break
  cmd('reset',1000+case,case);cmd('speed',mode);cmd('spawn',7,0);cmd('request',256,135,3);cmd('spawn',4,player)
  check(('spawn',case));landed=None
  for tick in range(540 if mode==2 else 360 if mode==1 else 200):
   if tick==24:cmd('object',256,0x108,p.read(optr(256)+0x108,4)|0x2000)
   cmd('tick');check(('natural',case,tick))
   if p.read(optr(255)+0x24,4)==467 and landed is None:landed=tick
  flush()
  assert landed is not None,(case,'never landed',[(hex(off),hex(p.read(optr(255)+off,4))) for off in [0x24,0x28,0x30,0x38,0x44,0x58,0x5c,0x60,0xc8,0x104,0x108]],read(reg(player),3))
  assert not any(read(reg(2),64)) and p.read(0x46a904,4)==255
  assert p.read(tp(255),4)==0x147540 and p.read(optr(255)+0x44,4)==0
  traces.append(dict(speed_mode=mode,player=player,landing_tick=landed,weapon_action=p.read(optr(255)+0x24,4)))
  flush()
 #Clock early returns, one-record catchup, landing/jump and old-JDG
 #publication use original AID/ACT records, never synthesized action bytes.
 action_steps=[(0,0),(6,1),(16,3),(36,3),(48,0),(466,7),(467,0)]
 for case in range(24 if quick else 280):
  action,step=action_steps[case%len(action_steps)];cmd('reset',2000+case,0);cmd('spawn',4,0)
  cmd('object',256,0x104,0x200);cmd('request',256,action,3);cmd('object',256,0x28,step)
  for offset,value in [(0x2c,rng.choice([0,255,256,1023,0x7fffffff,0xffffffff])),(0x30,rng.choice([0,85,128,256,512,4096])),
    (0xdc,rng.choice([0,0,0,1,0xffffffff])),(0x104,0x200|rng.choice([0,0x10,0x100,0x2000,0x4000,0x40000000,0x20000000])),
    (0xfc,rng.choice([0,0,0,0x200000])),(0x44,bits(rng.choice([-1,0,1,4.75]))),(0x58,rng.choice([0,65536,0xffff0000,0x80000000])),
    (0x38,0x10000000|rng.choice([0,0x40000]))]:cmd('object',256,offset,value)
  cmd('jump',rng.choice([0,1,0xa5]));cmd('animate',256);check(('clock',case,action,step))
  if case%100==99:flush()
 flush()
 #Independent motion/shake paths, including committing displacement while
 #frozen and color updates which advance per visit, not by resolved delta.
 for case in range(24 if quick else 360):
  cmd('reset',3000+case,0);cmd('spawn',4,case%2)
  for off in range(0x4c,0x64,4):cmd('object',256,off,rng.getrandbits(32))
  for off,val in [(0x30,rng.choice([0,85,256,512,0xffffffff])),(0x40,bits(rng.randrange(-200,900)/4)),(0x44,bits(rng.choice([-1,-0.0,0,20]))),
    (0x38,rng.choice([0,0x40000,0x80000,0xc0000,0x2000000,0x1000000,0x30c0000])),(0x104,rng.choice([0,0x20])),
    (0x108,rng.choice([0,0x400,0x800,0xc00])),(0xc8,case%3),(0xdc,rng.choice([0,1,255,256,257,0x7fffffff,0xffffffff])),
    (0xe0,rng.choice([0,1,0x7fffffff,0xffffffff])),(0xfc,rng.choice([0,1,255,0x100000,0x200000,0xa500ff])),(0x8c,rng.getrandbits(32))]:cmd('object',256,off,val)
  for off in [0x90,0x98,0xa0,0xa8]:cmd('object',256,off,rng.choice([0,1,255,0xffffff00,0x7fffffff,0xffffffff]))
  cmd('gauge',0,case%2);cmd('move',256);check(('motion',case))
  if case%100==99:flush()
 flush()
 #Registry owner precedence, completion flags, parent position/color copy,
 #draw invisibility/capacity and retained140 storage across beginFrame.
 for case in range(12 if quick else 144):
  cmd('reset',4000+case,0);cmd('spawn',4,case%2);cmd('spawn',7,0);cmd('request',255,135,0)
  cmd('speed',case%5);cmd('object',256,0x104,0x210|(case%2)*2);cmd('object',256,0xc0,case%2)
  cmd('object',256,0x108,rng.choice([0,0x10000,0x20000,0x30000,0x40000,0x70000])|rng.choice([0,0x2000,0x4000,0x8000])|rng.choice([0,0x80000,0x4000000]))
  for i in range(2):
   cmd('actor',i,rng.choice([0,0x800000,0x8000000,0x200000]),7 if case%3==i else 0,2 if case%4==i else 0)
   cmd('parent',i,0x30,rng.choice([85,128,256,512]));cmd('parent',i,0x38,rng.getrandbits(32));cmd('parent',i,0x8c,rng.getrandbits(32))
   for off in range(0x40,0x70,4):cmd('parent',i,off,bits(rng.randrange(640)) if off in [0x40,0x44] else rng.getrandbits(32))
  cmd('gauge',4,case);cmd('gauge',5,case+1);cmd('update',case%2);check(('registry-update',case))
  cmd('draw-count',[0,1,510,511][case%4]);cmd('draw',case%2);cmd('draw',2);check(('registry-draw',case))
  cmd('begin');cmd('draw',2);check(('draw-reuse',case));cmd('visit',case%2);check(('registry-free',case))
  if case%24==23:flush()
 flush()
 #One-visit keepalive02000000 protects a completed object, then clears.
 cmd('reset',9001,0);cmd('spawn',7,0);cmd('object',256,0x108,0x02001000);cmd('object',256,0x104,0x100)
 cmd('visit',2);check('keepalive');assert p.read(reg(2),4)
 cmd('visit',2);check('free-next');assert not p.read(reg(2),4) and p.read(tp(256)+4,4)==2
 flush()
 report=dict(status='passed',quick=quick,snapshots=total,original_instructions=instructions,groups=dict(groups),functions=dict(counts),natural_traces=traces,
  elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,
  scope='Whole unmodified11f450,11d730,11d6c8,147028,146ef8,1470a8 and every reached callee. Shared256 task/object pools,all160 registry slots,complete raw objects and511 draw slots. Real resource51/action135 loops/free and resource00/action466->467 flights/landing; audible object command160 selects before source345188=0 disables playback. Original buffered libc,finite scalar compatibility model. Explicit phase composition with fixed actor parent inputs,not whole140270/1494f0,actual lock trigger,GS rendering,SPU playback or hardware FP. Callback mutation of other registry slots is not yet exercised; special170340/header400 remains unsupported.')
 target='auxiliary_frame_quick_validation.json' if quick else 'auxiliary_frame_validation.json'
 (ROOT/'outputs/ss6-feasibility'/target).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
