#!/usr/bin/env python3
"""Whole original121b80, real palette allocation, packets and atlas writes."""
import collections,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
from character_tiles_oracle import fixture,begin,bits,ROOT,ASSETS,ATLAS
from extract_collision_tables import SOURCE_HASH
from validate_object_pools import digest
BIN=ROOT/'work/ss6/build-native/ss6-character-tiles-probe'
def main():
 quick='--quick' in sys.argv;p=fixture();rng=random.Random(0x121b80)
 native_pin=hashlib.sha256(BIN.read_bytes()).hexdigest();validator_pin=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 commands=[];expected=[];labels=[];quads=[];instructions=total_quads=0;counts=collections.Counter();groups=collections.Counter()
 def run(fn,args=()):
  nonlocal instructions
  _,n=p.run(fn,args,limit=800000,observe=observe);instructions+=n;counts[hex(fn)]+=1
 def observe(pc):
  if pc==0x108910:
   at=p.registers[4];assert p.registers[5]==4
   quads.append([p.read(at+i*4,4) for i in range(24)]+[p.registers[6]&0xffffffff,p.read(0x3a8e44,4),p.read(0x348b10,4)])
 def words(at,n,fmt='I'):return list(struct.unpack_from(f'<{n}{fmt}',p.memory,at))
 def snapshot(label):
  nonlocal total_quads
  r=[p.read(0x3eb910,4),p.read(0x3db8f8,4),p.read(0x3db900,4),p.read(0x3a8e44,4)]
  for at,n,fmt in [(0x439a48,24,'I'),(0x439aa8,24,'I'),(0x439b08,24,'I'),(0x43ab70,1024,'H'),(0x43b370,1024,'I'),(0x439b70,1024,'I'),(0x11e7980,1024,'I')]:r.append(digest(words(at,n,fmt)))
  r += [digest(p.memory[0x3f8a40:0x439a40]),digest(p.memory[ATLAS:ATLAS+131072]),len(quads)]
  r += [v for q in quads for v in q];total_quads+=len(quads);commands.append('snapshot');expected.append(r);labels.append(label);groups[label[0]]+=1
  if len(expected)%100==0:print('validated original snapshots',len(expected),flush=True)
 def start(seed=0,count=0,zcount=0):
  quads.clear();begin(p,seed,count,zcount);commands.append(f'begin {seed} {count} {zcount}')
 def render(disabled=0,flags=0,color=0,amount=0):
  commands.append(f'render {disabled} {flags} {color} {amount}')
  for at,v in [(0x3ec73c,disabled),(0x3ebf18,flags),(0x3ec730,color),(0x3ec734,amount)]:p.write(at,v,4)
 def cache(row,index,value):commands.append(f'cache {row} {index} {value&0xffffffff}');p.write(0x439a48+(row*24+index)*4,value,4)
 def sprite(s):
  commands.append('sprite '+' '.join(str(v&0xffffffff) for v in s))
  for at,v in [(0x479244,s[10]),(0x3db900,s[11]),(0x47923c,s[12]),(0x479240,s[13]),(0x348b10,s[14]),(0x1239d8c,s[15])]:p.write(at,v,4)
  p.floats[12:17]=s[5:10];run(0x121b80,s[:5])
 def default(slot,palette,image,flags=0x10,color=0xff808080):return [slot,palette,image,flags,0,*map(bits,[280.125,210.75,-10,1,1]),1,color,0,0xffffffff,0,bits(.25)]
 entries=[]
 for slot,res,actions in [(0,0,[185,186,190,466,467,499]),(1,0,[466,467]),(2,51,[135])]:
  aid=(ASSETS/f'aid_{res:02}.bin').read_bytes();act=(ASSETS/f'act_{res:02}.bin').read_bytes();pil=(ASSETS/f'pil_{res:02}.bin').read_bytes();seen=set()
  for action in actions:
   startrec=struct.unpack_from('<h',aid,action*2)[0]
   for step in range(aid[0x1000+action]):
    for ref in struct.unpack_from('<5h',act,(startrec+step)*60+4):
     if ref<=0:continue
     image,_,_,_,color,flags,_=struct.unpack_from('<hhhhIHH',pil,(ref-1)*16)
     if image<=0 or (image,flags,color) in seen:continue
     seen.add((image,flags,color));entries.append(default(slot,res*5,image-1,flags,color))
 render()
 for case,source in enumerate(entries):
  for mirror,scale,rot in itertools.product(range(1 if quick else 4),[1,.73125],[0,0x2000]):
   start(case,0,case%7);s=source.copy();s[3]|=mirror<<18|rot;s[8]=bits(scale);s[9]=bits(scale if case%2 else scale*.15);s[10]=2 if s[3]&0x20 else 1;s[14]=int(s[10]==2)
   #Release prior-use marks via the same shared state, retaining color copies.
   for i in range(24):cache(1,i,0)
   sprite(s);snapshot(('images',case,mirror,scale,rot))
 for case in range(20 if quick else 240):
  start(case);s=rng.choice(entries).copy();s[3]|=rng.randrange(4)<<18|rng.choice([0,0x2000,0x80000000]);s[12]=rng.choice([0,0x10000,0x2000,0x8000])
  s[5:10]=list(map(bits,[rng.choice([-100,-32,-.5,0,639.5,640,700]),rng.choice([-100,-32,-.5,0,447.5,448,500]),rng.choice([-80,-10,0,20]),rng.choice([.5,.73125,1,1.25]),rng.choice([.15,.5,1,1.25])]))
  s[10]=rng.choice([1,2,3]);s[11]=rng.choice([0,0x013f7fbf,0xff808080,0xff818181,0x80ffffff,0xffc8c8c8]);s[14]=rng.randrange(2);s[15]=bits(rng.choice([-.25,0,1.125]))
  render(disabled=int(case%19==0),flags=rng.choice([0,2]),color=rng.getrandbits(32),amount=rng.choice([0,1,127,256]))
  for i in range(24):cache(1,i,0)
  sprite(s);snapshot(('edges',case))
 render()
 #Full cache: every slot is reserved. No quad/depth allocation can happen.
 for i in range(24):cache(2,i,1)
 start(77);sprite(default(2,255,409));snapshot(('palette-full',))
 for i in range(24):cache(2,i,0);cache(0,i,0xffffffff);cache(1,i,0)
 for count in [0,1022,1023,1024]:
  start(78,count,255);sprite(default(0,0,678));sprite(default(2,255,409));snapshot(('atlas-capacity',count))
 #Compose real1208b0 body/shadow preparation with enabled121b80 and packet
 #callees. No synthetic intermediary sprite is supplied at this boundary.
 render()
 for case,(slot,action,mirror) in enumerate(itertools.product(range(3),[0,1,2],range(1 if quick else 4))):
  aid=(ASSETS/f'aid_{[0,0,51][slot]:02}.bin').read_bytes();action=135 if slot==2 else [186,466,467][action]
  for step in range(aid[0x1000+action]):
   start(case);o=[0]*82;o[3]=o[4]=slot;o[7]=[0,0,255][slot];o[9]=action;o[10]=step;o[0x38//4]=0x10000000|(mirror<<18)
   o[0x40//4]=bits(280.125);o[0x44//4]=bits(55.25);o[0x48//4]=bits(-10);o[0x70//4]=bits(.73125 if step%2 else 1);o[0x8c//4]=0xffffffff;o[0xb0//4]=bits(.125)
   camera=list(map(bits,[320,120,-400,0,-120]));controls=[0,0,0xfffffffe,15 if case%3==0 else 0]
   commands.append('object '+' '.join(map(str,[*o,*camera,*controls])))
   at=0x1e00000;p.memory[at:at+328]=struct.pack('<82I',*o)
   for addr,value in zip([0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68,0x46a918,0x46a91c,0x46a948,0x4c3808],[*camera,*controls]):p.write(addr,value,4)
   p.write(0x4a2a64,bits(-160),4)
   for i in range(24):cache(1,i,0)
   #Release commands must precede the native object as they do the original.
   object_command=commands.pop(-25);commands.append(object_command)
   run(0x1208b0,[at]);snapshot(('object-composition',slot,action,step,mirror))
 #All1024 color entries exercise whole116588 with actual16/32-bit branches.
 for i in range(1024):
  for op,at,value,size in [('raw16',0x43ab70,rng.getrandbits(16),2),('raw32',0x43b370,rng.getrandbits(32),4),('format',0x439b70,i%3==0,4),('tone',0x3ebf30,rng.choice([0,1,2,4,5,8]),2)]:
   commands.append(f'{op} {i} {int(value)}');p.write(at+i*size,value,size)
 for flags,amount in itertools.product([0,1,2,4,8],[0,1,127,256]):
  color=rng.getrandbits(32);render(flags=flags,color=color,amount=amount)
  commands.append(f'colorize {flags} {color} {amount}');run(0x116588);snapshot(('palette-color',flags,amount))
 result=subprocess.run([str(BIN),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected),(len(actual),len(expected))
 for label,a,e in zip(labels,actual,expected):
  assert a==e,(label,[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(a,e)) if x!=y][:20],len(a),len(e))
 report=dict(status='passed',quick=quick,snapshots=len(expected),quad_snapshots=total_quads,source_sprite_entries=len(entries),groups=dict(groups),original_instructions=instructions,functions=dict(counts),
  elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,probe_sha256=hashlib.sha256((ROOT/'work/ss6/mips_probe.py').read_bytes()).hexdigest(),oracle_sha256=hashlib.sha256((ROOT/'work/ss6/character_tiles_oracle.py').read_bytes()).hexdigest(),
  scope='Whole1208b0 composition plus whole unmodified121b80 with real115d40/116478 palette allocation,108910 packet construction,114e00 depth and CHR copies; raster-disable0 except explicit disable tests. Entire retained512x5124bpp atlas,all24shared palette keys/use/reservations,source palette transparent mutation,raw16/raw32/type/converted1024colors,all4vertex24words/palette/blend/additive arguments and counters compared. Ordinary palette mode0 from actual resource00/resource51,all chosen body/heavy/lock/drop/common/victory images,mirrors,transpose,scales,clipping,color overrides and global tint,full palette/1024group capacities. Whole116588 exercises both cache formats/global/per-color tones. Original packet callees execute but native comparison stops at108910 arguments,not GS raster/VRAM/hardware/live match. Finite FP model,buffered libc; no patched/skipped callees.')
 path=ROOT/'outputs/ss6-feasibility'/('character_tiles_quick_validation.json' if quick else 'character_tiles_validation.json');path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
