#!/usr/bin/env python3
"""Compare the native practice-mode settings, window and battle rules with SLPS-25559."""
import hashlib
import json
import random
import struct
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from mips_probe import signed
from extract_console_versus_art import prepare, ORIGINAL
from extract_practice_mode import build, MISC, NAME, SKILLS
from validate_practice_mode_driver import DRIVER
from validate_practice_mode_rules import rules

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/practice_mode_validation.json'
G, ACTORS, BATTLE, DESC = 0x4c3808, 0x1f00000, 0x1f10000, 0x4d7068
A, CA, B, CB, L = 0x13738a0, 0x13738d0, 0x1373900, 0x1373930, 0x1373960
STATE, MENU, KEY, LIST, SUB, DETAIL, CONFIRM = 0x12d385c, 0x12d39d8, 0x12d3a70, 0x12d3af0, 0x12d4360, 0x12d4bd0, 0x12d4c48
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)   # jr ra; move v0,zero
PROMPTS = {0x665240: 4, 0x5f2070: 2, 0x5f2098: 3}
NINTH = {0x664e98: 0, 0x664ea8: 1}
HELP = {0x182268: 0, 0x1820f8: 1, 0x182318: 2, 0x182648: 3, 0x1826b0: 4, 0x182700: 5, 0x1827c0: 6}

class Native:
    def __init__(self, exe):
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def ask(self, *words):
        self.proc.stdin.write(' '.join(map(str, words))+'\n'); self.proc.stdin.flush()
        return list(map(int, self.proc.stdout.readline().split()))
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0

