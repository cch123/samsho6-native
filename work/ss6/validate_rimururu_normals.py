#!/usr/bin/env python3
"""Compare selected Rimururu's movement, command normal and ordinary strikes to the Japanese executable."""
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
from validate_dash_motion import Original, PIN
from validate_haohmaru_special import BUILD, ELF, ROOT, run_native
from validate_nakoruru_combat import MixedContactOracle
from validate_normal_attacks import attack_cases
from validate_selected_combat import prefix
from validate_unarmed_normals import bring_stage, cases as unarmed_cases
from validate_collisions import ACTORS
from round_entry_oracle import fixture


def lineup(side, character=2, opponent=0):
    return (opponent, character) if side else (character, opponent)


def opening(side, character=2, opponent=0):
    pads = prefix(lineup(side, character, opponent))
    pads[229] = [128, 128]  # Move both actual spirit cursors from Ken to Rage.
    return [(sum(1 for _ in group), *word) for word, group in groupby(pads)]


def input_row(side, count, attack, defend=0):
    return (count, defend, attack) if side else (count, attack, defend)


def replay(commands, fields):
    return run_native(os.environ.get('SS6_NORMALS_REPLAY',os.environ.get('SS6_RIMURURU_TEST_REPLAY','ss6-match-replay')), ['%d %d %d' % c for c in commands], '--mode', 'select', fields)


def motion(job, character=2):
    side, name = job
    forward = (128,64)[side]
    back = forward ^ 192
    pre = opening(side,character)
    source, target, base = 23+26*side, 23+26*(side^1), 3+10*side
    unarmed=name.startswith('unarmed-')
    move=name.removeprefix('unarmed-')
    if unarmed:pre += [input_row(side,1,8|forward),(120,0,0)]
    if move in ('walk-forward','walk-back'):
        inputs=[forward if move=='walk-forward' else back]*20+[0]*15
    elif move.startswith('wall'):
        pre += [input_row(side,120,back),(15,0,0)]
        inputs = [16|back]+[0]*10+[forward|(16 if move=='wall-high' else 32)]*3+[0]*65
    elif move=='run':
        inputs = [0,forward,0]+[forward]*16+[0]*43
    elif move=='backstep':
        inputs = [0,back,0,back]+[0]*46
    elif move=='3+B':
        inputs = [32|forward|512]+[0]*70
    else:
        inputs = [16|{'vertical':0,'forward':forward,'back':back}[move]]+[0]*60
    if character==3:inputs += [0]*22  # His 26/27 landing lasts through update 64.
    rows = replay(pre + [input_row(side,1,pad) for pad in inputs], '--wall-fields')[-len(inputs)-1:]
    oracle = Original(side,character)
    p, a, o = oracle.p, oracle.a, oracle.o
    stage,_ = p.run(0x140040)
    if unarmed:
        p.write(a+0x23c,p.read(a+0x23c,4)&~4096,4)
        p.run(0x120390,[o,1])  # Start every unarmed case on the true unarmed idle.
    actions, callbacks, max_y = [], [], 0
    free_x = 0 if move.startswith('wall') else len(inputs) if move in ('vertical','3+B') else 16
    p.write(o+0x40,int(rows[0][source]),4)
    for tick,(pad,previous,row) in enumerate(zip(inputs,rows,rows[1:])):
        # Only the stage's horizontal constraints and last body anchors come
        # from the live match. The independent actor integrates its own jump.
        p.write(stage+0x10,int(row[129]),4);p.write(stage+0x14,int(row[130]),4)
        p.write(o+0x1040,int(previous[target]),4)
        if tick>=free_x:
            p.write(o+0x40,int(previous[source]),4)
        ref = oracle.frame(pad)
        callback = 88+27*side
        actual = (int(row[base+1])<<16|int(row[base]),int(row[base+2]),int(row[base+3]),
                  int(row[source+1]),int(row[source+2])&0x80000,int(row[callback]),int(row[source+5])&1)
        expected = (ref[0],ref[54],ref[55],ref[69],ref[58]&0x80000,ref[12],ref[5]&1)
        if expected[1]==actual[1] and expected[1] in (0,1):
            # The fixture starts from idle; selection already advanced that
            # looping idle clip by a different number of visits.
            expected = (*expected[:2],actual[2],*expected[3:])
        assert expected==actual,(side,name,tick,expected,actual)
        if tick<free_x:
            assert ref[68]==int(row[source]),(side,name,tick,'free horizontal motion',ref[68],row[source])
        if not actions or actions[-1]!=ref[54]:actions.append(ref[54])
        if not callbacks or callbacks[-1]!=ref[12]:callbacks.append(ref[12])
        max_y=max(max_y,struct.unpack('<f',struct.pack('<I',ref[69]))[0])
    required={'vertical':{14,16,26},'forward':{18,20,26},'back':{22,24,26},'run':{28,34},
              'backstep':{36},'wall-high':{38,40},'wall-low':{38,42},'3+B':{239},'walk-forward':{10},'walk-back':{12}}[move]
    required={a+unarmed for a in required}
    if move=='3+B' and character==3:required={204 if unarmed else 194}
    assert required<=set(actions) and actions[-1]==int(unarmed),(side,name,actions)
    if name.endswith('3+B') and character!=3:
        assert callbacks==([0x16b2b8] if character==2 else [])+[0x16b318,0x16b368,0x169a50,0]
        assert (max_y>0)==(character==2)
    return dict(seat=side+1,input=name,frames=len(inputs),actions=actions,
                free_horizontal_frames=free_x,callbacks=[hex(x) for x in callbacks],peak_height=max_y,original_instructions=oracle.instructions)


