#!/usr/bin/env python3
"""Reach every armed Haohmaru ordinary attack with two human pads starting at round one."""
import argparse
import copy
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
import subprocess
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "work/ss6/build-native"
OUTPUT = ROOT / "outputs/ss6-feasibility"
ASSETS = Path(os.environ.get("SS6_TEST_ASSETS", OUTPUT / "native-viewer/assets"))


def attack_cases(player, character=0):
    forward = 64 if player else 128
    for strength, button in enumerate((256, 512, 1024)):
        for crouch in (0, 1):
            for far in (0, 1):
                walk = (26 if character==1 else 30) if far else 45
                prefix = [(walk, forward), (2, 0)]
                if crouch:
                    prefix.append((10, 32))
                yield (4*strength+crouch, 185+6*crouch+2*strength+far,
                       prefix, button | (32 if crouch else 0))
        for diagonal in (0, 1):
            # The vertical light box is short. Use a descending jump at close
            # range so the acceptance check exercises a real body collision.
            prefix = [] if diagonal else [(45, forward), (2, 0)]
            # Nakoruru falls through the target later. Her heavy needs time
            # to reach its active record before landing resets the attack.
            if character==1:
                wait=(32,33,27)[strength]
            else:
                wait=23 if not diagonal and strength==1 else 29
            prefix += [(1, 16 | (forward if diagonal else 0)), (wait, 0)]
            yield 4*strength+2+diagonal, 209+strength+3*diagonal, prefix, button
        yield 17+strength, 219+strength, [(1,forward),(1,0),(13,forward)], button|forward
    for n, direction in enumerate((0, forward, 32, forward|32)):
        yield 12+n, 197+n, [(45,forward),(2,0)], 2048|direction
    yield 16, 217, [(1,16|forward),(29,0)], 2048
    yield 20, 222, [(1,forward),(1,0),(13,forward)], 2048|forward


def additional_motion_cases(player):
    forward=(128,64)[player];back=forward^192
    for i,button in enumerate((256,512,1024,2048)):
        # Jumping away reaches the diagonal attack clips. A button tapped in
        # the early backstep is tested at the same distance, with no buffering
        # into a later standing attack. Both naturally leave the defender intact.
        yield 7,(3+4*i if i<3 else 16),(212+i if i<3 else 217),[(45,forward),(2,0),(1,16|back),(10,0)],button
        yield 44,24,36,[(45,forward),(2,0),(1,back),(1,0),(2,back)],button
    yield 8,16,217,[(45,forward),(2,0),(1,16),(10,0)],2048


def original_approach(player, approach, system):
    from validate_directional_slash import setup_actor
    actor=setup_actor(player)
    p=actor.p
    p.write(actor.a+0x10c,system,4)
    actor.run(0x179258,actor.a+0x2c4,actor.a+0x10c)
    # The native match starts with the actual console intro. The independent
    # actor fixture starts at playable idle at those same two world positions.
    for obj,x in zip((actor.o,actor.o+0x1000),((400,240) if player else (240,400))):
        struct.pack_into('<f',p.memory,obj+0x40,x)
    # Prime the released pad once, as in the idle opening before the native inputs.
    actor.frame(0)
    for n,mask in approach:
        for _ in range(n):actor.frame(mask)
    return actor


