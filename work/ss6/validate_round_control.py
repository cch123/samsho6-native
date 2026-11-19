#!/usr/bin/env python3
"""Actor-facing round stages against whole original functions, including skip gates."""
import hashlib
import argparse
import itertools
import json
import random
import struct
import subprocess
from collections import Counter
from pathlib import Path
from extract_collision_tables import SOURCE_HASH
from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT/'work/ss6/build-native/ss6-round-control-probe'
FUNCTIONS = [0x143798, 0x1438f0, 0x1441e0, 0x144360, 0x144570, 0x143390,
             0x14375c, 0x144458, 0x143524, 0x1b4d90, 0x1b4e88, 0x1b4f78,
             0x144e10, 0x143b88, 0x143344, 0x143320, 0x143430, 0x1435d8, 0x144950]


def main():
    options = argparse.ArgumentParser()
    options.add_argument('--presentation', action='store_true')
    options.add_argument('--combat', action='store_true')
    options.add_argument('--dispatcher', action='store_true')
    opts = options.parse_args()
    presentation, combat, dispatcher = opts.presentation, opts.combat, opts.dispatcher
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    p = Probe(raw)
    buffered_stdout(p)
    b, a0, o0 = 0x1b00000, 0x1c00000, 0x1e00000
    p.write(0x4d3d00, b, 4)
    p.write(0x4d3d08, a0, 4)
    #This option makes the original channel-stop callees return normally.
    #No logging/audio callee is patched or skipped by the oracle.
    p.write(0x345188, 0, 4)
    for at in range(0x46a908, 0x46a944, 4):
        p.write(at, 0, 4)
    rng = random.Random(0x143798)
    commands, expected, labels = [], [], []
    rejections = []
    counts = Counter()
    instructions = 0
    event = force = place_x = place_y = 0
    bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]

    def words(at, values):
        p.memory[at:at+len(values)*4] = struct.pack(f'<{len(values)}I', *[v & 0xffffffff for v in values])

    def read(at, size=4, signed_value=False):
        value = p.read(at, size)
        return signed(value, size*8) if signed_value else value

    def snapshot(op, predicate=0):
        out = [read(b+off, signed_value=True) for off in [0, 4, 12, 0x18]]+[read(b+0x138)]
        out += [read(b+0x114+j*4, signed_value=True) for j in range(7)]
        count = read(b+0x80)
        out.append(count)
        for j in range(count):
            out += [read(b+0x84+j*8, 1), read(b+0x88+j*8, signed_value=True)]
        for i in range(2):
            a, o = a0+i*0xf2c, o0+i*0x1000
            out += [read(a+off, 1 if off == 0x24c else 4) for off in [0x23c, 0x244, 0x24c, 0x194, 0x18c]]
            out += [read(a+off, 2, True) for off in [0x190, 0x192]]
            out += [read(a+0xa3c, signed_value=True), read(a+0x2f0)]
            out += [read(a+0x1b0+j*4, signed_value=True) for j in range(35)]
            out += [read(o+off, 2 if off == 0xfe else 4) for off in [0x24, 0x104, 0x108, 0xfe, 0x40, 0x44]]
            out += [read(o+off, signed_value=True) for off in [0x4c, 0x50, 0x54, 0x58, 0x5c, 0x60]]
        if op >= 6:
            out += [read(0x132c1e0, signed_value=True), read(0x132c1e4, signed_value=True),
                    read(0x132c1e8), read(0x132c1f8, signed_value=True), read(0x132c0e0)]
            out += [read(at) for at in [0x132c0e8, 0x132c0ec, 0x132c0f0, 0x132c210]]
            out += [read(at, signed_value=True) for at in [0x132c0f4, 0x132c0f8, 0x132c0fc]]
            out += [read(0x443150, signed_value=True), read(0x3d2e80), read(read(0x5d1bf8)+0xa8, 8), read(0x3d2e78)]
            out += [read(a0+i*0xf2c+0xa30, signed_value=True) for i in range(2)]
            out += [read(o0+0x40), read(o0+0x1040), (read(o0+0x38)>>19)&1, predicate]
        if op >= 12:
            out += [read(b+8, signed_value=True), read(b+0x13c, signed_value=True), read(0x4c3828)]
            for i in range(2):out += [read(b+0x254+i*0x108+off, signed_value=True) for off in [0x10, 0x14, 0x18]]
        if op >= 15:
            out += [read(b+off, signed_value=True) for off in [0x104, 0x108, 0x10c, 0x110]]
            out += [read(at) for at in [0x4452ac, 0x4c3834, 0x4c3820]]
            owner = read(b+0x30)
            assert owner in (0, 0x3d2e88), hex(owner)
            out += [int(bool(owner)), read(b+0x1c, signed_value=True)]
            for i in range(2):out += [read(b+0x254+i*0x108+off, signed_value=True) for off in [0x28, 0x2c]]
        return out

    def execute(op, command, label):
        nonlocal instructions
        args, stop, label_prefix = [b], (), 'whole'
        sp, end = 0x1fff000, 0x1ffff00
        if op in [6, 7]:
            #Explicit post-console tails. Supply the frame/registers left by
            #the original prologue; never patch/skip a callee and resume it.
            words(sp, [a0, a0+0xf2c])
            words(sp+0x10, [o0, o0+0x1000])
            words(sp+0x20, [b+0x254, b+0x35c])
            p.registers[16] = b if op == 6 else sp
            p.registers[17] = 0
            p.registers[18] = b
            p.write(sp+(0x38 if op == 6 else 0x48), end, 8)
            label_prefix = 'tail'
        elif op == 8:
            stop, label_prefix = (0x143550,), 'slice'
        elif op == 9:
            args = [event, force]
        elif op == 10:
            p.floats[12], p.floats[13], p.floats[14] = place_x, place_y, bits(-123)
        elif op == 14:
            p.registers[2] = b
            stop, label_prefix = (0x14337c,), 'slice'
        entry_state = read(b, signed_value=True)
        if op == 16 and entry_state in [1, 8] and read(b+4, signed_value=True) != entry_state:
            #The original dispatcher prefix ends at the entry callee. Its
            #console-free business tail and publication footer are separate
            #evidence; this never claims a whole console-dependent entry.
            _, count = p.run(0x143430, [b], stop_before=(0x143708 if entry_state == 1 else 0x1443f0,), limit=250000)
            instructions += count;counts['entry_prefix143430'] += 1
            words(sp, [a0, a0+0xf2c]);words(sp+0x10, [o0, o0+0x1000]);words(sp+0x20, [b+0x254, b+0x35c])
            p.registers[16] = b if entry_state == 1 else sp
            p.registers[17] = 0;p.registers[18] = b
            p.write(sp+(0x38 if entry_state == 1 else 0x48), end, 8)
            tail = 0x14375c if entry_state == 1 else 0x144458
            _, count = p.run(tail, limit=250000)
            instructions += count;counts[f'entry_tail{tail:06x}'] += 1
            p.registers[16] = b;p.write(sp+0x18, end, 8)
            value, count = p.run(0x143560, limit=250000)
            instructions += count;counts['entry_footer143560'] += 1
        else:
            value, count = p.run(FUNCTIONS[op], args, stop_before=stop, limit=250000)
            instructions += count
            counts[f'{label_prefix}{FUNCTIONS[op]:06x}'] += 1
        commands.append(command)
        expected.append(snapshot(op, value if op in [11, 16] else 0))
        labels.append(label)

    def fixture(op, *, index=0, ready=0, pressed=0, mode=3, submode=0, winner=0,
                draw=False, dead=2, wins=(0, 0), current=8, lock=-1, queue=3,
                event_id=0, event_force=0, old_state=0, old_flags=0, pending=0,
                event_x=320, positions=(280, 360), mirror=0, life=(200, 0),
                random_mode=0, placement=(320, 0), time_option=3, timer0=256, field08=0,
                postures=(0x1000, 0x1000), trigger_timers=(0, 0), previous_life=(200, 200),
                previous_posture=(0, 0), last_hit=(0, 0), items=0,
                request_state=4, current_state=4, interaction=0, old_interaction=0,
                timer_flags=0, timer_lock=0, raw_delta=256, delta=256, timer1=0, timer2=0,
                profile_busy=0, continue_word=0, final_gate=0, owner_active=0, expected_error=None):
        nonlocal event, force, place_x, place_y
        event_pending = pending
        seed = rng.getrandbits(32)
        flags = rng.getrandbits(32)
        request = rng.randrange(11)
        for off, value in [(0, request), (4, current), (12, lock), (0x18, index),
                           (0x20, int(draw)), (0x24, winner), (0x138, flags), (0x80, int(queue >= 0))]:
            p.write(b+off, value, 4)
        if queue >= 0:
            p.write(b+0x84, queue, 1)
            p.write(b+0x88, 17 << (8 if queue >= 3 else 0), 4)
        words(b+0x114, [seed+j*17 for j in range(7)])
        p.write(0x4c3808, mode, 4)
        p.write(0x4c38a8, submode, 4)
        values = [seed, op, request, current, lock, index, flags, mode, submode,
                  winner, int(draw), wins[0], 2, wins[1], 2, queue]
        for i in range(2):
            a, o, stats = a0+i*0xf2c, o0+i*0x1000, b+0x254+i*0x108
            p.write(b+0x24c+i*4, a, 4)
            p.write(a, o, 4)
            p.write(a+0xa24, i, 4)
            p.write(stats+0x28, wins[i], 4)
            p.write(stats+0x2c, 2, 4)
            posture = 0x1000 | (0x80 if dead & (1 << i) else 0)
            gates = (rng.getrandbits(32) & ~0x40000000) | (0x40000000 if ready & (1 << i) else 0)
            input_lock = rng.randrange(256)
            force = rng.getrandbits(32)
            table, state, action = rng.choice([-1, 0, 1, 2]), rng.randrange(-1, 65), rng.choice([-1, 0, 492])
            feature = rng.choice([1, 0x80000000, 0xffffffff]) if pressed & (1 << i) else 0
            f104, f108, pending = rng.getrandbits(32), rng.getrandbits(32), rng.randrange(65536)
            for off, v in [(0x23c, posture), (0x244, gates), (0x194, 39 << 16), (0x18c, force),
                           (0xa3c, action), (0x2f0, feature)]:
                p.write(a+off, v, 4)
            p.write(a+0x24c, input_lock, 1)
            p.write(a+0x190, table, 2)
            p.write(a+0x192, state, 2)
            words(a+0x1b0, [seed+i*43+j*19 for j in range(35)])
            for off, v in [(0x24, 189+i), (0x104, f104), (0x108, f108),
                           (0x40, struct.unpack('<I', struct.pack('<f', 280+i*80))[0]), (0x44, 0x40e00000)]:
                p.write(o+off, v, 4)
            p.write(o+0xfe, pending, 2)
            words(o+0x4c, [3, -7, 11, -13, 17, -19])
            values += [posture, gates, input_lock, force, table, state, action, feature, f104, f108, pending]
        if op >= 6:
            event, force = event_id, event_force
            place_x, place_y = map(bits, placement)
            #The body pending word above is unrelated to the stage queue.
            old_request, object_flags = rng.randrange(-2, 4), rng.getrandbits(32)
            lib_seed = rng.getrandbits(64)
            final_pending = rng.getrandbits(32)
            extra = [old_state, old_request, old_flags, event_pending, object_flags,
                     bits(event_x), bits(11.5), bits(-27), bits(97.5), 3, -7, 11,
                     random_mode, seed, lib_seed, final_pending, *life,
                     *map(bits, positions), mirror, event, force, place_x, place_y]
            for at, v in zip([0x132c1e0, 0x132c1e4, 0x132c1e8, 0x132c1f8, 0x132c0e0,
                              0x132c0e8, 0x132c0ec, 0x132c0f0, 0x132c210, 0x132c0f4, 0x132c0f8, 0x132c0fc], extra[:12]):
                p.write(at, v, 4)
            p.write(0x443150, random_mode, 4)
            p.write(0x3d2e80, seed, 4)
            p.write(read(0x5d1bf8)+0xa8, lib_seed, 8)
            p.write(0x3d2e78, final_pending, 4)
            for i in range(2):
                p.write(a0+i*0xf2c+0xa30, life[i], 4)
                p.write(o0+i*0x1000+0x40, bits(positions[i]), 4)
            p.write(o0+0x38, mirror << 19, 4)
            values += extra
        if op >= 12:
            p.write(b+8, field08, 4);p.write(b+0x13c, time_option, 4);p.write(b+0x114, timer0, 4)
            p.write(0x4c3828, items, 4);p.write(0x123a0c0, 0, 1)
            values += [field08, time_option, items, timer0]
            for i in range(2):
                p.write(a0+i*0xf2c+0x23c, postures[i], 4)
                p.write(a0+i*0xf2c+0x1e8, trigger_timers[i], 4)
                words(b+0x254+i*0x108+0x10, [previous_life[i], previous_posture[i], last_hit[i]])
                values += [postures[i], trigger_timers[i], previous_life[i], previous_posture[i], last_hit[i]]
        if op >= 15:
            extra = [request_state, current_state, interaction, old_interaction,
                     timer_flags, timer_lock, raw_delta, delta, timer1, timer2,
                     profile_busy, continue_word, final_gate, owner_active]
            for off, v in zip([0, 4, 8, 12, 0x104, 0x108, 0x10c, 0x110, 0x118, 0x11c], extra[:10]):
                p.write(b+off, v, 4)
            for at, v in [(0x4452ac, profile_busy), (0x4c3834, continue_word), (0x4c3820, final_gate),
                          (b+0x30, 0x3d2e88 if owner_active else 0), (0x3d2e88, 1), (b+0x1c, -1)]:
                p.write(at, v, 4)
            for i in range(2):p.write(o0+i*0x1000+0xc0, 0, 4)
            values += extra
        command = 'fixture '+' '.join(map(str, values))
        if expected_error is not None:
            rejections.append((command, expected_error))
            return
        execute(op, command, values[:16])

    if dispatcher:
        p.finite_model = True
        #Whole dispatchers with every reached callee executed normally. The
        #console-dependent entries and active weapon-lock branch are outside
        #these cases; positive delay still visits interaction/publication.
        for state, delay_value, step_delta, old_interaction in itertools.product(
                range(11), [1, 255, 256, 257], [0, 128, 256, 512], [-1, 0, 1, 17]):
            fixture(15, request_state=state, current_state=-1, timer2=delay_value, delta=step_delta,
                    old_interaction=old_interaction, timer1=0x7fffffff,
                    life=(197, 3), previous_life=(200, 200), postures=(0x1008, 0x1080))
        for op, state, delay_value, step_delta, flags in itertools.product(
                [15, 17], [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, -0x80000000],
                [-256, 0], [0, 128, 256, 512], [0, 1, 2, 3]):
            fixture(op, request_state=state, current_state=state, timer2=delay_value, delta=step_delta,
                    timer_flags=flags, timer1=0x7fffff80, profile_busy=1, continue_word=19,
                    owner_active=int(state==3), ready=0, pressed=0, queue=3,
                    postures=(0x1080, 0x1088), life=(0, 0))
        for op, state, interaction, old_interaction in itertools.product(
                [15, 16, 17], [2, 7, 10, -1, 11, 0x7fffffff, -0x80000000],
                [-1, 0, 1, 17], [-1, 0, 1, 17]):
            fixture(op, request_state=state, current_state=4, interaction=interaction,
                    old_interaction=old_interaction, timer1=1234, final_gate=7, winner=-1, draw=True,
                    postures=(0x1080, 0x1080))
        for state, ready, pressed, index, complete in itertools.product(
                [1, 8], range(4), range(4), [0, 1], [False, True]):
            fixture(15, request_state=state, current_state=state, ready=ready, pressed=pressed,
                    index=index, winner=0, wins=(2, 0) if complete else (0, 0),
                    postures=(0x1000, 0x1080), timer1=100)
            #A request can change without entry/publication until timer2
            #expires. These visits exercise the real old-value delay gate.
            if read(b+0x11c, signed_value=True)>0:
                for _ in range(3):execute(15, 'step 15', 'persistent delayed transition')
        for busy, delta_value, timer1_value in itertools.product(
                [0, 1, 0x80000000], [0, 256, -256], [0, 0x7fffffff, -0x80000000]):
            fixture(15, request_state=6, current_state=6, profile_busy=busy, continue_word=17,
                    delta=delta_value, timer1=timer1_value, postures=(0x1080, 0x1080))
            execute(15, 'step 15', 'profile resume must not reenter ending')
        for new, old in itertools.product([-0x80000000, -1, 0, 2, 17, 0x7fffffff],
                                         [-0x80000000, -1, 0, 1, 2, 17, 0x7fffffff]):
            fixture(18, interaction=new, old_interaction=old)
            execute(18, 'step 18', 'unchanged inactive interaction')
        for state, index, winner, hp, final in itertools.product([1, 8], [0, 1], [-1, 0, 1], [100, 200], [False, True]):
            fixture(16, request_state=state, current_state=7, index=index, winner=winner, draw=winner==-1,
                    life=(hp, hp), wins=(2, 0) if final else (0, 0), timer1=1234,
                    interaction=17, old_interaction=1, old_flags=0x100)
            execute(16, 'step 16', 'same requested/current must not repeat entry')
        #Unsupported dependencies must not look like successful state
        #transitions. These native rejection checks have no oracle claim.
        fixture(16, request_state=9, current_state=8, expected_error='1447c0')
        fixture(17, request_state=9, current_state=9, expected_error='144848')
        # The complete submode-0 result and submode-2 overlay now have
        # separate original-code comparisons. Exercise the dispatch into
        # the latter here as well, with an initialized PS2 menu task pool.
        p.run(0x112570)
        fixture(16, request_state=10, current_state=8, final_gate=1, submode=2)
    elif combat:
        p.finite_model = True
        event_flags = [read(0x573430+i*4) for i in range(15)]
        #Priority: each player's delayed trigger precedes THEIR HP change;
        #player0 damage wins over player1 trigger. Refusal still consumes2000.
        for op, old_state, stage_pending, variant in itertools.product([12, 13], range(15), [0, 14], range(12)):
            posture = [0x1000, 0x1000]
            life = [200, 200]
            times = [0, 0]
            prior = [0, 0]
            if variant < 4:posture[variant % 2] |= 0x2000;times[variant % 2] = 0 if variant < 2 else 1
            elif variant < 8:life[variant % 2] = 100
            elif variant < 10:posture = [0x1008, 0x1008] if variant == 8 else [0x1008, 0x1000]
            elif variant == 10:posture[1] |= 0x2000;life[0] = 50
            else:prior = [1, 1]
            fixture(op, old_state=old_state, old_flags=event_flags[old_state], pending=stage_pending,
                    postures=posture, trigger_timers=times, previous_posture=prior, life=life,
                    last_hit=(variant % 2, variant // 2), mirror=variant % 2,
                    event_x=320 if variant % 3 else 340)
            execute(14, 'step 14', 'publish previous player state')
            execute(op, f'step {op}', 'repeat after publication')
        for option, field08, timer, dead in itertools.product([0, 1, 2, 3, -1], [-1, 0, 1, 2], [-256, 0, 1, 256], range(4)):
            posture = [0x1000 | (0x80 if dead & (1 << i) else 0) for i in range(2)]
            fixture(13, time_option=option, field08=field08, timer0=timer, postures=posture,
                    life=(0 if dead & 1 else 200, 0 if dead & 2 else 200),
                    old_state=0, old_flags=0x10, items=1 if option != 3 and field08 != 1 and timer == 0 else 0)
    elif not presentation:
        for index, ready, pressed in itertools.product([0, 1, -1, 0x7fffffff], range(4), range(4)):
            fixture(0, index=index, ready=ready, pressed=pressed)
            execute(0, 'step 0', 'repeat introduction')
            if read(b) == 2:
                execute(1, 'step 1', 'actual skipped-intro continuation')
        for winner, draw, dead in itertools.product([-1, 0, 1], [False, True], range(4)):
            fixture(2, winner=winner, draw=draw, dead=dead)
            execute(3, 'step 3', 'camera after entry')
        for queue in [-1, 0, 2, 3]:
            fixture(3, queue=queue)
        for mode, pressed, ready, winner, submode in itertools.product([0, 1, 2, 3, 11, 12], range(4), range(4), [-1, 0, 1], [0, 5, 6]):
            wins = rng.choice([(0, 0), (2, 0), (0, 2), (2, 2)])
            fixture(4, mode=mode, pressed=pressed, ready=ready, winner=winner,
                    submode=submode, wins=wins, draw=winner == -1,
                    index=rng.choice([0, 7, 0x7fffffff, -0x80000000]))
        for state, lock in itertools.product(range(-1, 12), [-1, 0, 1, 0x7fffffff]):
            fixture(5, current=state, lock=lock)
    else:
        #Use the declared finite model for the source's rounded mean/subtract;
        #this does not assert EE hardware low-bit equivalence.
        p.finite_model = True
        flags = [read(0x573430+i*4) for i in range(15)]
        for old_state, event_id, event_force, stage_pending in itertools.product(range(15), range(15), [0, 1], [0, 14]):
            fixture(9, old_state=old_state, old_flags=flags[old_state], pending=stage_pending,
                    event_id=event_id, event_force=event_force, event_x=rng.choice([299.5, 300, 301, 319.5, 320, 339, 340, 340.5]),
                    mirror=rng.randrange(2))
        stage_pending = 0
        for positions, offset, mirror in itertools.product([(280, 360), (-321.5, 300), (0.25, 1.25), (-1.25, -0.25)],
                                                           [-20.5, -20, -19.5, -0.5, 0, 0.5, 19.5, 20, 20.5], [0, 1]):
            fixture(11, positions=positions, event_x=int(sum(positions)/2)+offset, mirror=mirror)
        for placement in itertools.product([-320.5, -0.0, 0, 320, 1e6], [-91.5, 0, 27.25]):
            fixture(10, placement=placement)
        for index, old_flags, stage_pending in itertools.product([0, 1, -1], [0, 0x20, 0x40, 0x100], [0, 14]):
            fixture(8, index=index, old_flags=old_flags, pending=stage_pending)
            execute(6, 'step 6', 'stage reset then introduction entry')
        for winner, hp, random_mode, final, old_flags, stage_pending in itertools.product([-1, 0, 1], [0, 100, 199, 200, 250], [0, 1],
                                                                                        [False, True], [0, 0x100], [0, 14]):
            life = [0, 0]
            if winner != -1:
                life[winner] = hp
            fixture(7, winner=winner, draw=winner == -1, life=life, random_mode=random_mode,
                    dead=rng.randrange(4), wins=(2, 0) if final else (0, 0), old_flags=old_flags, pending=stage_pending)
            execute(7, 'step 7', 'persistent victory/RNG continuation')
    result = subprocess.run([str(BINARY), str(ROOT/'work/ss6/extracted/resources')],
                            input='\n'.join(commands)+'\n', text=True, capture_output=True)
    assert result.returncode == 0, (len(result.stdout.splitlines()), result.stderr)
    actual = [list(map(int, line.split())) for line in result.stdout.splitlines()]
    assert len(actual) == len(expected), (len(actual), len(expected))
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, (i, labels[i], len(got), len(want),
                             [(j, x, y) for j, (x, y) in enumerate(zip(got, want)) if x != y][:12])
    for command, message in rejections:
        rejected = subprocess.run([str(BINARY), str(ROOT/'work/ss6/extracted/resources')],
                                  input=command+'\n', text=True, capture_output=True)
        assert rejected.returncode == 1 and message in rejected.stderr and not rejected.stdout, (message, rejected)
    report = dict(status='passed_for_projected_fields', functions=dict(counts),
                  compared_snapshots=len(actual), original_instructions=instructions,
                  elf_sha256=SOURCE_HASH, native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                  scope='Whole143798,1438f0,1441e0,144360,144570,143390 and reached callees. Muted audio option, resource00 body actions. Compare both actors, pending requests/action queue, input skip features, all35 actor timers, body flags/pending/motion, battle requests/flags/round index/all7 timers/camera queue. Covers first/later intro, both skip buttons, readiness early-return order, winner-only/mode-specific skip, draw/match transitions and integer wrap. Separate component, not whole143430/143320 or live SDL integration; normal42/43 are requests only.')
    if presentation:
        report['scope'] = ('Whole1b4d90/1b4f78/1b4e88, post-console tails14375c/144458 and explicit143524..143550 stage-reset slice. '
                           'All reached callees run unchanged; no console/kernel call is patched or resumed. Compare both actors and their body/timer/request fields, '
                           'stage event state/queue/flags/placement/motion/facing, both RNG seeds, final-sound pending bit and battle camera/timers. '
                           'Muted audio option, finite scalar FP model; not full round entry functions, event actor animation/rendering, full frames or live input integration.')
    if combat:
        report['scope'] = ('Whole144e10 and ordinary versus143b88, all reached callees unchanged, plus143344..14337c publication slice. '
                           'Explicit disabled stage-item option except timeout early returns; no item/console/audio callee patched or skipped. '
                           'All15 stage priorities/pending refusal, trigger consumption, player/damage/weapon priority, HP history, '
                           'time-limit exact-zero/field08/no-time-limit gates and both KO bits. Same full actor/body/timer/camera/RNG fields as baseline. '
                           'Separate shared controller component; enabled item branch, whole143320/143430, actor event animations and live match not claimed.')
    if dispatcher:
        report['native_unsupported_branch_checks'] = len(rejections)
        report['scope'] = ('Whole143320/1435d8/143430/144950 for admitted branches with every reached callee unchanged. '
                           'Whole entry coverage: empty2, camera7,10 with explicit nonzero global+18/submodes0/2, unsigned out-of-range. '
                           'Whole update coverage:0..8/10/out-of-range except inactive opening console continuation; profile wait6 includes persistent6->5. '
                           'Positive timer2 delays include all0..10 pending entries and still run interaction/publication. '
                           'Compare both actors/body requests/35 timers, battle7 timers and header, current/request/interaction, HP/posture history, '
                           'stage events, RNG, camera commands, profile-busy/continue/global18, wins and result. '
                           'Muted ordinary mode, finite scalar FP model. Entries1/8 additionally compare explicit143430 prefix,14375c/144458 tail and143560 footer. '
                           'Console-dependent entries0/3/4/5/6 rely on separately validated components, '
                           'not claimed whole here. Active weapon lock has separate evidence; state9 remains outside these cases. Dedicated result and menu suites cover final145628. Full actor/object frames and live SDL are outside this dispatcher suite.')
    name = 'round_dispatcher_validation.json' if dispatcher else 'round_combat_validation.json' if combat else 'round_presentation_validation.json' if presentation else 'round_control_validation.json'
    (ROOT/'outputs/ss6-feasibility'/name).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
