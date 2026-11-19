#!/usr/bin/env python3
"""Check selected 01 vs 00 at original 412/236 command, ACT, camera and contact boundaries."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess

from validate_dash_motion import Original, PIN
from validate_haohmaru_special import BUILD, ELF, RES, ROOT
from validate_nakoruru_combat import MixedContactOracle
from validate_selected_combat import prefix


def controls(side, state, mode):
    forward, back = ((128, 64), (64, 128))[side]
    button = 256 << ((state - 64) % 3)
    low = state <= 66
    pair = lambda a, b=0: (b, a) if side else (a, b)
    pre = prefix((1-side, side))
    pre[229] = [128, 128]  # Both choose the first sword spirit.
    walk, settle = {'miss': (100, 10), 'edge': (125, 16), 'hit': (40, 4), 'guard': (40, 4)}[mode]
    direction = pair(back, forward) if mode == 'miss' else pair(forward, forward if mode == 'edge' else back)
    pre += [direction] * walk + [pair(0)] * settle
    motion = [back, 32|back, 32|button] if low else [32, 32|forward, forward|button]
    defense = (forward | (32 if low else 0)) if mode == 'guard' else 0
    sequence = motion + [0] * 175
    return pre, sequence, [pair(k, defense) for k in sequence]


def body_trace(rows, side, state, words):
    oracle = Original(side, 1)
    p, a, obj = oracle.p, oracle.a, oracle.o
    stage, _ = p.run(0x140040)
    body, other, head, registry = 23+26*side, 23+26*(1-side), 3+10*side, 75+27*side
    checked, events, finished = 0, [], False
    for tick, (key, previous, row) in enumerate(zip(words, rows, rows[1:]), 1):
        # Import just the horizontal anchors and the live stage edges. The
        # original actor runs the pad interpreter, timing and vertical motion.
        for offset, value in ((0x10, row[129]), (0x14, row[130])):
            p.write(stage+offset, int(value), 4)
        p.write(obj+0x40, int(previous[body]), 4)
        p.write(obj+0x1040, int(previous[other]), 4)
        reference = oracle.frame(key)
        expect = [reference[0], reference[54], reference[55], reference[56], reference[69], reference[58]&0x80000]
        actual = [int(row[head+1])<<16|int(row[head]), int(row[head+2]), int(row[head+3]), int(row[registry+24]), int(row[body+1]), int(row[body+2])&0x80000]
        if int(row[head]) == 1 or reference[0]&0xffff == 1:
            for index in (0, 1, 2, 3, 6, 11):
                expect.append(p.read(a+0x28c+4*index, 4))
                actual.append(int(row[registry+index]))
            if reference[59]&0x8000:
                events.append([tick, p.read(obj+0x10c, 4), p.read(obj+0x110, 4), p.read(obj+0x114, 4), bool(reference[59]&0x10000)])
        assert actual == expect, (side, state, tick, actual, expect)
        p.write(obj+0x104, p.read(obj+0x104,4) & ~0x18000, 4)  # 1404dc..140500 consume the attachment.
        checked += 1
        if tick > 3 and (int(row[head]), int(row[head+1])) == (0, 0):
            finished = True
            break
    assert finished and any(e[1] == 794 for e in events), (side,state,events)
    return dict(frames=checked, original_instructions=oracle.instructions, original_attachments=events)


def case(job):
    side, state, mode, replay = job
    lineup = (1-side, side)
    original_contact = MixedContactOracle(lineup)
    pre, words, both = controls(side, state, mode)
    proc = subprocess.run([replay, RES, '--mode', 'select', '--wall-fields'],
                          input=''.join('1 %d %d\n'%tuple(p) for p in pre+both), text=True, capture_output=True)
    assert proc.returncode == 0, (job[:3], len(proc.stdout.splitlines()), proc.stderr)
    rows = [r.split() for r in proc.stdout.splitlines()[-len(both)-1:]]
    head, target, body = 3+10*side, 3+10*(1-side), 23+26*side
    registry = 75+27*side
    assert rows[3][head:head+2] == ['1', str(state)] and rows[-1][head:head+3] == ['0','0','0']
    hits, guards = map(int, rows[-1][head+7:head+9])
    life = int(rows[-1][target+6])
    if mode in ('hit','edge'): assert hits == 1 and guards == 0 and life < 200, (job[:3],hits,guards,life)
    if mode == 'guard': assert (hits,guards,life) == (0,1,199), (job[:3],hits,guards,life)
    if mode == 'miss': assert (hits,guards,life) == (0,0,200), (job[:3],hits,guards,life)
    contacts = original_contact.contacts(rows, side)
    assert len(contacts) == hits+guards
    for item in contacts:
        assert item['raw'] == (24 if state <= 66 else 17), item
        if not item['defense']: assert item['target_state'] == (65 if state <= 66 else 63), item
    phases = []
    for t, row in enumerate(rows):
        if int(row[head]) != 1 or int(row[head+1]) != state: continue
        phase = int(row[registry]); act = int(row[head+2]); key=[phase,act]
        if not phases or key != phases[-1][1:3]:
            x, = struct.unpack('<f', struct.pack('<I',int(row[body])))
            phases.append([t,*key,round(x,3),int(row[129]),int(row[130])])
    assert phases[0][2] == (529 if state<=66 else 540)+(state-64)%3
    if state <= 66:
        assert any(p[1] == 1 for p in phases) == (mode in ('guard','edge')), (job[:3],phases)
    else:
        assert phases[-1][1:3] == [2,546+state-67]
    if mode == 'edge':
        frame = next(t for t, phase, *_ in phases if phase == 1)
        prev, current = rows[frame-1], rows[frame]
        # Source 14aad8 tests the current X integral pixel against the
        # published front edge ±36. Hitstop and the player's rear edge must
        # never substitute for this condition in a no-guard fight.
        x, = struct.unpack('<f', struct.pack('<I',int(current[body])))
        assert (int(x) <= int(current[129])+36 if int(prev[body+2])&0x80000 else int(x) >= int(current[130])-36), (job[:3],phases,frame,x)
    result = dict(player=side+1,command=('412' if state<=66 else '236')+'+'+'ABC'[(state-64)%3],state=state,outcome=mode,hp=life,phases=phases,contacts=contacts)
    if mode == 'miss': result['actor_trace']=body_trace(rows,side,state,words)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay');parser.add_argument('--state',type=int);parser.add_argument('--mode');parser.add_argument('--seat',type=int)
    args=parser.parse_args()
    digest=lambda p: sha256(p.read_bytes()).hexdigest()
    assert digest(ELF) == PIN
    initial = digest(args.replay)
    jobs=[(s,i,m,args.replay) for s in range(2) for i in range(64,70) for m in ('miss','hit','guard','edge') if args.state in (None,i) and args.mode in (None,m) and args.seat in (None,s+1)]
    with ProcessPoolExecutor(max_workers=4) as workers:
        result=[]
        for r in workers.map(case,jobs):
            result.append(r);print(r['player'],r['command'],r['outcome'],r['hp'],flush=True)
    assert digest(args.replay)==initial
    if len(jobs)!=48:return
    report=dict(status='passed',elf_sha256=PIN,replay_sha256=initial,cases=result,original_contacts=sum(len(r['contacts']) for r in result),original_actor_frames=sum(r.get('actor_trace',{}).get('frames',0) for r in result),scope='Both real selections and human pad inputs, direct and blocked contacts through original 1536e8/1544a0/155850/155a88 or 155d50 on prior native snapshots. Whiffs independently execute Japanese 1495e8/149d08/149918/11d8e0 for every phase/step, vertical motion and attachment command. The isolated actor receives the actual horizontal anchors and camera bounds. Edge cases physically push forward and strike without guarding.')
    (ROOT/'outputs/ss6-feasibility/nakoruru_strikes_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(jobs),'battles,',report['original_actor_frames'],'callback frames,',report['original_contacts'],'original contacts')

if __name__ == '__main__': main()
