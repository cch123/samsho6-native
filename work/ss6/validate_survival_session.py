#!/usr/bin/env python3
"""Drive SURVIVAL MODE end to end through the replay binary: title mode menu -> single-seat
character select -> candidate window -> fights against several opponents -> loss ->
GAME OVER -> record -> title, and a second run in the same process.

The rules themselves (candidates 17aca8, controller 180630, match end 145628, record
1384f8) are compared with the original code by validate_survival_run.py, and the
battle-side rules ported for the integration by validate_survival_battle.py; this script
checks that the integrated game applies them in a real session."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'outputs/ss6-feasibility'
UP,DOWN,LEFT,RIGHT=0x10,0x20,0x40,0x80
LIGHT,MEDIUM,HEAVY,KICK,START,SELECT=0x100,0x200,0x400,0x800,8,0x10000
Z=(0,0)
GAME_OVER=0x138340
FULL_CLOCK=99*0xb400

# Column indices of --survival-fields.
UPD,STATE=0,1
P=[dict(table=3+10*i,index=4+10*i,life=9+10*i,wins=12+10*i) for i in range(2)]
(MODE,TITLE,SELECTING,RUN,SCENE,MATCH,REQUESTED,CLOCK,SECONDS,SEED,ARENA,ROUNDWINNER,WINNER)=range(23,36)
(SSTATE,SPREV,DELAY,FADE,TWINS,WINS,FRAMES,SAVEDLIFE,SAVEDCLOCK,PENDING,LIFEGAIN,CLOCKGAIN,MSGTIMER,MSGTEXT,
 CURSOR,FOCUS,HUDLINE,PAUSE,NOTICEEMPTY)=range(36,55)
ROWS=[55+6*i for i in range(3)]   # stage, human spirit, character, colour, reward, mission
CURRENT=73
LEVEL,SETUPSTAGE=79,80
SETUP=[dict(control=81+4*i,character=82+4*i,colour=83+4*i,spirit=84+4*i) for i in range(2)]
F=[dict(character=89+7*i,system=90+7*i,kind=91+7*i,level=92+7*i,flags248=93+7*i,finish=94+7*i,special=95+7*i) for i in range(2)]
MISSION=103
EVENTS=125
RECWINS,RECSECONDS=134,135
# After the run: the GAME OVER scene (run gone, arcade scene set).
GMODE,GSUB,GWINNER,GFRAME,GCHAR,GRECWINS,GRECSECONDS,GNOTICEEMPTY=range(36,44)
LIFE_GAIN={0:30,1:60,2:90,3:150,7:200}
CLOCK_GAIN={4:10,5:20,6:30,7:100}
LEVELS=lambda n:0 if n<3 else 1 if n<6 else 2 if n<9 else 6 if n==9 else 0

def tap(word,gap=6,seat=0):
    return [((word,0) if seat==0 else (0,word))]+[Z]*gap
def held(word,ticks,seat=0):
    return [((word,0) if seat==0 else (0,word))]*ticks
def attack(seat=0,ticks=40):
    """Walk toward the opponent and slash: enough to beat the low survival levels."""
    forward=RIGHT if seat==0 else LEFT
    return held(forward,10,seat)+tap(HEAVY,12,seat)+tap(HEAVY,16,seat)

class Session:
    def __init__(self,binary,assets):
        self.binary,self.assets=binary,assets
        self.runs=self.ticks=0
    def run(self,pads,fields='--survival-fields'):
        body=''.join(f'1 {a} {b}\n' for a,b in pads)
        r=subprocess.run([self.binary,self.assets,'--mode','title','--unlock-modes',fields],input=body,text=True,capture_output=True)
        assert r.returncode==0,r.stderr[-2000:]
        rows=[line.split() for line in r.stdout.splitlines()]
        assert len(rows)==len(pads)
        self.runs+=1;self.ticks+=len(pads)
        return rows

def num(row,col):return int(row[col])
def running(row):return row[RUN]=='1'
def candidate(row,at):return [num(row,at+k) for k in range(6)]

def enter(seat=0):
    """Title -> mode menu -> SURVIVAL (third row below ARCADE with byte 43d0d6 set) -> the cursor's fighter."""
    return [Z]*32+tap(START,15,seat)+tap(DOWN,20,seat)*3+tap(HEAVY,40,seat)+[Z]*150+tap(HEAVY,30,seat)

