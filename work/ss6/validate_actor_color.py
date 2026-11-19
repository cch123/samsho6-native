#!/usr/bin/env python3
"""Selected spirit resource00 color callback against whole original14b190."""
import hashlib,itertools,json,random,subprocess,sys
from pathlib import Path
from mips_probe import Probe,signed

ROOT=Path(__file__).resolve().parents[2]

def main():
 system=5 if '--ken' in sys.argv else 4 if '--zero' in sys.argv else 3 if '--ten' in sys.argv else 2 if '--zan' in sys.argv else 1 if '--shin' in sys.argv else 0
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 p=Probe(raw);a,o=0x1c00000,0x1d00000
 commands=[];expected=[];labels=[];instructions=0
 rng=random.Random(0x14b190)
 def check(label,kind=0,rage=0,state=0,action=0,flags=0xffffffff,color=0x12345678,
           field20=0xa5a5a5a5,fieldA28=0x76543210,delta=256,timers=None):
  nonlocal instructions
  timers=list(timers) if timers is not None else [0]*35
  p.memory[a:a+0xf2c]=bytes(0xf2c);p.memory[o:o+0x200]=bytes(0x200)
  for off,value in [(0,o),(0x10c,system),(0xa2c,kind),(0x120,rage),(0x194,state),(0xa28,fieldA28),(0x1ac,delta)]:p.write(a+off,value,4)
  for off,value in [(0x24,action),(0x38,flags),(0x8c,color),(0x20,field20)]:p.write(o+off,value,4)
  for i,value in enumerate(timers):p.write(a+0x1b0+4*i,value,4)
  before_actor=bytearray(p.memory[a:a+0xf2c]);before_body=bytearray(p.memory[o:o+0x200])
  _,n=p.run(0x14b190,[a],limit=10000);instructions+=n
  result=[p.read(o+off,4) for off in [0x38,0x8c,0x20]]
  result += [signed(p.read(a+0x1b0+4*i,4),32) for i in range(35)]
  #The whole helper may only mutate its two timers and three body words in
  #this admitted character/system. Check the rest, not just selected outputs.
  for off in [0x1f0,0x1f8]:before_actor[off:off+4]=p.memory[a+off:a+off+4]
  for off in [0x20,0x38,0x8c]:before_body[off:off+4]=p.memory[o+off:o+off+4]
  assert before_actor==p.memory[a:a+0xf2c],label
  assert before_body==p.memory[o:o+0x200],label
  commands.append(' '.join(map(str,[kind,rage,state,action,flags,color,field20,fieldA28,delta,*timers])))
  expected.append(result);labels.append(label)
  return result

 #Table colors must bypass rage/flash timers even when both are active.
 for kind,rage,state,delta in itertools.product([*range(11),0xffffffff],[-1,0,1,2,3,0x7fffffff],[0,0x80000,0x2e0000],[128,256,512]):
  timers=[i*71-200 for i in range(35)]
  timers[9]=0x700;timers[16]=0x77ff;timers[17]=1;timers[18]=0x870;timers[33]=0x900
  check(('palette',kind,rage,state,delta),kind,rage,state,189,delta=delta,timers=timers)
 pulse_edges=[-0x80000000,-0x173400,-10241,-10240,-6145,-6144,-257,-256,-255,-1,
              0,1,255,256,11*256,12*256,19*256,20*256,23*256,24*256,39*256,40*256,
              0x76ff,0x7700,0x77ff,0x7800,0x7801,0x1733ff,0x173400,0x7fffff00,0x7fffffff]
 for rage,state,delta,old in itertools.product([0,1,2,3],[0,0x2e0000],[0,128,256,512],pulse_edges):
  timers=[0]*35;timers[16]=old
  check(('pulse',rage,state,delta,old),rage=rage,state=state,delta=delta,timers=timers)
 flash_edges=[-0x80000000,-1,0,1,0x3ff,0x400,0x401,0x7ff,0x800,0x9ff,0xa00,0xa01,0x173400,0x7fffffff]
 for state,kind,flash,delta in itertools.product([0,0x80000,0x2e0000],[0,1,8,9],flash_edges,[128,256,512]):
  timers=[0]*35;timers[9]=flash;timers[16]=256*13;timers[33]=flash
  check(('flash',state,kind,flash,delta),kind,2,state,delta=delta,timers=timers)
 actions=[-0x80000000,-1,0,163,164,184,185,189,190,257,258,277,278,319,320,528,529,715,716,717,718,0x7fffffff]
 fade_edges=[-0x80000000,-17,-16,-15,-1,0,1,15,16,17,2160,2175,2176,2177,4095,4096,4097,0x173400,0x7fffffff]
 for action,active,old in itertools.product(actions,[-1,0,1],fade_edges):
  timers=[0]*35;timers[17]=active;timers[18]=old
  check(('fade',action,active,old),action=action,delta=[128,256,512][len(commands)%3],timers=timers)
 for i in range(3000):
  timers=[signed(rng.getrandbits(32),32) for _ in range(35)]
  check(('random',i),kind=rng.choice([0,0,0,1,2,3,4,5,6,7,8,9,0xffffffff]),rage=rng.randrange(-1,5),
        state=rng.choice([0,0x80000,0x2e0000,rng.getrandbits(32)]),action=rng.choice(actions),
        flags=rng.getrandbits(32),color=rng.getrandbits(32),field20=rng.getrandbits(32),fieldA28=rng.getrandbits(32),
        delta=rng.choice([0,128,256,512,0x7fffffff,-0x80000000]),timers=timers)
 traces=0
 for rage,action,delta in itertools.product([0,1,2,3],[0,189,342,529],[128,256,512]):
  traces+=1;timers=[0]*35;flags=0xffffffff;color=0xff808080
  for tick in range(180):
   timers[17]=1 if tick<90 else 0
   result=check(('trace',traces,tick),kind=1 if 30<=tick<50 else 0,rage=rage,state=0,
                action=action,flags=flags,color=color,delta=delta,timers=timers)
   flags,color=result[:2];timers=result[3:]
 binary=ROOT/'work/ss6/build-native/ss6-actor-color-probe'
 digest=hashlib.sha256(binary.read_bytes()).hexdigest()
 run=subprocess.run([str(binary),str(system)],input='\n'.join(commands)+'\n',capture_output=True,text=True)
 assert run.returncode==0,run.stderr
 actual=[list(map(int,line.split())) for line in run.stdout.splitlines()]
 assert len(actual)==len(expected),(len(actual),len(expected))
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,labels[i],commands[i],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y])
 assert digest==hashlib.sha256(binary.read_bytes()).hexdigest()
 report=dict(status='passed',whole14b190_cases=len(expected),continuous_traces=traces,original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=digest,
  system=system,scope='Whole original14b190 resource00. All damage color selectors including out-of-range fallback; rage states,raw normal8/46,old-timer pulse/new-timer wrap,flash and fade precedence,action classification boundaries,all35timers and untouched actor/body bytes. Signed-word overflow and continuous pulses/fades checked. No live ContactTrial integration,draw-packet/GS rendering,other-character visibility or other-system claim.')
 (ROOT/'outputs/ss6-feasibility'/(('','shin_','zan_','ten_','zero_','ken_')[system]+'actor_color_validation.json')).write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
