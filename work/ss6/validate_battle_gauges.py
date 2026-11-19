#!/usr/bin/env python3
"""Shared gauge registration/dispatch/cancellation versus unchanged original."""
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
from validate_object_pools import TASKS, OBJECTS, handle, digest

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT/'work/ss6/build-native/ss6-battle-gauges-probe'
B, A, O = 0x1b00000, 0x1c00000, 0x1e00000
th = lambda v: handle(v, TASKS, 52)
oh = lambda v: handle(v, OBJECTS, 320)
ACTOR_FIELDS = [0x120, 0x124, 0x128, 0x130, 0x134, 0x138, 0x194, 0x19a, 0x23c,
                0x14c, 0x150, 0x154, 0x158]


class AudioObserver(Probe):
    #Observe the genuine audio request boundary without patching the callee.
    requests = None

    def read(self, address, size):
        if address == 0x213878 and size == 4 and self.requests is not None:
            self.requests.append([self.registers[4] & 0xffffffff, self.registers[5] & 0xffffffff])
        return super().read(address, size)


def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASH
    p = AudioObserver(raw, finite_model=True)
    rng = random.Random(0x11e708)
    commands, expected, labels = [], [], []
    counts = collections.Counter()
    instructions = 0

    def words(at, values):
        values = list(values)
        p.memory[at:at+4*len(values)] = struct.pack(f'<{len(values)}I', *[v & 0xffffffff for v in values])

    def readwords(at, count):
        return list(struct.unpack_from(f'<{count}I', p.memory, at))

    def call(pc, args=(), stop=(), kind='whole'):
        nonlocal instructions
        result, n = p.run(pc, args, limit=150000, stop_before=stop)
        instructions += n
        counts[f'{kind}{pc:06x}'] += 1
        return result & 0xffffffff

    def reset(seed):
        buffered_stdout(p)
        words(0x3d2e88, [0]*512)
        words(OBJECTS, [0]*(256*80))
        words(0x1232440, [0]*258)
        words(0x3d3698, [0]*257)
        call(0x1123a8);call(0x112570);call(0x11e290)
        words(B, [0]*300)
        p.requests = []
        for at in [0x5a9e78, 0x1553b5c, 0x1553a40, 0x123a174]:p.write(at, 0, 4)
        words(0x46a910, (seed+i*17 for i in range(12)))
        p.memory[0x3ebf30:0x3ec730] = struct.pack('<1024H', *[(seed+i*19)&65535 for i in range(1024)])
        p.write(0x4d3d00, B, 4);p.write(0x4d3d08, A, 4);p.write(0x123a0c0, 0, 1)
        for i in range(2):
            a, o = A+i*0xf2c, O+i*0x1000
            p.memory[a:a+0xf2c] = bytes(0xf2c)
            p.memory[o:o+320] = bytes(320)
            p.write(a, o, 4);p.write(a+0xa24, i, 4)
        commands.append(f'P {seed}')

    def configure(rows, requested=4, current=4, field08=0, lock=0, paused=0,
                  scales=(256, 256), limits=(100, 100)):
        delta = rng.getrandbits(32)
        values = [requested, current, field08, lock, paused, *scales, delta, *limits]
        for at, v in zip([B, B+4, B+8, B+0x108, 0x46a940, 0x1239d84, 0x1239d88, 0x46a908,
                          0x43d069, 0x43d06c], values):
            p.write(at, v, 1 if at in [0x43d069, 0x43d06c] else 4)
        for i, row in enumerate(rows):
            a, o = A+i*0xf2c, O+i*0x1000
            for off, v in zip(ACTOR_FIELDS, row):p.write(a+off, v, 1 if off == 0x19a else 4)
            p.write(o+0x104, row[-2], 4);p.write(o+0x108, row[-1], 4)
            values += row
        commands.append('F '+' '.join(str(v & 0xffffffff) for v in values))

    def snapshot(result):
        row = [result, *[signed(p.read(at, 4), 32) for at in [B, B+4, B+8, B+0x108]]]
        row += [p.read(at, 4) for at in [0x46a940, 0x1239d84, 0x1239d88, 0x46a908]]
        row += [p.read(at, 1) for at in [0x43d069, 0x43d06c]]
        row += readwords(0x46a910, 12)
        row.append(digest(struct.unpack_from('<1024H', p.memory, 0x3ebf30)))
        for i in range(2):
            a, o = A+i*0xf2c, O+i*0x1000
            for off in ACTOR_FIELDS:
                v = p.read(a+off, 1 if off == 0x19a else 4)
                row.append(v if off in [0x194, 0x19a, 0x23c] else signed(v, 32))
            row += [p.read(o+off, 4) for off in [0x104, 0x108]]
        tasks, objects = readwords(TASKS, 256*13), readwords(OBJECTS, 256*80)
        for i in range(256):
            tasks[i*13+3] = th(tasks[i*13+3]);tasks[i*13+7] = oh(tasks[i*13+7])
            objects[i*80+78] = oh(objects[i*80+78])
        row += [th(p.read(0x1232844, 4)), th(p.read(0x1232840, 4)), p.read(0x3d3a98, 4),
                digest(tasks), digest(objects), digest(map(th, readwords(0x1232440, 256))),
                digest(readwords(0x3d3698, 256)), p.read(0x3d3690, 4)]
        row += [signed(p.read(B+0x18, 4), 32), *[p.read(at, 4) for at in [0x5a9e78, 0x1553b5c, 0x1553a40, 0x123a174]], len(p.requests)]
        row += list(itertools.chain.from_iterable(p.requests))
        count = p.read(B+0x80, 4)
        row.append(count)
        for i in range(count):row += [p.read(B+0x84+i*8, 1), signed(p.read(B+0x88+i*8, 4), 32)]
        row.append(signed(p.read(B+0x120, 4), 32))
        return row

    mutable = {j for off in [0x120, 0x124, 0x130, 0x134, 0x138, 0x14c, 0x150, 0x158] for j in range(off, off+4)}

    def execute(code, label):
        before = [bytes(p.memory[A+i*0xf2c:A+(i+1)*0xf2c]) for i in range(2)]
        before_objects = [bytes(p.memory[O+i*0x1000:O+i*0x1000+320]) for i in range(2)]
        if code == 'e':
            #143b08 is called with143430's callee-saved s0=B. Later
            #rounds return before13aaf8's console/IOP branch, so the entire
            #143b54 post-console tail runs. First rounds use explicit
            #fragments ending BEFORE console/kernel I/O, never patched calls.
            p.registers[16] = B
            p.write(0x1fff000+0x30, 0x1ffff00, 8)
            if p.read(B+0x18, 4):
                call(0x143b54, kind='tail')
            else:
                call(0x143b54, stop=(0x143b5c,), kind='slice')
                call(0x13ab20, stop=(0x13ab40,), kind='slice')
                call(0x214118, stop=(0x213900,), kind='prefix_to_RPC')
                p.registers[16] = B;p.write(0x1fff000+8, 0x1ffff00, 8)
                call(0x13ab48, kind='tail')
                p.write(0x1fff000+0x30, 0x1ffff00, 8)
                call(0x143b64, kind='tail')
            result = 0
        else:
            result = call(dict(a=0x11e520, x=0x11e600, u=0x11e708, d=0x112838)[code])
        for i in range(2):
            assert all(v == before[i][j] or j in mutable for j, v in enumerate(p.memory[A+i*0xf2c:A+(i+1)*0xf2c])), (label, i, 'actor preservation')
            assert all(v == before_objects[i][j] or 0x108 <= j < 0x10c for j, v in enumerate(p.memory[O+i*0x1000:O+i*0x1000+320])), (label, i, 'body preservation')
        commands.append(code);expected.append(snapshot(th(result) if code == 'a' else 0));labels.append(label)

    def actor(rage=0, amount=0, decay=62, table=0, state=0):
        return [rage, amount, decay, 0, 20000, 46080 if rage in [1, 2] else 25600,
                (state << 16) | table, 4, 0x1000, 0, 0, 0, 0, 0, 0]

    reset(71)
    #Pauses use requested state and positive lock; every branch still updates
    #global scale. Compare the original low-word product, not widened math.
    for requested, current, lock, paused, scales in itertools.product([3, 4, 5], [3, 4, 5], [-1, 0, 1], [0, 1],
                                                                      [(256, 256), (1, 255), (0xffffffff, 257), (0x80000000, 3)]):
        configure([actor(), actor(1, 70)], requested, current, lock=lock, paused=paused, scales=scales)
        execute('u', ('gates', requested, current, lock, paused, scales))
    #Rage0..3, strict-negative expiry, raw1/36 exception and other tables.
    for rage, amount, decay, table, state, transition in itertools.product(range(4), [0, 1, 62], [0, 1, 62], range(4), [0, 21, 36], [-1, 0, 1, 2]):
        configure([actor(rage, amount, decay, table, state), actor(3-rage, amount, decay, table, state)], field08=transition)
        execute('u', ('rage', rage, amount, decay, table, state, transition))
    for case in range(1024):
        rows = []
        for i in range(2):
            rage = rng.randrange(4)
            row = actor(rage, rng.randrange(0xb801), rng.randrange(129), rng.randrange(4), rng.choice([0, 21, 36]))
            row[3] = rng.choice([0, 1, 20]);row[4] = rng.randrange(row[5]+257)
            row[7] = rng.randrange(256)
            row[9:13] = [rng.randrange(3), rng.choice([0, 0, 1, -1, 0x7fffffff, -0x80000000]),
                          signed(rng.getrandbits(32), 32), signed(rng.getrandbits(32), 32)]
            row[-2:] = [rng.choice([0, 0x30, 0x40000, 0x80000, 0xc0030]), rng.choice([0, 0x10, 0x210, 0xe10])]
            rows.append(row)
        configure(rows, field08=rng.choice([-1, 0, 1, 2]), limits=(rng.randrange(256), rng.randrange(256)))
        execute('u', ('bonus_and_cost', case))

    reset(190)
    #Real registration and repeated dispatch, including explicit duplicate
    #registration (two updates), cancellation, delayed reuse and new rounds.
    for cycle in range(48):
        configure([actor(2, 120), actor(1, 200)], limits=(50, 100))
        execute('a', ('lifecycle', cycle, 'start'))
        if cycle % 3 == 0:execute('a', ('lifecycle', cycle, 'duplicate_start'))
        for visit in range(5):execute('d', ('lifecycle', cycle, visit))
        execute('x', ('lifecycle', cycle, 'stop'))
        execute('d', ('lifecycle', cycle, 'reclaim'))
        assert p.read(0x3d3a98, 4) == 0 and th(p.read(0x1232844, 4)) == 256
    #Cancellation preserves the global pause and both array holes.
    configure([actor(), actor()], paused=1, scales=(17, 29))
    execute('x', 'stop while globally paused')
    reset(203)
    configure([actor(), actor(1, 200)])
    for index, parameter in itertools.product([0, 1, 2, -1, 0x7fffffff], [0, 17, 0xffffffff]):
        initial = [index, parameter, rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32)]
        for at, v in zip([B+0x18, 0x5a9e78, 0x1553b5c, 0x1553a40, 0x123a174], initial):p.write(at, v, 4)
        p.write(B+0x80, 1, 4);p.write(B+0x84, 3, 1);p.write(B+0x88, 17 << 8, 4);p.write(B+0x120, 91 << 8, 4)
        commands.append('R '+' '.join(str(v & 0xffffffff) for v in initial))
        execute('e', ('combat_entry', index, parameter))
        execute('d', ('combat_entry', index, 'gauge_visit'))
        execute('x', ('combat_entry', index, 'stop'))
        execute('d', ('combat_entry', index, 'reclaim'))
    output = subprocess.run([str(BINARY), str(ROOT/'work/ss6/extracted/resources')],
                            input='\n'.join(commands)+'\n', text=True, capture_output=True)
    assert output.returncode == 0, (len(output.stdout.splitlines()), output.stderr)
    actual = [list(map(int, line.split())) for line in output.stdout.splitlines()]
    assert len(actual) == len(expected), (len(actual), len(expected))
    for i, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, (i, labels[i], [(j, a, b) for j, (a, b) in enumerate(zip(got, want)) if a != b][:20])
    report = dict(status='passed', snapshots=len(expected), whole_calls=dict(counts), original_instructions=instructions,
                  continuous_lifecycles=48, elf_sha256=SOURCE_HASH, native_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                  scope='Whole unmodified11e520/11e708/11e600 and112838 with real11e760 callees, ordinary resource00/system0. Both persistent actor meter/bonus/raw state fields and body flags, original actor/body write preservation,256 task/object records, scheduler heads/tags/free count, globals46a908/910..93c/940 and scale factors,1024 palette tones. Requested-state/positive-lock/global-pause gates,32-bit product,all rage0..3 including1/36 exception,bonus wrap/limits,duplicate registration,48start/dispatch/stop/reclaim cycles. Additional15combat entries: later143b54 post-console tail; first-round explicit143b54..143b5c,13ab20..13ab40,214118 prefix ending at213900 before RPC,13ab48 tail,143b64 tail. Compare actual213878 command/argument and state fields; no whole143b08/13aaf8/214118 or IOP/audio playback claim. No patched/skipped callees. Ordinary mode byte0 and explicit player bonus-limit bytes; active charging/auxiliary explosion gauges,other systems,full actor/frame loop and hardware cadence excluded. Explicit finite FP model.')
    (ROOT/'outputs/ss6-feasibility/battle_gauges_validation.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':main()
