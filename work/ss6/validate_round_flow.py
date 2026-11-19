#!/usr/bin/env python3
"""Whole13fd80 first/subsequent reset, dispatcher, and explicit label slice."""
import hashlib,itertools,json,random,subprocess
from round_entry_oracle import fixture,ROOT
from mips_probe import signed
OFFSETS=[0x1c,0x20,0x24,0x28,0x2c,0x34,0x38,0x3c]
def main():
 rng=random.Random(0x13fd80);commands=[];expected=[];instructions=0
 for case in range(128):
  p,a,o,b=fixture();a1=a+0xf2c;o1=o+0x1000
  p.memory[a1:a1+0xf2c]=p.memory[a:a+0xf2c];p.memory[o1:o1+0x140]=p.memory[o:o+0x140]
  p.write(a1,o1,4);p.write(a1+0xa24,1,4);p.write(o1+0xcc,1,4);p.write(b+0x250,a1,4)
  index=1+case%4 if case<64 else 0;p.write(b+0x18,index,4);p.write(0x345188,0,4);p.write(0x4c3820,1,4)
  values=[index]
  for i in range(2):
   stats=[rng.randrange(-1,3),rng.randrange(-1,3),rng.randrange(-1,3),rng.randrange(2),2,
          rng.randrange(120),rng.randrange(1000),rng.randrange(50),*[rng.randrange(256) for _ in range(5)]]
   meters=[case%2,rng.randrange(1000),rng.randrange(100),rng.randrange(21),rng.randrange(60000)]
   player=b+0x254+i*0x108;actor=a+i*0xf2c
   for off,v in zip(OFFSETS,stats):p.write(player+off,v,4)
   for j,v in enumerate(stats[8:]):p.write(player+0x40+j,v,1)
   for off,v in zip([0x120,0x124,0x128,0x130,0x1ac+20*4],meters):p.write(actor+off,v,4)
   values+=stats+meters
  commands.append('reset '+' '.join(map(str,values)))
  instructions+=p.run(0x13fd80,limit=200000)[1]
  log=bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0];assert b'ASSERT' not in log
  #143430 also invokes sound hardware/323050 console logging, outside the
  # offline runner. Its observed final state1 boundary is explicitly seeded;
  # the reset above is WHOLE13fd80, not a substituted/continued parent call.
  p.write(b,1,4);p.write(b+4,1,4)
  def snapshot():
   out=[p.read(b+0x18,4)]+[p.read(b+off,4) for off in [0x38,0x3c,0x40,0x44,0x48]]
   out += [signed(p.read(b+off,4),32) for off in range(0x104,0x130,4)]
   for i in range(2):
    player=b+0x254+i*0x108;actor=a+i*0xf2c
    out += [signed(p.read(player+off,4),32) for off in OFFSETS]+[p.read(player+0x40+j,1) for j in range(5)]
    out += [signed(p.read(actor+off,4),32) for off in [0xa30,0xa34,0x120,0x124,0x128,0x130,0x134,0x138,0x1ac+20*4]]
   return out+[p.read(b,4),p.read(b+4,4)]
  expected.append(snapshot())
  for tick in range(31):
   instructions+=p.run(0x1435d8,[b],limit=10000)[1];expected.append(snapshot())
 label_cases=0
 for index,wins0,wins1,required in itertools.product([0,1,2,3,8,9,10,12],range(3),range(3),range(1,4)):
  p.write(b+0x18,index,4)
  for i,wins in enumerate([wins0,wins1]):
   player=b+0x254+i*0x108;p.write(player+0x28,wins,4);p.write(player+0x2c,required,4)
   p.write(0x1fff000+0x20+i*4,player,4)
  # Start after323050 at a declared fixture boundary; stop before sound.
  # No unsupported logger call is skipped and resumed within an invocation.
  p.put(16,b);p.put(17,1)
  instructions+=p.run(0x14398c,stop_before=[0x1439f0])[1]
  commands.append(f'label {index} {wins0} {required} {wins1} {required}')
  expected.append([p.registers[17]]);label_cases+=1
 binary=ROOT/'work/ss6/build-native/ss6-round-flow-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
 report=dict(status='passed_for_projected_fields',whole13fd80_cases=128,whole1435d8_visits=128*31,label_slices=label_cases,
  original_instructions=instructions,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole unmodified13fd80 with resident resource00, initialized pools, real buffered libc logging, ordinary mode3/no-time-limit;64 first-round and64 subsequent-round cases. Native actual round entry compares represented camera,timers,match stats,life,meters and retained timer19; full149008 fields separately verified. Explicit state1 boundary then31 whole1435d8 visits validates first60 gate, subsequent direct1->3 request and OLD-value timer gate; no state2 on this path.216 label-selection slices14398c..1439f0, ordinary mode. No whole143430, full actor frames, sound/kernel/GS claim.')
 (ROOT/'outputs/ss6-feasibility/round_flow_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
