"""Replay repeated blocks in native fights and resolve the same contacts with the JP executable."""
from pathlib import Path
from collections import namedtuple
import json
import struct
import subprocess
import tempfile

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_haohmaru_special import ACTORS, BUILD, OBJECTS, QUEUE, Boundary, ContactOracle

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/ss6-feasibility'
Fighter = namedtuple('Fighter', 'seat character spirit table state state_flags flags23c flags244 timer6 '
                     'controller mode down back low_back life hits guards rage_state rage_amount sword sword_max flags248')
Result = namedtuple('Result', 'seat life hits guards table state action delta hitstop slowdown guard_timer')
# Fighter IDs, spirits, enabled CPU bitmask, human pad pattern and contact tick.
# Each input stream begins at round entry with full health and no prior commands.
CASES = (
    (0, 2, 5, 1, 3, 5, 1350),
    (0, 3, 1, 4, 3, 1, 11287),
    (0, 3, 2, 5, 3, 2, 2062),
    (0, 3, 3, 0, 2, 3, 10837),
    (0, 3, 4, 1, 3, 4, 2062),
    (1, 2, 1, 4, 3, 1, 8458),
    (2, 0, 2, 4, 3, 2, 11405),
    (3, 2, 0, 5, 1, 0, 7551),
    (3, 2, 3, 2, 1, 3, 2679),
)


def compare(case, rows):
    p = ContactOracle().probe
    fighters, after, objects = {}, {}, []
    for row in rows.splitlines():
        kind, *values = row.split()
        data = list(map(int, values))
        if kind == 'fighter':
            fighter = Fighter(*data)
            fighters[fighter.seat] = fighter
        elif kind == 'object':
            objects.append(data)
        elif kind == 'after':
            result = Result(*data)
            after[result.seat] = result
        else:
            raise ValueError(row)
    instructions = 0

    def original(fn, *args, **options):
        nonlocal instructions
        value, count = p.run(fn, args, limit=300000, **options)
        instructions += count
        return value

    for side, f in fighters.items():
        a = ACTORS + side * 0xf2c
        for off, val in [(0, OBJECTS[side]), (0xa24, side), (0xa10, f.character), (0x114, f.character),
                         (0xa14, f.character), (0x10c, f.spirit), (0x23c, f.flags23c), (0x244, f.flags244),
                         (0x1c8, f.timer6), (0xa20, f.controller), (0xc8, f.mode), (0x3c0, f.down),
                         (0x39c, f.back), (0x398, f.low_back), (0xa30, f.life), (0xa34, 200),
                         (0x120, f.rage_state), (0x124, f.rage_amount), (0x134, f.sword),
                         (0x138, f.sword_max), (0x248, f.flags248)]:
            p.write(a + off, val, 4)
        p.write(a + 0x194, f.table, 2)
        p.write(a + 0x196, f.state, 2)
        p.write(a + 0x19a, f.state_flags, 1)
    original(0x153440)
    for i, obj in enumerate(objects):
        kind, slot, owner, char, profile, descriptor, act, step, facing, flags, flags2, x, y = obj
        at = OBJECTS[slot] if kind < 2 else 0x1e04000 + i * 0x1000
        aid, records, jdg = [(ASSETS / f'{name}_{char:02}.bin').read_bytes() for name in ('aid', 'act', 'jdg')]
        frame = (struct.unpack_from('<h', aid, 2 * act)[0] + step) * 60
        refs, bank = 0x17a0000 + 32 * i, 0x1600000 + 0x40000 * slot
        assert len(jdg) <= 0x40000
        p.memory[bank:bank + len(jdg)] = jdg
        p.write(0x4751e0 + slot * 4, bank, 4)
        p.memory[refs:refs + 16] = records[frame + 14:frame + 30]
        judgment = struct.unpack_from('<H', records, frame + 30)[0]
        for off, val in [(0xcc, kind), (0xc, slot), (0x10, owner), (0x14, char), (0x18, profile),
                         (0xd0, descriptor), (0x24, act), (0x28, step), (0x38, facing), (0x104, flags),
                         (0x108, flags2), (0x40, x), (0x44, y), (0xbc, refs)]:
            p.write(at + off, val, 4)
        p.write(at + 0xb8, judgment, 2)
        p.write(at + 0xba, judgment & 7, 1)
        original(0x153450, at)
    addresses = [p.read(0x12d2410 + 4*i, 4) for i in range(p.read(0x12d2408, 4))]
    for a in addresses:
        for b in addresses:
            if a != b:
                original(0x1536e8, a, b)
    original(0x1544a0)
    attacks = [side for side, f in fighters.items() if after[side].guards == f.guards + 1]
    assert len(attacks) == 1, (case, attacks)
    source, target = attacks[0], attacks[0] ^ 1
    f, actor = fighters[target], ACTORS + target * 0xf2c
    for index in range(p.read(0x12d2698, 4)):
        event = QUEUE + index * 108
        obj = p.read(event + 0x40, 4)
        if (p.read(event, 4) == 7 and p.read(event + 0x68, 4) == OBJECTS[target]
                and p.read(obj + 0x10, 4) == source and not p.read(obj + 0x104, 4) & 0x06000000):
            break
    else:
        raise AssertionError(('missing original contact', case))
    assert f.table == 2 and 0 <= f.state <= 5 and (f.controller, f.mode) == (1, 35)
    defense = original(0x155850, event)
    p.write(actor + 0xa20, 0, 4)
    human = original(0x155850, event)
    p.write(actor + 0xa20, f.controller, 4)
    assert {defense, human} == {1, 2}, (case, f, defense, human)
    boundary = Boundary(0x155e90)  # Original chip damage, before the hit spark.
    original(0x155d50, event, 0, defense, stop_before=boundary)
    assert boundary.stopped == 0x155e90
    original(0x14d5a0, actor, obj, defense, p.read(event + 12, 4))
    reaction = p.read(actor + 0x192, 2)
    hp = f.life - p.read(actor + 0xa38, 4)
    pose = (292 if defense == 2 else 288) + int(not f.flags23c & 0x1000)
    result = after[target]
    assert (result.life, result.table, result.state, result.action) == (hp, 2, reaction, pose), (case, result)
    # Contacts precede the fighter's timer visit. Crouch block adds two ticks
    # before that visit, and a half-speed visit can leave a fractional balance.
    p.write(actor + 0x1ac, result.delta, 4)
    original(0x151eb0, actor)
    timers = tuple(p.read(actor + 0x1b0 + 4*n, 4) for n in (0, 1, 32))
    assert (result.hitstop, result.slowdown, result.guard_timer) == timers, (case, result, timers)
    return dict(fighters=case[:2], spirits=case[2:4], cpu_mask=case[4], tick=case[-1], defender=target+1,
                source_kind=p.read(obj+0xcc, 4), source_act=p.read(obj+0x24, 4), original_guard=defense,
                human_guard_at_same_input=human, native_guard_act=pose, remaining_hp=hp, timers_after_contact=timers,
                original_instructions=instructions)


