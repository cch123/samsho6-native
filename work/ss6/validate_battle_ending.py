#!/usr/bin/env python3
"""Battle integration ending checks, explicitly not a full original-frame oracle."""
import hashlib,json,subprocess
from pathlib import Path
from validate_contact_trial import run,ROOT,PROBE,VIEWER
from mips_probe import Probe
def main():
 cases=[];original=Probe((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes())
 b=0x1b00000;actors=[0x1c00000,0x1c01000];objects=[0x1e00000,0x1e01000]
 original.write(0x4d3d00,b,4);original.write(0x4c3808,3,4)
 phase_checks=dict(whole144360=0,whole144570_wait=0,slice144570_complete=0)
 for attacker,life in [(0,200),(1,200),(2,1),(0,99),(1,99),(0,100),(1,100)]:
  players=[attacker] if attacker<2 else [0,1]
  start=['place 280 344']
  for player in ([1-attacker] if attacker<2 else [0,1]):start += [f'life {player} 1']
  if attacker<2 and life<200:start += [f'life {attacker} {life}']
  start += [f'command {p} 5' for p in players]
  commands=start+['tick 1']*480
  rows=run(commands);end=rows[-1]
  dead=[1-attacker] if attacker<2 else [0,1]
  assert end[1]==attacker and end[57:60]==[8,8,1] and end[68]==1,end
  death=next(r for r in rows if any(r[2+p*11]==0 for p in dead));death_tick=int(death[0])
  by_tick={int(r[0]):r for r in rows}
  assert death[57:59]==[4,4] and death[1]==-1
  assert by_tick[death_tick+1][57:59]==[4,5]
  assert by_tick[death_tick+2][57:59]==[5,5]
  # Result history is committed ON entry5, not at fatal life commit or
  # after the victory animation. A doubleKO records one result for BOTH.
  for player in range(2):
   base=74+player*10
   assert by_tick[death_tick+1][base]==0
   awarded=attacker==2 or player==attacker
   entry=by_tick[death_tick+2]
   assert entry[base]==int(awarded) and entry[base+1]==2
   result_byte=4 if attacker==2 else 32 if life==200 else 0
   assert entry[base+5:base+10]==([result_byte,255,255,255,255] if awarded else [255]*5)
   assert all(r[base:base+10]==entry[base:base+10] for r in rows if r[0]>=death_tick+2)
  assert end[94:97]==([1,18,0] if attacker==2 else [0,15,0])
  assert by_tick[death_tick+2][102]==30*256 # timer5, not an actor timer
  assert by_tick[death_tick+2][98]==0 # timer1 resets on entry
  for tick in range(death_tick+3,481):
   prev,now=by_tick[tick-1],by_tick[tick]
   expected_timer=prev[98] if now[64] else 0 if prev[57]!=prev[58] else min(prev[98]+256,0x173400)
   assert now[98]==expected_timer,(tick,prev[98],now[98],expected_timer)
  paused=[r for r in rows if r[64]]
  assert len(paused)==40 and [int(r[0]) for r in paused]==list(range(death_tick+5,death_tick+45))
  assert all(r[65] and r[66]>0 for r in paused), 'Effects continue during ordinary battle pause'
  assert by_tick[death_tick+2][65:67]==[1,0], 'New priority5 task is queued after this visit'
  first_ui=next(int(r[0]) for r in rows if r[66]>0)
  last_ui=next(int(r[0]) for r in rows if r[0]>death_tick+2 and not r[65])
  assert first_ui==death_tick+3 and last_ui==death_tick+82
  assert by_tick[last_ui][66]>0 and by_tick[last_ui+1][66]==0, 'Final draw survives task completion'
  assert end[67]==1
  before_pause=by_tick[death_tick+4]
  assert all(r[1:62]==before_pause[1:62] for r in paused), 'Pause must hold actors, clocks, contacts, gates and meters'
  # Leaving the attack table still assigns swordWait20; the gauge callback
  # itself must not recover sword or decay rage after requested state5.
  gauge_fields=[24,25,27,28,29,30,31,33,34,35]
  assert all(all(r[j]==by_tick[death_tick+1][j] for j in gauge_fields) for r in rows if r[0]>death_tick+1), 'Round end must stop meter recovery'
  for r in rows:
   if r[0]>=death_tick+2:assert int(r[41])&1 and int(r[43])&1
  milestones=[]
  for player in dead:
   base=2+player*11;extra=45+player*6
   assert end[base:base+5]==[0,2,15,48,1] and end[extra+1:extra+4]==[0,1,1]
   ko=next(r for r in rows if r[extra+1]>0);prior=by_tick[int(ko[0])-1]
   assert prior[base+1:base+4]==[0,0,2],('reaction must enter normal before fallback',prior)
   assert ko[0]>death[0] and ko[extra]==0
   phases=[next(int(r[0]) for r in rows if r[extra+1]==phase) for phase in [1,2,3,4]]
   assert phases==sorted(set(phases));milestones.append(dict(player=player,phases=phases))
  if attacker<2:assert end[3+attacker*11:6+attacker*11]==[0,41,495 if life>=100 else 497]
  body_ready=int(next(r[0] for r in rows if r[59]));entry7=int(next(r[0] for r in rows if r[57]==7))
  entry8=int(next(r[0] for r in rows if r[57]==8));ending_ready=int(next(r[0] for r in rows if r[68]))
  assert entry7==body_ready+1 and by_tick[body_ready][58]==7
  assert by_tick[entry8-1][57:59]==[7,8]
  assert all(int(by_tick[ending_ready-1][60+i])&0x40000000 for i in [0,1])
  if attacker<2:
   heads=[]
   for r in rows:
    if r[57]==7 and (not heads or heads[-1][1]!=r[71]):heads.append((int(r[0]),int(r[71])))
   #Whole1441e0 checks the WINNER'S OPPONENT via1400a8. These areKO
   #fixtures: no living-loser focus or30-tick hold belongs in their queue.
   assert [v for _,v in heads]==[2,0],heads
   assert by_tick[heads[-1][0]+1][58]==8
  else:assert by_tick[entry7][69:72]==[1,1,0] and entry8==entry7+2
  # Replay the original round-update phase from the previous native
  # snapshot. This compares that phase only; actor animation/gates happen
  # later in the native frame. The successful state8 path stops BEFORE the
  # first timer/stat transition, without patching/skipping any callee.
  for tick in range(entry7+1,ending_ready+1):
   before,after=by_tick[tick-1],by_tick[tick]
   if before[57]!=before[58]:continue
   state=int(before[57]);original.write(b,state,4)
   original.write(b+0x34+0x4c,int(before[69]),4)
   original.write(b+0x34+0x50,int(before[71]),1)
   for i,(a,o) in enumerate(zip(actors,objects)):
    original.write(b+0x24c+i*4,a,4);original.write(a,o,4)
    original.write(a+0x244,int(before[60+i]),4);original.write(a+0x2f0,0,4)
    original.write(o+0x104,int(before[50+i*6]),4)
   original.run(0x144360 if state==7 else 0x144570,[b],stop_before=() if state==7 else (0x1446b8,))
   complete=original.registers[29]!=0x1fff000
   if state==7:
    phase_checks['whole144360']+=1;assert original.read(b,4)==after[58]
   else:
    phase_checks['slice144570_complete' if complete else 'whole144570_wait']+=1
    assert complete==bool(after[68])
   for i,(a,o) in enumerate(zip(actors,objects)):
    assert original.read(a+0x244,4)&0x20000==int(after[60+i])&0x20000
    assert original.read(o+0x104,4)&0x400000==int(after[50+i*6])&0x400000
  # Inputs after lock must not restart a body action or revive either actor.
  spam=commands+[x for _ in range(60) for x in ['command 0 5','command 1 5','command 0 1','command 1 2','tick 1']]
  after=run(spam)[-1]
  for base in [2,13]:assert after[base:base+5]==end[base:base+5] and after[base+5]==end[base+5]
  assert after[47]==end[47] and after[53]==end[53] and after[59]==1
  assert run(commands)==rows
  suffix='' if life in (1,200) else '-low' if life==99 else '-100'
  scenario=ROOT/'work/ss6/scenarios'/f'battle-ending-{attacker}{suffix}.txt'
  scenario.write_text('\n'.join(start)+'\n')
  cases.append(dict(attacker=attacker,winner_initial_life=life,initial_life_fixture=True,death_update=death_tick,
                    first_body_ready=body_ready,entry7=entry7,entry8=entry8,ending_ready=ending_ready,
                    first_ui_draw=first_ui,last_ui_draw=last_ui,knockout_phases=milestones))
 invalid=subprocess.run([str(PROBE),str(ROOT/'work/ss6/extracted/resources')],input='tick 1\nlife 0 1\n',text=True,capture_output=True)
 assert invalid.returncode and 'unstarted battle' in invalid.stderr
 report=dict(status='passed_for_integration_fixture',scenarios=cases,original_phase_checks=phase_checks,
  probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),viewer_sha256=hashlib.sha256(VIEWER.read_bytes()).hexdigest(),
  scope='Actual contacts from explicit1HP starting fixtures: both winners/doubleKO, delayed entries4/5/7/8,40+2KO pause,effects and final draw,KO bodies,493 wait,48 corpse,495/497 victory at HP99/100, correctedKOcamera2/0 (draw0), completion flags,input lock,determinism. Entry5 commits wins/perfect/draw history once; timer1 entry/reset/update phase and timer5 assignment checked. Whole144360 and waiting144570 replay on native snapshots; completed144570 stops BEFORE1446b8 transition (slice only). Whole1441e0 camera/request coverage lives in round_control_validation.json. Non-final bout; complete original frames, final-match UI, next round, GS and audio excluded.')
 (ROOT/'outputs/ss6-feasibility/battle_ending_validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
