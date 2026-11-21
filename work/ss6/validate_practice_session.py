#!/usr/bin/env python3
"""Drive PRACTICE MODE end to end through the replay binary: title mode menu ->
practice character select -> VS faceoff -> battle with the practice window.

The rules themselves (window 17f790, gauges 180260, life 151968/1494f0, counters
139588, recording flags of 13f9f0, posture controller 15ab30) are compared with
the original code by validate_practice_mode*.py and validate_practice_dummy.py;
this script checks that the integrated game applies them in a real session."""
import argparse
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'outputs/ss6-feasibility'
UP,DOWN,LEFT,RIGHT=0x10,0x20,0x40,0x80
LIGHT,MEDIUM,HEAVY,KICK,START,SELECT=0x100,0x200,0x400,0x800,8,0x10000
Z=(0,0)

# Column indices of --practice-fields.
UPD,STATE=0,1
P=[dict(table=3+10*i,index=4+10*i,action=5+10*i,x=7+10*i,y=8+10*i,life=9+10*i,hits=10+10*i,guards=11+10*i) for i in range(2)]
MODE,TITLE,SELECTING,FACEOFF,SESSION,BATTLE,REQUESTED,ROUND=range(23,31)
(WSTATE,WLAST,ROW,LEVEL,VALUE,CHOICE,REC,PLAY,LAST,TOTAL,MAXD,COMBO,RESETS,EXIT,EXITDONE,PAUSE,
 A2,A3,A5,A6,B0,B6,B10,KEYI,KEYS)=range(31,56)
F=[dict(kind=56+10*i,code=57+10*i,flags=58+10*i,index=59+10*i,maxlife=60+10*i,rage=61+10*i,amount=62+10*i,
        timer28=63+10*i,level=64+10*i,flags23c=65+10*i) for i in range(2)]

def tap(word,gap=6,seat=0):
    return [((word,0) if seat==0 else (0,word))]+[Z]*gap
def hold(word,ticks,seat=0):
    return [((word,0) if seat==0 else (0,word))]*ticks

class Session:
    def __init__(self,binary,assets):
        self.binary,self.assets=binary,assets
        self.runs=self.ticks=0
    def run(self,pads,fields='--practice-fields'):
        body=''.join(f'1 {a} {b}\n' for a,b in pads)
        r=subprocess.run([self.binary,self.assets,'--mode','title',fields],input=body,text=True,capture_output=True)
        assert r.returncode==0,r.stderr[-2000:]
        rows=[line.split() for line in r.stdout.splitlines()]
        assert len(rows)==len(pads)
        self.runs+=1;self.ticks+=len(pads)
        return rows

def num(row,col):return float(row[col]) if '.' in row[col] else int(row[col])

def enter(seat=0):
    """Title -> mode menu -> PRACTICE (second row below ARCADE) confirmed by `seat`."""
    pads=[Z]*32+tap(START,15,seat)+tap(DOWN,20,seat)+tap(DOWN,20,seat)+tap(HEAVY,40,seat)
    return pads

def select_pages(s,pads,seat=0):
    """Confirm every select page with the practising pad; on the stage page (spirit
    phase 20) one step right of RANDOM leaves the random draw for a fixed, ported arena."""
    start=len(pads)
    probe=pads+[x for _ in range(24) for x in tap(HEAVY,20,seat)]
    rows=s.run(probe,'--select-fields')
    stage=next(i for i,r in enumerate(rows) if i>=start and '20' in (r[33],r[43]))
    pads=probe[:stage+1]+[Z]*6+tap(RIGHT,12,seat)
    for _ in range(12):pads+=tap(HEAVY,20,seat)
    rows=s.run(pads,'--select-fields')
    assert rows[-1][52] in('0','1') and rows[-1][49]=='0' and rows[-1][24]=='0',rows[-1][45:53]
    return pads

def to_battle(s,seat=0):
    pads=select_pages(s,enter(seat),seat)
    rows=s.run(pads)
    first=next(i for i,r in enumerate(rows) if r[BATTLE]=='1')
    select=next(i for i,r in enumerate(rows) if r[SELECTING]=='1')
    return pads[:first+1],rows,select,first

