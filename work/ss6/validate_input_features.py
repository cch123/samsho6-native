#!/usr/bin/env python3
"""Compare complete177310/177908 with normalized controller words supplied."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2]
FEATURES=0x12d26b8;LATCHES=0x12d2968;HELD=0x12d2978;PRESSED=0x12d2e28;PADS=0x1237cc8

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x177908);commands=[];expected=[];counts={};instructions=0
 #Arbitrary nonzero initial words make accidental whole-array clearing
 #visible, especially the unused0xc0 feature. Both latch sets are seeded.
 features=[rng.getrandbits(32) for _ in range(171)]
 latches=[rng.choice([0,1,2,3,4,255]) for _ in range(12)]
 recordings=[[rng.randrange(65536) for _ in range(600)] for _ in range(2)]
 p.memory[FEATURES:FEATURES+684]=struct.pack('<171I',*features)
 p.memory[LATCHES:LATCHES+12]=bytes(latches)
 for address,values in zip([HELD,PRESSED],recordings):p.memory[address:address+1200]=struct.pack('<600H',*values)
 commands.append(' '.join(map(str,['seed',*features,*latches,*recordings[0],*recordings[1]])))
 #Mappings deliberately differ between mode6 and ordinary mode. No claim
 #about menu defaults or a physical controller driver's bit generation.
 mapping=[1<<i for i in range(8,16)]+[1<<i for i in reversed(range(8,16))]
 def sample(derive,player,held,pressed,facing=0,actual=0,reverse=0,playback=0,index=-1,mode=0,masks=None):
  nonlocal instructions
  masks=mapping if masks is None else masks
  p.write(PADS+player*12,held,4);p.write(PADS+player*12+4,pressed,4)
  p.write(0x4c38a8,mode,4)
  for address,values in [(0x4eaac0,masks[:8]),(0x12d32d8,masks[8:])]:
   p.memory[address+player*32:address+player*32+32]=struct.pack('<8I',*values)
  before=bytes(p.memory[LATCHES:LATCHES+12]);before_record=[bytes(p.memory[a:a+1200]) for a in [HELD,PRESSED]]
  address=0x177908 if derive else 0x177310
  _,n=p.run(address,[player,facing,actual,reverse,playback,index],limit=10000)
  instructions+=n;counts[hex(address)]=counts.get(hex(address),0)+1
  assert p.read(FEATURES+0xc0,4)==features[0xc0//4]
  untouched=1-player
  assert bytes(p.memory[LATCHES+untouched*6:LATCHES+untouched*6+6])==before[untouched*6:untouched*6+6]
  if not derive:assert bytes(p.memory[LATCHES:LATCHES+12])==before
  for a,old in zip([HELD,PRESSED],before_record):
   new=bytes(p.memory[a:a+1200])
   if playback or not 0<=index<600:assert new==old
   else:assert new[:index*2]==old[:index*2] and new[index*2+2:]==old[index*2+2:]
  values=[*struct.unpack_from('<171I',p.memory,FEATURES),*p.memory[LATCHES:LATCHES+12]]
  values += [p.read(HELD+index*2,2),p.read(PRESSED+index*2,2)] if 0<=index<600 else [0,0]
  commands.append(' '.join(map(str,['sample',derive,player,held,pressed,facing,actual,reverse,playback,index,mode,*masks])))
  expected.append(values)
 #Every simultaneous direction combination, both facing views/reversal,
 #both players, and both mapping modes. Includes opposing directions.
 for derive,direction,facing,actual,reverse,player,mode in itertools.product([0,1],range(16),[0,1],[0,1],[0,1],[0,1],[0,6]):
  sample(derive,player,(direction<<4)|0xa500,(direction<<4)|0x5a00,facing,actual,reverse,mode=mode)
 direction_cases=len(expected)
 #Every combination of six basic buttons, followed by six releases, tests
 #per-player four-visit latches and raw/exclusive/latched predicate splits.
 for player,bits in itertools.product([0,1],range(64)):
  held=((bits&31)<<8)|((bits>>5)<<3)
  for visit in range(7):sample(1,player,held if visit<3 else 0,held if visit==0 else 0)
 latch_cases=len(expected)-direction_cases
 #All combination-button subsets are recorded before expansion, then
 #replayed with different facing/mappings to exercise the saved boundary.
 for index in range(600):
  sample(1,index%2,rng.randrange(65536),rng.randrange(65536),index%2,(index//2)%2,(index//4)%2,index=index,mode=6 if index%3==0 else 0)
 for index in range(600):sample(1,index%2,0xffffffff,0xffffffff,index%2,1-index%2,(index//3)%2,1,index,6)
 for playback,index in itertools.product([0,1],[-2147483648,-1,600,601,2147483647]):sample(1,0,0xffffffff,0xffffffff,playback=playback,index=index)
 for case in range(1024):
  #Multi-bit masks test the original any-intersection rule; normalized
  #words are deliberately not constrained to physically plausible edges.
  masks=[rng.getrandbits(32) if case%3 else rng.choice([0,1,1<<31]) for _ in range(16)]
  sample(case%2,case%2,rng.getrandbits(32),rng.getrandbits(32),rng.randrange(2),rng.randrange(2),rng.randrange(2),
         rng.randrange(2),rng.choice([-1,0,599,600]),rng.choice([0,5,6,7]),masks)
 commands.append('recording');expected.append([*struct.unpack_from('<600H',p.memory,HELD),*struct.unpack_from('<600H',p.memory,PRESSED)])
 binary=ROOT/'work/ss6/build-native/ss6-input-features-probe'
 result=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,commands[i+1][:200],[(hex(j*4) if j<171 else j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:20])
 report=dict(status='passed_at_normalized_pad_boundary',snapshots=len(expected)-1,direction_cases=direction_cases,latch_cases=latch_cases,
  original_calls=counts,original_instructions=instructions,elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole177310/177908 including118128 with supplied normalized pad words. All171 features, both player latch banks and full600-entry held/pressed recording arrays checked. All16 direction combinations, facing/actualFacing/reversal,mode6 mappings,chord expansion,four-visit latches,record/playback and signed index boundaries. No skipped callees. Physical PS2/SDL input driver, game scheduler phase, binding initialization, action selection and gameplay integration not covered.')
 (ROOT/'outputs/ss6-feasibility/input_features_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
