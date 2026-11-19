#!/usr/bin/env python3
"""Whole179258, including system predicates, overrides and priority sort."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2];OWNER=0x1c00000;CONFIG=0x1d00000

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x179258);commands=[];expected=[];instructions=0;cases=[]
 special=(ROOT/'work/ss6/extracted/resources/input_special.bin').read_bytes()
 characters=sorted(set(special[i] for i in range(0,len(special),12))-{255});assert characters==list(range(42))+list(range(43,49))
 #Stock descriptors are read from the original data, then supplied at
 #152758's mode6 descriptor pool so the real lookup is exercised as well.
 descriptors=[bytes(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 for character,system in itertools.product(characters,range(9)):cases.append((1,system,character,descriptors[character%8]))
 for descriptor,character in itertools.product(descriptors,characters):cases.append((1,6,character,descriptor))
 #Vary relevant custom fields independently, including unassigned values.
 for field,byte in itertools.product([1,2,3,4,5,6,9,10],[0,4,7,8,11,12,13,14,15,17,18,19,20,21,22,24,25,27,28,34,36,255]):
  d=bytearray(descriptors[0]);d[field]=byte;cases.append((1,6,rng.choice(characters),d))
 for character in characters:cases.append((0,6,character,descriptors[0]))
 for case,(present,system,character,d) in enumerate(cases):
  seed=rng.getrandbits(32);p.memory[OWNER:OWNER+0x800]=bytes(0x800)
  p.memory[OWNER:OWNER+684]=struct.pack('<171I',*([seed]*171))
  p.write(OWNER+0x5bc,32,4);p.write(OWNER+0x5c0,4,4)
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    for offset,value,sz in [(0x644 if special else 0x4c4,123,2),(0x5c4 if special else 0x448,i%2,4),(0x328 if special else 0x2ac,seed,4)]:p.write(OWNER+offset+i*sz,value,sz)
    address=OWNER+(0x684 if special else 0x502)+i*6
    p.memory[address:address+6]=struct.pack('<BBHBB',3,4,52,10,0xa5)
    if special:p.write(OWNER+0x3a8+i*4,seed,4)
  p.memory[OWNER+0x428:OWNER+0x448]=bytes(range(100,132))
  p.memory[CONFIG:CONFIG+20]=struct.pack('<5I',system,1,character,3,0)
  p.write(0x4c38a8,6,4);p.memory[0x12d2308+11*16:0x12d2308+12*16]=d
  _,n=p.run(0x179258,[OWNER,CONFIG if present else 0],limit=100000);instructions+=n
  start=signed(p.read(OWNER+0x5c0,4),32);count=signed(p.read(OWNER+0x5bc,4),32)
  want=[int(start!=-1),count,start,*struct.unpack_from('<171I',p.memory,OWNER)]
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    want += [signed(p.read(OWNER+(0x644 if special else 0x4c4)+i*2,2),16),p.read(OWNER+(0x5c4 if special else 0x448)+i*4,4),p.read(OWNER+(0x328 if special else 0x2ac)+i*4,4)]
    if special:want.append(p.read(OWNER+0x3a8+i*4,4))
    address=OWNER+(0x684 if special else 0x502)+i*6
    want += struct.unpack_from('<BBHB',p.memory,address);assert p.read(address+5,1)==0xa5
  want += p.memory[OWNER+0x428:OWNER+0x448]
  commands.append(' '.join(map(str,[seed,present,system,character,*d])));expected.append(want)
 binary=ROOT/'work/ss6/build-native/ss6-input-bindings-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,cases[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20])
 report=dict(status='passed_whole_binding_initialization',whole_179258_cases=len(expected),characters=characters,systems=list(range(9)),
  original_instructions=instructions,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole179258 and179178,all availability helpers including14f4e0/152758 descriptor lookup,character overrides,alternate commands and179810 priority sort.48 character keys with explicit special blocks,systems0..8,all8 stock system6 descriptors,custom field variants and null disable. All exposed owner features,slot definitions/remap flags/results/progress/special cancel permission flags/priority bytes compared; padding preserved. Descriptor selection is caller supplied natively. Character42/49/50 input aliases unresolved and rejected; initialized bindings are not proof of playable characters or action execution.')
 (ROOT/'outputs/ss6-feasibility/input_bindings_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
