#!/usr/bin/env python3
"""Shared two-actor reset compared with whole ordinary13fd80 and callees."""
import hashlib
import argparse
import json
import struct
import subprocess
from round_entry_oracle import ROOT, fixture
from extract_collision_tables import SOURCE_HASH
from mips_probe import signed
from validate_input_features import FEATURES, LATCHES, HELD, PRESSED
from validate_object_pools import TASKS, OBJECTS, handle, digest
from validate_stage_camera import bits

BINARY = ROOT/'work/ss6/build-native/ss6-battle-round-probe'
CONTROL = [0x88, 0x8c, 0xbc, 0xc4, 0xcc, 0xd8, 0xe4, 0xe8]
CAMERA = [0, 4, 8, 12, 16, 20, 28, 32, 36, 40, 44, 48, 52]
PROJECTION = [0x4a2a58, 0x4a2a5c, 0x4a2a60, 0x4a2a6c, 0x4a2a68]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--entries', action='store_true')
    parser.add_argument('--dispatcher', action='store_true')
    opts = parser.parse_args()
    entries = opts.entries or opts.dispatcher
    assert hashlib.sha256((ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()).hexdigest() == SOURCE_HASH
    commands, expected, labels = [], [], []
    instructions = rounds = dispatches = 0
    names = []

    def run(pc, args=(), stop_before=()):
        nonlocal instructions
        value, count = p.run(pc, args, stop_before=stop_before, limit=250000)
        instructions += count
        return value

    def words(address, values):
        p.memory[address:address+4*len(values)] = struct.pack(f'<{len(values)}I', *[v & 0xffffffff for v in values])

    def readwords(address, count):
        return list(struct.unpack_from(f'<{count}I', p.memory, address))

    def reset():
        nonlocal p, a0, o0, b, images
        p, a0, o0, b = fixture()
        p.finite_model = True
        p.write(0x345188, 0, 4)
        p.write(0x4c3820, 1, 4)
        p.write(0x443150, 0, 4)
        p.write(0x3d2e80, 1, 4)
        p.write(p.read(0x5d1bf8, 4)+0xa8, 1, 8)
        run(0x146388, [b+0x34])
        images = [[0]*3 for _ in range(2)]
        for i in range(2):
            a, o = a0+i*0xf2c, o0+i*0x1000
            p.memory[a:a+0xf2c] = bytes(0xf2c)
            p.memory[o:o+0x140] = bytes(0x140)
            p.write(b+0x24c+i*4, a, 4)
            for off, value in [(0, o), (0x190, -1), (0x194, 41 << 16), (0x1a0, -1), (0x1a4, -1),
                               (0x23c, 0x1000), (0xa24, i), (0xa30, 100), (0xa34, 200), (0xa3c, -1), (0x1ac, 256)]:
                p.write(a+off, value, 4)
            p.write(a+0x255, 255, 1)
            for off, value in [(0x30, 256), (0x70, bits(1)), (0xc8, 1), (0xcc, i), (0x104, 0x200), (0x8c, 0xff808080)]:
                p.write(o+off, value, 4)
            run(0x120390, [o, 189+i])
            for off, value in [(0x38, 0x10000000 | (i << 19)), (0x104, 0x40000200), (0x108, 0),
                               (0x40, bits(280+i*80)), (0xc4, 189+i)]:
                p.write(o+off, value, 4)
            words(o+0x4c, [0]*6)
            run(0x179258, [a+0x2c4, a+0x10c])
        commands.append('reset')

    def seed(value, index, request, flags, mode):
        for off, v in [(0, request), (4, 8), (8, 17), (12, 19), (0x18, index), (0x130, 9), (0x138, flags), (0x140, 23)]:
            p.write(b+off, v, 4)
        for at, v in [(0x12d2304, 29), (0x132c4bc, 31), (0x132c4c0, 37), (0x132c218, 41), (0x12d2300, 43),
                       (0x443150, mode), (0x3d2e80, value)]:
            p.write(at, v, 4)
        p.write(p.read(0x5d1bf8, 4)+0xa8, value*0x100000001, 8)
        for at, v in [(0x132c1e0, value%15), (0x132c1e4, 7), (0x132c1e8, 0x100 if value%2 else 0x40),
                      (0x132c1f8, 14 if value%3 == 0 else 0), (0x132c0e0, 0x12345678),
                      (0x132c0e8, bits(400)), (0x132c0ec, bits(70)), (0x132c0f0, bits(-5)), (0x132c210, bits(27)),
                      (0x132c0f4, 1), (0x132c0f8, 3), (0x132c0fc, 5), (0x3d2e78, value)]:
            p.write(at, v, 4)
        words(0x439a48, [value+j*5 for j in range(72)])
        for off, v in [(0, 64), (4, bits(440)), (8, bits(200)), (12, bits(400))]:
            p.write(b+0x34+off, v, 4)
        #Boundary reseeding replaces the prior camera script. A real entry
        #leaves its0 sentinel, unlike the bare13fd80 reset's empty queue.
        run(0x146ad8, [b+0x34])
        run(0x146b30, [b+0x34, 3, 17])
        run(0x146b30, [b+0x34, 0, 0])
        assert p.read(b+0x34+0x4c, 4) == 2
        words(b+0x104, [7, 99, 128, 512]+[61]*7)
        words(FEATURES, [value+j*13 for j in range(171)])
        p.memory[LATCHES:LATCHES+12] = bytes((value+i+j) & 255 for i in range(2) for j in range(6))
        for address, values in [(HELD, [value+j*13 for j in range(600)]), (PRESSED, [value*3+j*7 for j in range(600)])]:
            p.memory[address:address+1200] = struct.pack('<600H', *[v & 65535 for v in values])
        for i in range(2):
            a, owner = a0+i*0xf2c, a0+i*0xf2c+0x2c4
            for off, v in [(0x120, (value+i)%4), (0x124, 501+i), (0x128, 17+i), (0x130, 5+i), (0x134, 123+i), (0x138, 456+i),
                           (0x240, 0xabcdef01), (0xa50, 43), (0xb4, 61), (0xb8, 67), (0xc0, 71), (0xc8, 38 if i else 4)]:
                p.write(a+off, v, 4)
            words(a+0xc, [79]*10)
            words(a+0x38, [83]*10)
            p.memory[a+0xf14:a+0xf22] = bytes([255])*14
            p.memory[a+0xf22:a+0xf2b] = bytes([0x5a])*9
            words(a+0x1b0, [value+j*19 for j in range(35)])
            words(owner, [value+i*7+j*13 for j in range(171)])
            for special, count in [(False, 31), (True, 32)]:
                for j in range(count):
                    p.write(owner+(0x328 if special else 0x2ac)+j*4, value+j, 4)
                    if special:
                        p.write(owner+0x3a8+j*4, j+1, 4)
                    address = owner+(0x684 if special else 0x502)+j*6
                    p.memory[address:address+5] = struct.pack('<BBHB', j%3, j+2, (value+j)&65535, j%7)
            stats = b+0x254+i*0x108
            for off, v in zip([0x1c, 0x20, 0x24, 0x28, 0x2c, 0x34, 0x38, 0x3c], [5, 7, 11, i, 2, 13, 17, 19]):
                p.write(stats+off, v, 4)
            p.memory[stats+0x40:stats+0x45] = bytes([1, 2, 3, 4, 5])
        commands.append(f'seed {value} {index} {request} {flags} {mode}')

    def snapshot():
        values = []
        names.clear()

        def add(v, name):
            values.append(v)
            names.append(name)

        def many(vs, name):
            for i, v in enumerate(vs):
                add(v, f'{name}[{i}]')

        many([signed(p.read(b+off, 4), 32) for off in [0, 4, 8, 12, 0x18]], 'battle state')
        many([p.read(b+off, 4) for off in [0x138, 0x140, 0x130]], 'battle flags')
        add(p.read(0x12d2304, 4), 'voice marker')
        add(signed(p.read(0x132c4bc, 4), 32), '132c4bc')
        many([p.read(at, 4) for at in [0x132c4c0, 0x132c218, 0x12d2300]], 'global')
        many([signed(p.read(0x443150, 4), 32), p.read(0x3d2e80, 4), p.read(p.read(0x5d1bf8, 4)+0xa8, 8)], 'random')
        many([signed(p.read(at, 4), 32) for at in [0x585224, 0x58524c]], 'sound history')
        many([p.read(b+0x34+off, 4) if i in [1, 2, 3, 7, 8, 9] else signed(p.read(b+0x34+off, 4), 32)
              for i, off in enumerate(CAMERA)], 'camera')
        many([p.read(at, 4) for at in PROJECTION], 'projection')
        #146ad8/146b30 use camera+4c as a count and8-byte queue records;
        #the earlier44/48 words belong to separate camera effect timers.
        count = p.read(b+0x34+0x4c, 4)
        add(count, 'camera commands')
        for i in range(count):
            many([p.read(b+0x34+0x50+i*8, 1), signed(p.read(b+0x34+0x54+i*8, 4), 32)], 'command')
        many([signed(v, 32) for v in readwords(b+0x104, 11)], 'timers')
        add(digest(readwords(FEATURES, 171)), 'sampled shared features')
        many(p.memory[LATCHES:LATCHES+12], 'latches')
        for at in [HELD, PRESSED]:
            add(digest(struct.unpack_from('<600H', p.memory, at)), 'recording')
        for player in range(2):
            a, o, stats = a0+player*0xf2c, o0+player*0x1000, b+0x254+player*0x108
            many([signed(p.read(stats+off, 4), 32) for off in [0x1c, 0x20, 0x24, 0x28, 0x2c, 0x34, 0x38, 0x3c]], f'p{player} stats')
            many(p.memory[stats+0x40:stats+0x45], 'match history')
            for off in [0x194, 0x18c, 0x190, 0x192, 0x198, 0x19a, 0x23c, 0x240, 0x244, 0x248, 0x24c,
                        0x1a4, 0xb4, 0xb8, 0xc0, 0xc8, *CONTROL, 0xa2c, 0xa50]:
                v = p.read(a+off, 1 if off in [0x19a, 0x24c] else 2 if off in [0x190, 0x192, 0x198] else 4)
                if off in [0x190, 0x192, 0x198]:
                    v = signed(v, 16) & 0xffffffff
                add(v, f'p{player} actor{off:x}')
            many(readwords(a+0xc, 10), 'control timers')
            many(readwords(a+0x38, 10), 'control motion')
            many(p.memory[a+0xf14:a+0xf2b], 'character bytes')
            many([signed(p.read(a+off, 4), 32) for off in [0xa30, 0xa34, 0xa38, 0x120, 0x124, 0x128, 0x130, 0x134, 0x138, 0xa3c, 0x1ac]], 'life/meters/action')
            many([signed(v, 32) for v in readwords(a+0x1b0, 35)], 'actor timers')
            for off, count in [(0x15c, 3), (0x260, 7), (0x27c, 4), (0x28c, 13)]:
                many(readwords(a+off, count), f'actor{off:x}')
            many([p.read(o+off, 2 if off == 0xfe else 4) for off in [0x24, 0x28, 0x2c, 0xc0, 0x38, 0x104, 0x108, 0xfe, 0x8c, 0x20, 0x40, 0x44]], 'body')
            many([signed(p.read(o+off, 4), 32) for off in [0x4c, 0x50, 0x54, 0x58, 0x5c, 0x60, 0xc4]], 'motion/action')
            add(p.read(a+0xa5c, 1), 'history fraction')
            many(readwords(a+0xa60, 300), 'actor history')
            many([handle(p.read(stats+0x48+j*4, 4), TASKS, 52) for j in range(48)], 'registry')
            many(images[player], 'afterimages')
            owner = a+0x2c4
            add(digest(readwords(owner, 171)), 'actor input features')
            many([signed(p.read(owner+off, 4), 32) for off in [0x5bc, 0x5c0]], 'binding count/start')
            add(1, 'input enabled')
            many(p.memory[owner+0x428:owner+0x448], 'priority')
            for special, count in [(False, 31), (True, 32)]:
                for j in range(count):
                    many([signed(p.read(owner+(0x644 if special else 0x4c4)+j*2, 2), 16),
                          p.read(owner+(0x5c4 if special else 0x448)+j*4, 4),
                          p.read(owner+(0x328 if special else 0x2ac)+j*4, 4),
                          p.read(owner+0x3a8+j*4, 4) if special else 0,
                          *struct.unpack_from('<BBHB', p.memory, owner+(0x684 if special else 0x502)+j*6)], 'command slot')
        th = lambda ptr: handle(ptr, TASKS, 52)
        oh = lambda ptr: handle(ptr, OBJECTS, 320)
        many([th(p.read(b+0x14c+j*4, 4)) for j in range(64)], 'global registry')
        many([th(p.read(0x1232844, 4)), oh(p.read(0x46a900, 4)), p.read(0x46a904, 4)], 'pool heads/count')
        tasks, objects = readwords(TASKS, 3328), readwords(OBJECTS, 20480)
        for i in range(256):
            tasks[i*13+3], tasks[i*13+7] = th(tasks[i*13+3]), oh(tasks[i*13+7])
            objects[i*80+1], objects[i*80+78] = th(objects[i*80+1]), oh(objects[i*80+78])
            if objects[i*80+0x118//4]:
                ptr = objects[i*80+0x118//4]
                assert ptr in [a0, a0+0xf2c], hex(ptr)
                objects[i*80+0x118//4] = (ptr-a0)//0xf2c+1
            if objects[i*80+0xbc//4]:
                objects[i*80+0xbc//4] -= 0x1700000-1
        many([digest(tasks), digest(objects), th(p.read(0x1232840, 4)), p.read(0x3d3a98, 4),
              digest(map(th, readwords(0x1232440, 256))), digest(readwords(0x3d3698, 256))], 'pools/scheduler')
        many([signed(p.read(at, 4), 32) if at in [0x132c1e0, 0x132c1e4, 0x132c1f8, 0x132c0f4, 0x132c0f8, 0x132c0fc]
              else p.read(at, 4) for at in [0x132c1e0, 0x132c1e4, 0x132c1e8, 0x132c1f8, 0x132c0e0,
                                           0x132c0e8, 0x132c0ec, 0x132c0f0, 0x132c210, 0x132c0f4, 0x132c0f8, 0x132c0fc]], 'stage event')
        add(p.read(0x3d2e78, 4), 'final sound pending')
        many(readwords(0x439a48, 72), 'palette state')
        return values

    def append(command):
        commands.append(command)
        expected.append(snapshot())
        labels.append((case, step, command, names.copy()))

    p = a0 = o0 = b = images = None
    for case in range(16):
        reset()
        for step in range(3):
            #Reseed retained state as a boundary fixture, not a fabricated
            #full intervening match. Actor/body/input identities persist.
            seed(101+case*5+step, 0 if case < 8 and step == 0 else step+1,
                 0 if entries else (case+step)%7, 0xdeadbeec | (case%4), case%2)
            for owner, count in [(0, 1+case%3), (1, 2), (2, 3)]:
                registry = b+0x14c if owner == 2 else b+0x29c+owner*0x108
                for _ in range(count):
                    run(0x1471a8, [registry, 64 if owner == 2 else 48, 0x1396+owner, 0])
                #No projection until reset; these fixtures deliberately vary
                #nonsemantic defaults outside the covered actor fields.
                commands.append(f'allocate {owner} {count}')
                expected.append(None)
                labels.append((case, step, 'allocate', []))
            if entries:
                #Three explicit fragments, excluding the console diagnostic
                #prologue in143708. All reached callees run normally; this
                #is not a whole143430 claim or a patched console return.
                p.registers[16] = p.registers[17] = b
                if opts.dispatcher:run(0x143430, [b], stop_before=(0x143708,))
                else:run(0x14350c, stop_before=(0x143558,))
                p.registers[16] = b
                p.write(0x1fff000+0x38, 0x1ffff00, 8)
                run(0x14375c)
                p.registers[16] = b
                p.write(0x1fff000+0x18, 0x1ffff00, 8)
                run(0x143560)
            else:
                run(0x13fd80)
            rounds += 1
            for player in range(2):
                images[player] = [handle(p.read(p.read(b+0x29c+player*0x108+j*4, 4)+0x1c, 4), OBJECTS, 320) for j in range(3)]
            append('dispatch-round' if opts.dispatcher else 'entry-round' if entries else 'round')
            run(0x112838)
            dispatches += 1
            append('dispatch')
            for player in range(2):
                run(0x149918, [a0+player*0xf2c])
                run(0x11d8e0, [o0+player*0x1000])
            append('commit')
            log = bytes(p.memory[0x1a00000:0x1a10000]).split(b'\0')[0]
            assert b'ASSERT' not in log
    result = subprocess.run([str(BINARY), str(ROOT/'work/ss6/extracted/resources')],
                            input='\n'.join(commands)+'\n', text=True, capture_output=True)
    assert result.returncode == 0, (len(result.stdout.splitlines()), result.stderr)
    actual = [list(map(int, line.split())) for line in result.stdout.splitlines()]
    assert len(actual) == len(expected), (len(actual), len(expected))
    for i, (got, want) in enumerate(zip(actual, expected)):
        if want is None:
            continue
        case, step, command, fields = labels[i]
        assert got == want, (i, case, step, command, len(got), len(want),
                             [(j, fields[j], x, y) for j, (x, y) in enumerate(zip(got, want)) if x != y][:20])
    report = dict(status='passed_for_projected_fields', scenarios=16, whole13fd80=rounds, whole149008=rounds*2,
                  whole112838=dispatches, compared_snapshots=sum(v is not None for v in expected),
                  original_instructions=instructions, elf_sha256=SOURCE_HASH,
                  native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                  scope='Ordinary mode3/no-time-limit, two persistent resource00/human/system0 actors. Whole13fd80 and reached callees unchanged, then separate whole112838,149918,11d8e0. Compare shared pools/full256-slot normalized hashes,global64 and player48 registries,task queues/tags,actor states/callbacks/timers/HP/meters/controls/60 histories,body clocks/motion/colors,input definitions/progress/features/latches/600 recordings,RNG and both sound histories,match stats/camera/battle flags and globals.16 seeded boundary fixtures each reset3 times,8 first rounds; old189/190 history before commits. This does not execute intervening full matches,whole143430/1494f0,object-phase callbacks,SDL input or hardware rendering. Explicit finite FP model.')
    report['scope'] += ' Also compare persistent stage event fields,final-sound pending and all72 palette-state words;13fd80 preserves these.'
    if entries:
        report['entry_prefixes'] = report['introduction_tails'] = report['entry_footers'] = rounds
        report['scope'] += (' Native ordinary round entry additionally composes145d98(muted),1159d0,13fd80,stage placement/request,143708 behavior and state publication/timer1 reset. '
                            'Original comparison uses14350c..143558 prefix,14375c post-console tail and143560 footer; no whole143430/143708 claim. '
                            'Each of the48 prefixes reaches whole13fd80/149008. Pending stage-event priority, first/later introduction and both shared RNGs preserved.')
    if opts.dispatcher:
        report['scope'] = report['scope'].replace('uses14350c..143558 prefix', 'uses143430..143708 prefix')
        report['scope'] += ' Native RoundDispatcher.enter state0 path; original143430 prefix stops at143708, followed by explicit14375c tail and143560 footer. Not whole143430.'
    filename = 'battle_round_dispatch_validation.json' if opts.dispatcher else 'battle_round_entry_validation.json' if entries else 'battle_round_validation.json'
    (ROOT/'outputs/ss6-feasibility'/filename).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