def menu_rows(n,seat=0):
    return tap(DOWN,6,seat)*n if n>0 else tap(UP,6,seat)*(-n)

def check_entry(s,seat):
    pads,rows,select,first=to_battle(s,seat)
    mode=str(9+seat)
    # 1cd428: mode word 9/10 and the practice session exist from the select onwards.
    assert rows[select][MODE]==mode and rows[select][TITLE]=='0',rows[select][23:31]
    assert rows[select+1][SESSION]=='1'
    assert any(r[FACEOFF]=='1' for r in rows[select:first]),'the practice select must pass through the VS faceoff'
    r=rows[first]
    assert r[MODE]==mode and r[SESSION]=='1'
    # 13fd80: no introduction, requested state 4; 17f5a0: window state 1, the battle is held.
    assert r[REQUESTED]=='4' and r[WSTATE]=='1' and r[STATE]=='-1',r[:3]+r[23:34]
    dummy=1-seat
    assert r[F[dummy]['kind']]=='1' and r[F[seat]['kind']]=='0'
    # 15a0e0: STAND NORMAL (code 0) on both controllers, AI level word 0x31.
    assert r[F[0]['code']]==r[F[1]['code']]=='0' and r[F[dummy]['level']]=='49'
    # The window keeps the battle in the requested state for as long as it is open.
    pads+=[Z]*60
    rows=s.run(pads)
    assert all(row[STATE]=='-1' and row[WSTATE]=='1' for row in rows[first+2:]),'menu open: 140270 must not run'
    assert rows[-1][P[0]['x']]=='240' and rows[-1][P[1]['x']]=='400'
    # PRACTICE START: reset request, window state 0, battle state 4 two frames later.
    pads+=tap(MEDIUM,10,seat)
    rows=s.run(pads)
    assert rows[-1][WSTATE]=='0' and rows[-1][RESETS]=='1' and rows[-1][STATE]=='4',rows[-1][:3]+rows[-1][31:47]
    assert rows[-1][ROUND]=='1','13ab48 marks the round as running'
    return pads

def check_life(s):
    pads,_,_,first=to_battle(s)
    pads+=[Z]*30
    # GAUGE SETTING -> 2P LIFE: one step right from 100% wraps to 1%.
    pads+=menu_rows(4)+tap(MEDIUM)+menu_rows(5)+tap(MEDIUM)+tap(RIGHT)+tap(MEDIUM)+tap(LIGHT)
    # DATA DISPLAY on, then PRACTICE START.
    pads+=menu_rows(2)+tap(MEDIUM)+tap(RIGHT)+tap(MEDIUM)
    pads+=menu_rows(-6)+tap(MEDIUM,10)
    start=len(pads)
    pads+=hold(RIGHT,60)+[Z]*5
    for _ in range(4):pads+=tap(HEAVY,70)
    pads+=[Z]*80
    rows=s.run(pads)
    assert rows[start][A6]=='1' and rows[start][WSTATE]=='0'
    fight=rows[start:]
    # 180260: maximum (1 * 200 + 99) / 100 = 2 for the dummy, 200 for the player.
    assert all(r[F[1]['maxlife']]=='2' and r[F[0]['maxlife']]=='200' for r in fight)
    lives=[int(r[P[1]['life']]) for r in fight]
    hits=int(fight[-1][P[0]['hits']])
    assert hits>=4,hits
    # 151968: the life never reaches 0, the KO bit 0x80 never appears and the round never ends.
    assert min(lives)==1 and max(lives)==2,(min(lives),max(lives))
    assert all(not int(r[F[1]['flags23c']])&0x80 and r[STATE]=='4' for r in fight)
    # 1494f0: the life returns to the maximum on the actor visit that finds timer 28 expired.
    refills=0
    for before,after in zip(fight,fight[1:]):
        if before[P[1]['life']]=='1' and after[P[1]['life']]=='2':
            assert after[F[1]['timer28']]=='0',after[F[1]['timer28']]
            refills+=1
        if int(after[F[1]['timer28']])>0:assert after[P[1]['life']]=='1'
    assert refills>=2,refills
    # 139588: last / total / maximum, the total capped by the combo and restarted afterwards.
    assert int(fight[-1][MAXD])>0 and all(int(r[TOTAL])<=int(r[MAXD])<=999 for r in fight)
    assert any(r[COMBO]=='1' and int(r[TOTAL])>0 for r in fight),'149f20 must end the combo'
    totals=[int(r[TOTAL]) for r in fight]
    assert any(b<a for a,b in zip(totals,totals[1:])),'a new combo restarts the total'
    return {'hits':hits,'refills':refills,'max_damage':int(fight[-1][MAXD])}

