#!/usr/bin/env python3
"""Exercise bare-handed Haohmaru from a real weapon discard on both pads."""
import argparse
import copy
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from validate_collisions import ACTORS
from validate_dash_motion import ASSETS, ELF, PIN, PROBE, ROOT, digest
from validate_haohmaru_special import ContactOracle
from validate_weapon_handling import setup

EXE = PROBE.with_name('ss6-match-replay')
REPORT = ROOT / 'outputs/ss6-feasibility/unarmed_normals_validation.json'
BUTTONS = (256, 512, 1024, 2048)


def cases():
    for pose, states, actions in (
        ('stand', (0, 4, 8, 12), (201, 202, 202, 205)),
        ('crouch', (1, 5, 9, 14), (203, 204, 204, 207)),
        ('vertical', (2, 6, 10, 16), (215, 216, 216, 218)),
        ('forward-jump', (3, 7, 11, 16), (215, 216, 216, 218)),
        ('back-jump', (3, 7, 11, 16), (215, 216, 216, 218)),
        ('run', (17, 18, 19, 20), (223, 223, 223, 224)),
    ):
        for mask, state, action in zip(BUTTONS, states, actions):
            yield pose, mask, state, action, True
            if pose in ('stand', 'crouch'):
                yield pose, mask, state, action, False
    for pose, mask, state, action in (
        ('forward-kick', 2048, 13, 206),
        ('low-forward-kick', 2048, 15, 208),
        ('low-forward-B', 512, 22, 240),
        ('A+B', 768, 0, 201),
    ):
        yield pose, mask, state, action, True
        yield pose, mask, state, action, False


def make_sequence(slot, pose, button, hit):
    forward = (128, 64)[slot]
    back = forward ^ 192
    warm = [(500, 0, 0), (1, 8 | forward, 0), (115, 0, 0)]
    if hit:
        if pose == 'back-jump':
            # The back jump retreats out of range in open space. The attacker
            # walks into their corner, and the defender approaches on foot.
            warm += [(210, back, back), (80, 0, back)]
        elif pose == 'forward-jump':
            warm.append((6, 0, back))
        elif pose != 'run':
            warm.append((100, 0, back))
    else:
        warm.append((100, 0, forward))
    warm.append((50 if pose == 'run' else 15, 0, 0))

    if pose in ('vertical', 'forward-jump', 'back-jump'):
        jump = {'vertical': 16, 'forward-jump': 16 | forward, 'back-jump': 16 | back}[pose]
        setup_pads = [jump] + [0] * 29
    elif pose == 'run':
        setup_pads = [forward, 0] + [forward] * 13
    elif pose == 'crouch':
        setup_pads = [32] * 10
    else:
        setup_pads = []
    direction = {'forward-kick': forward, 'run': forward, 'crouch': 32,
                 'low-forward-B': 32 | forward, 'low-forward-kick': 32 | forward}.get(pose, 0)
    inputs = setup_pads + [button | direction] + [0] * 230
    commands = warm + [(1, value, 0) for value in inputs]
    if slot:
        commands = [(count, other, own) for count, own, other in commands]
    return commands, inputs, len(warm) - 1, len(setup_pads)


@lru_cache(maxsize=2)
def original_after_discard(slot):
    # Own floor weapon must exist in the original registry: an A press in
    # its pickup interval selects state 51 before the normal attack.
    src, registry = setup(slot)
    p = src.p
    here, other = ((240, 400), (400, 240))[slot]
    struct.pack_into('<f', p.memory, src.o+0x40, here)
    struct.pack_into('<f', p.memory, src.o+0x1040, other)
    for held in [8 | (128, 64)[slot]] + [0] * 115:
        src.run(0x147028, registry, 48)
        src.frame(held)
        src.run(0x146ef8, registry, 48)
        src.run(0x1207d8)
        src.run(0x1470a8, registry, 48)
    assert p.read(src.a+0x194, 4) == 0 and p.read(src.o+0x24, 4) == 1
    assert p.read(src.a+0x23c, 4) & 0x1000 == 0
    tasks = [t for t in struct.unpack_from('<48I', p.memory, registry) if t]
    weapons = [p.read(t+28, 4) for t in tasks if p.read(p.read(t+28, 4)+0xcc, 4) == 4]
    assert len(weapons) == 1 and p.read(weapons[0]+0x24, 4) == 467
    x = struct.unpack_from('<f', p.memory, weapons[0]+0x40)[0]
    return src, x


