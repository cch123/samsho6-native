#!/usr/bin/env python3
"""Resource00 intro/victory/corpse playback against unmodified helpers."""
import hashlib,itertools,json,subprocess
from pathlib import Path
from mips_probe import idle_fixture,signed
from round_entry_oracle import buffered_stdout
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'work/ss6/extracted/resources'
def main():
 raw=(ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
 p,o=idle_fixture(raw,(ASSETS/'aid_00.bin').read_bytes(),(ASSETS/'act_00.bin').read_bytes())
 buffered_stdout(p);p.write(0x345188,0,4)
 actor,ctx,battle=0x1c00000,0x1e02000,0x1b00000
 p.write(0x4d3d00,battle,4);p.write(battle+0x254+0x2c,2,4)
 fields=[0x24,0x28,0x2c,0xc0,0x3c,0x38,0x104,0x108,0xc4,0xfe]+list(range(0x4c,0x64,4))+[0x40,0x44]
 callbacks={0:0,0x14e320:1,0x169a50:2};commands,expected,scenarios=[],[],[]
 def command(op,*vs):
  commands.append(' '.join(map(str,[op,*vs])))
  if op=='reset':
   p.memory[o:o+0x200]=bytes(0x200);p.memory[actor:actor+0xf2c]=bytes(0xf2c)
   p.write(actor,o,4);p.write(ctx,actor,4);p.write(actor+0xa3c,-1,4)
   p.write(0x4d3d08,actor,4)
   p.write(actor+0x1ac,256,4)
   p.write(o+0xc8,1,4);p.write(o+0x104,0x200,4)
   for address,args in [(0x120390,[o,0]),(0x11dda0,[o]),(0x11de10,[o]),(0x11e1c0,[o])]:p.run(address,args)
  elif op=='flags':
   for off,v in zip([0x38,0x104,0x108],vs):p.write(o+off,v,4)
  elif op in ('begin','final'):
   loser,posture,gates,life=vs
   p.write(actor+0x23c,posture,4);p.write(actor+0x244,gates,4);p.write(actor+0xa30,life,4)
   p.write(actor+0x194,(2|(15<<16)) if loser else 41<<16,4)
   p.write(battle+0x254+0x28,2 if op=='final' else 0,4)
   p.run(0x14e178 if loser else 0x14e000,[ctx]);p.run(0x149918,[actor])
  elif op=='intro':
   player,gates=vs;p.write(actor+0xa24,player,4);p.write(actor+0x244,gates,4)
   #The delayed restart clears the object's mute bit. Keep the original
   #owner lookup valid even though sound hardware is disabled globally.
   p.write(0x4d3d08,actor-player*0xf2c,4);p.write(o+0xcc,player,4)
   p.write(actor+0x23c,0x1000,4);p.write(actor+0x194,39<<16,4)
   p.run(0x14df00,[ctx]);p.run(0x149918,[actor])
  elif op=='defer':p.run(0x14be28,[actor,vs[0]])
  elif op=='commit':p.run(0x11d8e0,[o])
  elif op in ('animate','move'):
   p.write(o+0x30,vs[0],4);p.write(actor+0x1ac,vs[0],4);p.run(0x11d730 if op=='animate' else 0x11d6c8,[o])
  elif op=='callback':
   p.run(0x168aa0,[ctx]);p.run(p.read(actor+0x260,4),[ctx]);p.run(0x149918,[actor])
  expected.append([p.read(actor+0x244,4),callbacks[p.read(actor+0x260,4)]]+[
   signed(p.read(o+off,4),32) if 0x4c<=off<0x64 else p.read(o+off,2 if off==0xfe else 4) for off in fields]+[p.read(actor+0x238,4)])
 cases=[(1,armed,alternate,0,mirror,delta) for armed,alternate,mirror,delta in itertools.product([0,1],[0,1],[0,1],[128,256,512])]
 cases += [(0,armed,0,life,mirror,delta) for armed,life,mirror,delta in itertools.product([0,1],[49,99,100,200],[0,1],[128,256,512])]
 cases=[(*case,False) for case in cases]+[(0,1,0,life,mirror,delta,True) for life,mirror,delta in itertools.product([49,99,100,200],[0,1],[128,256,512])]
 for loser,armed,alternate,life,mirror,delta,final in cases:
  command('reset');command('flags',0x10000000|mirror*0x80000,0x200,0)
  command('final' if final else 'begin',loser,armed*0x1000|loser*0x80,0x40000000|alternate*0x8000,life);command('commit')
  action=p.read(o+0x24,4);first_ready=None
  for tick in range(640 if final else 480):
   command('animate',delta);command('move',delta);command('callback')
   if first_ready is None and expected[-1][0]&0x40000000:first_ready=tick+1
  assert first_ready is not None and p.read(o+0x24,4)==action
  assert p.read(actor+0x190,4)==0, 'Holding damage15 must not restart KO'
  scenarios.append(dict(loser=loser,armed=armed,alternate=alternate,life=life,mirror=mirror,delta=delta,final=final,action=action,first_ready=first_ready))
 for player,delay,delta in itertools.product([0,1],[0,1,3,17],[128,256,512]):
  command('reset');command('flags',0x10000000|player*0x80000,0x200,0)
  command('intro',player,0x40000000);command('defer',delay);command('commit')
  first_ready=None;steps=set();zero_holds=0;restart_ticks=[]
  for tick in range(460):
   old_timer=p.read(actor+0x238,4)
   command('animate',delta);command('move',delta)
   steps.add(p.read(o+0x28,4))
   if p.read(o+0x28,4)==12 and p.read(o+0x104,4)&0x100:zero_holds+=1
   command('callback');command('commit')
   if old_timer and not p.read(actor+0x238,4):restart_ticks.append(tick+1)
   if first_ready is None and expected[-1][0]&0x40000000:first_ready=tick+1
  assert first_ready is not None and steps==set(range(21)) and zero_holds==1,(player,delay,delta,first_ready,steps,zero_holds)
  if delay:assert restart_ticks==[(delay*256+delta-1)//delta]
  scenarios.append(dict(introduction=True,player=player,delay=delay,delta=delta,action=492,first_ready=first_ready))
 binary=ROOT/'work/ss6/build-native/ss6-ending-playback-probe'
 run=subprocess.run([str(binary),str(ASSETS)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
 actual=[list(map(int,row.split())) for row in run.stdout.splitlines()];assert len(actual)==len(expected)
 for i,(a,e) in enumerate(zip(actual,expected)):assert a==e,(i,commands[max(0,i-4):i+1],a,e)
 report=dict(status='passed',scenarios=scenarios,states=len(expected),elf_sha256=hashlib.sha256(raw).hexdigest(),
  native_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),scope='Whole14e178/14e000/14df00 resource00 entry including auxiliary null paths,149918 action queue; whole168aa0,14be28,14e320 including positive timer34/reposition/restart492,1a3930 resource00 readiness,169a50 case4,player wrappers. Both armed states for corpse48..51/non-final495..498; armed final499/501, HP99/100. Same-character intro492, both players, all21records including one zero-duration hold, supplied delay0/1/3/17,delta128/256/512. Original mute flag; audio output,cross-character voice-delay selection,unarmed final variants,full actor/round scheduler excluded.')
 (ROOT/'outputs/ss6-feasibility/ending_playback_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v if k!='scenarios' else len(v) for k,v in report.items()},indent=2))
if __name__=='__main__':main()