def open_menu(seat=0):
    return tap(SELECT,24,seat)

def check_reset(s):
    pads=check_entry(s,0)
    pads+=hold(RIGHT,40)+[Z]*4+tap(HEAVY,30)
    moved=len(pads)
    pads+=open_menu()+tap(MEDIUM,10)
    rows=s.run(pads)
    assert float(rows[moved-1][P[0]['x']])>260
    assert rows[moved+20][WSTATE]=='1' and rows[moved+20][UPD]!=rows[moved+10][UPD],'held frames still dispatch'
    # 13f9f0(0): both fighters return to the round positions, the actor is rebuilt.
    r=rows[-1]
    assert r[RESETS]=='2' and r[P[0]['x']]=='240' and r[P[1]['x']]=='400' and r[STATE]=='4',r[:23]
    assert r[P[0]['hits']]=='0'
    return {'resets':int(r[RESETS])}

def check_record_replay(s):
    pads=check_entry(s,0)
    pads+=[Z]*20+open_menu()+menu_rows(1)+tap(MEDIUM,4)
    begin=len(pads)
    # The practising pad now drives the dummy (seat 1) through the swapped port.
    script=[Z]*10+hold(LEFT,45)+[Z]*8+tap(HEAVY,50)+hold(RIGHT,25)+[Z]*20
    pads+=script
    end=len(pads)
    rows=s.run(pads)
    rec=rows[begin+2]
    assert rec[REC]=='1' and rec[PLAY]=='0' and rec[RESETS]=='2'
    # 13fb64: kinds swapped; the dummy reads the other port and records (8|2), the player's fighter is CPU kind 1 (8).
    assert rec[F[0]['kind']]=='1' and rec[F[1]['kind']]=='0',rec[56:76]
    assert int(rec[F[0]['flags']])&0xe==8 and int(rec[F[1]['flags']])&0xe==10
    recorded={int(r[F[1]['index']]):(r[P[1]['x']],r[P[1]['action']],r[P[1]['table']],r[P[1]['index']]) for r in rows[begin+2:end]}
    assert float(rows[end-1][P[1]['x']])!=400 or any(v[1]=='189' or v[1]=='190' for v in recorded.values())
    assert any(v[2]=='1' for v in recorded.values()),'the recorded dummy must have attacked'
    # The player's own fighter stands under the posture controller (code 0) and takes the recorded slash.
    assert rows[end-1][P[1]['hits']]!='0' and rows[end-1][F[0]['code']]=='0'
    # CPU TYPE -> REPLAY (one step left of STAND wraps to the last entry), then PRACTICE START.
    pads+=open_menu()
    stop=len(pads)
    pads+=menu_rows(1)+tap(MEDIUM)+tap(LEFT)+tap(MEDIUM)+menu_rows(-2)+tap(MEDIUM,4)
    play=len(pads)
    pads+=[Z]*(len(script)+700)
    rows=s.run(pads)
    assert rows[stop][REC]=='1' and rows[stop][WSTATE]=='1'
    r=rows[play+2]
    assert r[REC]=='0' and r[PLAY]=='1' and r[A2]=='8' and r[RESETS]=='3',r[31:56]
    # 13fcf4: replay bit 4 on the CPU-kind actor only; both control kinds are back.
    assert r[F[0]['kind']]=='0' and r[F[1]['kind']]=='1' and int(r[F[1]['flags']])&0xe==4 and int(r[F[0]['flags']])&0xe==0
    assert r[F[1]['code']]=='37'
    replayed={}
    for row in rows[play+2:play+2+len(script)-4]:
        replayed.setdefault(int(row[F[1]['index']]),(row[P[1]['x']],row[P[1]['action']],row[P[1]['table']],row[P[1]['index']]))
    same=[i for i in replayed if i in recorded]
    assert len(same)>=len(script)-12,len(same)
    for i in same:assert replayed[i]==recorded[i],(i,replayed[i],recorded[i])
    # 1497b0: only the replay index wraps, at 720; the recording holds 600 samples.
    indices=[int(row[F[1]['index']]) for row in rows[play+2:]]
    assert max(indices)==719 and 0 in indices[10:],max(indices)
    wrap=indices.index(719)+1
    second=rows[play+2+wrap:]
    again={int(row[F[1]['index']]):row[P[1]['action']] for row in second}
    assert any(a in('189','190') for a in again.values()),'the replay loops'
    return {'recorded':len(recorded),'compared':len(same)}