def to_window(s,pads,limit=1500):
    """Extend with idle frames until the candidate window accepts input; returns (pads, row)."""
    rows=s.run(pads+[Z]*limit)
    i=next(i for i in range(len(pads)-1,len(rows)) if running(rows[i]) and rows[i][SSTATE]=='1' and rows[i][FOCUS]=='1')
    return (pads+[Z]*limit)[:i+1],rows[i]

def dismiss(s,pads,seat):
    """Result message and reward counting: press until the next candidate window is up. Returns the rows seen."""
    seen=[];start=len(pads)-1
    for _ in range(40):
        rows=s.run(pads+[Z]*40)
        seen=rows
        last=rows[-1]
        if not running(last):break
        if last[SSTATE]=='1' and last[FOCUS]=='1':
            i=next(i for i in range(len(pads)-1,len(rows)) if rows[i][SSTATE]=='1' and rows[i][FOCUS]=='1')
            return (pads+[Z]*40)[:i+1],rows[start:i+1]
        pads=pads+[Z]*40+(tap(LIGHT,10,seat) if last[SSTATE] in ('2','3') else [])
    raise AssertionError('the candidate window did not return')

def choose(pads,row,seat):
    return pads+tap(DOWN,10,seat)*row+tap(HEAVY,10,seat)

def fight(s,pads,seat,script,limit):
    """Run the fight until 145628: returns (pads through the end frame, rows, won)."""
    probe=list(pads)
    while len(probe)<len(pads)+limit:probe+=script()
    rows=s.run(probe)
    start=len(pads)-1
    for i in range(start,len(rows)):
        r=rows[i]
        if not running(r):return probe[:i+1],rows[:i+1],False
        if r[REQUESTED]=='-1' and r[SSTATE]=='2' and num(r,TWINS)>num(rows[start],TWINS):return probe[:i+1],rows[:i+1],True
    raise AssertionError('the fight did not end')

def check_entry(s,seat,report):
    pads=enter(seat)
    rows=s.run(pads+[Z]*400)
    select=next(i for i,r in enumerate(rows) if r[SELECTING]=='1')
    assert rows[select][MODE]==str(11+seat) and rows[select][TITLE]=='0'            # 1ccfb8
    first=next(i for i,r in enumerate(rows) if running(r))
    r=rows[first]
    human,cpu=seat,1-seat
    # 139660: 180510 leaves the controller in state 1 with a pause request; the placeholder fight is hidden.
    assert r[SSTATE]=='1' and r[SPREV]=='-1' and r[PAUSE]=='1' and r[TWINS]=='0' and r[WINS]=='0'
    assert r[REQUESTED]=='3' and num(r,CLOCK)==FULL_CLOCK and r[SECONDS]=='99'                      # 13fd80, 1406e0
    assert num(r,SETUP[human]['control'])==0 and num(r,SETUP[cpu]['control'])==1 and num(r,LEVEL)==0  # 1398c0
    assert candidate(r,CURRENT)==[0]*6                                               # T+0x104 after boot
    after=rows[first+1]
    assert after[FADE]=='255' and after[SPREV]=='1' and after[MSGTEXT]=='0'
    rowsets=[candidate(after,at) for at in ROWS]
    assert len({c[1] for c in rowsets})==3 and all(c[1] in (0,1,2,3,4,5,7) for c in rowsets)       # 17aca8 step 3
    assert all(0<=c[0]<11 and 0<=c[3]<5 and 0<=c[4]<9 and 0<=c[5]<0x16 for c in rowsets)
    # The battle stays frozen behind the window: 140270 does not run.
    frozen=rows[first+1:first+60]
    assert all(x[STATE]=='-1' and x[FRAMES]=='0' and num(x,CLOCK)==FULL_CLOCK for x in frozen)
    pads,window=to_window(s,pads)
    report['entries']+=1
    return pads,window

