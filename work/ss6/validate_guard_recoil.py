#!/usr/bin/env python3
"""Run the Japanese guard, attacker recoil and real pad input on both sides of selected matches."""
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby

from validate_dash_motion import ELF, PIN
from validate_nakoruru_combat import MixedContactOracle
from validate_rimururu_normals import input_row, lineup, replay
from validate_selected_combat import prefix as selection
from validate_shin_evasion import setup_state
from validate_unarmed_normals import bring_stage
from validate_weapon_handling import setup


def case(job):
    character, seat, approach, button, timing, spirit = job
    front = (128, 64)[seat]
    defend = front | (button & 32)
    pads = selection(lineup(seat, character))
    # Both spirit cursors start on Ken (5) and wrap in screen coordinates.
    direction, count = (128, spirit+1) if spirit<=2 else (64, 5-spirit)
    for tick in (200, 213, 226)[:count]:
        pads[tick][seat] = direction
    pads[229][1-seat] = 128
    pre = [(sum(1 for _ in g), *k) for k,g in groupby(pads)]
    assert int(replay(pre, '--spirit-fields')[-1][23+4*seat])==spirit
    prefix = pre + [input_row(seat, approach, front), (2, 0, 0)]
    controls = [button] + [0] * 92
    if timing:
        controls[timing:timing+3] = [32, 32 | front, front | 256]
    rows = replay(prefix + [input_row(seat, 1, k, defend) for k in controls], '--whirlwind-fields')
    rows = rows[len(prefix)-1:]
    core, cb = 3+seat*10, 88+seat*27
    # Once the new special owns the actor, its projectile is a separate source.
    special = next((i for i,r in enumerate(rows) if r[core]=='1' and int(r[core+1])>=64), None)
    if special:
        rows = rows[:special+1]
    geometry = MixedContactOracle(lineup(seat, character))
    def strength(contact, p, event, target):
        contact['strength'] = p.read(event+12, 4)
    impacts = geometry.contacts([rows[0]]*5 + rows, seat, strength)
    assert impacts and all(e['defense'] for e in impacts), (job, impacts)
    by_frame = {e['frame']: e for e in impacts}

    src, _ = setup(seat, character)
    setup_state(src, spirit, 0, rows[0], seat, False)
    p, a, o = src.p, src.a, src.o
    result = []
    eligible = []
    for tick, (prev, now, held) in enumerate(zip(rows, rows[1:], controls)):
        bring_stage(src, prev)
        if e := by_frame.get(int(now[0])):
            # 155d50 acknowledges the previous ACT record and applies both
            # original stop timers before 155564 decides if this sword recoils.
            p.write(o+0x104, p.read(o+0x104,4) | 0x2080000, 4)
            src.run(0x14d5a0, src.other, o, e['defense'], e['strength'])
            bounce, _ = p.run(0x169700, [a])
            eligible.append(bool(bounce))
            if bounce:
                src.run(0x14d070, a, e['strength'], 0)
        v = src.frame(held)
        actual = [int(now[core]) | (int(now[core+1])<<16), *map(int, now[core+2:core+4]),
                  int(now[cb+11]), *map(int, now[cb:cb+3]), *map(int, now[cb+8:cb+10])]
        expected = [v[0], *v[54:57], *v[12:15], v[19], v[20]]
        # Selection has already played the idle animation before the first
        # button, so the idle clip's arbitrary looping phase is immaterial.
        if actual[0]==expected[0]==0 and actual[1]==expected[1]==0:
            break
        assert actual==expected, (job, tick, actual, expected)
        result.append((v[0]&65535, v[0]>>16, v[54]))
    poses = [k for k,_ in groupby(result)]
    recoils = [act for t,s,act in poses if t==0 and 25<=s<=30]
    assert bool(recoils)==any(eligible), (job, poses, eligible)
    if timing==19:
        assert special and poses[-1]==(1,64,529) and poses[-2]==(0,27,296), (job, poses)
    if timing==12:
        assert special is None and recoils==[296], (job, poses)
    return job, recoils, len(impacts), len(result), bool(special)


if __name__ == '__main__':
    assert sha256(ELF.read_bytes()).hexdigest()==PIN
    # Light, medium and heavy standing/crouching slash from both distances.
    # Include a blocked kick and an unflagged multi-hit slash as controls.
    jobs = [(c,s,d,b,0,0) for c in range(4) for s in range(2) for d in (26,45)
            for b in (256,512,1024,288,544,1056)]
    jobs += [(0,s,45,2048,0,0) for s in range(2)]
    jobs += [(0,s,45,1024,t,0) for s in range(2) for t in (12,19)]
    jobs += [(0,s,45,1024,19,spirit) for s in range(2) for spirit in range(1,6)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(case, jobs))
    print(f'{len(results)} matches, {sum(r[2] for r in results)} guards, '
          f'{sum(r[3] for r in results)} original actor updates, '
          f'{sum(r[4] for r in results)} accepted recoil cancels')
