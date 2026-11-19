#!/usr/bin/env python3
"""Whole knockdown/get-up callbacks, including real first-landing effect creation."""
import hashlib,itertools,json,struct,subprocess,random
from knockdown_oracle import fixture,ROOT,ASSETS,CTX,OTHER,OTHER_OBJECT
from mips_probe import signed
BINARY=ROOT/'work/ss6/build-native/ss6-knockdown-probe'
FIELDS=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,0xfe,*range(0x4c,0x64,4),0x40,0x44]

def main(fall_state=64,probe=BINARY):
 p,a,o,b=fixture();commands=[];expected=[];instructions=0;traces=[];dusts=0;float_logs=0
 callbacks={0:0,0x1715b0:1,0x171640:2,0x170cd8:4,0x1706c0:5,0x170758:6,0x170de8:7,0x170ef8:8}
 def original(fn,args=()):
  nonlocal instructions
  v,n=p.run(fn,[signed(v&0xffffffff,32) for v in args],limit=500000);instructions+=n;return v
 def snapshot(dust=0,life=0):
  callback=p.read(a+0x260,4)
  phase=(9 if p.read(a+0x274,4)==7 else 3) if callback==0x169a50 else callbacks[callback]
  return [phase,*[p.read(a+off,4) for off in [0x23c,0x244,0x248,0xb8]],p.read(OTHER+0xb8,4),p.read(OTHER+0x248,4),
   p.read(a+0x253,1),signed(p.read(a+0xa4c,4),32),signed(p.read(a+0x190,2),16),signed(p.read(a+0x192,2),16),p.read(a+0x18c,4),dust,life,
   *[signed(p.read(a+0x1b0+i*4,4),32) for i in range(35)],
   *[signed(p.read(o+off,4),32) if 0x4c<=off<0x64 else p.read(o+off,2 if off==0xfe else 4) for off in FIELDS],
   p.read(0x3d2e80,4),p.read(p.read(0x5d1bf8,4)+0xa8,4),p.read(p.read(0x5d1bf8,4)+0xac,4)]
 def command(op,*vs):
  nonlocal p,a,o,b,dusts,float_logs
  commands.append(' '.join(map(str,[op,*vs])));dust=life=0
  if op=='reset':p,a,o,b=fixture()
  elif op=='flags':
   for off,v in zip([0x38,0x104,0x108],vs[:3]):p.write(o+off,v,4)
   for off,v in zip([0x23c,0x244,0x248],vs[3:6]):p.write(a+off,v,4)
   p.write(a+0x24c,vs[6],1)
  elif op=='motion':
   for off,v in zip(range(0x4c,0x64,4),vs[:6]):p.write(o+off,v,4)
   for off,v in zip([0x40,0x44],vs[6:]):p.write(o+off,struct.unpack('<I',struct.pack('<f',v))[0],4)
  elif op=='state':
   p.write(a+0x194,vs[0]|(vs[1]<<16),4);p.write(a+0x190,-1,4);p.write(a+0x18c,0,4)
  elif op=='input':
   press,back100,down,control,training,training_action,choice,special,character,ready,ai,x,system,custom=vs
   assert not special and not ai and not training, 'producer fixture handled separately'
   for off,v in [(0x2ec,press),(0x3c4,back100),(0x3c0,down),(0xa20,control),(0xa10,character),(0x10c,system)]:p.write(a+off,v,4)
   p.write(OTHER_OBJECT+0x40,struct.unpack('<I',struct.pack('<f',x))[0],4)
   #System6 resolves descriptor through saved custom selection. Use the
   #already validated descriptor fixture from the input/entry suite.
   if system==6:raise AssertionError('custom descriptor setup pending')
  elif op=='choice':p.write(a+0xa4c,vs[0],4);p.write(a+0x253,vs[1],1)
  elif op=='random':p.write(0x443150,vs[0],4);p.write(0x3d2e80,vs[1],4);p.write(p.read(0x5d1bf8,4)+0xa8,vs[2],8)
  elif op=='heavy':original(0x171418,[CTX,fall_state-62]);original(0x149918,[a])
  elif op=='down':original(0x170c60,[CTX]);original(0x149918,[a])
  elif op=='rise':original(0x170690,[CTX])
  elif op=='commit':original(0x11d8e0,[o])
  elif op in ['animate','move']:
   p.write(o+0x30,vs[0],4);p.write(a+0x1ac,vs[0],4);original(0x11d730 if op=='animate' else 0x11d6c8,[o])
  elif op=='choose':original(0x1720b0,[CTX])
  elif op=='request':original(0x172008,[CTX])
  elif op=='landing':dust=original(0x173970,[CTX])
  elif op=='callback':
   old=p.read(0x46a904,4);cb=p.read(a+0x260,4);oldFlags=p.read(a+0x248,4);oldDelay=p.read(a+0x1b0+30*4,4)
   if cb:
    original(0x168aa0,[CTX]);original(cb,[CTX]);original(0x149918,[a])
   dust=old-p.read(0x46a904,4);assert dust in [0,1]
   if dust:
    dusts+=dust
    text=bytes(p.memory[0x1a00000:p.read(p.read(p.read(0x5d1bf8,4)+8,4),4)])
    assert b'createComplex:cn=29,x=' in text and b',y=0.0,z=0.0,mag=1.00,' in text
    text=None;float_logs+=1
   #The callback emits14a8d0(-10); that helper's handicap/mode/healing
   #effects belong to life commit, not the raw request event in this probe.
   if cb==0x170ef8 and oldDelay==0 and oldFlags&0x10000000:life=-10
  expected.append(snapshot(dust,life))
 def compare_states():
  result=subprocess.run([str(probe),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True)
  assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
  actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
  for i,(x,y) in enumerate(zip(actual,expected)):
   assert x==y,(i,commands[max(0,i-5):i+1],[(n,xx,yy) for n,(xx,yy) in enumerate(zip(x,y)) if xx!=yy])
 for armed,mirror,delta in itertools.product([0,1],[0,1],[128,256,512]):
  command('reset');command('flags',0x10000000|mirror*0x80000,0x340,0,armed*0x1000,0x8000,0,0)
  command('motion',4096,12345,256,8192,-16384,-512,320,-2)
  command('state',2,fall_state);command('choice',0,15);command('heavy');command('commit');changes=[];last=1
  for tick in range(600):
   command('animate',delta);command('move',delta);command('callback');command('commit')
   phase=expected[-1][0]
   if phase!=last:changes.append([tick+1,phase]);last=phase
   if p.read(a+0x190,2)!=65535:
    state=p.read(a+0x192,2)
    if state==16:command('state',2,16);command('down');command('commit')
    elif state==7:command('state',2,7);command('rise')
    else:break
  else:raise AssertionError('get-up did not finish')
  assert p.read(a+0x190,2)==0 and p.read(a+0x253,1)==0
  assert p.read(a+0x1b8,4)==0
  traces.append(dict(armed=armed,mirror=mirror,delta=delta,updates=tick+1,transitions=changes))
 print('ordinary knockdown traces',len(traces),'passed original execution',flush=True)
 if fall_state==62:
  compare_states()
  return dict(fall_state=62,traces=traces,snapshots=len(expected),original_instructions=instructions,landing_dust=dusts)
 #Delay/hold/release includes OLD-value timer semantics and rewinding an
 #already-ended lying-down clip without clearing its completion flag.
 for armed,alternate,delta,release,dead in itertools.product([0,1],[0,1],[128,256,512],[0,25,999],[0,1]):
  command('reset');command('flags',0x10000000,0x200,0,armed*0x1000|dead*0x80,alternate*0x8000,0,0)
  command('input',0,0,1,0,0,0,0,0,0,0,0,400,8,0);command('state',2,16);command('down');command('commit')
  held=0
  for tick in range(700):
   if p.read(a+0x260,4)==0x170de8:
    held+=1
    if held>release:command('input',0,0,0,0,0,0,0,0,0,0,0,400,8,0)
   command('animate',delta);command('move',delta);command('callback');command('commit')
   if p.read(a+0x190,2)!=65535 or expected[-1][0]==9:break
  else:raise AssertionError('delayed rise did not request')
  traces.append(dict(delay=True,armed=armed,alternate=alternate,delta=delta,release=release,dead=dead,updates=tick+1))
 selector_cases=0
 #Whole recovery selection/request at the exact Y/velocity boundaries.
 #These validate requests only; no roll or special animation is substituted.
 command('reset')
 for dead,blocked,y,vy,latched,press,back100 in itertools.product(
     [0,1],[0,1],[-1,0,20,20.125],[-256,0,256],[0,2],[0,1],[0,1]):
  command('flags',0x10000000,0x200,0,0x1000|dead*0x80,blocked*0x10,0,0)
  command('motion',0,0,0,0,vy,0,320,y);command('choice',latched,15)
  command('input',press,back100,0,0,0,0,0,0,0,0,0,400,0,0)
  command('choose');selector_cases+=1
 for choice,mirror,x,other,table,index in itertools.product(range(5),[0,1],[300,400],[300,400], [0,2],[0,64]):
  command('flags',0x10000000|mirror*0x80000,0x200,0,0x1000,0,0,0)
  command('motion',0,0,0,0,0,0,x,0);command('state',table,index);command('choice',choice,0)
  command('input',0,0,0,0,0,0,0,0,0,0,0,other,0,0);command('request');selector_cases+=1
 compare_states()
 report=dict(status='passed',traces=traces,states=len(expected),selector_cases=selector_cases,original_instructions=instructions,whole_first_landing_effects=dusts,float_formatted_logs=float_logs,
  native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Whole171418 variant2,1715b0 INCLUDING real170fa0/1242c0/124620 effect allocation,171640,169a50 case5,170c60/170cd8/170de8/170ef8,170690/1706c0/1706d8/170758,16fd90 and object wrappers. Initialized resident effect/task pools and cached libc Bigint/FILE; no patched/skipped callees. Both armed states/mirrors/deltas128/256/512,system8 delayed get-up including timeout health request and KO hold. Finite FP model,not hardware proof. Upstream AI/special recovery predicates and full state-entry/contact scheduler excluded.')
 (ROOT/'outputs/ss6-feasibility/knockdown_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:len(v) if k=='traces' else v for k,v in report.items()},indent=2))
if __name__=='__main__':main()