def attacks(side):
    forward=(128,64)[side]
    for state,act,approach,button in attack_cases(side,1):
        if state==2 or state==6:
            # These two descending hit boxes pass above a grounded opponent
            # when pressed at Nakoruru's later vertical jump timing.
            approach=approach[:-1]+[(27,0)]
        yield state,act,approach,button,0
    yield 22,239,[(45,forward),(2,0)],32|forward|512,0
    for condition in (1,2):  # Guard and whiff additional high-impact variants.
        for state,act,approach,key in attack_cases(side,1):
            if act not in (189,195,211,214,221):continue
            yield state,act,approach,key,condition
        yield 22,239,[(45,forward),(2,0)],32|forward|512,condition


def unarmed_attacks(side):
    forward=(128,64)[side]
    for pose,button,state,action,hit in unarmed_cases():
        if not hit or pose in ('back-jump','A+B'):
            continue
        approach=[(1,forward|8),(120,0)]
        if pose not in ('forward-jump','run'):
            # Walk off her grounded sword before pressing A, so the original
            # pickup action cannot silently replace an intended punch.
            approach += [(45,forward),(20,0)]
        if pose in ('vertical','forward-jump'):
            approach += [(1,16|(forward if pose=='forward-jump' else 0)),(30,0)]
        elif pose=='run':
            approach += [(1,forward),(1,0),(14,forward)]
            button |= forward
        elif pose=='crouch':
            approach += [(10,32)]
            button |= 32
        elif pose=='forward-kick':
            button |= forward
        elif pose in ('low-forward-kick','low-forward-B'):
            button |= 32|forward
        yield state,action,approach,button,0


def introduction(roster,side):
    source=3+10*side
    callback=88+27*side
    fields=23+26*side
    rows=replay([(1,*k) for k in prefix(roster)],'--wall-fields')
    intro=[r for r in rows if r[source+2]=='492' and int(r[0])>0]
    assert intro and any(r[1]=='4' for r in rows)
    p,a,o,_=fixture(side,roster[side])
    p.finite_model=True
    p.write(a+0xa1c,roster[side^1],4)
    p.write(o+0x104,0,4)
    _,count=p.run(0x149008,[a,1],limit=200000)
    ready=None
    for tick,r in enumerate(intro,1):
        for entry,arg in ((0x11d730,o),(0x11d6c8,o),(0x149d08,a),(0x149918,a),(0x11d8e0,o)):
            count+=p.run(entry,[arg],limit=200000)[1]
        expected=[p.read(addr,4) for addr in (o+0x24,o+0x28,o+0x2c,o+0x40,o+0x44,a+0x260)]
        actual=list(map(int,(r[source+2],r[source+3],r[callback+11],r[fields],r[fields+1],r[callback])))
        assert expected==actual and not ((p.read(o+0x104,4)^int(r[fields+3]))&0x300),(roster,side,tick)
        gate=int(r[fields+7])&0x40000000
        assert gate==p.read(a+0x244,4)&0x40000000
        if gate and ready is None:ready=tick
    assert ready is not None
    return dict(lineup=roster,seat=side+1,introduction_visits=len(intro),ready_at=ready,
                first_playable_match_update=int(next(r[0] for r in rows if r[1]=='4')),original_instructions=count)