def check_run(s,report):
    """Seat 0: several opponents with carry-over and a reward, then a loss and the record."""
    seat=0
    pads,window=check_entry(s,seat,report)
    wins=0;rewards=[];carries=[]
    life=200;clock=FULL_CLOCK
    lost=None
    while wins<6 and not (wins>=3 and rewards):
        options=[candidate(window,at) for at in ROWS]
        # Prefer a condition the scripted attack can meet: a heavy-slash win, then per-event counters.
        order=sorted(range(3),key=lambda i:(options[i][1]==7,{1:0,0x11:1}.get(options[i][5],2),i))
        result=None
        for row in order:
            trial=choose(pads,row,seat)
            confirm=s.run(trial+[Z]*40)
            done=next(i for i in range(len(trial)-12,len(confirm)) if confirm[i][SSTATE] in ('5','0'))
            c=confirm[done]
            assert candidate(c,CURRENT)==options[row],(candidate(c,CURRENT),options[row])       # 17b840
            assert all(m=='0' for m in c[MISSION:MISSION+22]) and all(e=='0' for e in c[EVENTS:EVENTS+9])  # 181548
            end,rows,won=fight(s,trial,seat,lambda:attack(seat),9000)
            if won:result=(row,end,rows);break
        assert result,'no candidate could be beaten with the scripted attack'
        row,end,rows=result
        chosen=options[row]
        # Reload 13a6c0: saved life and clock, then the new fight four held frames later.
        a=next(i for i in range(len(pads),len(rows)) if rows[i][SSTATE]=='0' and rows[i][SPREV]=='5')
        ra=rows[a]
        assert ra[DELAY]=='4' and ra[FADE]=='255'
        assert num(ra,SAVEDLIFE)==life and num(ra,SAVEDCLOCK)==clock,(ra[SAVEDLIFE],life,ra[SAVEDCLOCK],clock)
        assert num(ra,LEVEL)==LEVELS(wins) and num(ra,SETUPSTAGE)==chosen[0]                    # 17b890, 17b988
        assert num(ra,SETUP[1]['character'])==chosen[2] and num(ra,SETUP[0]['spirit'])==chosen[1]
        assert num(ra,SETUP[1]['spirit']) in range(6) and num(ra,SETUP[0]['control'])==0 and num(ra,SETUP[1]['control'])==1
        assert rows[a+1][MATCH]==rows[a][MATCH] and rows[a+1][DELAY]=='3'                       # arena frame
        rc=rows[a+2]
        assert num(rc,MATCH)==num(ra,MATCH)+1 and rc[UPD]=='1' and rc[DELAY]=='2'               # 13f9f0(1)
        assert num(rc,F[1]['character'])==chosen[2] and num(rc,F[1]['kind'])==1 and num(rc,F[0]['kind'])==0
        assert num(rc,F[1]['level'])==LEVELS(wins) and num(rc,F[0]['level'])==-1
        assert num(rc,F[0]['system'])==(chosen[1] if chosen[1]!=7 else 0)
        assert (rc[NOTICEEMPTY]=='1')==(chosen[1]!=7 and num(rc,ARENA)==chosen[0])
        if num(rc,ARENA)!=chosen[0]:assert rc[ARENA]=='0';report['arena_fallbacks']+=1
        # Carry-over: 180e98 for the human only, 180ec8 through 1406e0.
        assert num(rc,P[0]['life'])==life and num(rc,P[1]['life'])==200
        assert num(rc,CLOCK)==((clock+0xff)>>8)<<8 and rc[REQUESTED]=='3'
        carries.append((life,clock))
        held_frames=[x for x in rows[a+2:a+8] if x[STATE]=='-1' and x[UPD] in ('1','2','3')]
        assert rows[a+5][SPREV]=='0' and rows[a+5][FADE]=='247'                                 # delay 4 elapsed
        # One displayed count spans 180 updates: 256 units per running frame of state 4.
        combat=[i for i in range(a,len(rows)-1) if rows[i][STATE]=='4' and rows[i+1][STATE]=='4']
        steps={num(rows[i],CLOCK)-num(rows[i+1],CLOCK) for i in combat[:200]}
        assert steps<={0,128,256} and 256 in steps,steps
        assert num(rows[combat[0]],SECONDS)==(num(rows[combat[0]],CLOCK)+0xb3ff)//0xb400
        # Per-event rewards during the fight (180ef8 from the panel, applied by state 0).
        for i in range(a,len(rows)-1):
            x,y=rows[i],rows[i+1]
            if x[PENDING]!='-1' and x[SSTATE]=='0' and x[SPREV]=='0' and x[DELAY]=='0' and y[PENDING]=='-1':
                reward=num(x,PENDING)
                assert reward==chosen[4] and chosen[5] in range(0x10,0x15)
                assert y[MSGTIMER]=='180' and num(y,MSGTEXT)==5+reward
                if reward in CLOCK_GAIN and reward!=7:
                    assert num(y,CLOCK)>num(x,CLOCK) or num(y,CLOCK)==FULL_CLOCK
                if reward in LIFE_GAIN:
                    assert num(y,P[0]['life'])>=min(num(x,P[0]['life'])+LIFE_GAIN[reward],200)-40
                rewards.append(('event',chosen[5],reward))
        last=rows[-1]
        wins+=1
        assert num(last,TWINS)==wins and num(last,WINS)==wins and last[WINNER]=='0' and last[ROUNDWINNER]=='0'
        assert num(last,P[0]['wins'])==1 and num(last,P[1]['life'])<=0
        life,clock=num(last,P[0]['life']),num(last,CLOCK)
        message=num(last,MSGTEXT)
        per_event=chosen[5] in range(0x10,0x15)
        assert message in (2,3,4) and (message==2)==per_event
        elapsed=num(last,FRAMES)
        # Result message, reward counting, next window.
        before=(life,clock)
        pads,seen=dismiss(s,end,seat)
        window=seen[-1]
        assert num(window,FRAMES)==elapsed                                                      # only state 4 counts
        if message==3:
            reward=chosen[4]
            assert any(x[SSTATE]=='3' and num(x,MSGTEXT)==5+reward for x in seen)
            life=min(before[0]+LIFE_GAIN.get(reward,0),200)
            clock=min(before[1]+CLOCK_GAIN.get(reward,0)*0xb400,FULL_CLOCK)
            rewards.append(('win',chosen[5],reward))
        assert (num(window,P[0]['life']),num(window,CLOCK))==(life,clock),(window[P[0]['life']],life,window[CLOCK],clock)
        nxt=[candidate(window,at) for at in ROWS]
        assert all(c[2]!=chosen[2] for c in nxt)                                                # defeated list
        report['wins']+=1
    assert rewards,'no reward was granted'
    assert len(carries)>=3 and any(c!=(200,FULL_CLOCK) for c in carries)
    report['rewards']=[list(r) for r in rewards]
    report['carried']=[list(c) for c in carries]
    # Loss: stand still against the next opponent.
    options=[candidate(window,at) for at in ROWS]
    row=next(i for i in range(3) if options[i][1]!=7)
    trial=choose(pads,row,seat)
    end,rows,won=fight(s,trial,seat,lambda:[Z]*40,19000)
    assert not won
    final=rows[-2];over=rows[-1]
    assert running(final) and final[REQUESTED]=='10' and num(final,P[1]['wins'])==1
    assert num(over,SCENE)==GAME_OVER and over[GMODE]=='1' and over[GSUB]=='4' and over[GWINNER]=='1'     # 145628
    seconds=num(final,FRAMES)//60
    assert num(over,GRECWINS)==wins and num(over,GRECSECONDS)==seconds,(over[GRECWINS],wins,over[GRECSECONDS],seconds)
    character=num(over,GCHAR)
    report['record']=dict(character=character,wins=wins,seconds=seconds)
    report['losses']+=1
    last_candidate=options[row]
    # GAME OVER runs its 300 frames, then the title returns with the default battle block.
    after=s.run(end+[Z]*330)
    back=next(i for i in range(len(end),len(after)) if after[i][TITLE]=='1')
    assert back-len(end)==299 and after[back][MODE]=='3' and after[back][SCENE]=='-1'
    # Second run in the same process: the record is still there and 1398c0 builds its
    # placeholder fight from the candidate confirmed last in the previous run.
    again=end+[Z]*330+tap(START,15,seat)+tap(DOWN,20,seat)*3+tap(HEAVY,40,seat)+[Z]*150+tap(HEAVY,30,seat)
    rows=s.run(again+[Z]*400)
    first=next(i for i in range(len(end)+330,len(rows)) if running(rows[i]))
    r=rows[first]
    assert candidate(r,CURRENT)==last_candidate and num(r,SETUPSTAGE)==last_candidate[0]
    assert num(r,SETUP[1]['character'])==last_candidate[2] and r[TWINS]=='0' and r[WINS]=='0' and r[FRAMES]=='0'
    assert (num(r,RECWINS),num(r,RECSECONDS))==(wins,seconds)
    # A weaker second run keeps the record (1384f8 compares wins, then seconds).
    pads2,window=to_window(s,again)
    options=[candidate(window,at) for at in ROWS]
    row=next(i for i in range(3) if options[i][1]!=7)
    end2,rows,won=fight(s,choose(pads2,row,seat),seat,lambda:[Z]*40,19000)
    assert not won and num(rows[-1],SCENE)==GAME_OVER
    assert (num(rows[-1],GRECWINS),num(rows[-1],GRECSECONDS))==(wins,seconds)
    report['runs']+=2

