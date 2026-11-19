#!/usr/bin/env python3
"""Original match helpers and clearly bounded result-classification slice."""
import hashlib,itertools,json,random,subprocess
from pathlib import Path
from mips_probe import Probe,signed as signed_bits
def signed(value):return signed_bits(value,32)
ROOT=Path(__file__).resolve().parents[2]
OFFSETS=[0x1c,0x20,0x24,0x28,0x2c,0x34,0x38,0x3c]
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes();p=Probe(raw)
 b,a,o=0x1b00000,0x1c00000,0x1e00000;sp=0x1fff000
 players=[b+0x254,b+0x35c];actors=[a,a+0xf2c]
 p.write(0x4d3d00,b,4);p.write(0x4d3d08,a,4);p.write(0x4c3808,3,4)
 p.write(0x123a0c0,0,1)
 for i,(player,actor) in enumerate(zip(players,actors)):
  p.write(b+0x24c+i*4,actor,4);p.write(actor,o+i*0x1000,4);p.write(actor+0xa24,i,4)
 commands=[];expected=[];counts={};rng=random.Random(0x147db8)
 def add(kind,values,want):commands.append(' '.join(map(str,[kind,*values])));expected.append(want)
 def write_player(addr,values):
  for off,v in zip(OFFSETS,values):p.write(addr+off,v,4)
  for i,v in enumerate(values[8:]):p.write(addr+0x40+i,v,1)
 def read_player(addr):return [signed(p.read(addr+off,4)) for off in OFFSETS]+[p.read(addr+0x40+i,1) for i in range(5)]
 def sample():
  return [rng.choice([-1,0,1,2,5]),rng.choice([-1,0,1]),rng.randint(-1,10),rng.randrange(5),rng.randrange(1,6),
          rng.choice([0,1,99,104,119,120,0x7fffffff,-0x80000000,rng.randint(-1000,1000)]),
          signed(rng.getrandbits(32)),signed(rng.getrandbits(32)),*[rng.randrange(256) for _ in range(5)]]
 for _ in range(1536):
  values=sample();args=[rng.choice([0,4,5,6,255]),rng.randrange(2),rng.randrange(2),rng.randrange(2)]
  write_player(players[0],values);p.run(0x147db8,[players[0],*args]);out=read_player(players[0])
  p.write(a+0xa24,0,4);complete,_=p.run(0x14ab80,[a])
  add('record',[*values,*args],[*out,complete])
 counts['whole147db8_and14ab80']=1536
 for selected,source in itertools.product([-1,0,1,2],[-0x80000000,-1001,-1000,-1,0,999,1000,119000,0x7fffffff]):
  values=sample();write_player(players[0],values);p.write(0x443140,selected,4)
  for i in range(2):p.write(0x4430e0+i*0x30+8,source,4)
  p.run(0x147cc8,[players[0]]);out=read_player(players[0]);complete,_=p.run(0x14ab80,[a])
  add('init',[*values,selected,source],[*out,complete])
 counts['whole147cc8_projected_fields']=36
 for _ in range(128):
  values=sample();write_player(players[0],values);p.run(0x147d28,[players[0]])
  out=read_player(players[0]);complete,_=p.run(0x14ab80,[a]);add('reset',values,[*out,complete])
 counts['whole147d28_projected_fields']=128
 for _ in range(512):
  values=[sample(),sample()]
  life=rng.choice([[0,0],[200,0],[0,200],[199,0],[0,99],[80,80],[200,1],[1,200],[49,100],[100,49]])
  maximum=[200,200]
  for i,addr in enumerate(players):
   write_player(addr,values[i]);p.write(sp+i*4,actors[i],4);p.write(sp+0x20+i*4,addr,4)
   p.write(actors[i]+0xa30,life[i],4);p.write(actors[i]+0xa34,maximum[i],4)
  p.registers[18]=b
  # Unequal life branches return to143d58, bypassing143d54. Both stop
  # points precede mode/UI handling; every reached callee executes intact.
  p.run(0x143ce0,stop_before=(0x143d54,0x143d58))
  out=[signed(p.read(b+0x24,4)),p.read(b+0x28,4),p.registers[22],p.read(b+0x20,4)]
  for addr in players:out+=read_player(addr)
  complete,_=p.run(0x145358,[b]);out.append(complete)
  add('round',[*values[0],*values[1],*life,*maximum],out)
 counts['slice143ce0_result_and_whole145358']=512
 for mode,submode,winner,wins,required in itertools.product([0,1,2,3,11,12],[0,4,5,6],[-1,0,1],[(0,0),(1,0),(0,2),(2,2)],[1,2,3]):
  p.write(0x4c3808,mode,4);p.write(0x4c38a8,submode,4)
  p.write(b,8,4);p.write(b+0x18,7,4);p.write(b+0x20,winner==-1,4);p.write(b+0x24,winner,4)
  for i,actor in enumerate(actors):
   p.write(actor+0x244,0x40000000,4);p.write(actor+0x2f0,0,4)
   p.write(players[i]+0x28,wins[i],4);p.write(players[i]+0x2c,required,4)
  for address in range(0x46a908,0x46a944,4):p.write(address,0,4)
  p.run(0x144570,[b]);assert p.read(b+0x18,4)==8
  assert all(p.read(actor+0x244,4)&0x20000 for actor in actors)
  add('transition',[mode,submode,winner,int(winner==-1),wins[0],required,wins[1],required],
      [p.read(b,4),signed(p.read(b+0x114+2*4,4))//256])
 counts['whole144570_completion_no_skip']=len(commands)-sum(counts.values())
 timer=b+0x104
 for _ in range(1536):
  op=rng.randrange(6);index=rng.randrange(7);ticks=rng.choice([0,1,30,90,120,-1,0x7fffffff,-0x80000000])
  divisor=rng.choice([1,2,8]);lock=rng.choice([-1,0,1,40,0x7fffffff,-0x80000000])
  delta=rng.choice([0,85,128,256,512,0x7fffffff,-0x80000000])
  values=[rng.choice([0,1,256,0x173400,0x7fffffff,-0x80000000,signed(rng.getrandbits(32))]) for _ in range(7)]
  p.write(timer+4,lock,4);p.write(timer+0xc,delta,4)
  for i,v in enumerate(values):p.write(timer+0x10+i*4,v,4)
  result,_=p.run([0x143180,0x143228,0x143250,0x143260,0x143288,0x143200][op],[timer,index,ticks,divisor])
  active,_=p.run(0x143218,[timer])
  add('timer',[op,index,ticks,divisor,lock,delta,*values],
      [signed(result) if op in (3,4) else 0,signed(p.read(timer+4,4)),signed(p.read(timer+0xc,4)),
       *[signed(p.read(timer+0x10+i*4,4)) for i in range(7)],active])
 counts['whole143180_143228_143250_143260_143288_143200_143218']=1536
 binary=ROOT/'work/ss6/build-native/ss6-match-progress-probe'
 native=subprocess.run([str(binary)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 rows=[[int(v) for v in line.split()] for line in native.stdout.splitlines()]
 assert len(rows)==len(expected)
 for command,got,want in zip(commands,rows,expected):assert got==want,(command,got,want)
 report=dict(status='passed',cases=counts,total=len(rows),elf_sha256=hashlib.sha256(raw).hexdigest(),
  native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
  scope='Unmodified original helpers.147cc8/147d28 compare represented statistics only, excluding round buffer.143ce0 result classification is a slice stopping before mode/UI work; ordinary1393a0=false.144570 completion runs WHOLE with ready actors and no skip input across modes,submodes,draws and match thresholds. Timer helpers compare signed wrapping and OLD return values with supplied delta; global clock policy excluded. No whole game-frame or next-round initialization claim.')
 (ROOT/'outputs/ss6-feasibility/match_progress_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
