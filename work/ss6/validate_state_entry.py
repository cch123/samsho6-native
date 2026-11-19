#!/usr/bin/env python3
"""Whole state-channel helpers and1491e0 prefix before actual entry effects."""
import collections,hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
from validate_input_lifecycle import Boundary
ROOT=Path(__file__).resolve().parents[2];ACTOR=0x1c00000;AUX=0x1d00000

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x1491e0);commands=[];expected=[];calls=collections.Counter();outcomes=collections.Counter();instructions=0
 def run(pc,args,stops=()):
  nonlocal instructions
  value,n=p.run(pc,args,limit=10000,stop_before=stops);instructions+=n;calls[hex(pc)]+=1;return signed(value,32)
 for op in range(3):
  for case in range(4096 if op==2 else 1024):
   flags=rng.choice([0,0x1000,0x200000,0x800000,0xa00000,0xffffffff]);character=rng.choice([0,1,11,24,25,45,48])
   currentIndex=rng.choice([-2,-1,0,1,2,3,5,6,7,8,9,16,17,18,19,31,32,56,57,58,63,64,95,32767]);currentTable=case%4
   current=(((currentIndex&65535)<<16)|currentTable);alias=((case%4)<<16)|(case%3)
   pendingTable=rng.choice([-2,-1,0,1,2,3,32767]);pendingIndex=rng.choice([-2,-1,0,1,2,3,5,6,9,17,32,57,58,63,64,95,32767])
   if case%5==0:pendingTable=currentTable;pendingIndex=currentIndex
   request=case%3;auxAction=776 if case%2 else 777
   values=[flags,character,current,alias,-222,-333,0xab,0xcd,request,pendingTable,pendingIndex,19,-20,21,23,auxAction,-24,25,0xabcdef00,256]
   timers=[rng.randrange(-10000,10000) for _ in range(35)]
   p.memory[ACTOR:ACTOR+0x1000]=bytes([0xa5])*0x1000;p.memory[AUX:AUX+0x200]=bytes([0x5a])*0x200;p.write(ACTOR+4,AUX,4)
   fields=[(0x23c,4,flags),(0xa10,4,character),(0x194,4,current),(0x1a4,4,alias),(0x198,2,-222),(0x1a8,2,-333),(0x19a,1,0xab),(0x1aa,1,0xcd),(0x18c,4,request),(0x190,2,pendingTable),(0x192,2,pendingIndex),(0x19c,4,19),(0x1a0,2,-20),(0x1a2,2,21),(0x1ac,4,256)]
   for off,size,value in fields:p.write(ACTOR+off,value,size)
   for off,value in [(0x128,23),(0x24,auxAction),(0xc4,-24),(0xc0,25),(0x104,0xabcdef00)]:p.write(AUX+off,value,4)
   p.memory[ACTOR+0x1b0:ACTOR+0x23c]=struct.pack('<35i',*timers)
   if op==2:
    oldIndex=run(0x1500d0,[ACTOR]);oldTable=run(0x1500a8,[ACTOR]);boundary=Boundary(0x14a348)
    run(0x1491e0,[ACTOR],boundary);required=int(boundary.stopped==0x14a348)
    table=signed(p.registers[5],32) if required else oldTable;index=signed(p.registers[6],32) if required else oldIndex
    result=[-1,required,oldTable,oldIndex,table,index,int(required and oldTable==1 and table!=1)]
    outcomes[f'entry:{required}']+=1
   else:
    value=run([0x150000,0x150038][op],[ACTOR+0x18c]);result=[value if op==0 else -1];outcomes[f'{hex([0x150000,0x150038][op])}:{result[0]}']+=1
   out=[p.read(ACTOR+0x23c,4),p.read(ACTOR+0x194,4),p.read(ACTOR+0x1a4,4),signed(p.read(ACTOR+0x198,2),16),signed(p.read(ACTOR+0x1a8,2),16),p.read(ACTOR+0x19a,1),p.read(ACTOR+0x1aa,1),p.read(ACTOR+0x18c,4),signed(p.read(ACTOR+0x190,2),16),signed(p.read(ACTOR+0x192,2),16),p.read(ACTOR+0x19c,4),signed(p.read(ACTOR+0x1a0,2),16),signed(p.read(ACTOR+0x1a2,2),16),p.read(AUX+0x128,4),p.read(AUX+0x24,4),signed(p.read(AUX+0xc4,4),32),p.read(AUX+0xc0,4),p.read(AUX+0x104,4),*struct.unpack_from('<35i',p.memory,ACTOR+0x1b0)]
   assert p.read(ACTOR+0x19b,1)==0xa5 and p.read(ACTOR+0x1ab,1)==0xa5
   commands.append(' '.join(map(str,[op,*values,*timers])));expected.append([*result,*out])
 binary=ROOT/'work/ss6/build-native/ss6-state-entry-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True);assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for case,(got,want) in enumerate(zip(actual,expected)):assert got==want,(case,commands[case],[(i,x,y) for i,(x,y) in enumerate(zip(got,want)) if x!=y])
 report=dict(status='passed_state_entry_preparation',cases=len(expected),original_calls=calls,original_instructions=instructions,outcomes=outcomes,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='1024 whole150000 pending-vs-RAW-current tests and1024 whole150038 commits.4096 explicit1491e0 prefixes run original callees normally and stop before14a348; no-entry paths return normally. Whole1500a8/1500d0 independently establish old effective state. Compare both channels,metadata,all35 timers,auxiliary queue and emitted entry arguments. No14a348 or post-entry14f1a0 execution is claimed; finishAttackAfterEntry records that static continuation condition. Not complete state entry or playable move execution.')
 (ROOT/'outputs/ss6-feasibility/state_entry_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