def main():
    assert digest(ELF) == PIN
    lib = BUILD / 'libss6-runtime.a'
    with tempfile.TemporaryDirectory() as folder:
        exe = Path(folder) / 'guard'
        subprocess.run(['c++', '-std=c++20', '-O2', '-I', ROOT/'src', HERE/'cpu_guard_followup_trace.cpp',
                        lib, '-o', exe], check=True)
        inputs = ''.join(' '.join(map(str, case)) + '\n' for case in CASES)
        raw = subprocess.check_output([exe, ASSETS], input=inputs, text=True)
    blocks = raw.split('end\n')
    assert blocks.pop() == ''
    cases = [compare(case, rows) for case, rows in zip(CASES, blocks, strict=True)]
    assert {r['original_guard'] for r in cases} == {1, 2}
    assert {r['defender'] for r in cases} == {1, 2} and {0, 2} <= {r['source_kind'] for r in cases}
    report = dict(passed=True, original_sha256=PIN, runtime_sha256=digest(lib), cases=cases,
                  scope='Pad-only native VS and autonomous fights. PS2 registration, geometry, guard height, chip-damage prefix and guard-reaction request on the pre-contact poses. CPU and human guard choices compared on identical input.')
    (OUT/'cpu-guard-followups.json').write_text(json.dumps(report, indent=2)+'\n')
    print(len(cases), 'follow-up blocks, both seats, standing and crouching, body and projectile impacts')


if __name__ == '__main__':
    main()

