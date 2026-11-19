#!/usr/bin/env python3
"""Compare the Japanese gauge task, contact awards and round resets with native versus."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from validate_collisions import ACTORS, OBJECTS, QUEUE
from validate_dash_motion import ASSETS, ELF, PIN, PROBE, ROOT, digest
from validate_finishing_blow import mirror
from validate_haohmaru_special import ContactOracle, pads_for
from validate_input_lifecycle import Boundary

MATCH = PROBE.with_name('ss6-match-replay')
REPORT = ROOT / 'outputs/ss6-feasibility/versus_rage_validation.json'
BATTLE = 0x1b80000
OFFSETS = (0x120, 0x124, 0x128, 0x130, 0x134, 0x138)


def inputs(kind, slot):
    if kind in ('carry-active', 'carry-partial'):
        walk, wait = (35, 120) if kind == 'carry-active' else (70, 220)
        sequence = [(walk, 128, 0), (3, 0, 0), (1, 1024, 0), (wait, 0, 0)] * 6
        sequence += [(850, 0, 0)]
    elif kind == 'block-to-full':
        # All three 623+B records contact a standing guard. Release before
        # walking together again so previous guard and attack have recovered.
        special = [(1, mask, 128) for mask in pads_for(69, 0)]
        sequence = ([(35, 128, 64), (4, 0, 0)] + special + [(55, 0, 128), (60, 0, 0)]) * 31
        sequence.append((500, 0, 0))
    else:
        sequence = [(60, 64, 128), (3, 0, 0), (1, 1024, 0), (160, 0, 0),
                    (120, 128, 64), (3, 0, 0), (1, 1024, 0), (4, 0, 0), (40, 0, 128), (180, 0, 0)]
    if slot:
        sequence = [(n, mirror(b), mirror(a)) for n, a, b in sequence]
    return '500 0 0\n' + ''.join(f'1 {a} {b}\n' * n for n, a, b in sequence)


def load_rows(exe, mode, pads):
    result = subprocess.run([exe, ASSETS, mode], input=pads, text=True, capture_output=True, check=True)
    return [line.split() for line in result.stdout.splitlines()]


class OriginalGauges:
    def __init__(self):
        self.geo = ContactOracle()
        self.p = self.geo.probe
        self.counts = Counter()
        self.instructions = 0
        self.p.write(0x1239d84, 256, 4)
        self.p.write(0x1239d88, 256, 4)
        for slot in range(2):
            a = ACTORS + 0xf2c * slot
            self.p.write(a, OBJECTS[slot], 4)
            self.p.write(a+0xa24, slot, 4)
            self.p.write(a+0x110, slot, 4)
            self.run(0x14ec80, a+0x10c)

    def run(self, pc, *args, end=None):
        stops = Boundary(end) if end is not None else ()
        result, n = self.p.run(pc, args, limit=500_000, stop_before=stops)
        if end is not None:
            assert stops.stopped == end
        self.instructions += n
        self.counts[hex(pc)] += 1
        return result

    def meters(self, slot):
        a = ACTORS + 0xf2c * slot
        return [self.p.read(a+off, 4) for off in OFFSETS]

    def tick(self, previous, field):
        p = self.p
        for i, off in ((46, 0), (1, 4), (47, 8), (48, 0x108)):
            p.write(BATTLE+off, int(field[i]), 4)
        p.write(0x46a940, int(field[49]), 4)
        for i in range(2):
            a, o = ACTORS + i*0xf2c, OBJECTS[i]
            col = 23 + 26*i
            p.write(a+0x194, int(previous[3+10*i]) | (int(previous[4+10*i]) << 16), 4)
            p.write(a+0x19a, int(previous[col+10]), 1)
            p.write(a+0x23c, int(previous[col+5]), 4)
            p.write(o+0x104, int(previous[col+3]), 4)
            p.write(o+0x108, int(previous[col+4]), 4)
        for _ in range(int(field[50])):
            self.run(0x11e708)

    def contact(self, previous, slot):
        p = self.p
        for side in range(2):
            a = ACTORS + 0xf2c*side
            before = self.meters(side)
            self.geo.install_player(previous, side)
            # The collector consumes the previous geometry. Preserve EE meter
            # state just produced by this tick's earlier priority-5 update.
            for off, value in zip(OFFSETS, before):
                p.write(a+off, value, 4)
            p.write(a+0x110, side, 4)
        p.write(0x12d2698, 0, 4)
        for a, b in (OBJECTS, OBJECTS[::-1]):
            self.run(0x1536e8, a, b)
        self.run(0x1544a0)
        for i in range(p.read(0x12d2698, 4)):
            e = QUEUE + 108*i
            if p.read(e, 4) != 7 or p.read(e+0x40, 4) != OBJECTS[slot]:
                continue
            assert not (p.read(OBJECTS[slot]+0x104, 4) & 0x06000000)
            guard = self.run(0x155850, e)
            if guard:
                self.run(0x155d50, e, 0, guard, end=0x155e90)
            else:
                self.run(0x155a88, e, 0, end=0x155bb8)
            victim = ACTORS + (1-slot)*0xf2c
            return guard, p.read(victim+0xa38, 4), p.read(e+0x10, 4)
        raise AssertionError(('No original body contact', previous[0], slot))


def check(arg):
    exe, kind, slot = arg
    pads = inputs(kind, slot)
    all_rows = load_rows(exe, '--contact-fields', pads)
    fields = load_rows(exe, '--rage-fields', pads)
    assert len(fields) == len(all_rows) and len(fields[0]) == 51
    oracle = OriginalGauges()
    assert all(oracle.meters(i) == [0,0,0,0,25600,25600] for i in range(2))
    log, changes, carries = [], [], []
    freeze, decay, after_round, checked = 0, 0, 0, 0
    victim = 1-slot
    for prev, now, field, after in zip(all_rows, all_rows[1:], fields, fields[1:]):
        assert after[:23] == now[:23]
        frame = int(now[0])
        prior = oracle.meters(victim)
        oracle.tick(prev, field)
        pre_contact = oracle.meters(victim)
        if prior[0] == 1:
            if int(prev[3+10*victim]) == 2:
                assert pre_contact[:2] == prior[:2]
                freeze += 1
            if pre_contact[1] < prior[1]:
                decay += 1
        for attacker in range(2):
            col = 10+attacker*10
            counts = list(map(int, now[col:col+2]))
            if counts == list(map(int, prev[col:col+2])):
                continue
            assert attacker == slot
            defense, damage, base = oracle.contact(prev, attacker)
            assert counts[bool(defense)] == int(prev[col+bool(defense)])+1
            before_life, after_life = int(prev[9+10*victim]), int(now[9+10*victim])
            assert min(damage, before_life) == before_life-after_life,(kind,slot,frame,damage,before_life,after_life)
            log.append(dict(frame=frame, attacker_state=int(prev[4+10*slot]), guard=defense,
                            health_damage=before_life-after_life, calculated_damage=damage, auxiliary=base,
                            before=pre_contact[:2], after=oracle.meters(victim)[:2]))
        if int(field[1]) != 1 and int(after[1]) == 1 and int(after[45]) > 0:
            for side in range(2):
                oracle.run(0x14ec80, ACTORS+side*0xf2c+0x10c)
            carries.append(dict(frame=frame, phase=oracle.meters(victim)[0], amount=oracle.meters(victim)[1],
                                decay=oracle.meters(victim)[2], life=int(now[9+10*victim])))
        for side in range(2):
            a = ACTORS + side*0xf2c
            if int(prev[3+10*side]) == 1 and prev[3+10*side:5+10*side] != now[3+10*side:5+10*side]:
                oracle.run(0x14f1a0, a+0x10c)
            off = 23+11*side
            actual = list(map(int, after[off:off+6]))
            expected = oracle.meters(side)
            assert actual == expected, (kind, slot, frame, side, actual, expected, prev[3+10*side:6+10*side], now[3+10*side:6+10*side],field[45:51])
        current = oracle.meters(victim)
        if current[0] != prior[0]:
            changes.append(dict(frame=frame,before=prior[0],phase=current[0],amount=current[1],
                                decay=current[2],sword_capacity=current[5],round=int(after[45])+1))
        if int(after[45]) > 0:
            after_round += 1
        checked += 1
    if kind == 'ordinary-guard':
        assert len(log) == 1 and log[0]['guard'] and log[0]['after'] == [0,0] and not changes
    else:
        assert [r['phase'] for r in changes] == [1,0] and changes[0]['amount'] == 47104
        assert changes[0]['decay'] == 112 and (changes[0]['sword_capacity'], changes[1]['sword_capacity']) == (46080, 25600)
        assert decay == 421 and freeze > 0
        if kind == 'block-to-full':
            assert len(log) == 93 and all(r['guard'] and r['health_damage']==1 for r in log)
            assert all(r['after'][1]-r['before'][1] == 512 for r in log[:92]) and log[91]['after']==[1,47104]
        else:
            assert len(carries)==1 and carries[0]['life']==200 and after_round>200
            assert carries[0]['phase'] == int(kind=='carry-active') and carries[0]['amount'] > 0
    return dict(mode=kind, attacker=slot+1, frames_checked=checked, active_meter_decrements=decay,
                active_damage_state_updates=freeze, second_round_updates=after_round,
                phase_changes=changes, round_carry=carries, contacts=log, original_calls=oracle.counts,
                original_instructions=oracle.instructions)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe', type=Path, default=MATCH)
    parser.add_argument('--jobs', type=int, default=4)
    args=parser.parse_args()
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        exe=Path(tmp)/'match'
        shutil.copy2(args.exe, exe)
        with ProcessPoolExecutor(args.jobs) as pool:
            modes=('ordinary-guard','carry-active','carry-partial','block-to-full')
            results=list(pool.map(check, ((exe, mode, side) for mode in modes for side in range(2))))
        data=dict(status='passed', elf_sha256=PIN, native_sha256=digest(exe), validator_sha256=digest(Path(__file__)),
                  scope='Real neutral-start resource 00/system 0 native versus pads on both sides. Original priority-5 gauge callback, JDG/defense/award on native positions and original round reset. Compare rage phase, amount, decay, sword wait/current/cap after every update from first-round neutral. Original finite floating-point model. Ordinary guard/whiff, repeated special guard to full, natural expiry, KO and second-round carry.',
                  cases=results)
    REPORT.write_text(json.dumps(data, indent=2)+'\n')
    print(len(results), 'replays;', sum(r['frames_checked'] for r in results),'matched meter updates')


if __name__ == '__main__':
    main()
