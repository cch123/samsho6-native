#!/usr/bin/env python3
"""Whole weapon creation and admitted auxiliary action/landing paths."""
import collections,hashlib,json,random,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import pointer,handle,digest
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
BINARY=ROOT/'work/ss6/build-native/ss6-auxiliary-objects-probe'
TASKS=0x122f040;OBJECTS=0x456900;ACTORS=0x1c00000;PARENT=0x1b00000;BATTLE=0x1900000;CONTEXT=0x1b01000
ACT=[0x800000,0xa00000,0xc00000]
def floatbits(v):return struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 quick='--quick' in sys.argv;lock_drop='--lock-drop' in sys.argv
 native_pin=hashlib.sha256(BINARY.read_bytes()).hexdigest()
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x170440);groups=collections.Counter();coverage=collections.Counter();instructions=0;commands=[];expected=[];labels=[];total=0
 tp=lambda h:pointer(h,TASKS,52);op=lambda h:pointer(h,OBJECTS,320)
 th=lambda a:handle(a,TASKS,52);oh=lambda a:handle(a,OBJECTS,320)
 cached={c:((ASSETS/f'aid_{c:02}.bin').read_bytes(),(ASSETS/f'act_{c:02}.bin').read_bytes()) for c in range(49)}
 def native_row(row):
  row=list(row);row[1]=th(row[1]);row[78]=oh(row[78]);owner=row[0x118//4]
  if owner:assert owner in [ACTORS,ACTORS+0xf2c];row[0x118//4]=(owner-ACTORS)//0xf2c+1
  ref=row[0xbc//4]
  for base in ACT:
   if base<=ref<base+0x200000:row[0xbc//4]=ref-base+1;break
  return row
 def flush():
  nonlocal total
  if not commands:return
  assert hashlib.sha256(BINARY.read_bytes()).hexdigest()==native_pin,'Native changed during comparison'
  result=subprocess.run([str(BINARY),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
  assert result.returncode==0,(result.stderr,labels[len(result.stdout.splitlines())] if len(result.stdout.splitlines())<len(labels) else '')
  actual=[[int(v) for v in line.split()] for line in result.stdout.splitlines()]
  assert len(actual)==len(expected),(len(actual),len(expected))
  for i,(got,want) in enumerate(zip(actual,expected)):
   assert got==want,(labels[i],[(j,hex(a),hex(b)) for j,(a,b) in enumerate(zip(got,want)) if a!=b][:20])
  total+=len(expected);print('auxiliary',total,'passed',flush=True);commands.clear();expected.clear();labels.clear()
 def check(operation,case,character=0,resource=None,player=0,kind=4,armed=True,mode=3,flags=None,hole=0,handler=0,dx=12,dy=24,action=466,request_flags=3,y=None,muted=False):
  nonlocal instructions
  resource=character if resource is None else resource
  slots=[resource,resource,resource];slot=case%3
  actor=ACTORS+player*0xf2c;registry=BATTLE+0x29c+player*0x108
  for i,c in enumerate(slots):
   aid,act=cached[c];p.memory[0x46a9b0+i*0x1800:0x46a9b0+(i+1)*0x1800]=aid;p.memory[ACT[i]:ACT[i]+len(act)]=act
   p.write(0x4751b0+i*4,ACT[i],4);p.write(0x46a9a0+i*4,c,4)
  parent=[rng.getrandbits(32) for _ in range(80)];child=[rng.getrandbits(32) for _ in range(80)]
  parent[0xc//4]=slot;parent[0xcc//4]=player;parent[0x40//4]=floatbits(rng.randrange(-512,2048)/4);parent[0x44//4]=floatbits(rng.randrange(-64,512)/4)
  #Pointer fields use valid opaque identities; payload sentinels elsewhere
  #catch unintended clearing and retained Z motion/allocator tail changes.
  child[1]=child[2]=child[0x118//4]=child[0xbc//4]=child[78]=0
  child[0xc//4]=slot;child[0xcc//4]=kind;child[0x14//4]=resource
  child[0x24//4]=466 if case%2 else 0;child[0x28//4]=0
  child[0x40//4]=floatbits(320);child[0x44//4]=floatbits(y if y is not None else [0,1,15,16,17,-1][case%6])
  #Audio is enabled for creation (all reached records are silent). Landing
  #on audible467 is tested only under the source's explicit mute bit.
  child[0x104//4]=(rng.getrandbits(32)&~0x200)|(0x200 if muted else 0)
  if operation==5:child[0xfc//4]&=0xffff #normal landing has no pending actor flags
  flags=(rng.getrandbits(32)&~0x1000)|(0x1000 if armed else 0) if flags is None else flags
  game=rng.getrandbits(32);library=rng.getrandbits(64);tag=rng.getrandbits(32)
  data=[operation,*slots,player,character,flags,mode&0xffffffff,game,library,hole,kind,tag,handler,dx&0xffffffff,dy&0xffffffff,action,request_flags,*parent,*child]
  p.memory[ACTORS:ACTORS+2*0xf2c]=bytes([0xa5])*(2*0xf2c);p.memory[BATTLE:BATTLE+0x1000]=bytes([0x5a])*0x1000
  p.memory[PARENT:PARENT+320]=struct.pack('<80I',*parent)
  p.write(actor,PARENT,4);p.write(actor+0xa10,character,4);p.write(actor+0xa24,player,4);p.write(actor+0x23c,flags,4)
  p.write(0x4d3d08,ACTORS,4);p.write(0x4d3d00,BATTLE,4);p.write(BATTLE+0x24c+player*4,actor,4)
  p.write(CONTEXT,actor,4);p.write(CONTEXT+4,PARENT,4);p.write(CONTEXT+8,0,4)
  #Set the same preexisting singleton fixture as the native codec, while
  #keeping the original free-list initialization and every callee intact.
  p.run(0x112570);p.memory[OBJECTS:OBJECTS+256*320]=bytes(256*320);p.run(0x11e290)
  p.memory[OBJECTS:OBJECTS+320]=struct.pack('<80I',*child);p.write(TASKS,0x1701c0,4);p.write(TASKS+0x1c,OBJECTS,4)
  reg=[tp(1)]*48
  if hole<48:reg[hole]=0
  p.memory[registry:registry+192]=struct.pack('<48I',*reg)
  buffered_stdout(p);p.memory[0x1a00000:0x1a10000]=bytes(65536)
  reent=p.read(0x5d1bf8,4);p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(reent+0xa8,library,8)
  before_actor=bytes(p.memory[ACTORS:ACTORS+2*0xf2c]);before_battle=bytes(p.memory[BATTLE:BATTLE+0x1000])
  if operation==9:p.write(0x132c0e8,dx,4) # referee body +40, the release position
  pc,args={0:(0x11d9c8,[OBJECTS,PARENT,kind]),1:(0x140c68,[player,tag,kind,handler]),
           2:(0x170440,[actor]),3:(0x170070,[CONTEXT,dx,dy]),4:(0x170240,[CONTEXT]),
           5:(0x1701c0,[TASKS]),6:(0x147540,[TASKS]),7:(0x11d908,[OBJECTS,action,request_flags&1,(request_flags>>1)&1]),8:(0x16ffb0,[CONTEXT]),9:(0x170480,[player])}[operation]
  p.finite_model=operation in (7,9) #random prior motion words can need CVT.S.W rounding
  result,n=p.run(pc,[signed(v&0xffffffff,32) for v in args],limit=30000);instructions+=n
  result=oh(result&0xffffffff) if operation in [1,2,3,4,8,9] else 0
  tasks=list(struct.unpack('<3328I',p.memory[TASKS:TASKS+256*52]));objects=[]
  for i in range(256):
   tasks[i*13+3]=th(tasks[i*13+3]);tasks[i*13+7]=oh(tasks[i*13+7])
   objects.extend(native_row(struct.unpack('<80I',p.memory[OBJECTS+i*320:OBJECTS+(i+1)*320])))
  actual_flags=p.read(actor+0x23c,4)
  expected.append([result,actual_flags,p.read(0x3d2e80,4),p.read(reent+0xa8,8),th(p.read(0x1232844,4)),oh(p.read(0x46a900,4)),p.read(0x46a904,4),digest(tasks),digest(objects),
                   *[th(p.read(registry+i*4,4)) for i in range(48)],*(objects[(result-1)*80:result*80] if result else objects[:80])])
  commands.append(' '.join(map(str,data)));labels.append((operation,case,character,resource,player,mode,hole,y,muted))
  for i,v in enumerate(before_actor):
   if not actor+0x23c<=ACTORS+i<actor+0x240:assert p.memory[ACTORS+i]==v,(hex(ACTORS+i),'actor')
  for i,v in enumerate(before_battle):
   if not registry<=BATTLE+i<registry+192:assert p.memory[BATTLE+i]==v,(hex(BATTLE+i),'battle')
  assert p.memory[PARENT:PARENT+320]==struct.pack('<80I',*parent)
  groups[hex(pc)]+=1
  if result and operation in [2,3,4,8]:coverage['launch_vx:'+str(signed(objects[(result-1)*80+0x50//4],32))]+=1
  if operation==5:coverage['landing_taken:'+str(tasks[0]==0x147540)]+=1
  if len(commands)>=128:flush()
 if '--delivery' in sys.argv:
  for player in range(2):
   for n in range(24):
    check(9,n,character=48 if n==0 else 0,player=player,armed=False,hole=n%48,dx=floatbits((-60.5,241.25,320.,642.)[n%4]))
  flush()
  report=dict(status='passed',cases=total,elf_sha256=SOURCE_HASH,original_instructions=instructions)
  (ROOT/'outputs/ss6-feasibility/shin_weapon_delivery_validation.json').write_text(json.dumps(report,indent=2)+'\n')
  return
 if lock_drop:
  for c in range(51):
   for mode in [0,-2,3]:
    for k in range(6):
     check(8,k,character=c,resource=c if c<49 else 33,player=k%2,mode=mode,armed=k%3!=0,hole=[0,17,47][k%3])
  flush()
  report=dict(status='passed',cases=total,groups=dict(groups),coverage=dict(coverage),original_instructions=instructions,
   elf_sha256=SOURCE_HASH,native_probe_sha256=native_pin,
   scope='Whole unmodified16ffb0 with168ea0(kind3) and real170070/170240,112300,allocators/action entry.51 actor IDs,explicit resident mapping33 for49/50,three RNG modes,both players,all three resource slots,armed/unarmed and registry holes0/17/47. Complete pools/registry/parent and unrelated actor/battle bytes. Exact finite model,no instruction/callee changes. Weapon creation only,not animation/scheduling/GS/audio or live gameplay.')
  (ROOT/'outputs/ss6-feasibility/weapon_lock_drop_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return
 chars=[0,33,42,48] if quick else range(49)
 for c in chars:
  for kind in [4,6]:
   for k in range(2 if quick else 6):check(0,k,character=c,kind=kind)
  for k in range(2 if quick else 6):check(1,k,character=c,player=k%2,kind=4 if k%2 else 6,hole=[0,17,47,48,1,25][k],handler=0 if k%2 else 0x1701c0)
  for mode in [0,-2,3]:
   for k in range(2 if quick else 6):check(2,k,character=c,player=k%2,mode=mode,armed=k%3!=0)
 #Character49/50 are explicit actor IDs with a supplied resident mapping;
 #this does not claim their unresolved input binding aliases are implemented.
 for c in [49,50]:
  for k in range(6):check(2,k,character=c,resource=33,player=k%2,mode=k-2)
 for k in range(8 if quick else 128):
  check(3,k,character=33,player=k%2,dx=rng.randrange(-32768,32768),dy=rng.randrange(-32768,32768),mode=[0,-2,3][k%3])
  check(4,k,character=[0,11,33,43,48][k%5],player=k%2,mode=[0,-2,3][k%3])
 #Whole action requests cover immediate/deferred, force/duplicate and facing
 #toggle pending100. All enabled-audio cases use silent records0/466/468.
 for k in range(8 if quick else 192):
  check(7,k,character=k%43,kind=4 if k%2 else 6,action=[0,466,468][k%3],request_flags=k%4)
 #Threshold includes the adjacent binary32 values, not only whole heights.
 ys=[-1,-0.0,0,15,struct.unpack('<f',struct.pack('<I',0x417fffff))[0],16,struct.unpack('<f',struct.pack('<I',0x41800001))[0],17]
 for c in ([33,38] if quick else range(43)):
  for k,y in enumerate(ys):check(5,k,character=c,y=y,muted=c not in [32,34,38,39])
 for k in range(4 if quick else 64):check(6,k,character=k%43)
 flush()
 if quick:print('Protocol check only; report not overwritten');return
 report=dict(status='passed',cases=total,groups=dict(groups),coverage=dict(coverage),original_instructions=instructions,
  elf_sha256=SOURCE_HASH,native_probe_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Whole11d9c8/140c68(kind4/6),170440(including48special),170070,170240,11d908(admitted silent actions0/466/468),1701c0(muted or silent467),147540. All reached callees execute unchanged, real buffered libc; exact finite except192 action-request cases explicitly using finite ScalarFloat model for randomized motion words. Complete pools/registry/parent and unrepresented actor/battle preservation. Resource0..48 and both players, independent actor49/50 with explicit resident resource33. Native startup/commit uses original AID/ACT records,including motion and JDG flags; no rendering/audio/scheduler integration or complete enabled-audio landing claim.173108 damage registration and170340 special completion remain pending.')
 (ROOT/'outputs/ss6-feasibility/auxiliary_object_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