def check_dummy(s):
    out={}
    for name,value,option,expect in (('crouch',1,0,'crouch'),('jump',2,0,'jump'),('human',7,None,'human'),('cpu',6,None,'cpu'),
                                     ('guard',0,2,'guard')):
        pads,_,_,first=to_battle(s)
        pads+=[Z]*30+menu_rows(2)+tap(MEDIUM)+tap(RIGHT)*value+tap(MEDIUM)
        if option is not None:pads+=tap(RIGHT)*option+tap(MEDIUM)
        pads+=menu_rows(-2)+tap(MEDIUM,10)
        start=len(pads)
        if expect=='human':pads+=hold(LEFT,40,seat=1)+[Z]*10
        elif expect=='guard':pads+=hold(RIGHT,60)+[Z]*5+tap(HEAVY,70)+tap(HEAVY,70)
        else:pads+=[Z]*240
        rows=s.run(pads)
        r=rows[start+2]
        assert r[A2]==str(value) and r[WSTATE]=='0',(name,r[31:56])
        tail=rows[start+10:]
        if expect=='crouch':
            # Code 11: AI command 8 (down) every visit.
            assert r[F[1]['code']]=='11'
            assert all(row[P[1]['table']]=='0' and row[P[1]['x']]=='400' for row in tail)
            assert tail[-1][P[1]['index']]!='0' and tail[-1][P[1]['action']] not in('0','2'),tail[-1][13:23]
            out[name]=tail[-1][P[1]['action']]
        elif expect=='jump':
            assert r[F[1]['code']]=='20'
            assert max(float(row[P[1]['y']]) for row in tail)>20,'JUMP V must leave the ground'
            assert all(row[P[1]['x']]=='400' for row in tail)
            out[name]=max(float(row[P[1]['y']]) for row in tail)
        elif expect=='human':
            # Code 0x24: actor sampled from its own port (controller 2 in mode 9).
            assert r[F[1]['code']]=='36' and r[F[1]['kind']]=='1'
            assert float(tail[-1][P[1]['x']])<395,tail[-1][P[1]['x']]
            out[name]=float(tail[-1][P[1]['x']])
        elif expect=='cpu':
            # Code 0x23 from a fresh controller keeps the AI level word of the setup block (0).
            assert r[F[1]['code']]=='35' and r[F[1]['level']]=='0',r[56:76]
            assert any(row[P[1]['x']]!='400' or row[P[1]['table']]!='0' for row in tail),'the CPU must act'
            out[name]=tail[-1][P[1]['x']]
        else:
            assert r[F[1]['code']]=='2' and r[B0]=='2'
            assert int(tail[-1][P[0]['guards']])>=1 and tail[-1][P[0]['hits']]=='0',tail[-1][3:23]
            assert all(row[P[1]['life']]=='200' for row in tail)
            out[name]=int(tail[-1][P[0]['guards']])
    return out

