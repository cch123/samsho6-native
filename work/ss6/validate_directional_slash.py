#!/usr/bin/env python3
"""Haohmaru's down-forward + B command normal, compared with the Japanese ELF."""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_combined_slash import initialize_pools
from validate_dash_motion import ASSETS, ELF, Original, PIN, PROBE, ROOT, digest
from validate_haohmaru_special import ContactOracle

EXE = PROBE.parent/'ss6-match-replay'
REPORT = ROOT/'outputs/ss6-feasibility/directional_slash_validation.json'

def input_boundaries(slot, armed, near):
    advance = (128, 64)[slot]
    x = (240, 288 if near else 500)
    x = x[::-1] if slot else x
    examples = []
    for pad in (32 | 512, advance | 32 | 512):
        src = Original(slot)
        p = src.p
        for obj, value in zip((src.o, src.o+0x1000), x):
            struct.pack_into('<f', p.memory, obj+0x40, value)
        f = p.read(src.a+0x23c, 4)
        if not armed:
            f &= ~0x1000
            p.write(src.a+0x23c, f, 4)
        previous = p.read(src.a+0x244, 4)
        row = src.frame(pad)
        setup = f'reset {slot} {slot} {x[0]} {x[1]}\ncombat\nposture {f} {previous}\npad {pad} {pad}\n'
        result = subprocess.run([PROBE, ASSETS], input=setup, text=True, capture_output=True, check=True)
        native = list(map(int, result.stdout.splitlines()[-1].split()[:57]))
        state, action = row[0], row[54]
        assert (native[0], native[54]) == (state, action)
        if pad & advance:
            assert (state, action) == ((22 << 16) | 1, 239 if armed else 240)
        else:
            assert state == (5 << 16) | 1
            if armed:
                assert action == (193 if near else 194)
        examples.append(dict(pad=pad, state=state >> 16, action=action))
    return dict(player=slot+1, armed=armed, near=near, inputs=examples)

def replay(exe, slot, mode):
    forward = (128, 64)[slot]
    def pair(a, b):
        return (b, a) if slot else (a, b)
    approach = (forward ^ 192) if mode == 'whiff' else forward
    pads = [(500, 0, 0), (66, *pair(approach, 0)), (5, 0, 0)]
    press = 9 if mode == 'hold-direction-first' else 1
    direction = forward | 32
    for i in range(1, 97):
        ours = (direction | 512) if i == press else direction if i < press else 0
        guard = {'stand-block': forward, 'low-block': forward | 32, 'crouch': 32}.get(mode, 0)
        pads.append((1, *pair(ours, guard if 4 <= i <= 35 else 0)))
    data = ''.join(f'{n} {a} {b}\n' for n, a, b in pads)
    result = subprocess.run([exe, ASSETS, '--mode', 'versus', '--whirlwind-fields'], input=data, text=True, capture_output=True, check=True)
    return [r.split() for r in result.stdout.splitlines()][2:], [r[1:] for r in pads[2:]], press

def setup_actor(slot):
    src = Original(slot)
    p = src.p
    initialize_pools(p)
    aid = (ASSETS/'aid_00.bin').read_bytes()
    p.memory[0x46a9b0+0x1800:0x46a9b0+0x1800+len(aid)] = aid
    p.write(0x4751b4, p.read(0x4751b0, 4), 4)
    for obj, side in ((src.o, slot), (src.o+0x1000, 1-slot)):
        for off in (0xc, 0xcc):
            p.write(obj+off, side, 4)
    p.write(src.a+0xa30, 200, 4)
    p.write(src.a+0xa34, 200, 4)
    return src

