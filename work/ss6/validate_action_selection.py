#!/usr/bin/env python3
"""Whole original selectors and facing helpers, without action dispatch."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2];ACTOR=0x1c00000;BODY=0x1d00000;OTHER=0x1b00000;INPUT=0x1e00000
def sparse(values):
 pairs=[(i,v) for i,v in enumerate(values) if v];return [len(pairs)]+[v for pair in pairs for v in pair]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x1501e8);commands=[];expected=[];counts={};instructions=0
 p.write(0x4d3d08,ACTOR,4);p.write(ACTOR,BODY,4);p.write(ACTOR+0xf2c,OTHER,4);p.write(ACTOR+0xa24,0,4)
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 def original(address,args):
  nonlocal instructions
  v,n=p.run(address,args,limit=30000);counts[hex(address)]=counts.get(hex(address),0)+1;instructions+=n;return signed(v,32)
 def put_config(c):
  system,character,*d=c;p.memory[ACTOR+0x10c:ACTOR+0x120]=struct.pack('<5I',system,0,character,0,0)
  p.write(0x4c38a8,6,4);p.memory[0x12d2308:0x12d2318]=bytes(d)
 def put_actor(a):
  flags244,flags248,byte,state,alias,character,variant,bodyFlags,pending,x,other=a[1:]
  for off,v,size in [(0x23c,a[0],4),(0x244,flags244,4),(0x248,flags248,4),(0x24c,byte,1),(0x194,state,4),(0x1a4,alias,4),(0xa10,character,4),(0xa48,variant,4)]:p.write(ACTOR+off,v,size)
  p.write(BODY+0x38,bodyFlags,4);p.write(BODY+0xfe,pending,2)
  p.memory[BODY+0x40:BODY+0x44]=struct.pack('<f',x);p.memory[OTHER+0x40:OTHER+0x44]=struct.pack('<f',other)
 def select(op,a,state,threat,c,f,recognized):
  put_actor(a);put_config(c)
  p.memory[INPUT:INPUT+684]=struct.pack('<171I',*f);p.memory[INPUT+0x2ac:INPUT+0x328]=struct.pack('<31I',*recognized)
  address={'normal':0x1501e8,'system_normal':0x150410,'attack':0x150620,'chain':0x150850,'restricted_normal':0x150dd8,'supplemental':0x150b60,'system_only':0x150aa8}[op]
  value=original(address,[ACTOR,INPUT,state,state if op in ['supplemental','system_only'] else int(threat)])
  commands.append(' '.join(map(str,[op,*a,state,int(threat),*c,*sparse(f),*sparse(recognized)])))
  expected.append([value,p.read(BODY+0x38,4),signed(p.read(ACTOR+0xa48,4),32)])
 #Every transition cell, including255 refusal and the two raw-flag remaps.
 for kind,columns in [(0,31),(1,17),(2,17)]:
  for state,column,flags in itertools.product(range(64),range(columns),[0,0x1000,0x800000,0x801000]):
   p.write(ACTOR+0x23c,flags,4);v=original([0x1505d0,0x1507e0,0x150a38][kind],[ACTOR,state,column])
   commands.append(f'map {kind} {state} {column} {flags}');expected.append([v])
 #Exact14f5d8 including system8->5 and custom descriptor byte4.
 for system,byte in itertools.product(range(9),range(256)):
  d=descriptors[0].copy();d[4]=byte;c=[system,0,*d];put_config(c)
  commands.append(' '.join(map(str,['system',*c])));expected.append([original(0x14f5d8,[ACTOR+0x10c])])
 for state in range(64):
  commands.append(f'restricted_state {state}');expected.append([original(0x1511e0,[state])])
 #Facing uses float ordering, not truncated integer X. Equal positions,
 #air/force flags, state aliases and special-state turn lock are included.
 for case in range(4096):
  flags=rng.choice([0,0x10,0x200000,0x200010]);table=rng.choice([0,1,2,3]);index=rng.choice([0,1,2,19,63,64,65,95])
  a=[flags,0,rng.choice([0,0x10]),rng.choice([0,2,4,6]),(index<<16)|table,(rng.randrange(5)<<16)|rng.randrange(4),rng.choice([0,45,48]),-7,
     rng.getrandbits(32),0,rng.choice([-0.25,0,0.25,160.5,160.75]),rng.choice([-0.25,0,0.25,160.5,160.75])]
  force=case%2;put_actor(a);value=original(0x14a978,[ACTOR,force]);after=p.read(BODY+0x38,4)
  table=original(0x1500a8,[ACTOR]);index=original(0x1500d0,[ACTOR])
  commands.append(' '.join(map(str,['face',*a,force])));expected.append([value,after,table,index])
 #Exercise every normal state with all single recognized slots and raw
 #direction/button predicates, then conflicting inputs and nonboolean words.
 for state in range(64):
  for case in range(80):
   flags=rng.choice([0,0x1000,0x800000,0x801000]);a=[flags,rng.choice([0,1,0x400]),rng.choice([0,0x10]),rng.choice([0,2,4,6]),state<<16,0,
    rng.choice([0,32,45,48]),-11,rng.getrandbits(32),rng.choice([0,0x100]),rng.choice([159.5,160.5]),rng.choice([160.25,160.5])]
   system=case%9;c=[system,a[6],*descriptors[case%8]]
   f=[0]*171;r=[0]*31
   if case<31:r[case]=1
   elif case<48:f[[6,7,8,9,49,50,51,52,53,54,55,56,57,63,91,92,95][case-31]]=1
   else:
    for i in range(171):f[i]=rng.choice([0,0,0,1,0x80000000])
    for i in range(31):r[i]=rng.choice([0,0,0,1,0x80000000])
   for op in ['normal','system_normal','attack','chain','restricted_normal','supplemental','system_only']:select(op,a,state,case%2,c,f,r)
 #Supplemental selectors use permission bits2/4/8, raw packed-state36,
 #effective normal25..30 and damage0..5. Include conflicting candidates to
 #distinguish first-recognized from first-allowed transition behavior.
 for case in range(4096):
  state=rng.randrange(64);table=rng.randrange(4)
  a=[rng.choice([0,0x1000,0x800000,0x200000]),rng.choice([0,2,4,6,8,10,12,14]),0,2,(state<<16)|table,
   (rng.randrange(5)<<16)|rng.randrange(4),rng.choice([0,45]),-11,0x80000,rng.choice([0,0x100]),160.5,160.75]
  f=[0]*171;f[49+case%9]=1;r=[rng.choice([0,0,1,0x80000000]) for _ in range(31)]
  for op in ['supplemental','system_only','restricted_normal']:select(op,a,state,False,[case%9,0,*descriptors[case%8]],f,r)
 #Packed-state62/46 gates must ignore the effective-state alias and other
 #command priorities when the gate's own button pair remains held.
 for packed,flag,held0,held1,alias in itertools.product([62<<16,46<<16],[0,0x8000,0x10000,0x18000],[0,1],[0,1],[0,0x200000]):
  a=[flag|alias,0,0,2,packed,1,0,19,0x80000,0,0,1];f=[1]*171;f[91]=held0;f[92]=held1
  select('normal',a,packed>>16,1,[0,0,*descriptors[0]],f,[1]*31)
 binary=ROOT/'work/ss6/build-native/ss6-action-selection-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,commands[i][:250],got,want)
 report=dict(status='passed_whole_selector_boundaries',cases=len(expected),original_calls=counts,original_instructions=instructions,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='All64-state transition matrix cells; whole1501e8,150410,1505d0,150620,1507e0,150850,150a38,150aa8,150b60,150dd8 and1511e0; whole14a978 facing and1500a8/1500d0 aliases; whole14f5d8 including real system6 descriptor lookup. Compare result and body facing/actorA48 side effects. Actor state,171features,31recognized normal results and opponentThreat supplied. Request callers have a separate report. General command permission filtering, action commit, special-command selector and actual battle/controller integration not claimed.')
 (ROOT/'outputs/ss6-feasibility/action_selection_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