def check_items(s,report):
    """144f40 in survival: the first delivery as combat starts, then a fixed 600-update period."""
    pads,window=check_entry(s,0,report)
    options=[candidate(window,at) for at in ROWS]
    row=next(i for i in range(3) if options[i][1]!=7)
    pads=choose(pads,row,0)+[Z]*700
    state=s.run(pads)
    items=s.run(pads,'--stage-item-fields')
    combat=next(i for i,r in enumerate(state) if running(r) and r[STATE]=='4')
    timer=[num(r,25) for r in items]
    # The entry visit of state 4 runs no update; the first update delivers and reloads timer 3.
    assert timer[combat]==0 and timer[combat+1]==600*256 and timer[combat+2]==600*256-256,timer[combat-1:combat+4]
    assert items[combat+1][26]=='1' or items[combat+1][27]=='1'        # the delivery is on its way
    report['item_deliveries']+=1

def check_second_seat(s,report):
    """Mode word c: the human is seat 1 and the CPU seat 0."""
    seat=1
    pads,window=check_entry(s,seat,report)
    options=[candidate(window,at) for at in ROWS]
    row=next(i for i in range(3) if options[i][1]!=7)
    pads=choose(pads,row,seat)+[Z]*400
    rows=s.run(pads)
    r=rows[-1]
    assert r[MODE]=='12' and r[STATE]=='4' and r[SSTATE]=='0' and r[FADE]=='0'
    assert num(r,F[0]['kind'])==1 and num(r,F[1]['kind'])==0 and num(r,F[0]['character'])==options[row][2]
    assert num(r,F[0]['level'])==0 and num(r,F[1]['level'])==-1 and num(r,F[1]['system'])==options[row][1]
    assert num(r,FRAMES)>0 and r[MATCH]=='2'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default='work/ss6/build-native')
    parser.add_argument('--assets',default='outputs/ss6-feasibility/native-viewer/assets')
    args=parser.parse_args()
    binary=ROOT/args.build/'ss6-match-replay'
    s=Session(str(binary),str(ROOT/args.assets))
    report=dict(entries=0,wins=0,losses=0,runs=0,arena_fallbacks=0,item_deliveries=0)
    check_run(s,report)
    check_items(s,report)
    check_second_seat(s,report)
    report.update(status='passed',replays=s.runs,ticks=s.ticks,
                  binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  scope='Replay-driven native session: mode-menu confirm for both seats, the hidden placeholder fight of 139660, '
                        'candidate confirm (17b840, 181548), reload timing after 13a6c0, CPU level and spirit assignment, life and '
                        'clock carry-over, the 180-update count, per-event and end-of-fight rewards, the defeated list, the survival '
                        'item period, the loss path through 145628 into GAME OVER, the stored record and its persistence over a '
                        'second run, and the return to the title. No original code runs here.')
    (OUT/'survival_session_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
