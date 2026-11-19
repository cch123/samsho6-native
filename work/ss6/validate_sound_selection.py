#!/usr/bin/env python3
"""Whole original1e83c0, preserving shared previous choices and RNG seeds."""
import hashlib,itertools,json,random,subprocess
from round_entry_oracle import ROOT
from mips_probe import Probe,signed
from extract_collision_tables import SOURCE_HASH
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 p=Probe(raw);rng=random.Random(0x1e83c0);commands=[];expected=[];instructions=0
 reent=0x1b00000;p.write(0x5d1bf8,reent,4)
 def run(command,stage,mode,game,library,previous):
  nonlocal instructions
  for address,value,size in [(0x443150,mode,4),(0x3d2e80,game,4),(reent+0xa8,library,8),(0x4c380c,stage,4),
      (0x585224,previous[0],4),(0x58524c,previous[1],4)]:p.write(address,value,size)
  commands.append(' '.join(map(str,[command,stage,mode,game,library,*previous])))
  result,n=p.run(0x1e83c0,[command],limit=5000);instructions+=n
  state=[signed(result&0xffffffff,32),p.read(0x3d2e80,4),p.read(reent+0xa8,8),signed(p.read(0x585224,4),32),signed(p.read(0x58524c,4),32)]
  expected.append(state);return state
 for command,stage,mode in itertools.product(range(149,162),[-1,*range(13),0x7fffffff,-0x80000000],[0,-2,1,3,-1]):
  run(command,stage,mode,rng.getrandbits(32),rng.getrandbits(64),[rng.randrange(-1,301),rng.randrange(-1,301)])
 for command in [-0x80000000,-1,0,1,148,162,4095,0x7fffffff]:run(command,0,0,1,1,[0,0])
 #Mix all three commands in each shared anti-repeat group. Supply the
 #previous call's actual seeds/history to the next call without reseeding.
 for mode in [0,-2,1,3]:
  game,library,previous=1,1,[-1,-1]
  for i in range(512):
   result=run(150+rng.randrange(6),i%12,mode,game,library,previous)
   game,library=result[1:3];previous=result[3:]
 binary=ROOT/'work/ss6/build-native/ss6-sound-selection-probe';pin=hashlib.sha256(binary.read_bytes()).hexdigest()
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,result.stderr
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,commands[i],got,want)
 assert pin==hashlib.sha256(binary.read_bytes()).hexdigest()
 report=dict(status='passed',whole1e83c0_calls=len(expected),persistent_calls=2048,original_instructions=instructions,
  elf_sha256=SOURCE_HASH,native_sha256=pin,table_sha256=hashlib.sha256((ROOT/'work/ss6/extracted/resources/sound_selection.bin').read_bytes()).hexdigest(),
  scope='Whole unmodified1e83c0 and all reached1e8450/1e84b8/1e8550/1e85e8/1e8660/1e86d8 plus both RNG generators. Commands150..160 and refusal edges,all12 stages/defaults,both shared anti-repeat histories and continuous mixed choices. Compare return,history and both RNG seeds. Integer-only;not audio samples,SPU channels,full1e8298 or audible output.')
 (ROOT/'outputs/ss6-feasibility/sound_selection_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
