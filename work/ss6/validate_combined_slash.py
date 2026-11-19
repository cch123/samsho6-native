#!/usr/bin/env python3
"""Compare the system-0 A+B command, its two ACT phases and actual versus contacts."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from knockdown_oracle import initialize_effects
from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_dash_motion import ASSETS, ELF, Original, PIN, ROOT, digest
from validate_haohmaru_special import ContactOracle

EXE = ROOT / 'work/ss6/build-native/ss6-match-replay'
REPORT = ROOT / 'outputs/ss6-feasibility/combined_slash_validation.json'
CASES = ('whiff', 'hit', 'guard', 'low-guard', 'crouch')

def initialize_pools(p):
    initialize_effects(p)
    for fn in (0x1123a8, 0x112570, 0x11e290):
        p.run(fn, limit=150000)
    for bank, name in enumerate(('01HitFlash.bin', '02Guard.bin', '03etc.bin')):
        data = (ASSETS / name).read_bytes()
        start = 0x4a4810 + bank * 0x3da0
        p.memory[start:start + len(data)] = data

def replay(exe, slot, case):
    forward = (128, 64)[slot]
    def order(a, b):
        return (b, a) if slot else (a, b)
    pads = [(500, 0, 0), (66, *order(forward ^ 192 if case == 'whiff' else forward, 0)), (5, 0, 0)]
    guard = {'low-guard': 32 | forward, 'guard': forward, 'crouch': 32}.get(case, 0)
    for i in range(1, 271):
        response = guard if 20 <= i <= 62 else 0
        if case == 'armor-active':
            response = 256 if i == 2 else 0
        elif case == 'armor-expired':
            if 20 <= i <= 30:
                response = forward
            elif 32 <= i < 90:
                response = forward ^ 192
            elif i == 90:
                response = 1024
        pads.append((1, *order(768 if i == 1 else 0, response)))
    text = ''.join(f'{n} {a} {b}\n' for n, a, b in pads)
    result = subprocess.run([exe, ASSETS, '--whirlwind-fields'], input=text, text=True, capture_output=True)
    assert result.returncode == 0, (slot, case, result.stderr)
    return [r.split() for r in result.stdout.splitlines()][2:], [p[1:] for p in pads[2:]]

def check(args):
    exe, slot, case = args
    rows, pads = replay(exe, slot, case)
    victim = 1 - slot
    src = Original(slot)
    initialize_pools(src.p)
    defender = Original(victim)
    initialize_pools(defender.p)
    aid = (ASSETS/'aid_00.bin').read_bytes()
    defender.p.memory[0x46a9b0+0x1800:0x46a9b0+0x1800+len(aid)] = aid
    defender.p.write(0x4751b4, defender.p.read(0x4751b0, 4), 4)
    defender.p.write(defender.o+0xc, victim, 4)
    defender.p.write(defender.o+0x100c, slot, 4)
    defender.p.write(defender.o+0x10cc, slot, 4)
    defender.p.write(defender.a+0xa30, 200, 4)
    defender.p.write(defender.a+0xa34, 200, 4)
    geo = ContactOracle()
    g = geo.probe
    initialize_pools(g)
    out = g.read(g.read(0x5d1bf8, 4) + 8, 4)
    g.write(out, 0x19e0000, 4)
    g.write(out + 16, 0x19e0000, 4)
    elf_contact_instructions = 0
    def call(pc, *args):
        nonlocal elf_contact_instructions
        v, n = g.run(pc, args, limit=800000)
        elf_contact_instructions += n
        return v

    contacts = []
    actions = []
    callbacks = 0
    first_idle = None
    reaction_end = None
    for i, (prev, row) in enumerate(zip(rows, rows[1:]), 1):
        actual_hit = int(row[10+10*slot]) - int(prev[10+10*slot])
        actual_guard = int(row[11+10*slot]) - int(prev[11+10*slot])
        attack = 3 + 10 * slot
        target = 3 + 10 * victim
        recorded = False
        if 264 <= int(prev[attack+2]) <= 265:
            for side in (0, 1):
                geo.install_player(prev, side)
            g.write(0x12d2698, 0, 4)
            for pair in (OBJECTS, OBJECTS[::-1]):
                call(0x1536e8, *pair)
            call(0x1544a0)
            for idx in range(g.read(0x12d2698, 4)):
                event = QUEUE + 108 * idx
                if g.read(event, 4) != 7 or g.read(event+0x40, 4) != OBJECTS[slot]:
                    continue
                if g.read(OBJECTS[slot]+0x104, 4) & 0x06000000:
                    continue
                assert not recorded and g.read(event+0x20, 4) == 18
                defense = call(0x155850, event)
                call(0x155d50 if defense else 0x155a88, event, 1, defense)
                source = ACTORS + slot * 0xf2c
                other = ACTORS + victim * 0xf2c
                timers = [g.read(a+o, 4) for a in (source, other) for o in (0x1b0, 0x1b4)]
                # The collision oracle produced both actors' impact clocks
                # before the scheduler visits animation and actor callbacks.
                for off, value in zip((0x1b0, 0x1b4), timers):
                    src.p.write(src.a+off, value, 4)
                # Transfer only the request, counters and contact metadata
                # emitted by the original resolver to the defender fixture.
                for off in (0x18c, 0x190, 0x1b0, 0x1b4, 0x230, 0x23c, 0x244, 0x250, 0x254, 0x258, 0xa38):
                    defender.p.write(defender.a+off, g.read(other+off, 4), 4)
                want_state = g.read(other+0x190, 4)
                assert (int(row[target]) | int(row[target+1]) << 16) == want_state
                damage = g.read(other+0xa38, 4)
                assert int(prev[target+6]) - int(row[target+6]) == damage
                assert (actual_hit, actual_guard) == (int(not defense), int(bool(defense)))
                contacts.append(dict(tick=i, raw=18, defense=defense, damage=damage,
                                     victim_state=want_state >> 16, initial_timers=timers))
                recorded = True
                break
        assert bool(actual_hit or actual_guard) == recorded, (slot, case, i)
        if first_idle is None:
            # Use the preceding stage's published X coordinates. The player's
            # own pad history, state requests, animation and callbacks run in ELF.
            for obj, side in ((src.o, slot), (src.o+0x1000, victim)):
                src.p.write(obj+0x40, int(prev[23+26*side]), 4)
            result = src.frame(pads[i][slot])
            c = 88 + 27 * slot
            got = [result[0], *result[54:57], *result[12:19], bool(result[5] & 0x02000000),
                   *[src.p.read(src.a+k, 4) for k in (0x1b0, 0x1b4)]]
            want = [int(row[attack]) | int(row[attack+1]) << 16, *map(int, row[attack+2:attack+4]), int(row[c+11]),
                    *map(int, row[c:c+7]), bool(int(row[28+26*slot]) & 0x02000000), *map(int, row[c+8:c+10])]
            assert got == want, (slot, case, i, got, want)
            callbacks += 1
            if not actions or actions[-1][1] != result[54]:
                actions.append([i, result[54]])
            if result[54] == 0:
                first_idle = i
        if case != 'whiff' and reaction_end is None:
            for obj, side in ((defender.o, victim), (defender.o+0x1000, slot)):
                defender.p.write(obj+0x40, int(prev[23+26*side]), 4)
            dp = defender.p
            side = 23 + 26 * slot
            dp.write(defender.other+0x194, int(prev[attack]) | (int(prev[attack+1]) << 16), 4)
            dp.write(defender.other+0x23c, int(prev[side+5]), 4)
            dp.write(defender.other+0x244, int(prev[side+7]), 4)
            dp.write(defender.other+0x19a, int(prev[side+10]), 1)
            result = defender.frame(pads[i][victim])
            if contacts:
                c = 88 + 27 * victim
                got = [result[0], *result[54:57], *result[12:19],
                       *[dp.read(defender.a+k, 4) for k in (0x1b0, 0x1b4)]]
                want = [int(row[target]) | int(row[target+1]) << 16, *map(int, row[target+2:target+4]),
                        int(row[c+11]), *map(int, row[c:c+7]), *map(int, row[c+8:c+10])]
                assert got == want, ('defender', slot, case, i, got, want)
                if int(row[target]) == 0:
                    reaction_end = i
    assert [a for _, a in actions] == [264, 265, 0], (slot, case, actions)
    assert len(contacts) == int(case != 'whiff'), (slot, case, contacts)
    if contacts:
        expected_defense = {'guard': 1, 'low-guard': 2}.get(case, 0)
        assert contacts[0]['defense'] == expected_defense
        assert contacts[0]['damage'] == (0 if expected_defense else 59)
        assert contacts[0]['victim_state'] == {0: 64, 1: 0, 2: 3}[expected_defense]
        assert reaction_end is not None
    assert [int(rows[-1][5+10*side]) for side in (0, 1)] == [0, 0]
    return dict(player=slot+1, case=case, contacts=contacts, action_entry=actions,
                compared_attacker_visits=callbacks, victim_exit_tick=reaction_end,
                final_life=int(rows[-1][9+10*victim]), source_instructions=src.instructions + defender.instructions + elf_contact_instructions)

def check_armor(exe, slot, case):
    rows, _ = replay(exe, slot, case)
    geo = ContactOracle()
    g = geo.probe
    initialize_pools(g)
    other = 1 - slot
    expected_action = 264 if case == 'armor-active' else 265
    for i, (prev, now) in enumerate(zip(rows, rows[1:]), 1):
        if int(prev[5+10*slot]) != expected_action or int(prev[3+10*other]) != 1:
            continue
        for side in range(2):
            geo.install_player(prev, side)
        g.write(0x12d2698, 0, 4)
        for pair in (OBJECTS, OBJECTS[::-1]):
            g.run(0x1536e8, pair, limit=50000)
        g.run(0x1544a0, limit=50000)
        for rank in range(g.read(0x12d2698, 4)):
            event = QUEUE + 108 * rank
            if g.read(event, 4) != 7 or g.read(event+0x40, 4) != OBJECTS[other]:
                continue
            assert g.run(0x155850, [event])[0] == 0
            g.run(0x155a88, [event, 1], limit=400000)
            a = ACTORS + slot * 0xf2c
            req = g.read(a+0x190, 4)
            flags = g.read(a+0x23c, 4) & 0x06000000
            damage = g.read(a+0xa38, 4)
            assert flags == (int(now[28+26*slot]) & 0x06000000)
            assert int(prev[9+10*slot]) - int(now[9+10*slot]) == damage > 0
            if case == 'armor-active':
                assert req == 0xffffffff and flags == 0x04000000
                assert now[3+10*slot:6+10*slot] == ['1', '21', '264']
                assert any(int(r[10+10*slot]) for r in rows[i:])
            else:
                assert flags == 0 and req & 0xffff == 2
                assert int(now[3+10*slot]) == 2 and int(now[4+10*slot]) == req >> 16
            return dict(player=slot+1, case=case, tick=i, interrupted=req != 0xffffffff,
                        original_damage=damage, original_flags=flags, original_request=req)
    raise AssertionError((slot, case, 'missing incoming contact'))

def check_unarmed(slot):
    # Preserve the input tables and remove only the in-hand weapon from the
    # neutral actor. This isolates the selector's armed requirement.
    src = Original(slot)
    flags = src.p.read(src.a + 0x23c, 4) & ~0x1000
    flags244 = src.p.read(src.a + 0x244, 4)
    src.p.write(src.a + 0x23c, flags, 4)
    row = src.frame(768)
    commands = f"reset {slot} {slot} {500 if slot else 120} {120 if slot else 500}\ncombat\n"
    commands += f"posture {flags} {flags244}\npad 768 768\n"
    result = subprocess.run([EXE.parent/'ss6-ground-state-probe', ASSETS], input=commands,
                            text=True, capture_output=True, check=True)
    native = list(map(int, result.stdout.splitlines()[-1].split()[:57]))
    assert (row[0], row[54]) == (native[0], native[54]) == (1, 201)
    return dict(player=slot+1, raw_pad=768, table=1, state=0, action=201)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--one', nargs=2, metavar=('SLOT', 'CASE'))
    args = parser.parse_args()
    assert digest(ELF) == PIN
    if args.one:
        if args.one[1].startswith('armor-'):
            print(check_armor(EXE, int(args.one[0]), args.one[1]))
        else:
            print(check((EXE, int(args.one[0]), args.one[1])))
        return
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / 'match'
        shutil.copy2(EXE, exe)
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases = list(pool.map(check, [(exe, slot, case) for slot, case in product(range(2), CASES)]))
        report = dict(status='passed', elf_sha256=PIN, native_sha256=digest(exe),
                      validator_sha256=digest(Path(__file__)), cases=cases,
                      unarmed_input=[check_unarmed(slot) for slot in range(2)],
                      incoming=[check_armor(exe, side, variant) for side, variant in product(range(2), ('armor-active', 'armor-expired'))],
                      scope='Resource 00, system 0, armed mirror versus. Raw pads for both slots. Original attack input, ACT, fractional clock, callbacks, phase flag and hitstop timers through idle. Original collection, guard decision and impact handler on published live geometry. Original defender state/ACT/clock/callback/timers until exiting reaction, and received damage at impact. Incoming light during 264 and heavy during 265 are compared with original guard and hit handlers.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    for case in cases:
        print(case['player'], case['case'], case['contacts'], case['action_entry'])

if __name__ == '__main__':
    main()