def check_exits(s):
    pads=check_entry(s,0)
    # CPU UKEMI TYPE -> SHORT so that a setting visibly survives CHARACTER SELECT.
    # (the window only reopens once its slide has come to rest: 17f400)
    pads+=[Z]*20+open_menu()+menu_rows(3)+tap(MEDIUM)+tap(RIGHT)+tap(MEDIUM)
    # CHARACTER SELECT: the dialog opens on NO; LEFT selects YES.
    pads+=menu_rows(7)+tap(MEDIUM,24)
    asked=len(pads)
    pads+=tap(LEFT)+tap(MEDIUM,60)
    rows=s.run(pads)
    assert rows[asked-1][WSTATE]=='3' and rows[asked-1][CHOICE]=='1' and rows[asked-1][ROW]=='10',rows[asked-1][31:40]
    assert rows[asked][CHOICE]=='0'
    assert rows[-1][SELECTING]=='1' and rows[-1][MODE]=='9' and rows[-1][SESSION]=='1' and rows[-1][TITLE]=='0',rows[-1][23:31]
    left=next(i for i,r in enumerate(rows) if i>asked and r[SELECTING]=='1')
    # NO keeps the battle: checked on a separate branch of the same prefix.
    branch=pads[:asked]+tap(MEDIUM,30)
    back=s.run(branch)
    assert back[-1][WSTATE]=='1' and back[-1][SELECTING]=='0' and back[-1][EXIT]=='0'
    # Second battle from the reopened select: the settings were not reset.
    pads=select_pages(s,pads)
    rows=s.run(pads)
    again=next(i for i,r in enumerate(rows) if i>left and r[BATTLE]=='1' and r[SELECTING]=='0' and r[FACEOFF]=='0')
    assert rows[again][A3]=='1' and rows[again][WSTATE]=='1',rows[again][31:56]
    pads=pads[:again+1]+[Z]*30
    # RETURN TO TITLE.
    pads+=menu_rows(-1)+tap(MEDIUM,24)+tap(LEFT)+tap(MEDIUM,70)
    rows=s.run(pads)
    assert rows[-1][TITLE]=='1' and rows[-1][SESSION]=='0' and rows[-1][SELECTING]=='0',rows[-1][23:31]
    # The mode menu reopened on PRACTICE: confirming again starts a fresh session with default settings.
    mark=len(pads)
    pads=select_pages(s,pads+tap(HEAVY,40))
    rows=s.run(pads)
    fresh=[r for r in rows[mark:] if r[BATTLE]=='1' and r[SELECTING]=='0' and r[TITLE]=='0']
    assert fresh and fresh[0][A3]=='0' and fresh[0][MODE]=='9',(len(fresh),fresh[0][23:56] if fresh else [(i,r[:3],r[23:34]) for i,r in enumerate(rows) if i%25==0][-40:])
    return {'select_tick':left,'second_battle':again}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build',default=str(HERE/'build-native'))
    parser.add_argument('--package',action='store_true',help='use the packaged assets directory')
    args=parser.parse_args()
    assets=ROOT/'outputs/ss6-feasibility/native-viewer/assets'
    s=Session(Path(args.build)/'ss6-match-replay',assets)
    report={'validator':'practice_session','binary':str(s.binary)}
    for seat in (0,1):check_entry(s,seat)
    report['entry']={'seats':2}
    report['life']=check_life(s)
    report['reset']=check_reset(s)
    report['record_replay']=check_record_replay(s)
    report['dummy']=check_dummy(s)
    report['exits']=check_exits(s)
    report['runs']=s.runs;report['ticks']=s.ticks;report['passed']=True
    report['scope']=('replay-driven session through ss6-match-replay --mode title --practice-fields; the rule ports are '
                     'compared with the original executable by validate_practice_mode*.py and validate_practice_dummy.py')
    (OUT/'practice_session_validation.json').write_text(json.dumps(report,indent=1)+'\n')
    print(f"practice session: passed, {s.runs} replays / {s.ticks} ticks; {json.dumps(report['life'])} {json.dumps(report['record_replay'])}")

if __name__=='__main__':main()