def test_case(player, state, action, approach, attack, spirit=None, motion=0, expected_hit=True, original=None):
    source, victim = 3 + player*10, 3 + (1-player)*10
    inputs = [(500,0), *approach, (1,attack)] + [(1,0)] * 220
    replay = "".join(f"{n} {0 if player else mask} {mask if player else 0}\n" for n,mask in inputs)
    options=[f'--p{player+1}-spirit',spirit,f'--p{2-player}-spirit','rage','--spirit-fields'] if spirit else []
    result = subprocess.run([BUILD/"ss6-match-replay", ASSETS, "--mode", "versus",*options], input=replay, text=True,
                            capture_output=True, timeout=20)
    assert result.returncode==0, (player,state,action,result.stderr)
    rows = [r.split() for r in result.stdout.splitlines()]
    chosen = rows[1+len(approach)]
    table=0 if motion==44 else 1
    selected=tuple(map(int,chosen[source:source+3]))
    original_count=0
    if spirit:
        assert tuple(int(chosen[23+4*side]) for side in (player,1-player))==({'zan':2,'ten':3,'zero':4,'ken':5}[spirit],0)
        source_selection,original_count=original
        assert selected==source_selection,(player,motion,attack,selected,source_selection)
    assert selected==(table,state,action),(player,state,chosen)
    damaged = next((r for r in rows if int(r[victim+6]) < 200), None)
    if expected_hit:
        assert damaged and int(damaged[victim])==2, (player,state,"missing hit reaction")
    else:
        assert damaged is None and all(int(r[victim+6])==200 for r in rows),(player,motion,attack)
        if motion==44:assert all(int(row[source])==0 for row in rows),(player,motion,attack,'queued attack')
    finished = rows[-1]
    assert int(finished[source+7])==int(expected_hit) and int(finished[victim])==0, (player,state,finished)
    assert int(finished[source])==0 and int(finished[source+1])==0,(player,state,'did not return to idle')
    item=dict(player=player+1, attack_state=state, action=action, contact_update=int(damaged[0]) if damaged else None,
              hurt_state=int(damaged[victim+1]) if damaged else None, defender_hp=int(finished[victim+6]))
    if spirit:item.update(motion=motion,original_table=table,pad=attack,approach=approach,original_instructions=original_count)
    return item


def run_group(cases):
    player, _, _, approach, *_ = cases[0]
    original = original_approach(player, approach, {'zan':2,'ten':3,'zero':4,'ken':5}[cases[0][5]])
    results = []
    for case in cases:
        # Each button starts from the same unchanged Japanese actor and pad history.
        actor = copy.deepcopy(original)
        r = actor.frame(case[4])
        selected = (r[0] & 65535, r[0] >> 16, r[54])
        results.append(test_case(*case, original=(selected, actor.instructions)))
    return results


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    for name in ('zan','ten','zero','ken'):
        group.add_argument('--'+name,action='store_const',const=name,dest='spirit')
    args=parser.parse_args()
    jobs=[]
    for player in (0,1):
        for state,action,approach,pad in attack_cases(player):
            motion=66 if state>=17 else 9 if 212<=action<=214 or state==16 else 8 if 209<=action<=211 else 0
            jobs.append((player,state,action,approach,pad,args.spirit,motion,True))
        if args.spirit:
            for motion,state,action,approach,pad in additional_motion_cases(player):
                jobs.append((player,state,action,approach,pad,args.spirit,motion,False))
    if args.spirit:
        from validate_dash_motion import ELF, PIN, digest
        assert digest(ELF)==PIN
        groups = {}
        for case in jobs:
            groups.setdefault((case[0], tuple(case[3])), []).append(case)
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases = [case for group in pool.map(run_group, groups.values()) for case in group]
        assert len(cases)==72 and {r['motion'] for r in cases}=={0,7,8,9,44,66}
    else:cases=[test_case(*job) for job in jobs]
    hits=[case for case in cases if case['contact_update'] is not None]
    assert len(hits)==54 and {r['attack_state'] for r in hits}==set(range(21))
    evidence=dict(status='passed',native_match_sha256=hashlib.sha256((BUILD/'ss6-match-replay').read_bytes()).hexdigest(),
                  scope='Resource 00 armed ordinary attacks. Both human seats, real input, damage, hurt and recovery from round one.',cases=cases)
    if args.spirit:evidence.update(elf_sha256=PIN,source=f'{args.spirit.title()} attacker versus Rage, both player orders. Independent Japanese actor input and ACT selection from combat-ready positions. Native full-match hit, whiff and recovery. Early 44 button taps stay in backstep. No whole-console emulation.')
    filename=f'{args.spirit}-normal-attacks-validation.json' if args.spirit else 'normal_attack_match_validation.json'
    (OUTPUT/filename).write_text(json.dumps(evidence,indent=2)+'\n')
    print(len(cases),'cases;',len(hits),'natural hits;',len({r['action'] for r in hits}),'distinct hitting ACT clips')
