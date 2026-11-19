#!/usr/bin/env python3
"""Standing heavy hit selection and whole original grounded hurt callbacks."""
import hashlib,itertools,json,subprocess
from mips_probe import Probe,signed,idle_fixture
from round_entry_oracle import ROOT
ASSETS=ROOT/'work/ss6/extracted/resources'
BINARY=ROOT/'work/ss6/build-native/ss6-reaction-probe'

def compare(mode,commands,expected):
 result=subprocess.run([str(BINARY),str(ASSETS),mode],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()]
 assert len(actual)==len(expected)
 for c,a,e in zip(commands,actual,expected):assert a==e,(c,a,e)

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 source,target,os,ot,ctx=0x1c00000,0x1c00f2c,0x1e00000,0x1e01000,0x1e02000
 p.write(0x4d3d08,source,4);instructions=0;commands=[];expected=[];states=set()
 def original(address,args=()):
  nonlocal instructions
  v,n=p.run(address,[signed(x&0xffffffff,32) for x in args],limit=200000);instructions+=n;return v
 from round_entry_oracle import buffered_stdout
 buffered_stdout(p)
 for crouch,alternate,table,previous,part,special,air,shield,heavy in itertools.product(
     [0,1],[0,1],[0,2],[0,32,34,35,37,38,40,44,46,49,255],range(3),[0,1],[0,1],[0,1],[0,1]):
  p.memory[source:source+0x2000]=bytes(0x2000);p.memory[os:ctx+16]=bytes(ctx+16-os)
  flags=0x1000|(8 if crouch else 0)|(0x02000000 if shield else 0)
  for actor,obj,slot in [(source,os,0),(target,ot,1)]:
   for off,v in [(0,obj),(0xa24,slot),(0x190,-1),(0xa3c,-1)]:p.write(actor+off,v,4)
   p.write(obj+0xcc,slot,4)
  p.write(source+0x194,1|(8<<16),4);p.write(source+0x19a,12,1)
  p.write(source+0x23c,0x1000|(0x20 if air else 0),4);p.write(source+0x248,0x1234,4)
  p.write(target+0x194,table,4);p.write(target+0x23c,flags,4)
  p.write(target+0x24c,alternate*2,1);p.write(target+0x255,previous,1)
  p.write(target+0x258,heavy,4)
  file=p.read(p.read(0x5d1bf8,4)+8,4);p.write(file,0x1a00000,4);p.write(file+8,65536,4)
  original(0x14d198,[target,os,0,12,part,special]);state=p.read(target+0x255,1);states.add(state)
  result=[p.read(target+0x23c,4),signed(p.read(target+0x190,2),16),signed(p.read(target+0x192,2),16),
   p.read(target+0x18c,4),state,p.read(target+0x256,1),p.read(source+0x1b0,4),p.read(source+0x1b4,4),
   p.read(target+0x1b0,4),p.read(target+0x1b4,4)]
  p.write(ctx,target,4);p.write(ctx+4,source,4)
  if state==64:original(0x171418,[ctx,2])
  else:original(0x1707b0,[ctx,(state-32)//3,(state-32)%3])
  result += [p.read(target+0xa3c,4),p.read(target+0x258,4),p.read(source+0x248,4)]
  assert p.read(target+0x25c,4)==0
  commands.append(' '.join(map(str,[flags,alternate*2,previous,table,part,special,air,12,2,heavy,0x1234])));expected.append(result)
 compare('--ground',commands,expected);selection_cases=len(commands)
 commands=[];expected=[];flow_states=0;release_visits=0
 #The callback owns the zero-duration hold and terminal ACT jump suppression.
 #Run both original functions (prefix168aa0 and170890) without skipping callees.
 for state,delta,mirror in itertools.product([32,34,35,37,38,40,43,44,46,47,49],[128,256,512],[0,1]):
  p,o=idle_fixture(raw,(ASSETS/'aid_00.bin').read_bytes(),(ASSETS/'act_00.bin').read_bytes())
  p.write(0x4d3d08,source,4);p.write(target,o,4);p.write(target+0x194,2|(state<<16),4)
  p.write(target+0x23c,0x1000|(8 if state in [38,40,47,49] else 0),4)
  p.write(target+0xa3c,-1,4);p.write(target+0x190,-1,4);p.write(o+0x104,0x200,4)
  p.write(o+0x38,0x10000000|(mirror<<19),4);p.write(o+0xc8,1,4)
  p.write(ctx,target,4);p.write(ctx+4,source,4)
  original(0x1707b0,[ctx,(state-32)//3,(state-32)%3]);original(0x149918,[target]);original(0x11d8e0,[o])
  values=[]
  for tick in range(110):
   p.write(o+0x30,delta,4);original(0x11d730,[o]);original(0x11d6c8,[o])
   release_visits+=bool(p.read(o+0x104,4)&0x100)
   original(0x168aa0,[ctx]);original(0x170890,[ctx])
   values += [p.read(o+off,4) for off in [0x24,0x28,0x2c,0xc0,0x104,0x108]]
   values += [int(p.read(target+0x190,2)!=65535)];flow_states+=1
  commands.append(f'{state} {delta} {mirror} 110');expected.append(values)
 compare('--flow',commands,expected)
 report=dict(status='passed',selection_cases=selection_cases,selected_states=sorted(states),callback_traces=len(commands),
  callback_states=flow_states,hold_or_end_release_visits=release_visits,original_instructions=instructions,
  elf_sha256=hashlib.sha256(raw).hexdigest(),native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
  scope='Whole14d198 raw12/strength2/armed/resource00 grounded selection,previous reaction alternation,special/air-source flags,shield,timers,source40000000,target258;1707b0 or171418 action enqueue. Existing-heavy258=0/1 includes repeated-heavy64. Whole168aa0+170890 after11d730/11d6c8 validates hurt hold release,terminal jump suppression and recovery request at128/256/512deltas,both facings; no state-entry/retreat or full frame claim.')
 (ROOT/'outputs/ss6-feasibility/heavy_reaction_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
