#!/usr/bin/env python3
"""Replay the seven Haohmaru common specials under the Ten command table."""
from concurrent.futures import ProcessPoolExecutor
import itertools
import json
from pathlib import Path
from mips_probe import Probe
from validate_collisions import ACTORS
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_haohmaru_special import pads_for
from validate_haohmaru_whirlwind import contact as wind_contact
from validate_haohmaru_flask import FlaskContacts, children
from validate_shin_evasion import EXE, replay, setup_state
from validate_ten_chain import TenContacts
from validate_weapon_handling import setup

OUT=ROOT/'outputs/ss6-feasibility/ten_common_specials_validation.json'
GROUPS=[(64,66,529,0x4e4558,'236+A/B/C'),(67,67,539,0x4e4578,'236+D'),
        (68,70,549,0x4e4598,'623+A/B/C'),(71,73,568,0x4e45b8,'dash 623+A/B/C'),
        (74,76,584,0x4e45e0,'421+A/B/C'),(77,77,598,0x4e4608,'214+D'),(80,80,592,0x4e4620,'632146+AB')]


class TenFlask(FlaskContacts):
    def __init__(self,slot):
        super().__init__();self.slot=slot
    def install_player(self,row,slot):
        super().install_player(row,slot)
        self.probe.write(ACTORS+0xf2c*slot+0x10c,3 if self.slot==slot else 0,4)


def commands(slot,state,mode,reflect_strength=0):
    front,back=(128,64) if slot==0 else (64,128)
    pair=lambda n,a=0,b=0:(n,b,a) if slot else (n,a,b)
    start=[pair(500)]
    if mode=='reflect':
        start += [pair(15)]+[pair(1,0,v) for v in pads_for(64+reflect_strength,1-slot)]
        start += [pair(1)]*(11 if reflect_strength==2 else 9)
    else:
        approach=32
        if state<67:approach=20
        elif 71<=state<=73:approach=16
        elif state==77:approach=25 if mode=='guard' else 30
        elif state==80:approach=40
        start.extend([pair(110,back,front) if mode=='miss' else pair(approach,front,back),pair(30)])
    pad=pads_for(state,slot)
    guard=front if mode=='guard' else 0
    # Wall slash has a long startup. A defender already walking backward
    # during the motion can leave its range before the active ACT record.
    seq=[pair(1,k,guard if state!=80 else 0) for k in pad]
    seq += [pair(1,0,guard if (32<=i<=75 if state==80 else i<75) else 0) for i in range(340)]
    return start,seq