def contact_group(side,character=2,case_list=None,opponent=0):
    original = MixedContactOracle(lineup(side,character,opponent))
    own,other=3+10*side,3+10*(side^1)
    forward=(128,64)[side]
    results=[]
    for state,action,approach,button,condition,*guard_override in (case_list if case_list is not None else (*attacks(side),*unarmed_attacks(side))):
        armed=(approach[0][1]&8)==0
        prefix_rows=opening(side,character,opponent)
        if condition==2:
            # Put the defender against their own wall before the approach.
            prefix_rows += [input_row(side,132,0,forward),(5,0,0)]
        prefix_rows += [input_row(side,*step) for step in approach]
        guard=guard_override[0] if guard_override else (forward|(32 if state==9 else 0) if condition==1 else 0)
        # Hold the defender back from the input onward. A crouching defender
        # can still be hit by Rimururu's overhead, so use a standing guard on 3+B.
        inputs=[input_row(side,1,button,guard)]+[input_row(side,1,0,guard)]*230
        rows=replay(prefix_rows+inputs,'--contact-fields')
        if not armed:assert any(row[own+2]=='135' for row in rows) and not int(rows[-1][28+26*side])&4096
        start=len(prefix_rows)
        actual=tuple(map(int,rows[start][own:own+3]))
        if condition==2 and action in (189,195):action+=1
        assert actual==(1,state,action),(side,state,condition,action,actual)
        last=max(i for i in range(start,len(rows)) if rows[i][own]=='1')
        contacts=original.contacts(rows[start-5:last+2],side)
        hits,blocks=map(int,rows[-1][own+7:own+9])
        assert len(contacts)==hits+blocks,(side,state,condition,contacts,hits,blocks)
        assert (hits>0)==(condition==0) and (blocks>0)==(condition==1),(side,state,condition,hits,blocks)
        assert rows[-1][own:own+3]==['0','0',str(int(not armed))] and rows[-1][other]=='0'
        first_free=next(i for i,r in enumerate(rows[start+1:],1) if r[own:own+2]==['0','0'])
        reacted=next((i for i,r in enumerate(rows[start:],0) if r[other]=='2'),None)
        recovered=next((i for i,r in enumerate(rows[start:],0) if reacted is not None and i>reacted and r[other]=='0'),None)
        if contacts:assert recovered is not None
        results.append(dict(seat=side+1,state=state,action=action,approach=approach,button=button,
                            armed=armed,condition=('hit','guard','whiff')[condition],contacts=contacts,life=int(rows[-1][other+6]),
                            attacker_idle_after=first_free,defender_reaction_after=reacted,defender_free_after=recovered))
    return results


def jump_defenders(side,character=2):
    forward=(128,64)[side]
    results=[]
    for airborne in (False,True):
        for light in (False,True):
            wait=18 if airborne else 35 if character==3 else (27 if light else 30)
            posture=0 if airborne else 32
            opening_rows=opening(side,character)+[input_row(side,45,forward),(9,0,0),
                                        input_row(side,1,16,16 if airborne else 32),input_row(side,wait,0,posture)]
            button=256 if light else 1024
            rest=[input_row(side,1,button,posture)]+[input_row(side,1,0,posture)]*125
            rows=replay(opening_rows+rest,'--contact-fields')
            base,foe=3+10*side,3+10*(side^1)
            start=len(opening_rows)
            action=209 if light else 211
            assert int(rows[start][base+2])==action
            last=max(i for i in range(start,len(rows)) if rows[i][base]=='1')
            geo=MixedContactOracle(lineup(side,character))
            hits=geo.contacts(rows[start-5:last+2],side)
            hurt=next(i for i,r in enumerate(rows[start:],start) if r[foe]=='2')
            free=next(i for i,r in enumerate(rows[hurt:],hurt) if r[foe]=='0')
            assert len(hits)==1 and hits[0]['target_state']==(74 if airborne else 38 if light else 40)
            assert int(rows[hurt][foe+2])==(378 if airborne else 350 if light else 354)
            assert free>hurt and int(rows[-1][foe+6])<200 and rows[-1][base:base+3]==['0','0','0']
            results.append(dict(seat=side+1,action=action,defender='air' if airborne else 'crouch',
                                hits=hits,victim_action=int(rows[hurt][foe+2]),victim_reaction_updates=free-hurt))
    return results


