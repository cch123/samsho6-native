#!/usr/bin/env python3
"""Standing heavy integration, natural matches, original entry and PIL scenes."""
import hashlib,itertools,json,random,subprocess
from validate_contact_trial import run,validate_pixels,ROOT,ASSETS,PROBE,VIEWER
from validate_match_flow import play
from round_entry_oracle import fixture

def main():
 cases=[];entry_commands=[];entry_expected=[];entry_instructions=0
 for player,distance in itertools.product([0,1],[64,77.75,78,78.25,100,180]):
  p,a,o,b=fixture(player)
  def original(fn,args=()):
   nonlocal entry_instructions
   value,count=p.run(fn,args,limit=200000);entry_instructions+=count;return value
  original(0x149008,[a,0]);original(0x149918,[a]);original(0x11d8e0,[o])
  #168c58 distance conversion/comparison has its separate range report.
  #This supplies its near/far result to the whole original actor entry.
  p.write(a+0x244,p.read(a+0x244,4)|(0x4000 if distance>=78 else 0),4)
  original(0x14ff80,[a+0x18c,1,8]);original(0x149d08,[a]);original(0x149918,[a]);original(0x11d8e0,[o])
  strength=original(0x1696c8,[a])
  entry_expected.append([p.read(a+0x194,2),p.read(a+0x196,2),p.read(a+0x19a,1),p.read(a+0x23c,4),strength,
   *[p.read(o+off,4) for off in [0x24,0x28,0x2c,0xc0]]])
  entry_commands.append(f'heavy-entry {player} {distance}')
 entry_binary=ROOT/'work/ss6/build-native/ss6-ordinary-probe'
 r=subprocess.run([str(entry_binary),str(ASSETS)],input='\n'.join(entry_commands)+'\n',text=True,capture_output=True,check=True)
 actual=[list(map(int,line.split())) for line in r.stdout.splitlines()]
 assert actual==entry_expected,(actual,entry_expected)
 for distance,attacker,defense in itertools.product([64,100,180],[0,1],[0,3,4]):
  setup=[f'place 280 {280+distance}',f'command {1-attacker} {defense}','tick 1',f'command {attacker} 6']
  rows=run(setup+['tick 1']*240);end=rows[-1];source=2+attacker*11;target=2+(1-attacker)*11
  assert end[source]==200 and end[target]==(200 if defense else 162 if distance==64 else 157)
  assert end[source+9:source+11]==([0,1] if defense else [1,0])
  assert end[source+1:source+3]==[0,0] and end[target+1]==0
  if not defense:assert any(r[target+3]==342 for r in rows)
  cases.append(dict(distance=distance,attacker=attacker,defense=defense,life=end[target],recovered=True))
 #No target clamping shortcut: first walk to maximum separation, then whiff.
 rows=run(['command 0 2','command 1 2','tick 400','command 0 0','command 1 0','command 0 6']+['tick 1']*300)
 assert rows[-1][13]==200 and rows[-1][11]==0 and min(r[24] for r in rows)==84*256
 waiting=next(i for i,r in enumerate(rows) if r[26]==20)
 assert [r[26] for r in rows[waiting:waiting+21]]==list(range(20,-1,-1))
 assert len({r[24] for r in rows[waiting:waiting+21]})==1 and rows[-1][24]==25600
 cases.append(dict(whiff=True,sword_cost=16,recovered=True))
 for player in [0,1]:
  setup=['place 280 430',f'command {player} 6','tick 10',f'command {1-player} 5']
  rows=run(setup+['tick 1']*120)
  assert any(r[5+11*player]==143 and r[5+11*(1-player)]==141 for r in rows)
  assert rows[-1][2]==rows[-1][13]==200 and rows[-1][5]==rows[-1][16]==0
  cases.append(dict(mixed_clash=True,heavy_player=player,recovered=True))
  (ROOT/'work/ss6/scenarios'/f'heavy-clash-{player}.txt').write_text('\n'.join(setup)+'\n')
 rows=run(['place 280 344','command 0 6','command 1 6']+['tick 1']*200)
 assert rows[-1][2]==rows[-1][13]==162 and any(r[5]==r[16]==366 for r in rows)
 cases.append(dict(heavy_trade=True,counter_reaction=366,recovered=True))
 rng=random.Random(189190);commands=[]
 for episode in range(64):
  commands+=['reset',f'place 280 {310+rng.randrange(160)}']
  for _ in range(100):commands += [f'command {rng.randrange(2)} {rng.randrange(7)}',f'tick {rng.randrange(1,14)}']
 random_rows=run(commands)
 assert all(0<=r[2]<=200 and 0<=r[13]<=200 for r in random_rows)
 matches=[]
 for order in [[0,0],[1,1],[0,1,0]]:
  commands,case=play(order,attack=6,interval=80);matches.append(case)
  (ROOT/'work/ss6/scenarios'/('heavy-match-'+''.join(map(str,order))+'.txt')).write_text('\n'.join(commands)+'\n')
  print('heavy match passed',order,case['updates'],flush=True)
 #A fatal simultaneous heavy hit must still reach doubleKO and the next round.
 setup=['rounds','place 280 344','life 0 1','life 1 1','command 0 6','command 1 6']
 rows=run(setup+['tick 1']*600)
 assert any(r[1]==2 for r in rows) and rows[-1][74]==rows[-1][84]==1 and rows[-1][105]==1
 assert rows[-1][57]==4 and rows[-1][2]==rows[-1][13]==200
 cases.append(dict(heavy_double_ko=True,next_round_ready=True))
 print('heavy contacts passed; comparing PIL scenes',flush=True)
 pixels=validate_pixels(heavy=True)
 for name,distance,player,defense in [('near',64,0,0),('far',100,0,0),('mirrored',100,1,0),('guard',100,0,3),('crouch',100,1,4)]:
  (ROOT/'work/ss6/scenarios'/f'heavy-{name}.txt').write_text(f'place 280 {280+distance}\ncommand {1-player} {defense}\ntick 1\ncommand {player} 6\n')
 report=dict(status='passed_for_integration_fixture',entry_cases=len(entry_commands),whole149d08_entry_instructions=entry_instructions,
  entry_probe_sha256=hashlib.sha256(entry_binary.read_bytes()).hexdigest(),scenarios=cases,random_snapshots=len(random_rows),matches=matches,**pixels,
  probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),viewer_sha256=hashlib.sha256(VIEWER.read_bytes()).hexdigest(),
  scope='Armed resource00/system0 standing-heavy raw attack selection;whole original149d08 entry projection,near/far78 boundary,189/190,raw12 contact damage/guard/swordcost,hold release,clash143vs141,counter366,deterministic natural2-0/0-2/2-1 anddoubleKO,next-round reset. Independent decoded-PIL pixels and original anchor projection,not whole original battle or GS proof. Repeated-heavy64 is covered separately by knockdown_trial_validation.json. Pad parsing,cancels,other moves/characters,contact FX/audio remain outside the live subset.')
 (ROOT/'outputs/ss6-feasibility/heavy_trial_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