def case(args):
    slot,state,mode,strength=args;dst=1-slot
    first,last,base,_,_ = next(group for group in GROUPS if group[0]<=state<=group[1])
    start,seq=commands(slot,state,mode,strength)
    rows=replay(slot,'ten',start+seq)[len(start)-1:]
    core=3+10*slot
    entered=next((i for i,r in enumerate(rows) if list(map(int,r[core:core+3]))==[1,state,base+state-first]),None)
    assert entered,(args,sorted({tuple(r[core:core+3]) for r in rows}))
    assert rows[-1][core:core+3]==['0','0','0']
    events=[];reflection=None
    if state<67 or state==77:
        oracle=TenFlask(slot) if state==77 else TenContacts(slot)
        for i in range(1,len(rows)):
            prev,now=rows[i-1:i+1]
            if mode=='reflect':
                child=lambda r:{o[0x10//4] for o in children(r) if o[0xd0//4]==0}
                if child(prev)=={dst} and child(now)=={slot}:reflection=oracle.reflection(prev,now,slot)
            if now[core+7:core+9]!=prev[core+7:core+9]:
                events.append(wind_contact(oracle,prev,now,slot,mode=='guard') if state<67
                              else oracle.strike(prev,now,slot,int(mode!='reflect'),mode=='guard'))
    else:
        events=TenContacts(slot).contacts(rows,slot)
    assert bool(events)==(mode!='miss' and state!=67),(args,events,rows[-1][:23])
    assert all(bool(e['defense'])==(mode=='guard') for e in events)
    if mode=='reflect':assert reflection,(args,events)
    hp=int(rows[-1][9+10*dst]);assert (hp<200)==bool(events),(args,hp,events)
    result=dict(side=slot+1,state=state,mode=mode,first_action=base+state-first,entry_tick=int(rows[entered][0]),
                return_tick=next(int(r[0]) for r in rows[entered+1:] if r[core:core+3]==['0','0','0']),
                victim_hp=hp,contacts=events)
    if reflection:result.update(reflect_strength=strength,reflection=reflection)
    if mode!='miss':return result
    # On a miss the input, ACT clock, body height and callback evolve
    # continuously without cross-actor hitstop. Supply only the stage X data.
    src,_=setup(slot);setup_state(src,3,0,rows[0],slot,False);p,a,o=src.p,src.a,src.o
    cb,c=88+27*slot,23+26*slot
    for i,(key,old,now) in enumerate(zip(seq,rows,rows[1:]),1):
        p.write(o+0x40,int(old[c]),4);p.write(o+0x1040,int(old[23+26*dst]),4)
        p.write(src.b+0x144,abs(int(float(old[7]))-int(float(old[17]))),4)
        v=src.frame(key[slot+1])
        got=[int(now[core])|int(now[core+1])<<16,*map(int,now[core+2:core+4]),int(now[cb+11]),
             int(now[c+1]),*map(int,now[cb:cb+3])]
        want=[v[0],v[54],v[55],v[56],v[69],*v[12:15]]
        # The fixture starts from the same standing state at the selected
        # stage boundary, at a different initial idle-animation phase.
        if i<entered:assert got[:2]==want[:2],(args,i,got,want)
        else:assert got==want,(args,i,got,want)
        if i>entered and list(map(int,now[core:core+3]))==[0,0,0]:break
    result.update(original_actor_updates=i,original_actor_instructions=src.instructions)
    return result


def bare_case(spec):
    slot,state=spec
    front=(128,64)[slot]
    pair=lambda n,a,b:(n,b,a) if slot else (n,a,b)
    # Throw the sword away and step clear of its pickup region before
    # pressing slash. This tests command availability through live inputs.
    start=[(500,0,0),pair(1,front|8,0),(140,0,0),pair(50,front^192,front),(45,0,0)]
    pads=pads_for(state,slot)
    rows=replay(slot,'ten',start+[pair(1,key,0) for key in pads]+[(1,0,0)]*95)[len(start)-1:]
    core=3+slot*10;c=23+slot*26
    assert not int(rows[0][c+5])&0x1000 and int(rows[0][core+2])==1
    src,_=setup(slot);setup_state(src,3,0,rows[0],slot,True)
    for i,(key,old,now) in enumerate(zip(pads,rows,rows[1:]),1):
        src.p.write(src.o+0x40,int(old[c]),4);src.p.write(src.o+0x1040,int(old[23+(1-slot)*26]),4)
        src.p.write(src.b+0x144,abs(int(float(old[7]))-int(float(old[17]))),4)
        v=src.frame(key)
        assert (v[0],v[54])==(int(now[core])|int(now[core+1])<<16,int(now[core+2])),(spec,i,v[0],now[:23])
    result=list(map(int,rows[len(pads)][core:core+3]))
    if state==77:assert result==[1,77,599]
    else:assert result[0]==1 and result[1]<64
    assert rows[-1][core:core+3]==['0','0','1']
    return dict(side=slot+1,armed_command_state=state,bare_actor_state_and_act=result,
                original_instructions=src.instructions)


def samurai_drive_scope(image):
    p=Probe(image)
    config=0x1c00000
    p.write(config,3,4)
    has_option,count=p.run(0x14fdb0,[config])
    assert has_option==0
    text=lambda start:image[start:image.index(0,start)].decode('cp932')
    assert text(0x4e44c8)=='サムライドライブ' and 'SCアイコン' in text(0x4e44e0)
    return dict(system_heading=text(0x4e4350),option=text(0x4e44c8),explanation=text(0x4e44e0),
                original_gate='14c608 -> 14fdb0 -> 14f4e0',ten_gate_return=has_option,gate_instructions=count)


def main():
    assert digest(ELF)==PIN
    image=ELF.read_bytes()
    labels={command:image[offset:image.index(0,offset)].decode('cp932') for _,_,_,offset,command in GROUPS}
    jobs=[(s,n,m,0) for s in (0,1) for lo,hi,*_ in GROUPS for n in range(lo,hi+1) for m in ('hit','guard','miss')]
    jobs.extend((s,77,'reflect',k) for s,k in itertools.product(range(2),range(3)))
    with ProcessPoolExecutor(6) as pool:
        bare=list(pool.map(bare_case,[(s,n) for s in (0,1) for lo,hi,*_ in GROUPS for n in range(lo,hi+1)]))
        cases=list(pool.map(case,jobs))
    report=dict(status='passed',original_sha256=PIN,replay_sha256=digest(EXE),validator_sha256=digest(Path(__file__)),labels=labels,cases=cases,disarmed=bare,sc_marker=samurai_drive_scope(image),
                scope='Resource00, console VS, Ten caster against the default spirit through normalized player inputs. Original attacker command, ACT and callback run on each whiff through recovery. Hit/guard use original contact handlers on native positions. Flask reflection uses original route 5 plus the reflected projectile contact. The disarmed matrix checks the actual command outcome and return to idle for all 15 armed commands, including unarmed flask ACT599. Airborne targets, super cancels and counter/KO variants are outside this regression.')
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'{len(cases)} armed + {len(bare)} disarmed Ten common-special match scenarios confirmed')
if __name__=='__main__':main()