def heavy_timeline(job, character=2):
    side,action,approach,button=job
    actor=Original(side,character)
    geo=MixedContactOracle(lineup(side,character))
    base,fields,c=3+10*side,23+26*side,88+27*side
    movement=[0]+[key for count,key in approach for _ in range(count)]
    press=len(movement)
    pads=movement+[button]+[0]*130
    rows=replay(opening(side,character)+[input_row(side,1,k) for k in pads],'--whirlwind-fields')[-len(pads)-1:]
    hits=[]
    for tick,(previous,row,held) in enumerate(zip(rows,rows[1:],pads)):
        if tick>press and previous[base]=='1':
            impacts=geo.contacts([previous]*6+[row],side)
            if impacts:
                hits.extend(impacts)
                # Share only the two hitstop timers from the previous
                # original contact pass, before EE actor input and animation.
                for offset in (0x1b0,0x1b4):
                    actor.p.write(actor.a+offset,geo.probe.read(ACTORS+side*0xf2c+offset,4),4)
        bring_stage(actor,previous)
        reference=actor.frame(held)
        if tick<press:continue
        actual=(int(row[base])|int(row[base+1])<<16,*map(int,row[base+2:base+4]),int(row[c+11]),
                int(row[fields+1]),int(row[c]),int(row[c+8]),int(row[c+9]))
        expected=(reference[0],*reference[54:57],reference[69],reference[12],reference[19],reference[20])
        assert actual==expected,(side,action,tick-press,actual,expected)
        if tick==press:assert actual[1]==action
        if actual[0]==actual[1]==0:
            assert hits
            return dict(seat=side+1,action=action,checked_from_press=tick-press+1,hits=hits,
                        original_actor_instructions=actor.instructions)
    raise AssertionError((side,action,'did not recover'))


def run(binary):
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    jobs=[(s,name) for s in (0,1) for name in ('vertical','forward','back','wall-high','wall-low','run','backstep','3+B','unarmed-3+B')]
    with ProcessPoolExecutor(max_workers=4) as pool:
        contacts=[pool.submit(contact_group,s) for s in (0,1)]
        movements=list(pool.map(motion,jobs))
        heavy_jobs=[(side,action,approach,button) for side in (0,1)
                    for _,action,approach,button,condition in attacks(side)
                    if condition==0 and action in (189,190,195,196,211,214,221)]
        heavies=list(pool.map(heavy_timeline,heavy_jobs))
        defenders=[case for group in pool.map(jump_defenders,(0,1)) for case in group]
        fights=[r for f in contacts for r in f.result()]
    intros=[introduction(roster,side) for roster,side in (((2,0),0),((0,2),1),((2,1),0),((1,2),1),((2,2),0),((2,2),1))]
    report=dict(status='passed',introductions=intros,jump_contacts_vs_crouch_and_air=defenders,heavy_actor_timelines=heavies,elf_sha256=PIN,replay_sha256=sha256(binary.read_bytes()).hexdigest(),motions=movements,
                contact_cases=fights,actor_frames=sum(v['frames'] for v in movements),original_contacts=sum(len(v['contacts']) for v in fights),
                scope='Both seats choose cell24 in VS against Haohmaru and select Rage. EE 1495e8/149d08 is compared through every sampled motion update using live horizontal anchors; active ACT/step, callback, y bits, airborne posture and facing come from the original actor. Combat uses independent original 1536e8/1544a0/155850 resolution on the published two-body poses; damage, guard, target state and rage are checked at every strike. The seven armed heavy variants on each seat also check every attacking ACT, record, fractional clock, y bits, callback and both timers from press through first idle. The opening actor is compared from original 149008 for six selected lineups.')
    (ROOT/'outputs/ss6-feasibility/rimururu_normals_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(movements),'motions,',report['actor_frames'],'actor frames,',len(fights),'fights,',report['original_contacts'],'source contacts')


if __name__=='__main__':
    with tempfile.TemporaryDirectory() as directory:
        # A parallel packaging job can replace the build target between fights.
        # The checksum and every replay in this report use this single snapshot.
        binary=Path(directory)/'ss6-match-replay'
        shutil.copy2(BUILD/'ss6-match-replay',binary)
        os.environ['SS6_RIMURURU_TEST_REPLAY']=str(binary)
        run(binary)
