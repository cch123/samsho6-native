#!/usr/bin/env python3
"""Compare the playable ground-slash inputs with the Japanese PS2 executable."""
import hashlib
import itertools
import json
from pathlib import Path
import struct

from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import fixture
from validate_contact_trial import OUT, PROBE, ROOT, run
from validate_input_features import PADS
from validate_input_lifecycle import Boundary

# Software pad words use this fixture's identity mapping. TrialCommand values
# 5 and 6 are fresh button edges, independent of the persistent posture command.
LIGHT, HEAVY, DOWN = 0x100, 0x400, 0x20
POSTURES = {0: 0, 1: 7, 2: 1, 3: 2, 6: 3, 7: 4}  # normal state -> trial command
# name, previously held, currently held, ordered events delivered to ContactTrial
INPUTS = (
    ('light', 0, LIGHT, (5,)),
    ('heavy', 0, HEAVY, (6,)),
    ('light_then_heavy', 0, LIGHT | HEAVY, (5, 6)),
    ('heavy_then_light', 0, LIGHT | HEAVY, (6, 5)),
    ('neither', 0, 0, ()),
    ('light_held_heavy_pressed', LIGHT, LIGHT | HEAVY, (6,)),
    ('heavy_held_light_pressed', HEAVY, LIGHT | HEAVY, (5,)),
    ('both_held_no_new_edge', LIGHT | HEAVY, LIGHT | HEAVY, ()),
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_attack(player, state, down, distance, previous, held):
    probe, actor, body, battle = fixture(player)
    other = 0x1c00000 + (1 - player) * 0xf2c
    other_body = body + 0x1000
    owner = actor + 0x2c4
    instructions = 0

    def call(pc, *args, stops=()):
        nonlocal instructions
        _, count = probe.run(pc, args, limit=300000, stop_before=stops)
        instructions += count

    def commit():
        call(0x149d08, actor)
        call(0x149918, actor)
        call(0x11d8e0, body)

    probe.write(other, other_body, 4)
    probe.write(other + 4, body + 0x2000, 4)
    probe.write(other + 0x23c, 0x1000, 4)
    probe.write(other + 0xa24, 1 - player, 4)
    probe.write(battle + 0x24c + (1 - player) * 4, other, 4)
    probe.write(other_body + 0xcc, 1 - player, 4)
    probe.write(actor + 4, body + 0x3000, 4)
    probe.write(body + 0x30c4, -1, 4)
    call(0x149008, actor, 0)
    call(0x149918, actor)
    call(0x11d8e0, body)
    call(0x179258, owner, actor + 0x10c)
    probe.write(0x4c38a8, 0, 4)
    probe.write(battle, 4, 4)
    probe.write(battle + 0x144, 120, 4)
    probe.write(body + 0x38, 0x10000000 | player << 19, 4)
    probe.write(actor + 0xa08, player, 4)
    struct.pack_into('<f', probe.memory, body + 0x40, 280 + player * distance)
    struct.pack_into('<f', probe.memory, other_body + 0x40, 280 + (1 - player) * distance)
    struct.pack_into('<8I', probe.memory, 0x4eaac0 + player * 32, *(1 << n for n in range(8, 16)))
    call(0x14ff80, actor + 0x18c, 0, state)
    commit()
    assert probe.read(actor + 0x194, 4) == state << 16

    # The stage publishes distance before this visit's input. Let the original
    # compute it from the two bodies and produce its own near/far state flag.
    probe.put(11, body)
    probe.put(14, other_body)
    probe.put(18, battle)
    distance_end = Boundary(0x142918)
    call(0x1428f4, stops=distance_end)
    assert distance_end.stopped == 0x142918
    call(0x151b00, actor)
    call(0x151eb0, actor)

    pad = PADS + player * 12
    direction = DOWN if down else 0
    probe.write(pad, previous | direction, 4)
    probe.write(pad + 4, previous | direction, 4)
    call(0x179530, owner, player, player, player, 0, 1, 0, -1)
    edges = held & ~previous
    probe.write(pad, held | direction, 4)
    probe.write(pad + 4, edges, 4)
    # Human input route of 1494f0, entered with the caller's permission,
    # actor and opponent registers. All reached callees execute unmodified.
    probe.put(16, 1)
    probe.put(17, actor)
    probe.put(18, other)
    input_end = Boundary(0x149770, 0x1498b0)
    call(0x1495e8, stops=input_end)
    assert input_end.stopped == 0x149770
    sampled = tuple(probe.read(owner + index * 4, 4) for index in (6, 8, 63))
    assert sampled == (bool(edges & LIGHT), bool(edges & HEAVY), down)
    if probe.read(actor + 0x190, 2) != 1:
        return None, instructions
    assert 0x14c2d0 in input_end.seen
    commit()
    return (probe.read(actor + 0x196, 2), probe.read(body + 0x24, 4)), instructions


def playable_attack(player, state, down, distance, events):
    commands = [f'command {player} {POSTURES[state]}', 'tick 1',
                f'place 280 {280 + distance}', f'command {player} {7 if down else 0}']
    commands.extend(f'command {player} {event}' for event in events)
    rows = run([*commands, 'tick 1'])
    base = 3 + player * 11  # probe fields: table, state, body action
    assert rows[1][base:base + 2] == [0, state]
    table, selected, action = map(int, rows[-1][base:base + 3])
    return (selected, action) if table == 1 else None


def check_recovery(player, down):
    # Observe the exact whiff recovery visit in this build. An edge on that
    # visit must expire, even when the callback returns early to change state.
    setup = ['place 160 480', f'command {player} {7 if down else 0}', f'command {player} 6']
    base = 3 + player * 11
    control = run(setup + ['tick 1'] * 160)[len(setup):]
    assert control[0][base] == 1
    recovery = next(i for i, row in enumerate(control) if row[base] == 0)
    events = [f'command {player} 5', f'command {player} 6']
    trial = run([*setup, f'tick {recovery}', *events, *['tick 1'] * 5,
                 f'command {player} 6', 'tick 1'])
    assert trial[-7:-2] == control[recovery:recovery + 5], (player, down, recovery)
    assert trial[-1][base:base + 2] == [1, 9 if down else 8]
    return recovery + 1


def main():
    elf = ROOT / 'work/ss6/extracted/SLPS_255.59'
    fingerprints = {path: digest(path) for path in
                    [elf, PROBE, Path(__file__), Path(__file__).with_name('mips_probe.py'),
                     Path(__file__).with_name('round_entry_oracle.py')]}
    assert fingerprints[elf] == SOURCE_HASH
    count = instructions = 0
    actions = set()
    for player, state, down, distance in itertools.product(range(2), POSTURES, (False, True), (64, 100)):
        # Host event ordering is absent at the original software-pad boundary.
        # Compare both event orders with the same independently computed result.
        original = {}
        for label, previous, held, events in INPUTS:
            if (previous, held) not in original:
                choice, steps = original_attack(player, state, down, distance, previous, held)
                original[previous, held] = choice
                instructions += steps
            expected = original[previous, held]
            actual = playable_attack(player, state, down, distance, events)
            assert actual == expected, (player, state, down, distance, label, actual, expected)
            if actual is not None:
                actions.add(actual[1])
            count += 1
    assert actions == {185, 186, 189, 190, 191, 192, 195, 196}
    recovery = {f'p{player + 1}_{"crouching" if down else "standing"}': check_recovery(player, down)
                for player, down in itertools.product(range(2), (False, True))}
    assert all(digest(path) == value for path, value in fingerprints.items()), 'Inputs changed during validation'
    report = dict(status='passed', playable_cases=count, original_cases=count * 7 // 8,
                  original_instructions_excluding_fixture_construction=instructions, body_actions=sorted(actions),
                  normal_states=list(POSTURES), distances=[64, 100], input_cases=[case[0] for case in INPUTS],
                  native_whiff_recovery_visit=recovery,
                  sha256={path.name: value for path, value in fingerprints.items()},
                  scope='Armed Haohmaru/system0. Both players, both postures. Original human input dispatch through '
                        '14c2d0 followed by actor/body commit. Current playable ContactTrial table/state/action; '
                        'no attack compares refusal only. Four native-only whiff cases test edge expiry. '
                        'Does not exercise hardware controllers, SDL event delivery or the whole original battle frame.')
    text = json.dumps(report, indent=2) + '\n'
    (OUT / 'slash_input_validation.json').write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