class Oracle:
    """One Probe with two fixture actors, the practice battle type and the software pad."""
    def __init__(self, mode=9):
        self.p = p = prepare()
        self.n = 0; self.calls = Counter(); self.last = [0, 0]
        p.write(0x4d3d08, ACTORS, 4); p.write(0x4d3d00, BATTLE, 4)
        p.write(G, mode, 4); p.write(G+0xa0, 3, 4); p.write(0x123a0c0, 1, 1); p.write(0x443150, 1, 4)
        p.write(0x3ec73c, 1, 4)   # GS submission off; every draw routine still runs
        # Sound request, scene switch and the sound-driver stop are observed at entry and return at once.
        for at in (0x1e7b70, 0x1252f0, 0x1e7ad0): p.memory[at:at+8] = RETURN
        for seat in (0, 1):
            self.actor(seat, [0, 0]+[0]*8+[seat, int(seat != (mode == 10)), 0, 0, 0, 200, 200]+[0]*17)
    def run(self, pc, *args, limit=4000000, observe=None):
        value, count = self.p.run(pc, args, limit=limit, observe=observe)
        self.n += count; self.calls[hex(pc)] += 1
        return value
    def w(self, at): return signed(self.p.read(at, 4), 32)
    def words(self, at, n): return [self.w(at+4*i) for i in range(n)]
    def settings(self): return self.words(A, 12)+self.words(CA, 12)+self.words(B, 12)+self.words(CB, 12)+list(self.p.memory[L:L+32])
    def set_settings(self, values):
        for i, v in enumerate(values[:48]): self.p.write((A, CA, B, CB)[i//12]+4*(i % 12), v, 4)
        self.p.memory[L:L+32] = bytes(values[48:80])
    def actor(self, seat, f):
        """f = system, custom, d[8], seat, kind, behaviour, character, alternate, life, max, rage4, sword3, spirit4, time4, 244, 248."""
        p, a = self.p, ACTORS+0xf2c*seat
        h = a+0x10c
        p.write(h, f[0], 4); p.write(h+4, 0, 4); p.write(h+0xc, seat, 4)
        p.memory[DESC+16*seat:DESC+16*seat+8] = bytes(f[2:10])
        p.write(a+0xa24, f[10], 4); p.write(a+0xa20, f[11], 4); p.write(a+0xc8, f[12], 4)
        p.write(a+0xa10, f[13], 4); p.write(a+0xa14, f[13], 4); p.write(a+0x23c, 0x100000 if f[14] else 0, 4)
        p.write(a+0xa30, f[15], 4); p.write(a+0xa34, f[16], 4)
        for i, v in enumerate(f[17:32]): p.write(h+0x14+4*i, v, 4)
        p.write(a+0x244, f[32], 4); p.write(a+0x248, f[33], 4)
    def actor_row(self, seat):
        a = ACTORS+0xf2c*seat; h = a+0x10c
        return [self.w(a+0xa30), self.w(a+0xa34)]+self.words(h+0x14, 15)+[self.p.read(a+0x244, 4), self.p.read(a+0x248, 4)]
    def sample(self, held):
        for i, word in enumerate(held):
            self.p.write(0x443568+4*i, word, 4); self.p.write(0x443570+4*i, self.last[i], 4)
            self.run(0x117fd8, i)
        self.last = list(held)
    def pad(self, port): return [self.p.read(0x1237cc8+12*port+4, 4), self.p.read(0x1237cc8+12*port+8, 4)]

def random_system(rng):
    system = rng.choice((0, 1, 2, 3, 4, 5, 6, 6, 6, 7, 8))
    d = [rng.choice((0, 4, 7, 8, 9, 0xb, 0xd, 0xe, 0x18, 0x19, rng.randrange(256))) for _ in range(8)]
    return [system, int(system == 6)]+d

def settings_cases(native, rng):
    """210368/210550/210438 head, 211058 and every accessor and wrapper, over random arrays."""
    o = Oracle(); p = o.p; cases = 0
    for case in range(1500):
        mode = rng.choice((9, 10, 9, 10, 1, 2, 5, 8, 11, 12, 16, 18, 4, 0))
        p.write(G, mode, 4)
        btype = rng.choice((1, 1, 1, 0, 2)); p.write(0x123a0c0, btype, 1)
        replay, recording = rng.randrange(2), rng.randrange(2)
        p.write(0x123a0d8, replay, 4); p.write(0x123a0dc, recording, 4)
        values = [rng.randrange(0, 12) for _ in range(48)]+[rng.randrange(0, 32) for _ in range(32)]
        values[12+2] = rng.randrange(0, 11)                 # CPU TYPE, including out-of-table values
        for slot in (0, 12): values[24+slot+5] = rng.randrange(32)   # ACTION index into L
        if rng.randrange(3) == 0: values[24] = values[36] = 9
        o.set_settings(values); native.ask('X', btype, mode, replay, recording, *values)
        system = random_system(rng)
        dummy = 0 if mode == 10 else 1
        o.actor(dummy, system+[dummy, 1, 0, 0, 0, 200, 200]+[0]*17)
        h = ACTORS+0xf2c*dummy+0x10c
        want = [signed(o.run(f), 32) for f in (0x211058, 0x139c88, 0x139ce8, 0x139d20)]
        want += [signed(o.run(f, s), 32) for f in (0x139d78, 0x139dc0, 0x139e08, 0x211178, 0x211198, 0x2111b8) for s in (0, 1)]
        want += [o.run(0x2111d8), o.run(0x211150), signed(o.run(0x211160), 32)]
        want += [o.run(f) for f in (0x139388, 0x1393a0, 0x1393b8, 0x1393e0)]
        local = mode not in (3, 13, 14)
        want += [o.run(0x139488), o.run(0x1394e0), o.run(0x178f90)] if local else [0, 0, 0]
        want += [o.run(f, h) for f in (0x14fac0, 0x14fb08, 0x14fb58, 0x14fbd8, 0x14fc30)]
        want += [int(o.run(f, h) != 0) for f in (0x14eb78, 0x14ebd0)]
        got = native.ask('Q', *system)
        assert got == want, (case, mode, btype, values, system, got, want)
        op = rng.choice('RCE')
        o.run({'R': 0x210368, 'C': 0x210550}[op]) if op != 'E' else None
        if op == 'E':
            # 210438 also initialises the menu object; only its settings head is compared here.
            o.run(0x210438, MENU, 0)
        assert native.ask(op) == o.settings(), (case, op)
        cases += 1
    slots = 0
    for row in range(-1, 13):
        for value in range(-2, 14):
            assert native.ask('O', row, value) == [signed(o.run(0x2117a0, row, value), 32)]; slots += 1
    lists = 0
    for ident in list(range(-1, 80))+[100, 122]:
        first = o.run(0x15f4e8, ident); count = o.run(0x15f558, ident)
        third = o.run(0x15f518, ident, 3)
        assert native.ask('K', ident) == [(first-SKILLS)//12 if first else -1, count, (third-SKILLS)//12 if third else -1], ident
        lists += 1
    return dict(accessor_cases=cases, option_slots=slots, skill_lists=lists, instructions=o.n)

def selector_cases(native, rng):
    """Whole 20e028/20e0d0/20e128 over random flag words, ranges and pad words."""
    o = Oracle(); p = o.p; SEL, MAP = 0x1f20000, 0x1f20100
    keys = [0x10, 0x20, 0x40, 0x80, 8, 0x200, 2, 0x400, 4, 0x100000, 0x200000, 0x400000, 0x800000, 0x80000]
    flagbits = [1, 2, 4, 8, 0x10, 0x20, 0x80, 0x100, 0x200, 0x400, 0x800, 0x20000, 0x40000]
    cases = 0; codes = Counter()
    for case in range(6000):
        flags = sum(bit for bit in flagbits if rng.random() < (0.5 if bit < 8 else 0.12))
        lo, hi = rng.randrange(-3, 6), rng.randrange(-3, 110)
        step, page, value = rng.choice((0, 1, 1, 1, 2, 5)), rng.choice((-1, 0, 0, 1, 10, 200)), rng.randrange(-4, 112)
        bitmap = [rng.getrandbits(32) for _ in range(4)]
        for i, v in enumerate([flags, MAP, 0, 1, 1, value, 0]): p.write(SEL+4*i, v, 4)
        for i, v in enumerate(bitmap): p.write(MAP+4*i, v, 4)
        o.run(0x20e028, SEL, lo, hi, step, page)
        held = [0, 0]; port = rng.randrange(2)
        for _ in range(rng.randrange(1, 4)): held[port] |= rng.choice(keys)
        o.last = list(held) if rng.random() < 0.15 else [0, 0]
        o.sample(held); pressed, repeat = o.pad(port)
        sounds = []
        def obs(pc):
            if pc == 0x1e7b70:
                assert p.registers[4] & 0xffffffff == 0xffffffff; sounds.append(p.registers[5])
        # A value outside the bitmap would read past the fixture: keep the 0x800 lookups inside four words.
        current = o.w(SEL+0x14)
        if flags & 0x800 and not 0 <= current < 128: p.write(SEL, flags & ~0x800, 4); flags &= ~0x800
        ranged = o.words(SEL, 7)
        code = o.run(0x20e128, SEL, port, observe=obs)
        want = ranged[2:7]+[code, o.w(SEL+0x14)]+[len(sounds)]+sounds
        got = native.ask('S', flags, lo, hi, step, page, value, pressed, repeat, *bitmap)
        assert got == want, (case, flags, lo, hi, step, page, value, hex(pressed), hex(repeat), got, want)
        cases += 1; codes[code] += 1
    assert set(codes) == set(range(7)), codes
    return dict(selector_cases=cases, return_codes=dict(sorted(codes.items())), instructions=o.n)

class Window(Oracle):
    def __init__(self, native, rng, mode):
        super().__init__(mode)
        self.native, self.rng, self.mode, self.port = native, rng, mode, int(mode == 10)
        self.rows = 0; self.states = Counter(); self.events = Counter(); self.exits = []
        self.run(0x210368)
        native.ask('X', 1, mode, 0, 0, *self.settings())
        for seat in (0, 1): self.push_actor(seat, self.default_actor(seat))
        self.help = []
        self.names = {self.p.read(SKILLS+12*i+8, 4) for i in range(833)}
        self.run(0x17f5a0, observe=self.observer({}))
        native.ask('N')
        self.compare(native.ask('I'), [], {}, 'init')
    def default_actor(self, seat):
        return [0, 0]+[0]*8+[seat, int(seat != self.port), 0, 0, 0, 200, 200]+[0]*17
    def push_actor(self, seat, f):
        self.actor(seat, f); self.native.ask('A', seat, *f)
    def observer(self, info):
        p = self.p
        def obs(pc):
            r = p.registers
            if pc == 0x1e7b70:
                # Requests made between 17f7f0 and 17f838 belong to the four opaque sub-window updates.
                assert r[4] & 0xffffffff == 0xffffffff
                info.setdefault('opaque_sounds' if info.get('opaque') else 'sounds', []).append(r[5] & 0xffffffff)
            elif pc == 0x17f7f0: info['opaque'] = True
            elif pc == 0x1252f0:
                assert (r[4], r[5], r[6]) == (2, 0, 0x139778); info['exit'] = {0x128008: 1, 0x127940: 2}[r[7]]
            elif pc == 0x1e7ad0: info['stop'] = 1
            elif pc == 0x142168: info['lock'] = 1
            elif pc == 0x1772d0: info['clear'] = 1
            elif pc == 0x17f7fc: info['key'] = signed(r[2], 32)
            elif pc == 0x17f810: info['list'] = signed(r[2], 32)
            elif pc == 0x17f824: info['sub'] = signed(r[2], 32)
            elif pc == 0x17f838: info['detail'] = signed(r[2], 32); info['cursor'] = self.w(0x12d3b54); info['opaque'] = False
            elif pc in (0x20e8c0, 0x20eae0) and 0x17f790 <= r[31] < 0x180260: info['fill'] = 1
            elif pc == 0x210138 and 0x17f790 <= r[31] < 0x180260: info['open'] = 1
            elif pc == info.get('help_ra'): info['help_ra'] = None
            elif pc in HELP and not info.get('help_ra'):
                # Only requests issued by the ported functions. Until the request returns, the help object's own
                # nested lookups (182268 and 1827c0 tail-call 1820f8/182268) are internal and ignored.
                ra = r[31]
                if 0x17f5a0 <= ra < 0x180260 or 0x210368 <= ra < 0x2118a0:
                    info['help_ra'] = ra
                    a1, a2 = signed(r[5], 32), signed(r[6], 32)
                    kind = HELP[pc]
                    if kind == 1: self.help += [1, self.skill_by_name(a1), 0]
                    elif kind in (0, 6): self.help += [kind, a1, a2]
                    elif kind == 2: self.help += [2, a1, 0]
                    else: self.help += [kind, 0, 0]
        return obs
    def skill_by_name(self, pointer):
        if pointer == 0x664e18: return -1
        dummy = ACTORS+0xf2c*(0 if self.mode == 10 else 1)
        ident = self.w(dummy+0xa10)+(0x32 if self.p.read(dummy+0x23c, 4) & 0x100000 else 0)
        index = self.p.memory[L+self.w(MENU+0x8c)]
        # Read-only table walk: an observer must not start a nested Probe run.
        record = SKILLS
        while signed(self.p.read(record, 2), 16) != ident: record += 12
        record += 12*index
        assert self.p.read(record+8, 4) == pointer
        return (record-SKILLS)//12
    def slide(self, at): return self.words(at, 13)
    def selector(self, at): return [self.p.read(at, 4)]+self.words(at+8, 5)
    def row(self):
        p = self.p
        row = self.words(STATE, 5)
        row += self.words(MENU+0xc, 4)+self.slide(MENU+0x1c)+self.selector(MENU+0x50)+self.selector(MENU+0x78)
        row += [p.memory[MENU+0x6c], self.w(MENU+0x70), self.w(MENU+0x74)]
        ninth = p.read(0x59cdec, 4)
        row += [NINTH.get(ninth, -1)]
        row += self.words(CONFIRM+0xc, 4)+self.slide(CONFIRM+0x1c)+self.selector(CONFIRM+0x50)+[PROMPTS[p.read(CONFIRM+0x6c, 4)]]
        row += self.words(KEY, 2)+self.slide(KEY+0xc)
        for base in (LIST, SUB): row += self.words(base+0x14, 2)+self.slide(base+0x1c)
        row += self.words(DETAIL+0x14, 2)
        row += [int(p.read(0x123a0d8, 4) != 0), int(p.read(0x123a0dc, 4) != 0)]+self.settings()
        return row
    def compare(self, got, tail, info, label):
        want = self.row()+tail
        for seat in (0, 1): want += self.actor_row(seat)
        want += [len(self.help)//3]+self.help
        assert got == want, (self.mode, label, self.rows, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:12], len(got), len(want))
        self.rows += 1
    def tick(self, key=0, other=0, label=''):
        p = self.p
        held = [other, key] if self.port else [key, other]
        self.sample(held)
        paused = self.rng.random() < 0.15       # hit-stop already requested a pause this frame
        p.write(0x123a0c4, int(paused), 4); p.write(0x123a0cc, 0, 4); p.write(0x123a0d4, 7, 4)
        for at in (0x345178, 0x345180): p.write(at, 0, 4)
        info = {}; self.help = []
        self.run(0x17f790, limit=30000000, observe=self.observer(info))
        sounds = info.get('sounds', [])
        tail = self.pad(self.port)+[len(sounds)]+sounds
        tail += [p.read(0x123a0c4, 4) if not paused else int(self.w(STATE) > 0), p.read(0x123a0cc, 4), info.get('lock', 0),
                 info.get('clear', 0), info.get('fill', 0), info.get('open', 0), info.get('exit', 0)]
        if not paused: assert p.read(0x123a0c4, 4) == int(self.w(STATE) > 0), (p.read(0x123a0c4, 4), self.words(STATE, 2), self.rows)
        if p.read(0x123a0cc, 4): assert p.read(0x123a0d4, 4) == 0
        if 'exit' in info:
            assert info.get('stop') and self.w(G+0x18) == 1; self.exits.append(info['exit'])
            if info['exit'] == 1: assert [self.w(0x456890+o) for o in (0x10, 0x40, 0x2c, 0x5c)] == [0]*4
        got = self.native.ask('T', *held, *self.last_edges, int(paused), info['key'], info['list'], info['sub'], info['detail'], info['cursor'])
        self.compare(got, tail, info, label or hex(key))
        self.states[self.w(STATE)] += 1; self.events['opaque_sounds'] += len(info.get('opaque_sounds', []))
        for name in ('key', 'list', 'sub', 'detail'):
            if info[name]: self.events[f'{name}:{info[name]}'] += 1
    def sample(self, held):
        self.last_edges = [held[i] & ~self.last[i] for i in (0, 1)]
        super().sample(held)
    def tap(self, key, wait=1):
        self.tick(key)
        for _ in range(wait): self.tick()
    def state(self): return self.w(STATE)
    def randomize_actors(self):
        rng = self.rng
        for seat in (0, 1):
            kind = int(seat != self.port)
            character = rng.randrange(0, 42); alternate = int(rng.random() < 0.1 and self.p.run(0x15f4e8, [character+0x32])[0] != 0)
            count = self.p.run(0x15f558, [character+(0x32 if alternate else 0)])[0]
            behaviour = rng.choice((0, 1, 9, 0x23, 0x24, 0x25, 0x26+rng.randrange(max(1, min(count, 32))), 0x26, 0x46, 0x10))
            f = random_system(rng)+[seat, rng.choice((kind, kind, kind, 1-kind)), behaviour, character, alternate,
                                    rng.choice((0, 1, 100, 199, 200, 201, 5000)), rng.randrange(0, 300)]
            f += [rng.choice((0, 1, 2, 3)), rng.randrange(0x10000), rng.randrange(4), rng.randrange(4)]
            f += [rng.randrange(4), rng.randrange(0x10000), rng.randrange(0x10000)]
            f += [rng.choice((0, 2, 3, 4)), rng.randrange(0x10000), rng.randrange(4), rng.randrange(4)]
            f += [rng.choice((0, 0, 1, 2)), rng.randrange(0x10000), rng.randrange(4), rng.randrange(0x10000)]
            f += [rng.getrandbits(32), rng.getrandbits(32)]
            self.push_actor(seat, f)

UP, DOWN, LEFT, RIGHT, OK, CANCEL, MENUKEY = 0x10, 0x20, 0x40, 0x80, 0x200, 0x400, 0x80000

def scripted(native, rng, mode):
    w = Window(native, rng, mode)
    for _ in range(18): w.tick()
    assert w.state() == 1 and w.w(MENU+0x18) == 1
    def until(done, key, label):
        for _ in range(40):
            if done(): return
            w.tap(key() if callable(key) else key)
        raise AssertionError((label, w.state(), w.w(MENU+0x64), w.w(MENU+0x70), w.w(MENU+0x8c), w.w(MENU+0x18)))
    def goto(row):
        until(lambda: w.w(MENU+0x64) == row, lambda: DOWN if (row-w.w(MENU+0x64)) % 12 <= 6 else UP, ('row', row))
    # Every row: values to both ends with wrap, cancel restores, confirm commits.
    for row, count in ((2, 9), (3, 4), (5, 14), (6, 2)):
        goto(row); w.tap(OK, 2)
        assert w.w(MENU+0x70) == 1
        for _ in range(count+1): w.tap(RIGHT)
        w.tap(LEFT); w.tap(LEFT); w.tap(CANCEL, 2)
        assert w.w(MENU+0x70) == 0 and w.w(A+4*row) == w.w(CA+4*row)
        w.tap(OK, 2); w.tap(RIGHT); w.tap(OK, 2)
        if w.w(MENU+0x70) == 2: w.tap(OK, 2)      # CPU TYPE with an option list
        assert w.w(MENU+0x70) == 0
    # CPU TYPE: every type and every second-level option, with all three dummy capability classes.
    for system in ([0, 0], [3, 0], [2, 0], [6, 1]):
        w.randomize_actors()
        dummy = 0 if mode == 10 else 1
        f = system+([0, 0, 0, 0xd, 0, 0, 0, 0] if system[1] else [0]*8)+[dummy, 1, 0, rng.randrange(0, 42), 0, 200, 200]+[0]*17
        w.push_actor(dummy, f)
        goto(2)
        for kind in range(9):
            w.tap(OK, 2)
            until(lambda: w.w(MENU+0x8c) == kind, RIGHT, ('type', kind))
            w.tap(OK, 2)
            if kind < 6:
                assert w.w(MENU+0x70) == 2
                for _ in range(w.w(MENU+0x84)+1): w.tap(RIGHT)
                w.tap(0x800000); w.tap(0x200000); w.tap(LEFT); w.tap(CANCEL, 2); w.tap(OK, 2)
                for _ in range(rng.randrange(0, 12)): w.tap(RIGHT)
                w.tap(OK, 2)
            assert w.w(MENU+0x70) == 0, kind
    # GAUGE SETTING: vertical cursor, six second-level ranges, page keys, held-direction repeat.
    goto(4); w.tap(OK, 2)
    for sub in range(6):
        w.tap(OK, 2); assert w.w(MENU+0x70) == 2
        for key in (RIGHT, RIGHT, 0x400000, 0x400000, 0x100000, LEFT, LEFT, 0x800000, RIGHT, 0x200000, LEFT):
            w.tap(key)
        for _ in range(26): w.tick(RIGHT)
        w.tick(); w.tap(CANCEL, 2); w.tap(OK, 2)
        for _ in range(rng.randrange(1, 30)): w.tap(rng.choice((LEFT, RIGHT, 0x400000)))
        w.tap(OK, 2); assert w.w(MENU+0x70) == 1
        w.tap(DOWN)
    w.tap(UP); w.tap(CANCEL, 2)
    w.randomize_actors()
    # Window off, reopen by any key, hide and close (snap), reopen with the menu button.
    goto(9); w.tap(OK, 3); assert w.state() == 2
    w.tap(0x100, 3); assert w.state() == 2      # not in the wake mask f006fe
    w.tap(LEFT, 3); assert w.state() == 1
    w.tap(OK, 3); w.tap(MENUKEY, 3); assert w.state() == 0
    w.tap(MENUKEY, 18); assert w.state() == 1
    # PRACTICE START, reopen, cancel-close with and without a changed dummy type.
    goto(0); w.tap(OK, 18); assert w.state() == 0 and w.w(0x12d3868) != -1
    w.tap(MENUKEY, 18); w.tap(CANCEL, 18); assert w.state() == 0
    for kind in (8, 7, 6, 8):
        w.tap(MENUKEY, 18); goto(2); w.tap(OK, 2)
        until(lambda: w.w(MENU+0x8c) == kind, RIGHT, ('close type', kind))
        w.tap(OK, 2); w.tap(MENUKEY if kind == 7 else CANCEL, 18)
        assert w.state() == 0
        w.randomize_actors()
    # CPU RECORDING, then leave recording through a plain close.
    w.tap(MENUKEY, 18); goto(1); w.tap(OK, 18)
    assert w.p.read(0x123a0dc, 4) == 1 and w.state() == 0
    for _ in range(4): w.randomize_actors(); w.tick()
    w.tap(MENUKEY, 18); w.tap(CANCEL, 18); assert w.p.read(0x123a0dc, 4) == 0
    w.tap(MENUKEY, 18); goto(1); w.tap(OK, 18)
    # Key configuration and the skill list are opaque; their real event codes drive the ported machine.
    def reach(target, *keys):
        # The sub-windows are not ported: try the given keys until their own logic reports the transition.
        for _ in range(6):
            for key in keys:
                w.tap(key, 18)
                if w.state() == target: return
        raise AssertionError(('unreached', target, w.state()))
    w.tap(MENUKEY, 18); goto(8); w.tap(OK, 18); assert w.state() == 5
    w.tap(DOWN); w.tap(UP); w.tap(UP)
    reach(1, OK, MENUKEY)                       # EXIT row or the menu button
    for seat in (0, 1): w.push_actor(seat, w.default_actor(seat))
    goto(7); w.tap(OK, 18); assert w.state() == 6
    w.tap(DOWN); w.tap(UP)
    reach(7, OK); w.tap(DOWN); reach(8, OK, DOWN)
    w.tap(DOWN); reach(7, CANCEL, OK); reach(6, CANCEL)
    w.tap(DOWN); reach(7, OK); reach(6, CANCEL); reach(1, CANCEL)
    # Both exits: NO returns to the menu, YES requests the scene.
    exit_row = 10 if mode == 9 else 11
    goto(exit_row); w.tap(OK, 18); assert w.state() == 3
    w.tap(OK, 18); assert w.state() == 1
    w.tap(OK, 18); w.tap(CANCEL, 18); assert w.state() == 1
    w.tap(OK, 18); w.tap(LEFT); w.tap(RIGHT); w.tap(LEFT); w.tap(OK, 6)
    assert w.state() == 4 and w.exits == [1 if mode == 9 else 2]
    return w

def randomized(native, rng, mode, frames):
    w = Window(native, rng, mode)
    keys = [UP, DOWN, LEFT, RIGHT, OK, CANCEL, 2, 4, 8, MENUKEY, 0x100000, 0x400000, 0x200000, 0x800000, 0x100, 1]
    weight = [8, 14, 8, 12, 14, 5, 2, 1, 2, 3, 2, 3, 1, 1, 1, 1]
    held = 0
    for frame in range(frames):
        if w.state() == 4:
            # Exit requested: start a new battle scene with the same settings, as the game does.
            w.run(0x17f5a0, observe=w.observer({})); w.help = []
            native.ask('I')
        r = rng.random()
        if r < 0.35: held = 0
        elif r < 0.75: held = rng.choices(keys, weight)[0]
        elif r < 0.8: held |= rng.choices(keys, weight)[0]
        if rng.random() < 0.05: w.randomize_actors()
        w.tick(held, rng.choice((0, 0, 0, OK, MENUKEY, DOWN)))
    return w

def window_job(spec):
    exe, mode, kind, seed = spec
    native = Native(exe); rng = random.Random(seed)
    try:
        w = scripted(native, rng, mode) if kind == 'scripted' else randomized(native, rng, mode, 1300)
    except BaseException:
        # Surface the failure at once; the pool only reports it after every job has ended.
        print(f'window job {mode} {kind} failed', file=sys.stderr); traceback.print_exc(); sys.stderr.flush(); raise
    print(f'window job {mode} {kind}: {w.rows} frames', file=sys.stderr, flush=True)
    native.close()
    return dict(mode=mode, kind=kind, frames=w.rows, states=dict(sorted(w.states.items())), opaque_events=dict(sorted(w.events.items())),
                exits=w.exits, original_calls=dict(w.calls), instructions=w.n)

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = build(raw)[0]
    assert (ASSETS/NAME).read_bytes() == asset, 'run extract_practice_mode.py'
    rng = random.Random(0x17f790)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'practice.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/practice_mode.cpp',
                        ROOT/'src/console_menu.cpp', ROOT/'src/game_random.cpp', '-o', exe], check=True)
        report = dict(status='passed', elf_sha256=ORIGINAL, asset_sha256=hashlib.sha256(asset).hexdigest())
        with ProcessPoolExecutor(4) as pool:
            jobs = pool.map(window_job, [(exe, mode, kind, 0x17f790+mode+len(kind)) for kind in ('scripted', 'random') for mode in (9, 10)])
            native = Native(exe)
            report['settings'] = settings_cases(native, rng)
            report['selector'] = selector_cases(native, rng)
            report['rules'] = rules(native, rng, Oracle, ACTORS, BATTLE)
            native.close()
            windows = list(jobs)
        report['window'] = windows
    assert {int(s) for w in windows for s in w['states']} == set(range(9))
    assert sorted(e for w in windows if w['kind'] == 'scripted' for e in w['exits']) == [1, 2]
    report['original_instructions'] = (report['settings']['instructions']+report['selector']['instructions']
                                       + sum(w['instructions'] for w in windows)+report['rules']['instructions'])
    report['scope'] = (
        'Whole original 210368, 210550, 210438, 211058, 2117a0, the 139c88..139e08 wrappers, 139488/1394e0/178f90, the 14fac0.. '
        'capability predicates, 15f4e8/15f518/15f558, 20e028/20e0d0/20e128, and the complete 17f5a0 init and 17f790 per-frame window '
        '(210630 menu, 2128f8 dialog, entry/update handlers, 180260 for both fixture actors) driven through the software pad sampler '
        '117fd8. Stubbed with jr ra and observed at entry: 1e7b70 (sound request), 1252f0 (scene switch), 1e7ad0 (sound-driver stop). '
        'GS submission is disabled by 3ec73c; every draw routine still executes. The key-configuration window, skill list, sub-list and '
        'detail window run unmodified in the original; the native module receives their returned event codes and the list cursor as inputs '
        'and is compared on the slide/active/focus words it owns. Rules: whole 151968 (non-negative pending damage), 1418f8, 139550, '
        '139578, 139588, 13a160, 13a1b0, 13a030, 141dd0 (sprintf arguments), 141820, 134e48; explicit stop-before slices, not whole '
        'functions, for 14959c..1495ec, 1495e8..149618, 13fbe0..13fc18, 145068..144fd0, 172158..172220, 149634..1496ac, 149790..1497d0, '
        '13fb2c..13fbd4 and 12dbd0..12dc30. Actors, battle block and select records are memory fixtures, not a running battle or scene.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    frames = sum(w['frames'] for w in windows)
    print(f"practice mode: {report['settings']['accessor_cases']} accessor cases, {report['selector']['selector_cases']} selector cases, "
          f"{frames} window frames (all 9 states, both exits, modes 9/10), {report['rules']['cases']} rule cases; "
          f"{report['original_instructions']} original instructions")

if __name__ == '__main__': main()
