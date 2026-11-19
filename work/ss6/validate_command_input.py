#!/usr/bin/env python3
"""All original command grammars, buffering, and recognition-phase slices."""
import hashlib,itertools,json,random,struct,subprocess
from pathlib import Path
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
FEATURES=0x12d26b8;STATE=0x1e00000;OWNER=0x1c00000
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 data=(ASSETS/'input_commands.bin').read_bytes();defs=[data[i*17:(i+1)*17] for i in range(273)]
 p=Probe(raw);assert bytes(p.memory[0x4e9898:0x4e9898+len(data)])==data
 rng=random.Random(0x178ac8);commands=[];expected=[];counts={};instructions=0;traces=[]
 def original(address,args=(),stop=()):
  nonlocal instructions
  value,n=p.run(address,args,limit=300000,stop_before=stop);instructions+=n
  counts[hex(address)]=counts.get(hex(address),0)+1;return value
 def put_features(f):p.memory[FEATURES:FEATURES+171*4]=struct.pack('<171I',*f)
 def encoded(f):
  pairs=[(i,v) for i,v in enumerate(f) if v]
  return [len(pairs)]+[x for pair in pairs for x in pair]
 def get_state(addr=STATE):return list(struct.unpack_from('<BBHB',p.memory,addr))
 def eval(id,state,f,alternate=False,wrapper=False):
  p.memory[STATE:STATE+6]=struct.pack('<BBHBB',*state,0xa5);put_features(f)
  result=original(0x178980,[id,STATE,int(alternate)]) if wrapper or alternate else original(0x178ac8,[id,STATE])
  assert p.read(STATE+5,1)==0xa5
  assert bytes(p.memory[FEATURES:FEATURES+171*4])==struct.pack('<171I',*f), 'wrapper must restore shared features'
  after=get_state();commands.append(' '.join(map(str,['eval',id,int(alternate),*state,*encoded(f)])))
  expected.append([int(result!=0),*after]);return result,after
 def active_feature(f,index,alternate):f[index+17 if alternate and 49<=index<=65 else index]=1
 #Successful sequential input for EVERY template, through the whole
 #backup/remap/matcher/restore wrapper. State is retained across visits.
 for id,alternate in itertools.product(range(273),[False,True]):
  d=defs[id];state=[0,0,0,0];matched=False
  for visit in range(150):
   f=[0]*171;token=d[state[0]]
   if token==48:
    if state[2]<52:active_feature(f,d[state[0]-1],alternate)
    else:active_feature(f,d[state[0]+1],alternate)
   elif token!=255:active_feature(f,token,alternate)
   result,state=eval(id,state,f,alternate,True)
   if result:matched=True;break
  assert matched,(id,alternate,state)
  assert state==[0,0,0,d[15]]
  traces.append(dict(id=id,alternate=alternate,visits=visit+1,buffer=d[15]))
 #Every step position and timeout boundary, including byte wrap. The
 #snapshot cases are explicit machine-state fixtures, not physical pads.
 for id in range(273):
  d=defs[id]
  for step,elapsed in itertools.product(range(14),[0,d[14]-1,d[14],255]):
   f=[0]*171
   for _ in range(rng.randrange(10)):f[rng.randrange(171)]=rng.choice([1,0x80000000,0xffffffff])
   if d[step]!=255 and rng.randrange(2):f[d[step]]=1
   eval(id,[step,elapsed,rng.choice([0,1,51,52,5999,6000,65535]),rng.choice([0,1,4,10,33,255])],f)
 charge_cases=0
 for token,alternate,value in itertools.product(range(171),[False,True],[0,1,0x80000000]):
  f=[value]*171;put_features(f)
  result=original(0x178dc8,[token]);commands.append(' '.join(map(str,['charge',token,int(alternate),*encoded(f)])))
  expected.append([int(result!=0)]);charge_cases+=1
 #Near the charge threshold and saturation, independently toggle hold and
 #release. Progress failures must preserve an existing completion buffer.
 for id,d in enumerate(defs):
  if 48 not in d[:14]:continue
  step=d.index(48)
  for charge,held,alternate in itertools.product([0,50,51,52,53,5999,6000,65535],[False,True],[False,True]):
   f=[0]*171
   active_feature(f,d[step-1] if held else d[step+1],alternate)
   eval(id,[step,0,charge,10],f,alternate,True)
 #The31+32 slot loops start after177908/1788e8 have produced/copied the
 #features. This is a declared slice, not a skipped callee in179530.
 group_cases=0
 for case in range(80):
  enabled=case%10!=0;count=[-1,0,1,7,31,32][case%6];age=case%2
  p.memory[OWNER:OWNER+0x800]=bytes(0x800)
  p.write(OWNER+0x5c0,0 if enabled else -1,4);p.write(OWNER+0x5bc,count,4)
  values=['group',int(enabled),count,age];normal_consumed=[]
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    id=rng.choice([-1,*range(273)]);alternate=rng.randrange(2)
    result=rng.getrandbits(32);consumed=rng.getrandbits(32)
    state=[rng.randrange(14),rng.randrange(16),rng.choice([0,51,52,6000]),rng.choice([0,1,4,10,33])]
    values += [id,alternate,result,consumed,*state]
    for off,v,size_bytes in [(0x644 if special else 0x4c4,id,2),(0x5c4 if special else 0x448,alternate,4),
                             (0x328 if special else 0x2ac,result,4)]:p.write(OWNER+off+i*size_bytes,v,size_bytes)
    p.memory[OWNER+(0x684 if special else 0x502)+i*6:OWNER+(0x684 if special else 0x502)+i*6+6]=struct.pack('<BBHBB',*state,0xa5)
    if special:p.write(OWNER+0x3a8+i*4,consumed,4)
    else:normal_consumed.append(consumed)
  f=[int(rng.randrange(8)==0) for _ in range(171)];put_features(f)
  if enabled:
   p.put(17,OWNER);p.put(21,OWNER);p.put(20,OWNER+0x502);p.put(30,age)
   original(0x17959c,stop=[0x1796a8])
  else:original(0x179530,[OWNER,0,0,0,0,age,0,0])
  want=[]
  for special,size in [(False,31),(True,32)]:
   for i in range(size):
    addr=OWNER+(0x684 if special else 0x502)+i*6
    want += [p.read(OWNER+(0x328 if special else 0x2ac)+i*4,4),p.read(OWNER+0x3a8+i*4,4) if special else normal_consumed[i],*get_state(addr)]
    assert p.read(addr+5,1)==0xa5
  commands.append(' '.join(map(str,[*values,*encoded(f)])));expected.append(want);group_cases+=1
 binary=ROOT/'work/ss6/build-native/ss6-command-input-probe'
 result=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):
  assert got==want,(i,commands[i][:180],[(j,x,y) for j,(x,y) in enumerate(zip(got,want)) if x!=y][:16])
 report=dict(status='passed_for_recognition_boundary',templates=273,successful_traces=traces,
  snapshots=len(expected),charge_predicate_cases=charge_cases,group_cases=group_cases,
  original_calls=counts,original_instructions=instructions,elf_sha256=SOURCE_HASH,
  native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='All273 command templates; whole178ac8 and178980 core/remap wrapper,whole178dc8 charge predicate truth,all step positions/timeouts/byte wrap,charge52 threshold/6000saturation,completion buffer preservation.31normal+32special slot processing at explicit17959c..1796a8 slice with supplied171-feature frame;whole179530 only for disabled early-return cases. Includes disabled definitions with old buffers,unused-slot aging and special consumed reset. Features supplied as isolated predicates. Sampling,binding initialization and whole dispatch have separate input_features/input_bindings/input_pipeline reports; game-state action selection and gameplay integration remain pending.')
 (ROOT/'outputs/ss6-feasibility/command_input_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:len(v) if k=='successful_traces' else v for k,v in report.items()},indent=2))
if __name__=='__main__':main()
