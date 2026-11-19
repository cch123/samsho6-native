#!/usr/bin/env python3
"""Persistent native input streams against real bindings and whole dispatch."""
import hashlib,json,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_input_features import FEATURES,LATCHES,PADS
ROOT=Path(__file__).resolve().parents[2];OWNER=0x1c00000;CONFIG=0x1d00000

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);commands=[];expected=[];traces=[];instructions=0;calls=0
 mappings=[1<<i for i in range(8,16)]*2;button0=1<<8;button1=1<<9;side0=1<<7;side1=1<<6;down=1<<5
 #These names identify table definitions; direction words are at the
 #software-pad boundary, with no claim about physical controller labels.
 fixtures=[('motion38',0,0,38,[0,down,down|side0,side0|button0],True),
           ('motion38_timeout',0,0,38,[0,down]+[0]*13+[down|side0,side0|button0],False),
           ('charge35',14,0,35,[side1]*53+[side0|button0],True),
           ('charge35_short',14,0,35,[side1]*52+[side0|button0],False),
           ('double24',0,0,24,[0,side0,0,side0],True),
           ('double25',0,0,25,[0,side1,0,side1],True),
           ('staggered15',0,0,15,[button0,0,0,button1],True),
           ('staggered15_expired',0,0,15,[button0,0,0,0,button1],False)]
 for name,character,system,target,sequence,should_match in fixtures:
  for mirror in [0,1]:
   p.memory[OWNER:OWNER+0x800]=bytes(0x800);p.memory[FEATURES:FEATURES+684]=bytes(684);p.memory[LATCHES:LATCHES+12]=bytes(12)
   p.memory[CONFIG:CONFIG+20]=struct.pack('<5I',system,0,character,0,0);p.write(0x4c38a8,0,4)
   _,n=p.run(0x179258,[OWNER,CONFIG],limit=100000);instructions+=n
   for address in [0x4eaac0,0x12d32d8]:p.memory[address:address+32]=struct.pack('<8I',*mappings[:8])
   commands.append(' '.join(map(str,['init',system,character,*([0]*16),*mappings])))
   matched=[];old=0
   for visit,bits in enumerate(sequence+[0]*12):
    #For facing-dependent motions, mirror the physical horizontal bits.
    #The double-tap definitions use the world-direction block instead.
    if mirror and target not in [24,25]:
     bits=(bits&~(side0|side1))|((bits&side0)>>1)|((bits&side1)<<1)
    facing=mirror if target not in [24,25] else 0
    edge=bits&~old;old=bits
    p.write(PADS,bits,4);p.write(PADS+4,edge,4)
    _,n=p.run(0x179530,[OWNER,0,facing,1-facing,0,1,0,-1],limit=300000);instructions+=n;calls+=1
    want=[*struct.unpack_from('<171I',p.memory,OWNER),*p.memory[LATCHES:LATCHES+12]]
    found=False
    for special,size in [(False,31),(True,32)]:
     for i in range(size):
      definition=signed(p.read(OWNER+(0x644 if special else 0x4c4)+i*2,2),16)
      result=p.read(OWNER+(0x328 if special else 0x2ac)+i*4,4)
      cancel_allowed=p.read(OWNER+0x3a8+i*4,4) if special else 0
      state=struct.unpack_from('<BBHB',p.memory,OWNER+(0x684 if special else 0x502)+i*6)
      want += [definition,result,cancel_allowed,*state]
      if definition==target and result:found=True
    if found:matched.append(visit)
    commands.append(' '.join(map(str,['tick',0,bits,edge,facing,1-facing,0,1])));expected.append(want)
   assert bool(matched)==should_match,(name,mirror,matched)
   traces.append(dict(name=name,mirrored=mirror,target=target,recognized_visits=matched,visits=len(sequence)+12))
 binary=ROOT/'work/ss6/build-native/ss6-input-stream-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20])
 report=dict(status='passed_persistent_input_streams',traces=traces,whole_179258_calls=len(traces),whole_179530_calls=calls,
  original_instructions=instructions,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Native bindings+sampler+recognizer persist across all visits; original whole179258 then whole179530. Real mapped held/edge sequences, both facing directions, successful/expired multi-direction motion,52-held-visit charge threshold,double taps,staggered chords and completion buffer expiry. All171 actor features,12 latches and63 command definitions/results/progress compared. Software pad input supplied, no action selection or gameplay execution claimed.')
 (ROOT/'outputs/ss6-feasibility/input_stream_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
