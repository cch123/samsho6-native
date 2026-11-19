#!/usr/bin/env python3
"""Registry cleanup and task dispatch against whole unmodified functions.

Observer only records entry into two real callback functions; it never
changes instructions, skips calls, or substitutes their effects.
"""
import collections
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from mips_probe import Probe
from extract_collision_tables import SOURCE_HASH
from validate_object_pools import pointer, handle, digest, TASKS, OBJECTS

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / 'work/ss6/build-native/ss6-task-dispatch-probe'
REGISTRY = 0x1b00000
HEADS, CURRENT, FREE_TASKS = 0x1232440, 0x1232840, 0x1232844
TAGS, ACTIVE = 0x3d3698, 0x3d3a98
tp = lambda h: pointer(h, TASKS, 52)
op = lambda h: pointer(h, OBJECTS, 320)
th = lambda a: handle(a, TASKS, 52)
oh = lambda a: handle(a, OBJECTS, 320)


class Observer(Probe):
    observing = False

    def read(self, address, size):
        if self.observing and size == 4 and address in (0x147540, 0x11d990):
            arg = self.registers[4] & 0xffffffff
            self.calls.extend([address, th(arg) if address == 0x147540 else oh(arg),
                               th(super().read(CURRENT, 4))])
        return super().read(address, size)


