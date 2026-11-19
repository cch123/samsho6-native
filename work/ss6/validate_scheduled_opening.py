#!/usr/bin/env python3
"""Shared opening pools/owners and controller tails against original code.

Textures and buffered libc output are ordinary fixture data. Every reached
callee executes unchanged. Controller console/kernel diagnostics are outside
the explicitly identified fragments, never patched or silently skipped.
"""
import argparse
import collections
import hashlib
import itertools
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe, signed
from extract_collision_tables import SOURCE_HASH
from round_entry_oracle import buffered_stdout
from validate_object_pools import pointer, handle, digest, TASKS, OBJECTS

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'work/ss6/extracted/resources'
BINARY = ROOT/'work/ss6/build-native/ss6-scheduled-opening-probe'
OWNERS, DESCRIPTORS = 0x3d2e88, 0x4a3e30
B, A, O = 0x1b00000, 0x1c00000, 0x1e00000
tp = lambda h: pointer(h, TASKS, 52)
op = lambda h: pointer(h, OBJECTS, 320)
hp = lambda h: pointer(h, OWNERS, 8)
th = lambda a: handle(a, TASKS, 52)
oh = lambda a: handle(a, OBJECTS, 320)
hh = lambda a: handle(a, OWNERS, 8)
bits = lambda v: struct.unpack('<I', struct.pack('<f', v))[0]
DRAW_OFFSETS = [0x28, 0x2c, 0x30, 0x38, 0x40, 0x44, 0x48, 0x70,
                0x4c, 0x50, 0x54, 0x58, 0x5c, 0x60, 0x74, 0x78, 0x7c, 0x8c,
                *range(0x90, 0xb0, 4)]


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--quick', action='store_true')
    args.add_argument('--endings', action='store_true')
    args.add_argument('--ending-control', action='store_true')
    args.add_argument('--ending-entry', action='store_true')
    args.add_argument('--dispatch-entry', action='store_true')
    opts = args.parse_args()
    if opts.dispatch_entry and not opts.ending_entry:args.error('--dispatch-entry requires --ending-entry')
    quick, endings, ending_control = opts.quick, opts.endings or opts.ending_control or opts.ending_entry, opts.ending_control
    ending_projection = entry_projection = False
    entry_mode = opts.ending_entry
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    commands, expected, labels, traces = [], [], [], []
    counts = collections.Counter()
    instructions = draws = 0
    p = None

    def words(at, values):
        values = list(values)
        p.memory[at:at+4*len(values)] = struct.pack(f'<{len(values)}I', *[v & 0xffffffff for v in values])

    def readwords(at, count):
        return list(struct.unpack_from(f'<{count}I', p.memory, at))

    def run(pc, arguments=(), stop=(), kind='whole'):
        nonlocal instructions
        result, n = p.run(pc, arguments, stop_before=stop, limit=250000)
        instructions += n
        counts[f'{kind}{pc:06x}'] += 1
        return result & 0xffffffff

    def fixture(seed):
        nonlocal p, ending_projection, entry_projection
        ending_projection = entry_projection = False
        p = Probe(raw, finite_model=True)
        buffered_stdout(p)
        for bank, name in [(5, 'Display.bin'), (6, 'Display2.bin'), (7, 'Display3.bin')]:
            data = (ASSETS/name).read_bytes()
            base = 0x4a4810+(bank-1)*0x3da0
            p.memory[base:base+len(data)] = data
        words(OWNERS, [0]*512)
        words(OBJECTS, [0]*(256*80))
        words(0x1232440, [0]*258)
        words(0x3d3698, [0]*257)
        run(0x1123a8)
        run(0x112570)
        run(0x11e290)
        words(0x4c3510, range(1, 33))
        words(0x4c3658, ((seed+i) % 4 for i in range(44)))
        words(0x439a48, (seed+i*17 for i in range(72)))
        p.write(0x345188, 0, 4)
        p.write(0x123a0c0, 0, 1)  #ordinary match mode,1393a0 returns false
        words(B, [0]*300)
        words(B, [3, 3])
        if opts.dispatch_entry:
            words(B+8, [-1, -1]);words(B+0x104, [0, 0, 256, 256])
        p.write(0x5850e0, seed, 4)
        p.write(0x4d3d00, B, 4)
        p.write(0x4d3d08, A, 4)
        for i in range(2):
            p.write(B+0x24c+i*4, A+i*0xf2c, 4)
            p.write(A+i*0xf2c, O+i*0x1000, 4)
            p.write(O+i*0x1000+0x38, 0, 4)
            p.write(O+i*0x1000+0x40, bits(280+i*80), 4)
            p.write(B+0x254+i*0x108+0x2c, 2, 4)
        words(0x132c0a8, [0]*100)
        p.write(0x132c0e8, bits(320), 4)
        p.write(0x4a2250, 0, 4)
        commands.append(f'fixture {seed}')
        if opts.dispatch_entry:commands.append('dispatch-projection')

    def snapshot(result=0):
        tasks = readwords(TASKS, 256*13)
        objects = readwords(OBJECTS, 256*80)
        for i in range(256):
            tasks[i*13+3] = th(tasks[i*13+3])
            tasks[i*13+6] = hh(tasks[i*13+6])
            tasks[i*13+7] = oh(tasks[i*13+7])
            if tasks[i*13+8]:
                assert (tasks[i*13+8]-DESCRIPTORS) % 108 == 0
                tasks[i*13+8] = (tasks[i*13+8]-DESCRIPTORS)//108
            objects[i*80] = oh(objects[i*80])
            objects[i*80+78] = oh(objects[i*80+78])
        row = [result, hh(p.read(B+0x30, 4)), signed(p.read(B, 4), 32),
               signed(p.read(B+4, 4), 32), signed(p.read(B+0x18, 4), 32),
               p.read(0x5850e0, 4), signed(p.read(B+0x118, 4), 32),
               p.read(0x3d3690, 4), p.read(0x3d3688, 4), th(p.read(0x1232844, 4)),
               oh(p.read(0x46a900, 4)), p.read(0x46a904, 4), th(p.read(0x1232840, 4)),
               p.read(0x3d3a98, 4), digest(tasks), digest(objects),
               digest(map(th, readwords(0x1232440, 256))), digest(readwords(0x3d3698, 256)),
               digest(readwords(OWNERS, 512)), digest(readwords(0x439a48, 72)),
               digest(readwords(0x4c3510, 32)), digest(readwords(0x4c3658, 44))]
        row += [signed(p.read(at, 4), 32) for at in [0x132c1e0, 0x132c1e4]]
        row += [p.read(0x132c1e8, 4), signed(p.read(0x132c1f8, 4), 32), p.read(0x132c0e0, 4)]
        row += [p.read(at, 4) for at in [0x132c0e8, 0x132c0ec, 0x132c0f0, 0x132c210]]
        row += [signed(p.read(at, 4), 32) for at in [0x132c0f4, 0x132c0f8, 0x132c0fc]]
        count = p.read(0x4a2250, 4)
        row.append(count)
        for i in range(count):
            o = 0x479250+i*0x148
            assert p.read(o+0x144, 4) == 1
            rec = p.run(0x1233a0, [o])[0]
            row += list(struct.unpack_from('<30H', p.memory, rec))
            row += [p.read(o+offset, 4) for offset in DRAW_OFFSETS]
        if ending_projection:
            row += [signed(p.read(B+0x28, 4), 32)]
            for i in range(2):row += [signed(p.read(B+0x254+i*0x108+off, 4), 32) for off in [0x28, 0x2c]]
            for i in range(2):
                a, o = A+i*0xf2c, O+i*0x1000
                row += [p.read(a+off, 1 if off==0x24c else 4) for off in [0x23c, 0x244, 0x248, 0x24c, 0x194, 0x1a4, 0x18c]]
                row += [p.read(a+0x190, 2), p.read(a+0x192, 2), p.read(a+0xa3c, 4), p.read(a+0x160, 4), p.read(a+0x17c, 4)]
                row += [p.read(o+off, 4) for off in [0x38, 0x104, 0x108, 0xc0, 0x40]]
        if entry_projection:
            row += [p.read(B+0x20,4),signed(p.read(B+0x24,4),32),signed(p.read(B+0x28,4),32),signed(p.read(B+0x2c,4),32)]
            row += [signed(p.read(at,4),32) for at in [0x4c3810,0x4c3830,0x4c3894,0x4c38a8]]
            row += [p.read(at,4) for at in [0x4c3834,0x4c38ac,0x1d00004,0x1239090]]+[p.read(0x43d052,1)]
            row += [signed(p.read(at,4),32) for at in [0x123a0ec,0x123a0e8]]
            row += [signed(p.read(B+0x114+i*4,4),32) for i in range(7)]
            row += [p.read(at,4) for at in [0x46a940,0x1239d84,0x1239d88,0x46a908]]
            row += readwords(0x46a910,12)+[digest(struct.unpack_from('<1024H',p.memory,0x3ebf30))]
            for i in range(2):
                stats=B+0x254+i*0x108
                row += [signed(p.read(stats+off,4),32) for off in [0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x2c,0x34,0x38,0x3c]]
                row += [p.read(stats+0x40+j,1) for j in range(5)]
                row += [signed(p.read(A+i*0xf2c+off,4),32) for off in [0xa30,0xa34]]
        if opts.dispatch_entry:
            row += [signed(v,32) for v in readwords(B+8,2)+readwords(B+0x104,11)]
        return row

    def execute(command, label):
        nonlocal draws
        code, *values = command.split()
        values = list(map(int, values))
        result = 0
        if opts.dispatch_entry and code == 'enter-ending':
            run(0x143430,[B],stop=(0x143c60,),kind='entry_prefix')
        if code == 'start':
            p.write(B+0x30, run(0x1249c8, values), 4)
        elif code == 'ending':
            for reg, value in zip(range(12, 16), [320, 240, -50, 1]):p.floats[reg] = bits(value)
            p.write(B+0x30, run(0x124548, [values[0], 0x100000]), 4)
        elif code == 'owner-flags':
            p.write(p.read(B+0x30, 4), values[0], 4)
        elif code == 'gauge-start':
            result=th(run(0x11e520))
        elif code == 'enter-ending':
            sp=0x1fff000
            words(sp,[A,A+0xf2c]);words(sp+0x10,[O,O+0x1000]);words(sp+0x20,[B+0x254,B+0x35c])
            p.registers[18]=B;p.registers[30]=0;p.write(sp+0x78,0x1ffff00,8)
            #Non-final paths run the complete post-console tail. Final paths
            #stop at145118, whose nested139f20 contains kernel diagnostics.
            run(0x143cd8,stop=(0x145118,),kind='tail_or_prefix')
            complete=any(signed(p.read(B+0x254+i*0x108+0x28,4),32)>=signed(p.read(B+0x254+i*0x108+0x2c,4),32) for i in range(2))
            if complete:
                ui,ko=p.registers[22],p.registers[30]
                run(0x145118,[B],stop=(0x139f20,),kind='prefix')
                run(0x139f88,stop=(0x13a020,),kind='disabled_profile_gate')
                run(0x11c208)
                #Explicit caller continuation with the disabled-profile
                #return fixture. This is NOT a resumed/whole139f20 execution.
                p.registers[2]=0;p.registers[18]=B;p.registers[22]=ui;p.registers[23]=0x4c0000;p.registers[30]=ko
                p.write(sp+0x78,0x1ffff00,8)
                run(0x143e38,kind='disabled_profile_caller_tail')
        elif code == 'ending-update':
            run(0x144020, [B])
        elif code == 'enter':
            #143930 post-console tail, with the actual prologue's frame.
            sp = 0x1fff000
            p.registers[16], p.registers[17] = B, 1
            words(sp+0x20, [B+0x254, B+0x35c])
            p.write(sp+0x40, 0x1ffff00, 8)
            run(0x14398c, kind='tail')
        elif code == 'tick':
            p.write(0x46a924, values[0], 4)
            p.write(0x4a2250, 0, 4)
            run(0x112838)
        elif code == 'update':
            p.write(B+0x118, values[0], 4)
            owner = p.read(B+0x30, 4)
            if owner and p.read(owner, 4) & 1:
                run(0x143a38, [B])
            else:
                #The inactive branch reaches the console diagnostic. Verify
                #its prefix and subsequent timer tail as separate fragments.
                run(0x143a38, [B], stop=(0x143aa0,), kind='prefix')
                p.registers[16] = B
                p.write(0x1fff000+0x38, 0x1ffff00, 8)
                run(0x143ab0, kind='tail')
        elif code == 'allocate':
            buffered_stdout(p)
            result = hh(run(0x1123f0))
        elif code == 'release':
            buffered_stdout(p)
            run(0x1124b8, [hp(values[0])])
        elif code == 'active':
            result = run(0x112550, [hp(values[0])])
        elif code == 'initialize-owners':
            run(0x1123a8)
        elif code == 'cancel':
            run(0x112a70, [0x1b5b])
            run(0x11e3a0, [0x1b5b])
        elif code == 'clear-objects':
            run(0x146e88, [B+0x14c, 64])
        else:
            raise AssertionError(command)
        if opts.dispatch_entry and code == 'enter-ending':
            p.registers[16]=B;p.write(0x1fff000+0x18,0x1ffff00,8)
            run(0x1435a0,kind='entry_footer')
            command='dispatch-entry'
        commands.append(command)
        expected.append(snapshot(result))
        draws += p.read(0x4a2250, 4)
        labels.append(label)

    def configure(index, wins=(0, 0), required=(2, 2)):
        p.write(B+0x18, index, 4)
        for i in range(2):
            words(B+0x254+i*0x108+0x28, [wins[i], required[i]])
        commands.append(f'configure {index} {wins[0]} {required[0]} {wins[1]} {required[1]}')

    if not endings:
        #Whole1249c8 now includes real owner allocation; every visit compares
        #all256 task/object/owner slots and both scheduler list tails.
        for label, mode in itertools.product([1, 10] if quick else range(1, 11), [0] if quick else range(3)):
            fixture(label+mode*32)
            execute(f'start {label}', (label, mode, 'start'))
            visits = [210, 32, 310][mode]
            ended = None
            for visit in range(1, visits+1):
                execute(f'tick {int(mode==1 or (mode==2 and visit%3==1))}', (label, mode, visit))
                if not p.read(p.read(B+0x30, 4), 4) & 1 and ended is None:
                    ended = visit
            assert ended == [200 if label == 1 else 110, None, 300 if label == 1 else 165][mode]
            if ended:
                execute('update 0', (label, mode, 'controller_release'))
                assert p.read(B+0x30, 4) == 0 and p.read(B, 4) == 4
                assert p.read(0x46a904, 4) == 256 and p.read(0x3d3690, 4) == 256
            traces.append(dict(label=label, pause_mode=mode, ended_visit=ended))
            print(f'opening label={label} pause={mode} original trace collected', flush=True)

        #Entry selection and exact timer boundaries, then continuous rounds
        #with reused owners/pools: no reset of scheduler or residue between them.
        fixture(173)
        for index, wins, required in [(0, (0, 0), (1, 1)), (1, (0, 0), (2, 2)),
                                       (2, (1, 1), (2, 2)), (9, (0, 0), (3, 3)),
                                       (10, (0, 0), (2, 2)), (31, (0, 0), (2, 2))]:
            configure(index, wins, required)
            execute('enter', ('continuous', index, 'entry'))
            threshold = 0x8600 if index == 0 else 0x3900
            for timer in [threshold-1, threshold+1, threshold, threshold+256]:
                execute(f'update {timer}', ('continuous', index, timer))
            for visit in range(210):
                execute('tick 0', ('continuous', index, visit))
            execute(f'update {threshold}', ('continuous', index, 'release_and_event'))
            execute('update 0', ('continuous', index, 'null_owner_repeat'))
            assert p.read(0x3d3690, 4) == 256 and p.read(0x46a904, 4) == 256

        #Coexist with real registered-object tasks in the SAME256-slot pools,
        #including births between visits. They are not dispatched as callbacks
        #by112838 (flags1); their object phase remains a separate dependency.
        for occupied in [6, 48, 61]:
            fixture(211+occupied)

            def populate(count):
                for _ in range(count):run(0x1471a8, [B+0x14c, 64, 0x1396, 0])
                commands.append(f'populate {count}')

            populate(occupied)
            execute('enter', ('shared_pools', occupied, 'entry'))
            for visit in range(210):
                if visit == 37:populate(3)
                execute('tick 0', ('shared_pools', occupied, visit))
            execute('update 0', ('shared_pools', occupied, 'release'))
            assert p.read(0x46a904, 4) == 256-occupied-3 and p.read(0x3d3690, 4) == 256
            execute('clear-objects', ('shared_pools', occupied, 'clear_registered'))
            execute('tick 0', ('shared_pools', occupied, 'reclaim_registered'))
            assert p.read(0x46a904, 4) == 256 and p.read(0x3d3a98, 4) == 0

        #Cancel two tasks sharing one owner before or after reservation8 clears.
        #Original tag cancellation does not release texture refs/palette. Observe
        #that residue rather than inventing a cleanup the source never performed.
        for visits in [0, 40, 95, 150]:
            fixture(191+visits)
            execute('start 1', ('cancel', visits, 'start'))
            for visit in range(visits):execute('tick 0', ('cancel', visits, visit))
            execute('cancel', ('cancel', visits, 'cancel'))
            execute('tick 0', ('cancel', visits, 'reclaim'))
            execute('update 0', ('cancel', visits, 'release'))
            assert p.read(0x3d3690, 4) == 256

    if endings and not ending_control and not entry_mode:
        #The null-callback branch preserves reservation8; only owner bit2
        #requests immediate free. Final draws survive either completion path.
        for descriptor, mode, auto in itertools.product(range(15, 20), range(3), [False, True]):
            fixture(descriptor+mode*32+int(auto)*64)
            execute(f'ending {descriptor}', (descriptor, mode, auto, 'start'))
            owner = p.read(B+0x30, 4)
            if auto:execute('owner-flags 15', (descriptor, mode, auto, 'auto_release'))
            ended = None
            for visit in range(1, [90, 32, 130][mode]+1):
                execute(f'tick {int(mode==1 or (mode==2 and visit%3==1))}', (descriptor, mode, auto, visit))
                if not p.read(owner, 4) & 1 and ended is None:ended = visit
            assert (ended is None) == (mode == 1), (descriptor, mode, auto, ended)
            if ended:
                assert p.read(owner, 4) == (0 if auto else 12)
                assert p.read(0x46a904, 4) == 256
                assert p.read(0x3d3690, 4) == (256 if auto else 255)
                execute(f'release {hh(owner)}', (descriptor, mode, auto, 'release'))
                assert p.read(0x3d3690, 4) == 256
            traces.append(dict(descriptor=descriptor, pause_mode=mode, auto_release=auto, ended_visit=ended))
            print(f'ending descriptor={descriptor} pause={mode} auto={auto} collected', flush=True)

        #All ending groups coexist with registered actor tasks and reuse the
        #same owners/pools. Also cancel while active and after final draw.
        fixture(251)
        for _ in range(48):run(0x1471a8, [B+0x14c, 64, 0x1396, 0])
        commands.append('populate 48')
        for cycle, descriptor in enumerate([15, 18, 19, 17, 16, 15, 16, 19, 17, 18]):
            execute(f'ending {descriptor}', ('continuous_endings', cycle, descriptor))
            owner = p.read(B+0x30, 4)
            for visit in range(90):execute('tick 0', ('continuous_endings', cycle, visit))
            execute(f'release {hh(owner)}', ('continuous_endings', cycle, 'release'))
            assert p.read(0x46a904, 4) == 208 and p.read(0x3d3690, 4) == 256
        execute('clear-objects', ('continuous_endings', 'clear_registered'))
        execute('tick 0', ('continuous_endings', 'reclaim_registered'))
        for descriptor, visit_count in itertools.product(range(15, 20), [0, 7, 73, 90]):
            execute(f'ending {descriptor}', ('ending_cancel', descriptor, visit_count))
            for visit in range(visit_count):execute('tick 0', ('ending_cancel', descriptor, visit_count, visit))
            execute('cancel', ('ending_cancel', descriptor, visit_count, 'cancel'))
            execute('tick 0', ('ending_cancel', descriptor, visit_count, 'reclaim'))
            execute(f'release {hh(p.read(B+0x30, 4))}', ('ending_cancel', descriptor, visit_count, 'release'))
            assert p.read(0x46a904, 4) == 256 and p.read(0x3d3690, 4) == 256

    if ending_control:
        def actor(*, table=0, state=0, dead=False, air=False, blocked=False, end=0, pending=False,
                  queued=-1, condition=0, upper=0, x=280, mirror=False, lock=0, flags248=0):
            return [0x1000+int(dead)*128+int(air)*16, 2 if blocked else 0, flags248, lock,
                    (state<<16)|table, 0xffffffff, 0x1234, 7, 11, queued&0xffffffff,
                    condition, upper, 0x10000000+int(mirror)*0x80000, 1 if pending else 0, 0x89, end, bits(x)]

        def configure_ending(result, wins, rows):
            nonlocal ending_projection
            ending_projection = True
            words(B, [5, 5]);p.write(B+0x28, result, 4)
            config = [result, wins[0], 2, wins[1], 2]
            for i, row in enumerate(rows):
                a, o = A+i*0xf2c, O+i*0x1000
                p.write(B+0x254+i*0x108+0x28, wins[i], 4)
                p.write(a+0xa24, i, 4)
                for off, value in zip([0x23c, 0x244, 0x248, 0x24c, 0x194, 0x1a4, 0x18c, 0x190, 0x192, 0xa3c, 0x160, 0x17c], row[:12]):
                    p.write(a+off, value, 1 if off==0x24c else 2 if off in [0x190, 0x192] else 4)
                for off, value in zip([0x38, 0x104, 0x108, 0xc0, 0x40], row[12:]):p.write(o+off, value, 4)
                config += row
            commands.append('ending-config '+' '.join(map(str, config)))

        #Whole144020 makes readiness checks while captions are active too.
        #A fresh chained caption returns before either actor is inspected.
        for result, wins, descriptor in itertools.product(range(4), [(1, 0), (2, 0), (2, 2)], [0, 15, 18, 19]):
            fixture(131+result)
            rows = [actor(state=52, end=1), actor(dead=True, end=1, x=360)]
            configure_ending(result, wins, rows)
            if descriptor:execute(f'ending {descriptor}', ('controller_chain', result, wins, descriptor, 'start'))
            execute('ending-update', ('controller_chain', result, wins, descriptor, 'initial'))
            for visit in range(170 if descriptor else 0):
                execute('tick 0', ('controller_chain', result, wins, descriptor, visit, 'tick'))
                execute('ending-update', ('controller_chain', result, wins, descriptor, visit, 'update'))
            assert p.read(B, 4) == 7, (result, wins, descriptor)
            assert p.read(0x3d3690, 4) == 256 and p.read(0x46a904, 4) == 256
            traces.append(dict(result=result, wins=wins, descriptor=descriptor))
            print(f'ending controller result={result} wins={wins} caption={descriptor} collected', flush=True)

        #Independent readiness/facing boundaries. Both actor positions and
        #raw alias words are fixtures; this does not run actor animation.
        for table, state, dead, air, blocked, end, pending, queued in itertools.product(
                [0, 1, 2], [0, 52], [False, True], [False, True], [False, True], [0, 1], [False, True], [-1, 9]):
            fixture(37)
            configure_ending(0, (1, 0), [actor(table=table, state=state, dead=dead, air=air, blocked=blocked,
                end=end, pending=pending, queued=queued), actor(state=52, end=1, x=360)])
            execute('ending-update', ('readiness', table, state, dead, air, blocked, end, pending, queued))
        for condition, upper, positions, mirror, lock, table, state, flags248 in itertools.product(
                [0, 16, 32, 64, 1], [0, 1<<30], [(280, 360), (360, 280), (320, 320)],
                [False, True], [0, 4], [0, 1], [0, 64], [0, 16]):
            fixture(83)
            configure_ending(1, (0, 0), [actor(condition=condition, upper=upper, x=positions[0], mirror=mirror,
                lock=lock, table=table, state=state, flags248=flags248), actor(x=positions[1], mirror=not mirror)])
            execute('ending-update', ('condition_facing', condition, upper, positions, mirror, lock, table, state, flags248))

    if entry_mode:
        rng=random.Random(0x143c60)
        for case_id,(life,wins,submode,paused) in enumerate(itertools.product(
                [(200,0),(0,200),(99,0),(0,99),(0,0),(80,80),(200,1),(1,200)],
                [(0,0),(1,0),(0,1),(1,1)], [0,4,5,6], [0,1])):
            fixture(case_id+41);entry_projection=True
            seed=rng.getrandbits(32);metadata=rng.getrandbits(32);flags=rng.getrandbits(32);version=case_id%2
            values=[seed,submode,paused,metadata,flags,version]
            for at,value in [(B,5),(B+4,4),(B+0x20,0),(B+0x24,-1),(B+0x28,-1),(B+0x2c,97),
                             (0x4c3808,3),(0x4c3810,-1),(0x4c3830,31),(0x4c3894,17),(0x4c3834,9),(0x4c38ac,13),
                             (0x4c38a8,submode),(0x46a940,paused),(0x4d3d04,0x1d00000),(0x1d00004,metadata),
                             (0x1239090,flags),(0x123a168,0),(0x3d2e7c,0),(0x123a0ec,11),(0x123a0e8,7),
                             (0x1239d84,19),(0x1239d88,43),(0x46a908,77)]:p.write(at,value,4)
            p.write(0x43d052,version,1)
            words(B+0x114,(seed+i*23 for i in range(7)))
            words(0x46a910,(seed+i*17 for i in range(12)))
            p.memory[0x3ebf30:0x3ec730]=struct.pack('<1024H',*[(seed+i*19)&65535 for i in range(1024)])
            for i in range(2):
                stats=B+0x254+i*0x108;a=A+i*0xf2c
                row=[rng.randrange(201),rng.randrange(2),rng.randrange(3),rng.choice([-1,0,1,2,3,5]),rng.choice([-1,0,1]),
                     rng.randrange(9),wins[i],2,rng.choice([0,99,104,119]),signed(rng.getrandbits(32),32),signed(rng.getrandbits(32),32)]
                for off,value in zip([0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x2c,0x34,0x38,0x3c],row):p.write(stats+off,value,4)
                hist=[rng.randrange(256) for _ in range(5)]
                for j,value in enumerate(hist):p.write(stats+0x40+j,value,1)
                p.write(a+0xa24,i,4);p.write(a+0x10c,0,4);p.write(a+0xa14,0,4)
                p.write(a+0xa30,life[i],4);p.write(a+0xa34,200,4)
                values+=row+hist+[life[i],200]
            commands.append('entry-config '+' '.join(str(v&0xffffffff) for v in values))
            execute('gauge-start',('entry',case_id,'register_gauge'))
            if case_id%3==0:execute('gauge-start',('entry',case_id,'duplicate_gauge'))
            execute('enter-ending',('entry',case_id,life,wins,submode,paused))
            execute('tick 0',('entry',case_id,'reclaim_gauge_and_first_draw'))
            #Compose entry with whole144020 and the shared scheduler. Ready
            #actors are an explicit boundary fixture, never animation proof.
            if case_id%32 in [0,24]:
                for i in range(2):
                    a,o=A+i*0xf2c,O+i*0x1000;dead=life[i]<=0
                    for off,value in [(0x23c,0x1080 if dead else 0x1000),(0x244,0),
                                      (0x194,(30<<16)|2 if dead else 52<<16),(0xa3c,-1)]:p.write(a+off,value,4)
                    p.write(o+0xc0,1,4);p.write(o+0x104,0,4)
                commands.append('ending-ready')
                for visit in range(1,163):
                    execute('ending-update',('entry_lifecycle',case_id,visit,'control'))
                    execute('tick 0',('entry_lifecycle',case_id,visit,'dispatch'))
                assert p.read(B,4)==7 and p.read(B+0x30,4)==0
                assert p.read(0x3d3690,4)==256 and p.read(0x46a904,4)==256
            traces.append(dict(life=life,wins=wins,submode=submode,paused=paused))
            if case_id%64==0:print(f'ending entry case={case_id} collected',flush=True)

    #Owner bit semantics and all256 slots, exhaustion, duplicate release,
    #and initialization preserving other bits/value.
    rng = random.Random(0x1123f0)
    fixture(53)
    for scenario in range(8):
        owners = [[rng.getrandbits(32), rng.getrandbits(32)] for _ in range(256)]
        free, glob = rng.getrandbits(32), rng.getrandbits(32)
        words(OWNERS, itertools.chain.from_iterable(owners))
        p.write(0x3d3690, free, 4)
        p.write(0x3d3688, glob, 4)
        commands.append(' '.join(map(str, ['owners', free, glob, *itertools.chain.from_iterable(owners)])))
        for h in [0, 1, 2, 127, 256]:execute(f'active {h}', ('owner_bits', scenario, h))
        execute('initialize-owners', ('owner_init', scenario))
        for i in range(258):execute('allocate', ('owner_capacity', scenario, i))
        for h in [0, 1, 1, 256, 256, 127]:execute(f'release {h}', ('owner_release', scenario, h))
        execute('allocate', ('owner_recycle', scenario))

    output = subprocess.run([str(BINARY), str(ASSETS)], input='\n'.join(commands)+'\n',
                            text=True, capture_output=True)
    assert output.returncode == 0, (output.returncode, output.stderr)
    actual = [list(map(int, line.split())) for line in output.stdout.splitlines()]
    assert len(actual) == len(expected), (len(actual), len(expected))
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, (i, labels[i], len(got), len(want),
                             [(j, a, b) for j, (a, b) in enumerate(zip(got, want)) if a != b][:20])
    report = dict(status='passed', quick=quick, snapshots=len(expected), queued_draw_snapshots=draws,
                  original_functions=dict(counts), original_instructions=instructions, traces=traces,
                  elf_sha256=SOURCE_HASH, native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                  asset_sha256=hashlib.sha256((ASSETS/'opening_tasks.bin').read_bytes()).hexdigest(),
                  scope='Whole1249c8 with1123f0/116200/124620 and resident textures, whole112838 with124898 and actual completion callbacks, whole owner1123a8/1123f0/1124b8/112550, and tag cancellation. All256 task/object/owner records, free lists/counts, scheduler heads/tags, texture slots/refs,72 palette words, stage state and ordered record+26-field draws compared. Controller entry is explicit14398c post-console tail; active update is whole143a38, inactive update is143a38..143aa0 prefix plus143ab0 tail. Six continuous entries reuse pools; three additional openings share pools with9/51/64 registered-object tasks, real1471a8/146e88 and deferred reclamation. No instructions/callees patched/skipped. Muted audio, resident texture data, finite FP model. No whole143430/143320, GS/hardware, live SDL input or full match equivalence claim.')
    if endings:
        report['ending_asset_sha256'] = hashlib.sha256((ASSETS/'ending_tasks.bin').read_bytes()).hexdigest()
        report['scope'] = 'Whole unmodified124548/124620/112838/124898/1123a8/1123f0/1124b8/112550, original effect and completion callees, real buffered libc puts and muted sound option. All5 ending descriptors, pause/resume, null-callback reservation versus active semantics, optional auto-release, final queued draws,10 continuous presentations sharing48 actor tasks, cancellation, owner capacity. Full256-slot normalized task/object/owner hashes, scheduler lists/tags, texture refs/residency,72 palette words, ordered records and26-field draw state. No patched/skipped callees; finite FP model, resident texture fixtures. Separate component; no full state5 entry/update, original frame/hardware or live match claim.'
    if ending_control:
        report['scope'] = 'Whole unmodified144020 with actual145358/14ab80/149488/145240/14a978/151238 callees and124548/124620/112838/124898 caption lifecycle.36 persistent caption/controller chains plus12 null-owner scenarios; ordinary actor readiness/queued action distinction,raw0/52 state,air/lock/condition254 bits,facing and delayed normal52 requests. Compare full shared task/object/owner pools,texture refs,72 palette words,all queued draws and both actor/body/request projections. Every reached callee runs unchanged, buffered libc/muted option,finite FP. Boundary actor states are fixtures: not full1494f0/143430/state5 entry/entire matches or hardware cadence; transformed/auxiliary actors excluded.'
    if entry_mode:
        report['ending_choice_sha256']=hashlib.sha256((ASSETS/'ending_choices.bin').read_bytes()).hexdigest()
        report['scope']='Ordinary mode3/resource00/system0/muted/profile-disabled143c60 entry business. Nonfinal original paths run143cd8 post-console tail intact; final paths use143cd8 prefix stopping at145118,145118 prefix stopping at139f20,139f88 disabled-profile gate,whole11c208,and143e38 caller tail with explicit profile-return fixture. No whole143c60/145118/139f20 claim; no logger/callee patched. Whole reached gauge stop,result statistics,choice tables,pause,timer wrappers,palette reset,124548 and scheduler execute normally.256 entries spanningKO/doubleKO/time/dual-time,all win thresholds,submode4/5 exceptions,globalpause divisor8,duplicate gauge cancellation. Full shared pools,texture refs,72 palette words,1024 tones,all statistics/history,life,max,global result fields,7timers and queued draws compared;16 entry-to-state7 compositions with explicit ready-actor boundaries. Profile persistence,other modes/actors,full frames and live match integration remain pending.'
    if opts.dispatch_entry:
        report['scope'] += ' Native RoundDispatcher.enter state5 additionally compares actual143430 prefix to143c60 and1435a0 publication footer. Includes field08/field0c and complete battle timer header; not whole143430.'
    target = 'round_ending_dispatch_validation.json' if opts.dispatch_entry else 'round_ending_entry_validation.json' if entry_mode else 'round_ending_control_validation.json' if ending_control else 'scheduled_ending_validation.json' if endings else 'scheduled_opening_quick_validation.json' if quick else 'scheduled_opening_validation.json'
    (ROOT/'outputs/ss6-feasibility'/target).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