def check(args):
    exe, slot, mode = args
    victim = 1-slot
    rows, pads, press = replay(exe, slot, mode)
    actors = [setup_actor(i) for i in range(2)]
    geo = ContactOracle()
    p = geo.probe
    initialize_pools(p)
    out = p.read(p.read(0x5d1bf8, 4) + 8, 4)
    for offset in (0, 16):
        p.write(out+offset, 0x19e0000, 4)
    instructions = 0
    def run(pc, *args):
        nonlocal instructions
        v, n = p.run(pc, args, limit=700000)
        instructions += n
        return v
    impact = None
    idle = [None, None]
    callbacks = []
    for i, (prev, now) in enumerate(zip(rows, rows[1:]), 1):
        accepted = False
        if int(prev[5+10*slot]) == 239:
            for j in range(2):
                geo.install_player(prev, j)
            p.write(0x12d2698, 0, 4)
            for pair in (OBJECTS, OBJECTS[::-1]):
                run(0x1536e8, *pair)
            run(0x1544a0)
            for k in range(p.read(0x12d2698, 4)):
                e = QUEUE+108*k
                if p.read(e, 4) != 7 or p.read(e+0x40, 4) != OBJECTS[slot]:
                    continue
                if p.read(OBJECTS[slot]+0x104, 4) & 0x06000000:
                    continue
                assert impact is None and p.read(e+0x20, 4) == 11
                guard = run(0x155850, e)
                run(0x155d50 if guard else 0x155a88, e, 1, guard)
                target = ACTORS+0xf2c*victim
                damage = p.read(target+0xa38, 4)
                assert int(prev[9+10*victim])-int(now[9+10*victim]) == damage
                col = 10+10*slot+int(bool(guard))
                assert int(now[col])-int(prev[col]) == 1
                impact = dict(tick=i, defense=guard, damage=damage,
                              reaction=p.read(target+0x192, 2), raw=11)
                # The original collector runs on the published stage geometry.
                # Transfer its requests/timers into the two independent EE actor
                # fixtures before they process this tick's pads and callbacks.
                for side, actor in enumerate(actors):
                    offsets = [0x1b0, 0x1b4]
                    if side == victim:
                        offsets += [0x18c, 0x190, 0x230, 0x23c, 0x244, 0x250, 0x254, 0x258, 0xa38]
                    for off in offsets:
                        actor.p.write(actor.a+off, p.read(ACTORS+side*0xf2c+off, 4), 4)
                accepted = True
                break
        assert accepted == (prev[10+10*slot:12+10*slot] != now[10+10*slot:12+10*slot])
        for side, actor in enumerate(actors):
            if idle[side] is not None or (side == victim and mode == 'whiff'):
                continue
            other = 1-side
            base = 3+10*side
            j = 3+10*other
            s = 23+26*other
            q = actor.p
            for obj, owner in ((actor.o, side), (actor.o+0x1000, other)):
                q.write(obj+0x40, int(prev[23+26*owner]), 4)
            q.write(actor.other+0x194, int(prev[j]) | int(prev[j+1]) << 16, 4)
            q.write(actor.other+0x23c, int(prev[s+5]), 4)
            q.write(actor.other+0x244, int(prev[s+7]), 4)
            q.write(actor.other+0x19a, int(prev[s+10]), 1)
            r = actor.frame(pads[i][side])
            if side == slot and i < press or side == victim and impact is None:
                continue
            c = 88+27*side
            source = [r[0], *r[54:57], *r[12:19], *[q.read(actor.a+off, 4) for off in (0x1b0, 0x1b4)]]
            native = [int(now[base]) | (int(now[base+1]) << 16), *map(int, now[base+2:base+4]), int(now[c+11]),
                      *map(int, now[c:c+7]), *map(int, now[c+8:c+10])]
            assert native == source, (slot, mode, side, i, native, source)
            if side == slot:
                cb = r[12]
                if not callbacks or callbacks[-1][1] != cb:
                    callbacks.append([i, cb])
                if r[54] == 0:
                    idle[side] = i
            elif r[0] & 0xffff == 0:
                idle[side] = i
    assert [c for _, c in callbacks] == [0x16b318, 0x16b368, 0x169a50, 0], (slot, mode, callbacks)
    assert idle[slot] is not None and (impact is None) == (mode == 'whiff')
    if impact:
        assert idle[victim] is not None and impact['tick'] == press+16
        expected = (1, 0, 2) if mode == 'stand-block' else (0, 22, 39 if mode in ('low-block', 'crouch') else 33)
        assert (impact['defense'], impact['damage'], impact['reaction']) == expected
    return dict(player=slot+1, case=mode, press=press, contact=impact, attacker_idle=idle[slot],
                victim_reaction_exit=idle[victim], callbacks=callbacks,
                original_instructions=instructions+sum(actor.instructions for actor in actors))

def main():
    assert digest(ELF) == PIN
    modes = ('hit', 'stand-block', 'low-block', 'crouch', 'whiff', 'hold-direction-first')
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp)/'match'
        shutil.copy2(EXE, exe)
        with ProcessPoolExecutor(max_workers=4) as pool:
            cases = list(pool.map(check, ((exe, s, m) for s, m in product(range(2), modes))))
        choices = [input_boundaries(*x) for x in product(range(2), (False, True), (False, True))]
        report = dict(status='passed', elf_sha256=PIN, native_sha256=digest(exe),
                      validator_sha256=digest(Path(__file__)), cases=cases, inputs=choices,
                      scope='Armed resource 00 mirror, system 0. Two pad slots. Original command acceptance, actor callbacks and clocks through attack recovery/defender reaction exit. Collision and defense run in the original ELF on native positions. Independent actor fixtures compare armed and unarmed 3+B against 2+B at both distances. The Japanese move-list entry reads 特殊技, I3PLIB.')
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print([(r['player'], r['case'], r['contact'], r['attacker_idle']) for r in cases])

if __name__ == '__main__':
    main()