def main():
    raw = (ROOT / 'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    p = Observer(raw)
    rng = random.Random(0x112838)
    commands, expected, labels = [], [], []
    groups = collections.Counter()
    instructions = callback_calls = 0

    def words(address, values):
        p.memory[address:address + 4 * len(values)] = struct.pack(f'<{len(values)}I', *values)

    def readwords(address, count):
        return list(struct.unpack_from(f'<{count}I', p.memory, address))

    def setup(tasks=None, objects=None, registry=None, current=0):
        tasks = tasks or [[0] * 13 for _ in range(256)]
        objects = objects or [[0] * 80 for _ in range(256)]
        registry = registry or [0] * 64
        free_tasks = 0
        for i, t in enumerate(tasks):
            if not t[1]:
                t[3] = free_tasks
                free_tasks = i + 1
        used_objects = {t[7] for t in tasks if t[1] and t[7]}
        free_objects = count = 0
        for i, o in enumerate(objects):
            if i + 1 not in used_objects:
                o[78] = free_objects
                free_objects = i + 1
                count += 1
        heads = [rng.randrange(257) for _ in range(256)]
        tags = [rng.getrandbits(32) for _ in range(256)]
        active = rng.randrange(257)
        data = ['P', free_tasks, free_objects, count, current, active, *heads, *tags]
        for i, t in enumerate(tasks):
            data.extend(t)
            mapped = t.copy()
            mapped[3], mapped[7] = tp(t[3]), op(t[7])
            words(TASKS + i * 52, mapped)
        for i, o in enumerate(objects):
            data.extend(o)
            mapped = o.copy()
            mapped[78] = op(o[78])
            words(OBJECTS + i * 320, mapped)
        data.extend(registry)
        commands.append(' '.join(map(str, data)))
        for a, v in [(FREE_TASKS, tp(free_tasks)), (0x46a900, op(free_objects)),
                     (0x46a904, count), (CURRENT, tp(current)), (ACTIVE, active)]:
            p.write(a, v, 4)
        words(HEADS, list(map(tp, heads)))
        words(TAGS, tags)
        words(REGISTRY, list(map(tp, registry)))

    def snapshot(result=0):
        tasks = readwords(TASKS, 256 * 13)
        objects = readwords(OBJECTS, 256 * 80)
        for i in range(256):
            tasks[i * 13 + 3] = th(tasks[i * 13 + 3])
            tasks[i * 13 + 7] = oh(tasks[i * 13 + 7])
            objects[i * 80 + 78] = oh(objects[i * 80 + 78])
        return [result, th(p.read(FREE_TASKS, 4)), oh(p.read(0x46a900, 4)), p.read(0x46a904, 4),
                th(p.read(CURRENT, 4)), p.read(ACTIVE, 4), digest(tasks), digest(objects),
                digest(map(th, readwords(HEADS, 256))), digest(readwords(TAGS, 256)),
                *map(th, readwords(REGISTRY, 64)), len(p.calls), *p.calls]

    def run(code, *args, group):
        nonlocal instructions, callback_calls
        p.calls = []
        p.observing = True
        pc = {'t': 0x112570, 'o': 0x11e290, 'c': 0x146e88,
              'd': 0x112838, 'g': 0x1471a8}[code]
        original = [REGISTRY, *args] if code == 'c' else [REGISTRY, 64, *args, 0] if code == 'g' else args
        result, n = p.run(pc, original, limit=150000)
        p.observing = False
        instructions += n
        callback_calls += len(p.calls) // 3
        commands.append(' '.join(map(str, [code, *args])))
        expected.append(snapshot(th(result & 0xffffffff) if code == 'g' else 0))
        labels.append((group, code, args))
        groups[group] += 1

    # Wait boundaries include negative signed words. Bit8 suppresses both
    # callbacks and pending cancellation until it is explicitly released.
    flags = [0, 1, 2, 4, 6, 8, 10, 12, 14, 0x10, 0x18, 0x20, 0x28, 0x42, 0x4a, 0xffffffff]
    for case in range(64):
        tasks, objects = [], []
        for i in range(256):
            t = [rng.getrandbits(32) for _ in range(13)]
            t[1] = flags[(i + case) % len(flags)]
            t[0] = 0x11d990 if t[1] == 0x42 else 0x147540
            t[2] = 3 if t[1] == 0x20 else rng.choice([0, 1, 2, 0x7fffffff, 0x80000000, 0xffffffff])
            t[3], t[4], t[6], t[7], t[10] = 0, (i + case) % 256 if case % 2 else i % 3, 0, i + 1, 1
            tasks.append(t)
            o = [rng.getrandbits(32) for _ in range(80)]
            o[78] = 0
            objects.append(o)
        setup(tasks, objects, current=case % 257)
        for _ in range(3):
            run('d', group='mixed_flags_waits_and_callback_order')

    # Both round registry lengths, sparse prefixes, stale cancellation flags,
    # and deliberate aliases. Invalid duplicate ownership is compared as-is:
    # source146e88 frees twice; do not silently turn it into deduplication.
    for count in [0, 1, 3, 48, 64]:
        for mode in range(4):
            tasks = [[0] * 13 for _ in range(256)]
            objects = [[rng.getrandbits(32) for _ in range(80)] for _ in range(256)]
            for o in objects:
                o[78] = 0
            registry = [0] * 64
            for i in range(64):
                t = tasks[255-i]
                t[0], t[1], t[4], t[5], t[7], t[10] = 0x147540, [1, 4, 8, 0x10][mode], 50, i + 7000, 256-i, 1
                registry[i] = (256-i if mode != 3 else 256) if i % 3 != mode else 0
            setup(tasks, objects, registry)
            run('c', count, group='registry_prefix_and_aliases')
            run('d', group='deferred_task_reclamation')

    # Repeated reset with new allocations BEFORE dispatch: old objects are
    # available immediately, old task slots remain occupied until dispatch.
    setup()
    run('t', group='continuous_round_lifecycle')
    run('o', group='continuous_round_lifecycle')
    for round_index in range(96):
        run('c', 64, group='continuous_round_lifecycle')
        for tag in [0x1396] * 6 + [0x1b5b] * 2:
            run('g', tag, group='continuous_round_lifecycle')
        run('d', group='continuous_round_lifecycle')
        assert p.read(0x46a904, 4) == 248 and p.read(ACTIVE, 4) == 8
    run('c', 64, group='continuous_round_lifecycle')
    run('d', group='continuous_round_lifecycle')
    assert p.read(0x46a904, 4) == 256 and p.read(ACTIVE, 4) == 0

    output = subprocess.run([str(BINARY)], input='\n'.join(commands) + '\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in output.stdout.splitlines()]
    assert len(actual) == len(expected), (len(actual), len(expected))
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, (i, labels[i], [(j, a, b) for j, (a, b) in enumerate(zip(got, want)) if a != b][:12])

    # Native callback API contracts; these callbacks are deliberately not
    # original code and therefore have separate evidence and counts.
    native_cases = 0
    for kind in ('birth', 'cancel_later', 'coroutine'):
        commands.clear()
        tasks = [[0] * 13 for _ in range(256)]
        t = tasks[255]
        t[0], t[1], t[4], t[5], t[10] = 1, 0x10, 5, 71, 1
        if kind == 'cancel_later':
            t[0] = 3
            tasks[254][:] = t[:]
            tasks[254][0] = 2
        elif kind == 'coroutine':
            t[1], t[9], t[10], t[11] = 0x20, 99, 2, 17
        setup(tasks)
        commands += ['d', 'd']
        output = subprocess.run([str(BINARY)], input='\n'.join(commands) + '\n', text=True, capture_output=True, check=True)
        rows = [list(map(int, line.split())) for line in output.stdout.splitlines()]
        if kind == 'birth':
            assert rows[0][74:] == [3, 1, 256, 256] and rows[0][5] == 1
            assert rows[1][74:] == [3, 2, 255, 255] and rows[1][5] == 0
        elif kind == 'cancel_later':
            assert rows[0][74:] == [3, 3, 256, 256] and rows[0][5] == 0
            assert rows[1][74:] == [0]
        else:
            assert rows[0][74:] == [7, 4, 99, 256, 17, 5, 99, 0] and rows[0][5] == 0
            assert rows[1][74:] == [0]
        assert rows[1][1] == 256 and rows[1][4] == 0
        native_cases += 1

    report = dict(status='passed', whole_function_calls=sum(groups.values()), groups=dict(groups),
                  original_callback_calls=callback_calls, original_instructions=instructions,
                  continuous_round_resets=96, native_only_callback_contracts=native_cases,
                  elf_sha256=SOURCE_HASH, native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                  scope='Whole unmodified146e88/112838 and callees, with real147540 and11d990 callbacks. All256 task/object records, free lists/count,256 priority heads and active tags including unused tail,64 registry entries,current task and callback order/arguments compared. Exact integer model. Flag20 is compared only while wait>0; coroutine resume/destruction and birth/cancel-during-callback contracts are separate synthetic native checks. No complete object-phase dispatcher, original coroutine implementation, live frame or hardware equivalence claim.')
    (ROOT / 'outputs/ss6-feasibility/task_dispatch_validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
