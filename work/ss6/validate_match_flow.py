#!/usr/bin/env python3
"""Continuous native matches from real walking/light contacts, no midbout edits."""
import hashlib,json,subprocess
from pathlib import Path
from validate_contact_trial import run,ROOT,PROBE,ASSETS
def play(order,attack=5,interval=49,crouching=False):
 p=subprocess.Popen([str(PROBE),str(ASSETS)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 commands=[];rows=[]
 def send(command):
  commands.append(command);p.stdin.write(command+'\n');p.stdin.flush();line=p.stdout.readline()
  assert line,(command,p.stderr.read())
  row=[float(x) for x in line.split()];rows.append(row);return row
 row=send('match');last_attack=-100;old_command=[None,None]
 try:
  for tick in range(16000):
   if row[106]:break
   index=int(row[105]);attacker=order[min(index,len(order)-1)]
   for player in range(2):
    command=(1 if abs(row[18]-row[7])>66 else 7 if crouching else 0) if row[57]==4 and player==attacker else 0
    if command!=old_command[player]:row=send(f'command {player} {command}');old_command[player]=command
   if row[57]==4 and tick-last_attack>=interval and abs(row[18]-row[7])<=(66 if crouching else 78):
    row=send(f'command {attacker} {attack}');last_attack=tick
   row=send('tick 1')
  else:raise AssertionError(('match did not finish',order,row))
 finally:
  p.stdin.close();assert p.wait(timeout=10)==0,p.stderr.read()
 assert row[57:59]==[10,10] and row[96]==1 and row[74]+row[84]==len(order)
 assert [row[74],row[84]]==[order.count(0),order.count(1)]
 by_tick={int(r[0]):r for r in rows};transitions=[];previous=None
 for t,r in by_tick.items():
  if r[57]!=previous:transitions.append(dict(update=t,state=int(r[57]),round=int(r[105])));previous=r[57]
 # Each new round uses the original timer2 OLD-value gate and entry skip.
 resets=[t for t,r in by_tick.items() if r[57]==1 and by_tick[t-1][57]==8]
 assert len(resets)==len(order)-1
 for t in resets:
  before,reset=by_tick[t-1],by_tick[t]
  assert reset[2]==reset[13]==200 and reset[7]==240 and reset[18]==400
  assert reset[5]==(2 if reset[27] in [1,2] else 0) and reset[16]==(2 if reset[33] in [1,2] else 0)
  assert reset[1]==-1 and reset[94]==-1
  assert reset[74:94]==before[74:94], 'match history must survive actor reset'
  for base in [24,30]:
   #System0 preserves active rage across rounds, including its180-unit
   #sword capacity. Heavy contacts can reach this branch before the KO.
   capacity=(180 if reset[base+3]==1 else 100)*256
   assert reset[base:base+2]==[capacity,capacity]
  assert reset[98:104]==[0]*6
  assert by_tick[t+1][57:59]==[1,3] and by_tick[t+1][99]==30*256
  assert by_tick[t+31][57:59]==[1,3] and by_tick[t+32][57:59]==[3,3]
  assert by_tick[t+142][57:59]==[3,4] and by_tick[t+143][57:59]==[4,4]
  assert by_tick[t+142][66]>0 and by_tick[t+143][66]==0
  for visit in range(t,t+143):
   assert int(by_tick[visit][41])&1 and int(by_tick[visit][43])&1
 # Exactly two pause windows in a2-0 match:40 non-final,60 final.
 pauses=[];n=0
 for r in by_tick.values():
  if r[64]:n+=1
  elif n:pauses.append(n);n=0
 assert pauses==[40]*(len(order)-1)+[60],pauses
 assert row[5+order[-1]*11]==499 and row[95]==16
 assert run(commands)==rows
 return commands,dict(order=order,updates=int(row[0]),transitions=transitions,resets=resets,pauses=pauses,wins=[int(row[74]),int(row[84])])
def main():
 cases=[]
 for order in [[0,0],[1,1],[0,1,0]]:
  commands,case=play(order);cases.append(case)
  # Keep reviewable playback commands for UI/window checks. They contain
  # only initial setup and controls/ticks, never midround life/position edits.
  (ROOT/'work/ss6/scenarios'/('match-'+''.join(map(str,order))+'.txt')).write_text('\n'.join(commands)+'\n')
  print('passed',case['order'],case['updates'],case['wins'],flush=True)
 # Low-life final and final doubleKO use explicitly stated starting fixtures.
 for winner,life in [(0,99),(1,99),(0,100),(1,100),(2,1)]:
  initial=['rounds','win-limit 1','place 280 344']
  for player in range(2):initial.append(f'life {player} {life if player==winner else 1}')
  for player in ([winner] if winner<2 else [0,1]):initial.append(f'command {player} 5')
  rows=run(initial+['tick 1']*800);last=rows[-1]
  assert last[106]==1 and last[57:59]==[10,10]
  assert last[95]==(18 if winner==2 else 16)
  if winner<2:assert last[5+winner*11]==(501 if life<100 else 499)
  paused=sum(r[64] for r in rows);assert paused==(40 if winner==2 else 60)
  name=f'match-final-{winner}-{life}.txt';(ROOT/'work/ss6/scenarios'/name).write_text('\n'.join(initial)+'\n')
  cases.append(dict(winner=winner,initial_life=life,pause=paused,final_action=None if winner==2 else int(last[5+winner*11])))
 # A non-final doubleKO awards both players a win and takes the90-tick
 # transition. Both corpses must be restored before the deciding round.
 initial=['rounds','place 280 344','life 0 1','life 1 1','command 0 5','command 1 5']
 commands=initial+['tick 1']*500
 rows=run(commands);requested=next(r for r in rows if r[57:59]==[8,0])
 assert requested[99]==90*256 and requested[74]==requested[84]==1
 restored=next(r for r in rows if r[57:59]==[1,1])
 assert restored[2]==restored[13]==200 and restored[7]==240 and restored[18]==400
 assert rows[-1][57:59]==[4,4] and rows[-1][105]==1
 resumed=run(commands+['command 0 1','tick 50','command 0 0','command 0 5','tick 40'])[-1]
 assert resumed[13]<200 and resumed[74]==resumed[84]==1 and resumed[57]==4
 cases.append(dict(nonfinal_double_ko=True,transition_delay=90,reset_update=int(restored[0]),next_round_contact_life=int(resumed[13])))
 report=dict(status='passed_for_integration_fixture',cases=cases,probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),
  scope='Three complete matches from200HP using walking and standing-light contacts only:both2-0winners and2-1decider. First-round initialization and character492 introductions,opening,state8->0/1/3/4 (subsequent rounds skip2),life/position restoration,match history preservation,30timer2 delay,opening final draw,input lock,40/60KO pause,499match victory,state10 terminal boundary,deterministic replay. Five explicit initial-life/one-win fixtures cover501,HP100 and final doubleKO; one non-final doubleKO checks90delay,both corpses restored and next-round actual hit. Full original frames, physical pad parser,menu/audio/GS remain excluded.')
 (ROOT/'outputs/ss6-feasibility/match_flow_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
