#!/usr/bin/env python3
"""Whole179530: supplied pad words through sampling, recognition and aging."""
import hashlib,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH
from validate_input_features import FEATURES,LATCHES,HELD,PRESSED,PADS
ROOT=Path(__file__).resolve().parents[2];OWNER=0x1c00000

def encoded(f):
 pairs=[(i,v) for i,v in enumerate(f) if v]
 return [len(pairs)]+[x for pair in pairs for x in pair]

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x179530);commands=[];expected=[];instructions=0;enabled_cases=0
 mappings=[1<<i for i in range(8,16)]+[1<<i for i in reversed(range(8,16))]
 for case in range(512):
  enabled=case%13!=0;count=[-1,0,1,7,31,32][case%6];age=(case//2)%2;player=case%2
  facing=(case//4)%2;actual=(case//8)%2;reverse=(case//16)%2;playback=(case//32)%2
  index=[-1,0,599,600][case%4];mode=6 if case%3==0 else 0
  held=rng.randrange(65536);pressed=rng.randrange(65536)
  p.memory[OWNER:OWNER+0x800]=bytes(0x800)
  p.write(OWNER+0x5c0,0 if enabled else -1,4);p.write(OWNER+0x5bc,count,4)
  values=['pipeline',int(enabled),count,age];normal_cancel_allowed=[]
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    definition=rng.choice([-1,*range(273)]);alternate=rng.randrange(2)
    recognized=rng.getrandbits(32);cancel_allowed=rng.getrandbits(32)
    state=[rng.randrange(14),rng.choice([0,7,11,12,255]),rng.choice([0,51,52,5999,6000]),rng.choice([0,1,4,10,33])]
    values += [definition,alternate,recognized,cancel_allowed,*state]
    for off,v,sz in [(0x644 if special else 0x4c4,definition,2),(0x5c4 if special else 0x448,alternate,4),(0x328 if special else 0x2ac,recognized,4)]:p.write(OWNER+off+i*sz,v,sz)
    addr=OWNER+(0x684 if special else 0x502)+i*6
    p.memory[addr:addr+6]=struct.pack('<BBHBB',*state,0xa5)
    if special:p.write(OWNER+0x3a8+i*4,cancel_allowed,4)
    else:normal_cancel_allowed.append(cancel_allowed)
  shared=[rng.getrandbits(32) for _ in range(171)];owner=[rng.getrandbits(32) for _ in range(171)]
  latches=[rng.choice([0,1,4,255]) for _ in range(12)]
  saved=[rng.randrange(65536),rng.randrange(65536)]
  values += [player,held,pressed,facing,actual,reverse,playback,index,mode,*mappings,*encoded(shared),*encoded(owner),*latches,*saved]
  p.memory[FEATURES:FEATURES+684]=struct.pack('<171I',*shared);p.memory[OWNER:OWNER+684]=struct.pack('<171I',*owner)
  p.memory[LATCHES:LATCHES+12]=bytes(latches)
  for address in [HELD,PRESSED]:p.memory[address:address+1200]=bytes(1200)
  if 0<=index<600:
   p.write(HELD+index*2,saved[0],2);p.write(PRESSED+index*2,saved[1],2)
  p.write(PADS+player*12,held,4);p.write(PADS+player*12+4,pressed,4);p.write(0x4c38a8,mode,4)
  for address,m in [(0x4eaac0,mappings[:8]),(0x12d32d8,mappings[8:])]:p.memory[address+player*32:address+player*32+32]=struct.pack('<8I',*m)
  try:_,n=p.run(0x179530,[OWNER,player,facing,actual,reverse,age,playback,index],limit=300000)
  except Exception as e:raise RuntimeError(f'Whole179530 fixture {case}, enabled={enabled}, count={count}') from e
  instructions+=n;enabled_cases+=enabled;want=[]
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    addr=OWNER+(0x684 if special else 0x502)+i*6
    want += [p.read(OWNER+(0x328 if special else 0x2ac)+i*4,4),p.read(OWNER+0x3a8+i*4,4) if special else normal_cancel_allowed[i],*struct.unpack_from('<BBHB',p.memory,addr)]
    assert p.read(addr+5,1)==0xa5
  want += [*struct.unpack_from('<171I',p.memory,FEATURES),*struct.unpack_from('<171I',p.memory,OWNER),*p.memory[LATCHES:LATCHES+12]]
  want += [p.read(HELD+index*2,2),p.read(PRESSED+index*2,2)] if 0<=index<600 else [0,0]
  commands.append(' '.join(map(str,values)));expected.append(want)
 binary=ROOT/'work/ss6/build-native/ss6-command-input-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20])
 report=dict(status='passed_whole_input_dispatch',whole_179530_cases=len(expected),enabled_cases=enabled_cases,disabled_cases=len(expected)-enabled_cases,
  original_instructions=instructions,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole179530 including177908,177310,118128,1788e8,178980/178ac8 and all buffer aging. Normalized pad/controller mappings and command bindings supplied. Compare63 command states/results,32 cancel permission flags,shared and actor171-feature frames,both player latches and selected recording entry. Disabled owners preserve all these fields. No skipped callees or slice boundary. Binding initialization has a separate input_bindings report. Physical controller driver, game scheduler phase and action selection remain pending.')
 (ROOT/'outputs/ss6-feasibility/input_pipeline_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
