#!/usr/bin/env python3
"""Whole original special-state request callers; no move execution implied."""
import collections,hashlib,itertools,json,random,struct,subprocess
from validate_permission_stage import Oracle,extended,encoded,ROOT
from validate_input_permissions import context
from extract_collision_tables import SOURCE_HASH
from mips_probe import signed

def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();assert hashlib.sha256(raw).hexdigest()==SOURCE_HASH
 oracle=Oracle(raw);p=oracle.p;rng=random.Random(0x14c7d0);commands=[];expected=[];outcomes=collections.Counter()
 descriptors=[list(p.memory[0x4d7068+i*16:0x4d7068+(i+1)*16]) for i in range(8)]
 d=descriptors[0].copy();d[14]=44
 def run(kind,a,results,cancels=None,priority=None,count=32,system=6,descriptor=d):
  if cancels is None:cancels=[1]*32
  if priority is None:priority=list(reversed(range(32)))
  config=[system,a['character'],*descriptor];address,body=oracle.setup(a,extended(),context(),config,len(expected)%2);owner=address+0x2c4
  p.memory[owner:owner+0x744]=bytes([0xa5])*0x744
  p.write(owner+0x5bc,count,4);p.memory[owner+0x428:owner+0x448]=bytes(priority)
  p.memory[owner+0x328:owner+0x3a8]=struct.pack('<32I',*results);p.memory[owner+0x3a8:owner+0x428]=struct.pack('<32I',*cancels)
  request=rng.getrandbits(32);pending=[-1,-1];p.write(address+0x18c,request,4);p.memory[address+0x190:address+0x194]=struct.pack('<2h',*pending)
  before=bytes(p.memory[owner:owner+0x744]);beforeBody=bytes(p.memory[body:body+0x600])
  entry=[0x14c7d0,0x14c608,0x14cd78][kind];result=oracle.run(entry,[address])
  assert before==p.memory[owner:owner+0x744],(hex(entry),'input mutation')
  assert beforeBody==p.memory[body:body+0x600],(hex(entry),'body mutation')
  want=[result,p.read(address+0x18c,4),signed(p.read(address+0x190,2),16),signed(p.read(address+0x192,2),16),p.read(address+0x244,4),p.read(address+0x248,4),p.read(body+0x38,4),*p.memory[address+0xf14:address+0xf22]]
  commands.append(' '.join(map(str,['request',kind,*encoded(a),*config,count,*priority,*results,*cancels,request,*pending])));expected.append(want);outcomes[f'{hex(entry)}:{result}']+=1
 #Every character and every candidate slot; repeated raw states, cancel
 #permission, byte overflow and effective-state aliases are independent.
 for character,slot,variant in itertools.product(range(51),range(32),range(6)):
  a=extended();a.update(character=character,state194=[0,7<<16|1,(slot+64)<<16|1,64<<16|1,0,1][variant],flags244=8 if variant in [3,4] else 0,flags248=0xfedcba98,body38=0x80000)
  if variant==5:a.update(flags23c=0x201000,state1a4=1)
  a['bytes']=[255 if variant%2 else 0]*14;results=[0]*32;results[slot]=0x80000000;cancels=[int(variant!=4)]*32
  run(0,a,results,cancels)
 #Damage path uses fixed slots regardless of count, sorted priority or
 #cancelAllowed. Both character-specific first-slot precedence cases included.
 for kind,character,count,mask in itertools.product([0,2],[0,3,4,15],[-1,0,1,31,32],range(16)):
  a=extended();a.update(character=character,state194=81<<16|2,flags244=8);results=[0]*32
  for bit,slot in enumerate([16,17,22,23]):results[slot]=int(bool(mask&(1<<bit)))
  run(kind,a,results,[0]*32,count=count)
 #Current special family controls allowed target families. Try one selected
 #candidate and all candidates to exercise actual priority fall-through.
 for character,state,allCandidates in itertools.product(range(51),range(96),[0,1]):
  a=extended();a.update(character=character,state194=state<<16|1,body108=0x20,action=599)
  results=[1 if allCandidates or i==state%32 else 0 for i in range(32)]
  run(1,a,results)
 for system,byte,contact,table in itertools.product(range(9),[0,43,44,45,255],[0,0x20],[0,1,2]):
  a=extended();a.update(character=0,state194=64<<16|table,body108=contact);descriptor=d.copy();descriptor[14]=byte
  run(1,a,[1]*32,system=system,descriptor=descriptor)
 for case in range(2048):
  a=extended();a.update(character=rng.randrange(51),state194=(rng.randrange(96)<<16)|rng.randrange(3),state1a4=(rng.randrange(3)<<16)|rng.randrange(3),flags23c=rng.choice([0x1000,0x200000,0x10]),flags244=rng.getrandbits(32),flags248=rng.getrandbits(32),body108=rng.choice([0,0x20,0x40,0x60]),action=rng.choice([0,598,599,600]))
  a['bytes']=[rng.randrange(256) for _ in range(14)];priority=list(range(32));rng.shuffle(priority)
  results=[rng.choice([0,0,0,1,0x80000000]) for _ in range(32)];cancels=[rng.choice([0,1,0x80000000]) for _ in range(32)]
  run(case%2,a,results,cancels,priority,count=rng.choice([-1,0,1,7,31,32]))
 binary=ROOT/'work/ss6/build-native/ss6-input-permissions-probe'
 result=subprocess.run([str(binary),str(ROOT/'work/ss6/extracted/resources')],input='\n'.join(commands)+'\n',text=True,capture_output=True)
 assert result.returncode==0,(len(result.stdout.splitlines()),result.stderr)
 actual=[list(map(int,line.split())) for line in result.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(got,want) in enumerate(zip(actual,expected)):assert got==want,(i,commands[i],got,want)
 for entry in ['0x14c7d0','0x14c608','0x14cd78']:assert outcomes[f'{entry}:0'] and outcomes[f'{entry}:1']
 report=dict(status='passed_whole_special_requests',cases=len(expected),original_calls=oracle.calls,original_instructions=oracle.instructions,outcomes=outcomes,
  elf_sha256=SOURCE_HASH,native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Whole14c7d0,14c608 and14cd78. All51 character keys/32 slots,raw versus alias states,same-state exceptions,custom descriptor gate,first/second special categories,priority fall-through,cancel flags and fixed damage-escape slots. Compare pending request,18c,244/248,character bytes and unchanged input/body memory. Inputs are recognized-command snapshots; no sampling/permission/entry integration or playable special-move claim.')
 (ROOT/'outputs/ss6-feasibility/special_requests_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