def bring_stage(src, row):
    slot, other = src.player, 1-src.player
    for obj, side in ((src.o, slot), (src.o+0x1000, other)):
        src.p.write(obj+0x40, int(row[23+26*side]), 4)
    s = 23+26*other
    src.p.write(src.other+0x194, int(row[3+10*other]) | (int(row[4+10*other]) << 16), 4)
    for off, col in ((0x23c, 5), (0x244, 7)):
        src.p.write(src.other+off, int(row[s+col]), 4)
    src.p.write(src.other+0x19a, int(row[s+10]), 1)


def validate(arg):
    exe, slot, case = arg
    pose, button, state, action, hit = case
    commands, inputs, start, press = make_sequence(slot, pose, button, hit)
    text = ''.join(f'{n} {a} {b}\n' for n, a, b in commands)
    proc = subprocess.run([exe, ASSETS, '--mode', 'versus', '--whirlwind-fields'], input=text, text=True, capture_output=True)
    label = slot+1, pose, button, hit
    assert proc.returncode == 0, (label, proc.stderr, proc.stdout.splitlines()[-1:])
    rows = [line.split() for line in proc.stdout.splitlines()]
    base, target = 3+10*slot, 3+10*(1-slot)
    c = 88+27*slot
    assert rows[0][base+2] == '0' and rows[1][base+2] == '135' and rows[2][base+2] == '1'
    chosen = rows[start+press+1]
    assert list(map(int, chosen[base:base+3])) == [1, state, action], (label, chosen[base:base+3])
    assert rows[-1][base:base+3] == ['0','0','1'] and rows[-1][target:target+3] == ['0','0','0']
    assert all(int(r[28+26*slot]) & 0x1000 == 0 for r in rows[2:])
    if pose == 'run':
        assert rows[start+press][base:base+3] == ['0','23','29']
    template, weapon_x = original_after_discard(slot)
    src = copy.deepcopy(template)
    geo = ContactOracle()
    collisions = []
    idle = victim_idle = None
    checked = 0
    for i, (prev, now, held) in enumerate(zip(rows[start:], rows[start+1:], inputs)):
        if int(prev[base+2]) == action:
            # The detector consumes last tick's published JDG and resolves
            # before either actor's pad/callback visit. Replay that order.
            events = geo.contacts([prev]*6+[now], slot)
            collisions.extend(events)
            if events:
                a = ACTORS + 0xf2c * slot
                for off in (0x1b0, 0x1b4):
                    src.p.write(src.a+off, geo.probe.read(a+off, 4), 4)
        else:
            assert prev[base+7:base+9] == now[base+7:base+9], label
        if idle is None:
            bring_stage(src, prev)
            r = src.frame(held)
            if i >= press:
                native = [int(now[base]) | (int(now[base+1]) << 16), *map(int,now[base+2:base+4]),
                          int(now[c+11]), *map(int, now[c:c+7]), *map(int, now[c+8:c+10])]
                original = [r[0], *r[54:57], *r[12:19],
                            src.p.read(src.a+0x1b0, 4), src.p.read(src.a+0x1b4, 4)]
                assert native == original, (label, i, int(now[0]), native, original)
                checked += 1
                if native[0] == 0 and native[1] == 1:
                    idle = int(now[0])
        if collisions and victim_idle is None and now[target:target+3] == ['0','0','0']:
            victim_idle = int(now[0])
    assert idle and bool(collisions) == hit and len(collisions) <= 1, (label, idle, collisions)
    assert bool(victim_idle) == hit
    return dict(player=slot+1, pose=pose, button=button, expected_hit=hit, state=state, action=action,
                input_frame=int(chosen[0]), weapon_x=weapon_x, source_x=float(chosen[base+4]),
                contacts=collisions, attacker_idle_frame=idle, defender_idle_frame=victim_idle,
                original_attack_visits=checked, original_actor_instructions=src.instructions-template.instructions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--exe', type=Path, default=EXE)
    opts = parser.parse_args()
    assert digest(ELF) == PIN
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / 'match'
        shutil.copy2(opts.exe, exe)
        with ProcessPoolExecutor(opts.jobs) as pool:
            results = list(pool.map(validate, ((exe, slot, case) for slot in range(2) for case in cases())))
        report = dict(status='passed', scope='Japanese resource 00 mirror, system 0. Each native replay starts at round one, places the attacker’s own weapon on the floor, selects the unarmed attack from both pads and returns both actors to neutral. Independent original input selector, attacker act/clock/callbacks/timers through recovery. Original JDG and hit/guard handler on the native stage positions, comparing damage, reaction and rage.', elf_sha256=PIN, native_sha256=digest(exe),
                      validator_sha256=digest(Path(__file__)), cases=results)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(len(results), 'replays;', sum(bool(r['contacts']) for r in results), 'hits;',
          sum(r['original_attack_visits'] for r in results), 'matched attacker visits')


if __name__ == '__main__':
    main()
