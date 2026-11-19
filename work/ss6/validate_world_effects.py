#!/usr/bin/env python3
"""Unmodified124430 and real shared112838/124898 particle lifecycles."""
import collections,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import pointer,handle,digest,TASKS,OBJECTS
from validate_scheduled_opening import DRAW_OFFSETS
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
BINARY=ROOT/'work/ss6/build-native/ss6-world-effect-probe';OWNERS=0x3d2e88
th=lambda a:handle(a,TASKS,52);oh=lambda a:handle(a,OBJECTS,320);hh=lambda a:handle(a,OWNERS,8)
bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 whirlwind="--whirlwind" in sys.argv
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 native_pin=hashlib.sha256(BINARY.read_bytes()).hexdigest();validator_pin=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 p=Probe(raw,finite_model=True);rng=random.Random(0x124430)
 actions_mode=whirlwind or "--actions" in sys.argv;body=None
 commands=[];expected=[];labels=[];counts=collections.Counter();instructions=snapshots=draws=0
 def words(at,values):
  vs=list(values);p.memory[at:at+4*len(vs)]=struct.pack(f'<{len(vs)}I',*[v&0xffffffff for v in vs])
 def readwords(at,n):return list(struct.unpack_from(f'<{n}I',p.memory,at))
 world_births=[]
 def watch(pc):
  if pc==0x124430:
   assert p.registers[4]==29,p.registers[4]
   world_births.append((p.registers[5],p.registers[6],*p.floats[12:16]))
 def run(fn,args=()):
  nonlocal instructions
  result,n=p.run(fn,args,limit=250000,observe=watch if whirlwind and fn in (0x11d730,0x11d8e0) else None);instructions+=n;counts[f'whole{fn:06x}']+=1;return result
 for bank,name in [(1,'01HitFlash.bin'),(2,'02Guard.bin'),(3,'03etc.bin'),(4,'04tenso.bin'),(5,'Display.bin'),(6,'Display2.bin'),(7,'Display3.bin')]:
  data=(ASSETS/name).read_bytes();base=0x4a4810+(bank-1)*0x3da0;p.memory[base:base+len(data)]=data
 aid=(ASSETS/'aid_00.bin').read_bytes();act=(ASSETS/'act_00.bin').read_bytes()
 for slot in range(2):
  base=0x1400000+slot*0x100000
  p.memory[0x46a9b0+slot*0x1800:0x46a9b0+(slot+1)*0x1800]=aid
  p.memory[base:base+len(act)]=act;p.write(0x4751b0+slot*4,base,4);p.write(0x46a9a0+slot*4,0,4)
 BODY_FIELDS=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,*range(0x4c,0x64,4),0x40,0x44]
 def fixture(seed,mode=3):
  nonlocal body
  body=None
  buffered_stdout(p);words(OWNERS,[0]*512);words(OBJECTS,[0]*(256*80));words(0x1232440,[0]*258);words(0x3d3698,[0]*257)
  run(0x1123a8);run(0x112570);run(0x11e290)
  words(0x4c3510,range(1,33));words(0x4c3658,((seed+i)%4 for i in range(44)));words(0x439a48,(seed+i*17 for i in range(72)))
  p.write(0x345188,0,4);p.write(0x123a0c0,0,1);p.write(0x4a2250,0,4)
  game=rng.getrandbits(32);library=rng.getrandbits(64)
  p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(p.read(0x5d1bf8,4)+0xa8,library,8)
  commands.append(f'fixture {seed} {mode&0xffffffff} {game} {library}')
 def snapshot():
  tasks=readwords(TASKS,256*13);objects=readwords(OBJECTS,256*80)
  for i in range(256):
   tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+6]=hh(tasks[i*13+6]);tasks[i*13+7]=oh(tasks[i*13+7])
   ref=tasks[i*13+8]
   if ref:
    if ref in [0x4a2b30+id*108 for id in [1,2,3,4,5,6,10,12,15,25,26,27,36,29,30,41,42]]:tasks[i*13+8]=0x100+(ref-0x4a2b30)//108
    else:
     assert 0x4a3e30<=ref<0x4a3e30+20*108 and (ref-0x4a3e30)%108==0,hex(ref)
     tasks[i*13+8]=(ref-0x4a3e30)//108
   objects[i*80]=oh(objects[i*80]);objects[i*80+78]=oh(objects[i*80+78])
  row=[p.read(0x3d3690,4),p.read(0x3d3688,4),th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),
       th(p.read(0x1232840,4)),p.read(0x3d3a98,4),digest(tasks),digest(objects),digest(map(th,readwords(0x1232440,256))),
       digest(readwords(0x3d3698,256)),digest(readwords(OWNERS,512)),digest(readwords(0x439a48,72)),
       digest(readwords(0x4c3510,32)),digest(readwords(0x4c3658,44)),signed(p.read(0x443150,4),32),p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,8)]
  count=p.read(0x4a2250,4);row.append(count)
  for i in range(count):
   obj=0x479250+i*0x148
   record=run(0x1233a0,[obj]);assert record
   row+=list(struct.unpack_from('<30H',p.memory,record))+[p.read(obj+off,4) for off in DRAW_OFFSETS]
  if body:row += [p.read(body+off,4) for off in BODY_FIELDS]+[p.read(body+0xfe,2)]+readwords(body+0x10c,3)
  return row
 def execute(command,label):
  nonlocal draws,body
  op,*vs=command.split();vs=list(map(int,vs))
  if op=='player':
   body=0x1e00000;p.memory[body:body+320]=bytes(320)
   for off,value in [(0xc,vs[0]),(0xcc,vs[0]),(0xc8,1),(0x104,0x200)]:p.write(body+off,value,4)
   run(0x120390,[body,0]);run(0x11dda0,[body]);run(0x11de10,[body]);run(0x11e1c0,[body])
  elif op=='request':run(0x11d908,[body,vs[0],0,vs[1]])
  elif op=='commit':run(0x11d8e0,[body])
  elif op in ['animate','move']:
   p.write(body+0x30,vs[0],4);run(0x11d730 if op=='animate' else 0x11d6c8,[body])
  elif op=='flags':
   for off,value in zip([0x38,0x104,0x108],vs):p.write(body+off,value,4)
  elif op=='pending':p.write(body+0xfe,vs[0],2)
  elif op=='motion':
   for off,value in zip([*range(0x4c,0x64,4),0x40,0x44],vs):p.write(body+off,value,4)
  elif op=='release':p.write(body+0x104,p.read(body+0x104,4)&~0x100,4)
  elif op=='world':
   p.floats[12:16]=vs[3:];run(0x124430,vs[:3])
  elif op=='tick':p.write(0x4a2250,0,4);p.write(0x46a924,vs[0],4);run(0x112838)
  elif op=='opening':run(0x1249c8,vs)
  elif op=='ending':p.floats[12:16]=list(map(bits,[320,240,-50,1]));run(0x124548,[vs[0],0x100000,0])
  elif op=='cancel':run(0x112a70,vs);run(0x11e3a0,vs)
  else:raise AssertionError(op)
  commands.append(command);expected.append(snapshot());labels.append(label);draws+=p.read(0x4a2250,4)
 def world(id,flags,slot,x,y,z=-10,scale=1):
  execute('world '+' '.join(map(str,[id,flags,slot,*map(bits,[x,y,z,scale])])),('birth',id,flags,slot,x,y))
 def flush():
  nonlocal snapshots
  assert hashlib.sha256(BINARY.read_bytes()).hexdigest()==native_pin,"Native executable changed during validation"
  result=subprocess.run([str(BINARY),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True)
  assert result.returncode==0,result.stderr
  actual=[list(map(int,row.split())) for row in result.stdout.splitlines()];assert len(actual)==len(expected),(len(actual),len(expected))
  for i,(got,want) in enumerate(zip(actual,expected)):
   assert got==want,(labels[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20],len(got),len(want))
  previous=snapshots;snapshots+=len(expected)
  if snapshots//5000!=previous//5000:print(f"verified {snapshots} snapshots",flush=True)
  commands.clear();expected.clear();labels.clear()
 if '--hanzo-throw' in sys.argv:
  for effect,slot in itertools.product((25,26,27),range(2)):
   fixture(90+slot);world(effect,slot<<19,slot,311.25,91.125)
   for t in range(100):execute(f'tick {int(12<=t<19)}',('Hanzo throw effect',effect,slot,t))
   assert all((p.read(OWNERS+i*8,4)&1)==0 for i in range(256))
   flush()
  report=dict(status='passed',groups=[25,26,27],snapshots=snapshots,ordered_draws=draws,original_instructions=instructions,elf_sha256=SOURCE_HASH,probe_sha256=native_pin)
  (ROOT/'outputs/ss6-feasibility/hanzo-throw-effect-validation.json').write_text(json.dumps(report,indent=2)+'\n')
  print(snapshots,'throw-effect snapshots');return
 if '--nakoruru-throw' in sys.argv:
  # ACT682 and its two alternate victim sequences spawn in the world path:
  # group 15 shares a contact descriptor but its tag and facing come from
  # the actor. The six random shards must consume twelve library RNG draws.
  for effect,slot in itertools.product((15,29),range(2)):
   fixture(80+slot);world(effect,slot<<19,slot,210.875,57.25)
   for t in range(95):execute(f'tick {int(12<=t<19)}',('nakoruru throw effect',effect,slot,t))
   assert all((p.read(OWNERS+i*8,4)&1)==0 for i in range(256))
   flush()
  report=dict(status='passed',groups=[15,29],snapshots=snapshots,ordered_draws=draws,original_instructions=instructions,elf_sha256=SOURCE_HASH,probe_sha256=native_pin,scope='Both seats and directions compared to 124430/124620 and full 112838/124898 schedules. Checks particle allocators, owner lifetime, texture references, both RNGs, raw draws, motion, color and retirement with and without a pause. Group15 uses the existing shared Japanese descriptor and six randomized shards, and group29 the single landing puff.')
  (ROOT/'outputs/ss6-feasibility/nakoruru_throw_effects_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(snapshots,'throw-effect snapshots',draws,'draw records');return
 if '--attack-effects' in sys.argv:
  for effect,slot in itertools.product((1,2,3,4,5,6,10,30,41,42),range(2)):
   fixture(50+slot);world(effect,slot<<19,slot,280.125,45)
   for t in range(180 if effect==6 else 80):execute(f'tick {int(8<=t<14)}',('attack effect',effect,slot,t))
   # Callback groups retain the active bit; randomized meditation particles can outlive 80 ticks.
   assert sum(bool(p.read(OWNERS+i*8,4)&1) for i in range(256))==int(effect in (1,4)),(effect,slot,p.read(OWNERS,4))
   flush()
  report=dict(status='passed',groups=[1,2,3,4,5,6,10,30,41,42],snapshots=snapshots,draws=draws,original_instructions=instructions)
  (ROOT/'outputs/ss6-feasibility/attack_world_effect_validation.json').write_text(json.dumps(report,indent=2)+'\n')
  print(snapshots,'attack world effect snapshots');return
 if not actions_mode:
  #Births retain arbitrary flag inputs only through081c0000, distinct task
  #tags per resource slot, and exactly two library draws per random particle.
  for case,(id,flags,mode,slot) in enumerate(itertools.product([12,36],[0,0x80000,0x40000,0xc0000,0xffffffff],[-2,0,3],[0,1,2])):
   fixture(case+1,mode);world(id,flags,slot,280.125+case/8,80.25)
   for visit in range(85):execute(f'tick {int(visit%11<3)}',('lifecycle',case,visit))
   assert all((p.read(OWNERS+i*8,4)&1)==0 for i in range(256))
   flush()
  #Interleaved captions and both world groups reuse the exact same owners,
  #objects/tasks and texture references. Cancel one tag without killing peers.
  for case in range(8):
   fixture(200+case);execute(f'opening {1 if case%2 else 10}',('shared',case,'opening'))
   for visit in range(260):
    if visit in [0,4,8,20,80,100,140,200]:world(12 if visit%8==0 else 36,(case%4)<<18,case%3,240+visit/8,80)
    if visit==23:execute('cancel '+str(((case%3+12*4)<<16)+0x1b5b),('shared',case,'cancel'))
    if visit==120:execute('ending 15',('shared',case,'ending'))
    execute(f'tick {int(visit%9==0)}',('shared',case,visit))
   flush()
 else:
  #Real original ACT entry emits124430; no fixture-generated particle event.
  #Release at140's zero-duration record is an explicit callback boundary,
  #not a claim that normal31 or the weapon-drop consumer is implemented.
  for case,(action,mirror,slot,delta) in enumerate(itertools.product((1284,1285) if whirlwind else range(137,141),range(4),range(2),[128,256,512])):
   fixture(case+1,case%3);execute(f'player {slot}',('player',case))
   execute(f'flags {0x10000000|(mirror<<18)} {0x18200} 0',('flags',case))
   vals=[0x12345,0,0,(-0x23456)&0xffffffff,0,0,bits(280.125),bits(20.5)]
   execute('motion '+' '.join(map(str,vals)),('initial-motion',case))
   execute(f'request {action} 1',('request',case));execute('commit',('commit',case))
   for visit in range(95):
    if visit in [3,6]:
     flag=p.read(body+0x104,4)
     execute(f'flags {p.read(body+0x38,4)} {flag|0x10 if visit==3 else flag&~0x10} {p.read(body+0x108,4)}',('freeze',case,visit))
    execute(f'animate {delta}',('animate',case,visit));execute(f'move {delta}',('move',case,visit))
    execute(f'tick {int(visit%13<2)}',('effect-tick',case,visit))
    if p.read(body+0x104,4)&0x100:execute('release',('explicit-hold-release',case,visit))
   execute(f'request {action} 0',('same-action-refusal',case));execute('commit',('refused-commit',case))
   execute(f'request {action} 1',('forced-reentry',case));execute('commit',('reentry',case))
   for visit in range(45):execute('tick 0',('drain',case,visit))
   flush()
 report=dict(status='passed',snapshots=snapshots,queued_draw_snapshots=draws,original_instructions=instructions,functions=dict(counts),
  elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,
  scope='Whole unmodified124430/124620 and112838/124898 with real allocators,random library316b90,texture references,buffered printf and muted audio. World descriptors12 and36,90 lifecycle traces and8 shared opening/ending/world traces,flags/resource-tag variations,cancellation,pause/resume,owner auto-release. Full256-slot normalized task/object/owner pools,scheduler heads/tags,72palette words,32texture slots/44refs,both RNGs and ordered30-field records+26-field draw snapshots. Finite scalar model. Actor ACT emission and gameplay callbacks are not yet connected; this is not a full frame,GS raster or live playable weapon lock proof.')
 if actions_mode:
  report['scope']='Whole unmodified120390,11d908,11d8e0,11d730 and11d6c8 for resource00 actions137..140, with actual120d10->124430 births and shared112838 effect scheduling. 96 traces cover both slots,all horizontal/vertical mirror combinations,128/256/512 increments,freeze/resume,same-action refusal and forced reentry. Compare actor body clock/flags/6motion words/positions/FE/10c..114 and all shared effect pools,RNGs,texture refs,ordered record/draw snapshots. ACT coordinates use signed high-halfword pending offsets before motion entry.140 zero-duration hold release is explicit callback fixture,not normal31 gameplay or real weapon drop. Buffered libc,muted body sounds,finite FP; no original code patched/skipped,GS/live proof.'
 if whirlwind:
  assert len(world_births)==32 and {v[1] for v in world_births}=={0,1},world_births
  assert {v[0] for v in world_births}=={0x10000000|(i<<18) for i in range(4)}
  assert all(v[4:]==(bits(-10),bits(1)) for v in world_births),world_births
  report.update(traces=48,act_world29_births=len(world_births),distinct_spawn_arguments=len(set(world_births)),scope='Resource00 ACT1284/1285 entered from real 120390/11d908/11d8e0/11d730/11d6c8. Both timeline slots, horizontal/vertical flags and three clock increments; the zero-duration first pose advances according to recorded motion and the explicit hold-release fixture. Confirm group29 births in 124430, then compare allocator tags, owner lifetime, draw order, position/depth/scale, actor body/clock/motion and RNG after each operation. Zero-duration holds explicitly released to exercise the ACT. Gameplay callback selection and hardware raster are outside this test.')
 target='whirlwind_world_effect_validation.json' if whirlwind else 'weapon_lock_action_validation.json' if actions_mode else 'world_effect_validation.json'
 (ROOT/'outputs/ss6-feasibility'/target).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
