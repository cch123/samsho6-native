#!/usr/bin/env python3
"""Whole1208b0 and real nested preparation, with original raster-disable flag.

A read-only instruction observer records every121b80 entry. That function
executes its own3ec73c gate/return; no instructions or callees are replaced.
This proves submission parameters, NOT tile/palette/GS packet output.
"""
import collections,hashlib,itertools,json,random,struct,subprocess,sys
from pathlib import Path
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
BIN=ROOT/'work/ss6/build-native/ss6-character-draw-probe'
O=0x1e00000
GLOBALS=[0x47923c,0x479240,0x3db900,0x479244,0x348b10,0x1239d8c]
bits=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
def main():
 quick='--quick' in sys.argv;raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw,finite_model=True);rng=random.Random(0x1208b0)
 native_pin=hashlib.sha256(BIN.read_bytes()).hexdigest();validator_pin=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 aids=[]
 for slot,res in enumerate([0,0,51]):
  aid=(ASSETS/f'aid_{res:02}.bin').read_bytes();act=(ASSETS/f'act_{res:02}.bin').read_bytes();pil=(ASSETS/f'pil_{res:02}.bin').read_bytes();aids.append(aid)
  p.memory[0x46a9b0+slot*0x1800:0x46a9b0+(slot+1)*0x1800]=aid
  for pointer,data,base in [(0x4751b0,act,0x1400000+slot*0x100000),(0x4751c8,pil,0x1800000+slot*0x80000)]:
   p.memory[base:base+len(data)]=data;p.write(pointer+slot*4,base,4)
 #This is an actual global branch in121b80, not a patched/stubbed callee.
 p.write(0x3ec73c,1,4)
 commands=[];expected=[];labels=[];counts=collections.Counter();groups=collections.Counter();instructions=sprites=shadows=0
 state=[0x11223344,0x55667788,0x99887766,17,19,bits(1.25)]
 commands.append('state '+' '.join(map(str,state)))
 for at,v in zip(GLOBALS,state):p.write(at,v,4)
 def observe(pc):
  if pc in [0x1212c0,0x1213a8,0x121890,0x121b80,0x30bb20,0x1142b8,0x1142c8]:counts[hex(pc)]+=1
  if pc==0x121b80:
   collected.extend([*(v&0xffffffff for v in p.registers[4:9]),*p.floats[12:17],p.read(0x479244,4),p.read(0x3db900,4),p.read(0x47923c,4),p.read(0x479240,4),p.read(0x348b10,4),p.read(0x1239d8c,4)])
 def check(label,o,camera=None,clocks=(0,0),focus=-2,stage=0):
  nonlocal instructions,collected,sprites,shadows
  if camera is None:camera=list(map(bits,[320,120,-400,0,-120]))
  packed=struct.pack('<82I',*(v&0xffffffff for v in o));p.memory[O:O+328]=packed
  for at,v in zip([0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68],camera):p.write(at,v,4)
  p.write(0x4a2a64,bits(-160),4)
  for at,v in [(0x46a918,clocks[0]),(0x46a91c,clocks[1]),(0x46a948,focus),(0x4c3808,stage)]:p.write(at,v,4)
  collected=[]
  _,n=p.run(0x1208b0,[O],limit=200000,observe=observe);instructions+=n
  assert p.memory[O:O+328]==packed
  count=len(collected)//16;sprites+=count;shadows+=sum(collected[i+4] for i in range(0,len(collected),16))
  expected.append([*(p.read(at,4) for at in GLOBALS),count,*collected]);labels.append(label);groups[label[0]]+=1
  commands.append('draw '+' '.join(str(v&0xffffffff) for v in [*o,*camera,*clocks,focus,stage]))
 def fixture(slot,action,step):
  o=[0]*82;o[3]=slot;o[4]=slot;o[7]=[0,0,255][slot];o[9]=action;o[10]=step
  o[0x38//4]=0x10000000;o[0x40//4]=bits(280.125);o[0x44//4]=bits(37.25);o[0x48//4]=bits(-10)
  o[0x70//4]=bits(1);o[0x8c//4]=0xffffffff;o[0xb0//4]=bits(0.25);return o
 collected=[]
 cases=[]
 actions=[0,1,10,11,12,13,44,45,50,51,137,138,139,140,185,186,189,190,192,195,196,286,287,290,291,342,466,467,499]
 for slot in range(3):
  for action in ([135] if slot==2 else actions):
   for step in range(aids[slot][0x1000+action]):cases.append((slot,action,step))
 for slot,action,step in cases:
  for mirror,mode in itertools.product(range(4),[0,0x200000,0x100000,0x20000000]):
   if quick and mode not in [0,0x100000]:continue
   o=fixture(slot,action,step);o[0x38//4]|=mirror<<18|mode
   if (step+mirror)%2:o[0x70//4]=bits(.73125)
   check(('records',slot,action,step,mirror,mode),o)
 for case in range(100 if quick else 2000):
  slot,action,step=rng.choice(cases);o=fixture(slot,action,step)
  o[0x38//4]|=rng.choice([0,0x800000,0x40000000,0x40800000])|rng.randrange(4)<<18
  for flag in [0x10000,0x1000,0x8000,0x100000,0x200000,0x20000000]:
   if rng.randrange(2):o[0x38//4]|=flag
  o[0x104//4]=rng.choice([0,0x1000,2,0x1002]);o[0x8c//4]=rng.choice([0xffffffff,0xff808080,0x80604020,0x33000000,0,0x013f7fbf])
  o[0x40//4]=bits(rng.choice([-12.25,0,280.125,320,600.75]));o[0x44//4]=bits(rng.choice([-50,-.5,0,80.25]))
  o[0x48//4]=bits(rng.choice([-80,-10,0,20]));o[0x70//4]=bits(rng.choice([.25,.5,.73125,1,1.125,2]))
  o[0xe4//4]=rng.choice([-128,-1,0,10,16777217])&0xffffffff;o[0xe8//4]=rng.choice([-64,0,3])&0xffffffff
  o[0xec//4]=bits(rng.choice([-.75,0,.125,1.25]));o[0xf0//4]=bits(rng.choice([-1.125,0,.75]))
  o[0x4c//4]=rng.getrandbits(32);o[0x58//4]=rng.getrandbits(32);o[0xb4//4]=bits(rng.choice([-12.5,0,10]))
  o[0xb0//4]=bits(rng.choice([-.25,0,1.125]));o[0x20//4]=rng.choice([0,1,4,0xfffffffe]);o[0x10//4]=rng.randrange(3)
  o[0x138//4]=rng.getrandbits(32);o[0x13c//4]=rng.getrandbits(32)
  camera=list(map(bits,[rng.choice([160,320,480]),rng.choice([120,150,200]),rng.choice([-400,-480,-640]),rng.choice([0,-10]),rng.choice([-120,-100])]))
  check(('flags-offsets',case),o,camera,clocks=(rng.randrange(4),rng.randrange(4)),focus=rng.choice([-2,-1,0,1,2]),stage=rng.choice([0,14,15,16,17]))
 #The queue was already copied: unrelated live pools are overwritten before
 #decoding; neither native nor original renderer may dereference owner links.
 for slot,action,step in [(0,466,7),(1,467,0),(2,135,5)]:
  o=fixture(slot,action,step);o[0]=o[1]=o[0x118//4]=0xdeadbeef
  check(('detached-snapshot',slot),o)
 result=subprocess.run([str(BIN),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected),(len(actual),len(expected))
 for label,a,e in zip(labels,actual,expected):
  assert a==e,(label,[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(a,e)) if x!=y],len(a),len(e))
 assert counts['0x1142b8']>0 and shadows>0
 report=dict(status='passed',quick=quick,snapshots=len(expected),sprites=sprites,shadow_sprites=shadows,groups=dict(groups),
  original_instructions=instructions,functions=dict(counts),elf_sha256=SOURCE_HASH,native_sha256=native_pin,validator_sha256=validator_pin,
  probe_sha256=hashlib.sha256((ROOT/'work/ss6/mips_probe.py').read_bytes()).hexdigest(),
  scope='Whole1208b0/1212c0/1213a8/121890 with actual121b80 raster-disable3ec73c=1 gate,unchanged math-library floor and color-selection callees. Read-only instruction observer captures all121b80 arguments and render context; all six final globals and unchanged queued bytes compared. Resource00 selected body/light/heavy/lock/weapon/victory ACT records and resource51common135,all PIL layers/slots,mirrors,shadow/no-shadow/screen/depthscale,offset order,1041000 facing exception,current clock/focus dimming,color precedence,black/additive gates,stage15/16,persistent hidden state,detached owners. Finite FPmodel; no tile/palette lookup,GS packet/raster or actual hardware/live-match equivalence claim.')
 out=ROOT/'outputs/ss6-feasibility'/('character_draw_quick_validation.json' if quick else 'character_draw_validation.json');out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
