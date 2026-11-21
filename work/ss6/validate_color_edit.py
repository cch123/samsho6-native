#!/usr/bin/env python3
"""Run the COLOR EDIT coroutine 13b1c8 of SLPS-25559 visit by visit and compare the native scene."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import random
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from extract_collision_tables import SOURCE_HASH

ROOT = Path(__file__).resolve().parents[2]
ELF = ROOT/'work/ss6/extracted/SLPS_255.59'
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/color_edit_validation.json'
TASK, YIELD = 0x13b1c8, 0x112a28
TOP = 0x12621c0+0x4000          # 13b100: task stack 12621c0, size 4000
SP = TOP-0x1d90
TABLE, PAL_ALL, OPTION = 0x5735cc, 0x3f8a40, 0x43d058      # 13cc44: lui 40, addiu -75c0
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)   # jr ra; move v0, zero
# Rendering, resource loading, sound, memory card and scene switch. The
# screen frame 1822a0 (title, header, help and hint lines) is a draw-side
# widget of several menu scenes; its calls are recorded, not executed.
FRAME = (0x1822a0, 0x182318, 0x182648, 0x1826b0, 0x1825b8, 0x1827c0, 0x1827d8, 0x1827f0, 0x182828, 0x181c10, 0x182600)
DRAW = (0x20c038, 0x20f680, 0x20fb58, 0x20ef38, 0x20f360, 0x2129d0)
PREVIEW = (0x13f8a8, 0x11d448, 0x11d4f8, 0x11d488, 0x11d528, 0x11d668, 0x11d570, 0x11d908, 0x17eab0)
PREVIEW_UPDATE = (0x13bf00, 0x13bfd0, 0x13c4f8)
SERVICES = (0x1e7b70, 0x10f158, 0x1252f0)
OBJECTS = 0x1e00000
PANELS = (0x190, 0xa00, 0x1270, 0x1ae0, 0x1b70, 0x1c20, 0x1cc0)
SELECT = 0x80000
EVENTS = 218                    # row index of the request count

DRIVER = r'''
#include "color_edit.hpp"
#include "console_menu.hpp"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
static uint32_t crc(uint32_t c,const void* data,size_t n) {
    auto p=static_cast<const uint8_t*>(data);c=~c;
    while(n--){c^=*p++;for(int k=0;k<8;++k)c=(c>>1)^(0xedb88320u&(0u-(c&1)));}
    return ~c;
}
int main(int,char** argv) {
    using namespace ss6;
    ColorEditTables tables(argv[1]);
    SystemData data(argv[1]);
    std::ifstream in(std::string(argv[1])+"/pal_all.bin",std::ios::binary);
    std::vector<uint8_t> pal((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
    StandaloneEditPaletteCache cache(tables,data,pal);
    std::unique_ptr<ColorEdit> s;
    MenuPadRepeat repeat;
    std::array<uint32_t,2> last{};
    unsigned seat=0;
    char op;long long a,b,c,d,e;
    while(std::cin>>op>>a>>b>>c>>d>>e) {
        if(op=='L')data.option(0x16+size_t(a))=uint8_t(b);
        else if(op=='B'){seat=unsigned(a);s=std::make_unique<ColorEdit>(tables,data,pal,cache);}
        else if(op=='K') {
            const auto r=resolveEditPaletteSource(tables,uint32_t(a),int(b));
            std::cout<<int(r.table)<<' '<<r.group<<' '<<r.identity<<' '<<r.bank<<'\n';
        } else if(op=='P'||op=='Q') {
            const auto r=op=='P'?colorEditSprite(tables,int(a),b!=0,int(c),int(d),int(e)):colorEditCheckPose(tables,int(a),b!=0,int(d),int(c),int(e));
            uint32_t x,y;std::memcpy(&x,&r.x,4);std::memcpy(&y,&r.y,4);
            std::cout<<r.hidden<<' '<<x<<' '<<y<<' '<<r.action<<' '<<r.record<<' '<<r.flip<<' '<<r.paletteKey<<'\n';
        } else if(op=='S') {
            std::cout<<selectedPaletteKey(unsigned(a),unsigned(b),unsigned(c),d!=0)<<'\n';
        } else if(op=='T') {
            const std::array<uint32_t,2> held{uint32_t(a),uint32_t(b)};
            const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});
            last=held;
            const auto& events=s->tick({held[seat],pads[seat].pressed,pads[seat].repeat});
            auto& o=std::cout;
            o<<s->state()<<' '<<s->nextState()<<' '<<s->portrait<<' '<<s->portraitEnabled<<' '<<s->spriteLoaded;
            for(const ColorEdit::Panel* w:{&s->characterMenu,&s->colourMenu,&s->copyMenu,&s->partPanel,&s->swatchPanel,&s->sliderPanel,&s->dialog}) {
                const auto& l=w->list;const auto& m=w->slide;
                o<<' '<<w->visibleRows<<' '<<w->scroll<<' '<<w->visible<<' '<<w->active<<' '<<m.x<<' '<<m.y<<' '<<m.remaining<<' '<<m.state
                 <<' '<<m.targetX<<' '<<m.targetY<<' '<<l.flags<<' '<<l.min<<' '<<l.max<<' '<<l.step<<' '<<l.cursor<<' '<<l.page;
            }
            o<<' '<<s->partCharacter<<' '<<s->partRows;
            for(int v:s->partId)o<<' '<<v;
            o<<' '<<s->partPanel.list.disabled;
            for(auto v:s->swatch)o<<' '<<v;
            const auto& v=s->valueList;
            o<<' '<<v.flags<<' '<<v.min<<' '<<v.max<<' '<<v.step<<' '<<v.cursor<<' '<<v.page;
            for(auto f:s->field)o<<' '<<unsigned(f);
            for(auto f:s->backup)o<<' '<<unsigned(f);
            o<<' '<<s->clipboard<<' '<<s->highlight;
            const auto& p=s->preview;
            o<<' '<<p.portraitVisible<<' '<<p.colour<<' '<<p.spriteVisible<<' '<<p.part<<' '<<p.x0<<' '<<p.poseVisible<<' '<<p.pose;
            for(auto id:s->characterIds)o<<' '<<id;
            o<<' '<<crc(0,data.image().data()+4,0x6180);
            uint32_t k=crc(0,cache.identity.data(),96);k=crc(k,cache.reference.data(),96);k=crc(k,cache.colours.data(),1024);
            o<<' '<<k<<' '<<events.size();
            for(const auto& ev:events)o<<' '<<int(ev.kind)<<' '<<ev.a<<' '<<ev.b<<' '<<ev.c;
            o<<'\n';
        }
    }
}
'''

class Boundary:
    def __init__(self, *addresses): self.addresses, self.stopped = addresses, None
    def __contains__(self, pc):
        if pc in self.addresses: self.stopped = pc; return True
        return False

def machine(locks=()):
    p = Probe(ELF.read_bytes())
    buffered_stdout(p)
    image = bytearray((ASSETS/'save_default.bin').read_bytes())
    for character, value in locks: image[0x618c+0x16+character] = value
    p.memory[0x5735c8:0x5735c8+len(image)] = image
    p.memory[OPTION:OPTION+0x98] = image[0x618c:0x6224]      # 1b8b88 unpacks g_GameOption
    pal = (ASSETS/'pal_all.bin').read_bytes()
    p.memory[PAL_ALL:PAL_ALL+len(pal)] = pal
    return p

class Oracle:
    """Task 13b1c8 on its own stack; each run ends at the yield 112a28 and the next resumes behind it."""
    def __init__(self, seat, locks=()):
        self.p = p = machine(locks)
        for at in FRAME+DRAW+PREVIEW+PREVIEW_UPDATE+SERVICES: p.memory[at:at+8] = RETURN
        # 11e2e8 allocates the three preview objects; hand out distinct addresses.
        p.memory[0x11e2e8:0x11e2e8+12] = struct.pack('<III', 0x3c0201f0, 0x03e00008, 0x8c420000)
        p.write(0x4c3808, 0x10 if seat else 0xf, 4)          # 178f90: mode f reads seat 0, mode 10 seat 1
        p.write(0x443150, 1, 4)
        self.seat, self.last, self.pc, self.saved = seat, [0, 0], TASK, None
        self.instructions, self.events, self.allocated, self.preview = 0, [], 0, {}
        r = p.registers
        arg = lambda n: signed(r[n], 32)
        ev = lambda *v: self.events.append(tuple(v)+(0,)*(4-len(v)))
        obj = lambda: (r[4]-OBJECTS)//0x400
        def allocate():
            p.write(0x1f00000, OBJECTS+0x400*self.allocated, 4); self.allocated += 1
        def sound():
            assert arg(4) == -1; ev(0, arg(5))
        def portrait():
            assert obj() == 0 and (arg(6), arg(7), arg(8)) == (0x190, 0, 0x290000); ev(5, arg(5))
        def place():
            assert (arg(5), arg(8)) == (0xb, 0x210000); ev(6, obj(), arg(6), arg(7))
        def action():
            assert (arg(6), arg(7)) == (1, 0); ev(7, obj(), arg(5))
        def slide_out():
            if r[4] == SP+0x3c: ev(11)
        def key_hint():
            assert r[4] == SP+0x20+0xac; ev(16, {0x5e1d90: 0, 0x5e1da0: 1}[r[5]])
        def scene():
            assert (arg(4), arg(5), r[6], r[7]) == (1, 0, 0x13b188, 0x127940); ev(18)
        x0 = lambda: int(p.float_value(12))
        self.hooks = {
            0x11e2e8: allocate, 0x1e7b70: sound, 0x1159d0: lambda: ev(1), 0x13f8a8: lambda: ev(2),
            0x13be98: lambda: ev(3), 0x13bed0: lambda: ev(4, arg(4)), 0x11d668: portrait, 0x11d570: place,
            0x11d908: action, 0x182318: lambda: ev(8, arg(5)), 0x182648: lambda: ev(9), 0x1826b0: lambda: ev(10),
            0x17f4b0: slide_out, 0x1827c0: lambda: ev(12, arg(5), arg(6)), 0x1827d8: lambda: ev(13, arg(5)),
            0x1827f0: lambda: ev(14), 0x182828: lambda: ev(15), 0x181c10: key_hint, 0x10f158: lambda: ev(17),
            0x1252f0: scene,
            0x13bf00: lambda: self.preview.update(portrait=(obj(), arg(5), arg(6))),
            0x13bfd0: lambda: self.preview.update(sprite=(obj(), arg(5), arg(6), arg(7), x0())),
            0x13c4f8: lambda: self.preview.update(pose=(obj(), arg(5), arg(6), arg(7), arg(8), x0())),
        }

    def visit(self, held):
        p = self.p
        buffered_stdout(p)                                   # rewind the libc buffer of the debug prints
        for seat, word in enumerate(held):
            p.write(0x443568+4*seat, word, 4); p.write(0x443570+4*seat, self.last[seat], 4)
            self.instructions += p.run(0x117fd8, [seat])[1]
        self.last = list(held)
        self.events, self.preview, resume = [], {}, [True]
        hooks = self.hooks
        def observe(pc):
            if resume[0]:
                # Coroutine switch: Probe.run starts every run on its own stack. The
                # first run gets the task stack; later runs get the whole register file
                # saved at the yield, as 112a28 restores it.
                resume[0] = False
                if self.saved is None: p.registers[29] = TOP
                else: p.registers[:], p.registers_high[:], p.floats[:] = self.saved
            hook = hooks.get(pc)
            if hook: hook()
        boundary = Boundary(YIELD)
        self.instructions += p.run(self.pc, (), limit=4000000, stop_before=boundary, observe=observe)[1]
        assert boundary.stopped == YIELD and p.registers[29] == SP and p.registers[4] == 0
        self.saved = (list(p.registers), list(p.registers_high), list(p.floats))
        self.pc = p.registers[31]
        assert self.pc == 0x13b6ec
        return self.row()

    def row(self):
        p = self.p
        word = lambda at: signed(p.read(at, 4), 32)
        raw = lambda at: p.read(at, 4)
        out = [signed(p.registers[19], 32), signed(p.registers[21], 32), word(SP+0x1d38), word(0x124a180), word(0x124a184)]
        for base in PANELS:
            w, m, l = SP+base, SP+base+0x1c, SP+base+0x50
            out += [word(w+0xc), word(w+0x10), word(w+0x14), word(w+0x18), word(m), word(m+4), word(m+8), word(m+0x20),
                    word(m+0x18), word(m+0x1c), raw(l), word(l+8), word(l+0xc), word(l+0x10), word(l+0x14), word(l+0x18)]
        part, swatch, slider = SP+0x1ae0, SP+0x1b70, SP+0x1c20
        out += [word(part+0x6c), word(part+0x70), *[word(part+0x74+4*i) for i in range(5)], raw(part+0x88)]
        out += [raw(swatch+0x6c+4*i) for i in range(15)]
        v = slider+0x6c
        out += [raw(v), word(v+8), word(v+0xc), word(v+0x10), word(v+0x14), word(v+0x18)]
        out += [p.memory[slider+0x88+i] for i in range(6)]+[raw(slider+0x90), word(slider+0x94)]
        f = self.preview
        assert f['portrait'][0] == 0 and f['sprite'][0] == 1 and f['pose'][0] == 2
        assert f['portrait'][2] == f['sprite'][3] == f['pose'][3] and f['sprite'][2] == f['pose'][2] and f['sprite'][4] == f['pose'][5]
        out += [f['portrait'][1], f['portrait'][2], f['sprite'][1], f['sprite'][2], f['sprite'][4], f['pose'][1], f['pose'][4]]
        out += [signed(p.read(0x1373830+2*i, 2), 16) for i in range(0x37)]
        m = p.memory
        out += [zlib.crc32(m[TABLE:TABLE+0x6180]), zlib.crc32(m[0x439a48:0x439aa8]+m[0x439aa8:0x439b08]+m[0x43ab70:0x43af70])]
        out += [len(self.events)]+[x for e in self.events for x in e]
        return out

def order(locks=()):
    data = (ASSETS/'color_edit.bin').read_bytes()
    image = bytearray((ASSETS/'save_default.bin').read_bytes())
    for character, value in locks: image[0x618c+0x16+character] = value
    return [c for c in data[60:60+0x31] if c != 43 and not image[0x618c+0x16+c]]

def scripted(o, step, character, colour, rng):
    """Walk one character: every part, edits through all slider keys, copy/paste, both dialog answers, reset."""
    CONFIRM, CANCEL, UP, DOWN, LEFT, RIGHT = 0x200, 0x400, 0x10, 0x20, 0x40, 0x80
    tap = lambda k, n=1: [step(x) for _ in range(n) for x in (k, 0)]
    settle = lambda n=18: [step(0) for _ in range(n)]
    cur = lambda: signed(o.p.registers[19], 32)
    settle(20)
    assert cur() == 0
    index = order(o.locks).index(character)
    tap(0x400000, index//6); tap(DOWN, index % 6)
    assert signed(o.p.read(0x1373830+2*o.p.read(SP+0x190+0x64, 4), 2), 16) == character
    tap(CONFIRM); settle(); assert cur() == 1
    tap(DOWN, colour); tap(2); settle(); assert cur() == 2
    rows = o.p.read(SP+0x1ae0+0x70, 4)
    for row in range(rows):
        part = o.p.read(SP+0x1ae0+0x74+4*row, 4)
        tap(8 if row & 1 else CONFIRM); settle(3)
        if part == 4:
            assert cur() == 2                               # the whole-figure row refuses confirm
            tap(SELECT); settle(3); assert cur() == 2
            step(0x200000); step(0xa00000); step(0xa00000|0x100000); step(0xa00000|0x400000); step(0)
        else:
            settle(); assert cur() == 3
            for _ in range(3):
                tap(rng.choice((LEFT, RIGHT, 0x100000, 0x400000, 0x200000, 0x800000)), rng.randrange(1, 4))
                tap(CONFIRM); settle(3); assert cur() == 4
                for _ in range(4):
                    tap(rng.choice((UP, DOWN)), rng.randrange(0, 3))
                    key = rng.choice((LEFT, RIGHT))
                    for _ in range(rng.choice((1, 3, 26))): step(key)   # 20 visits, then every 2
                    step(0)
                    tap(rng.choice((0x100000, 0x400000, 0x200000, 0x800000, LEFT|RIGHT, SELECT, 0)))
                tap(rng.choice((CONFIRM, CANCEL, 4, 2))); settle(3); assert cur() == 3
                tap(SELECT); settle(); assert cur() == 5
                tap(rng.choice((UP, DOWN, 0)))
                tap(rng.choice((CONFIRM, CONFIRM, CANCEL, SELECT))); settle(); assert cur() == 3
            tap(CANCEL); settle(); assert cur() == 2
            tap(SELECT); settle(); assert cur() == 6
            tap(rng.choice((CONFIRM, CANCEL, SELECT))); settle(); assert cur() == 2    # cursor rests on "no"
            if (character == 33 and part == 3) or rng.random() < 0.4:
                tap(SELECT); settle(); tap(LEFT); tap(CONFIRM); settle(); assert cur() == 2   # "yes": restore
        tap(RIGHT); settle(2)
    tap(CANCEL); settle(); assert cur() == 1
    tap(4); settle(); assert cur() == 0
    tap(CANCEL)
    for _ in range(24): step(0)
    assert cur() == -2

def wander(o, step, rng, visits):
    keys = [0x10]*4+[0x20]*5+[0x40]*5+[0x80]*6+[0x200]*5+[2]*2+[8]+[0x400]*2+[4]+[SELECT]*3+[0x100000, 0x400000, 0x200000, 0x800000]
    held = 0
    for _ in range(visits):
        roll = rng.random()
        if roll < 0.35: held = 0
        elif roll < 0.75: held = rng.choice(keys)
        elif roll < 0.8: held = rng.choice(keys) | rng.choice(keys)
        if signed(o.p.registers[19], 32) == -2: break
        # Leaving the scene ends the run; refuse most cancels on the character list.
        if signed(o.p.registers[19], 32) == 0 and held & 0x404 and rng.random() < 0.9: held &= ~0x404
        step(held)

def check(spec):
    exe, kind, seat, seed, argument = spec
    rng = random.Random(seed)
    locks = [(c, rng.randrange(2)) for c in rng.sample(range(49), 12)] if kind == 'wander' and seed & 1 else []
    locks = [(c, v) for c, v in locks if c]
    if kind == 'walk': locks = [(argument[0], 0)]              # hidden fighters are locked in the factory image
    o = Oracle(seat, locks); o.locks = locks
    commands = [f'L {c} {v} 0 0 0' for c, v in locks]+[f'B {seat} 0 0 0 0']
    expected = []
    states = set()
    def step(key):
        other = rng.choice((0, 0, 0x200, 0x20, 0x400, 0x80, SELECT))      # the idle seat must be ignored
        held = (other, key) if seat else (key, other)
        commands.append(f'T {held[0]} {held[1]} 0 0 0'); expected.append(o.visit(held)); states.add(expected[-1][0])
    if kind == 'walk': scripted(o, step, argument[0], argument[1], rng)
    else: wander(o, step, rng, argument)
    native = subprocess.run([exe, ASSETS], input='\n'.join(commands)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(expected)
    for i, (a, b) in enumerate(zip(actual, expected)):
        assert a == b, (kind, seat, seed, argument, i, commands[i+len(locks)+1], len(a), len(b),
                        [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12], b[EVENTS:], a[EVENTS:])
    table = bytes(o.p.memory[TABLE:TABLE+0x6180])
    default = (ASSETS/'save_default.bin').read_bytes()[4:4+0x6180]
    events = [e for row in expected for e in zip(*[iter(row[EVENTS+1:])]*4)]
    return dict(case=kind, seat=seat, seed=seed, argument=argument, visits=len(expected), instructions=o.instructions,
                states=sorted(states), sounds=sum(e[0] == 0 for e in events), cache_resets=sum(e[0] == 1 for e in events),
                edited_colours=sum(table[i:i+2] != default[i:i+2] for i in range(0, 0x6180, 2)),
                exit_requested=any(e[0] == 18 for e in events), table_versions=len({row[EVENTS-2] for row in expected}),
                cache_versions=len({row[EVENTS-1] for row in expected}), table_crc32=zlib.crc32(table))

def reset_overflow():
    """13cbd8 for character 33, part 3: confirm the store past stored bank 2 on a seeded table."""
    p = machine()
    seeded = bytes((i*7+3) & 255 for i in range(0x6180))
    results = []
    for colour in range(5):
        p.memory[TABLE:TABLE+0x6180] = seeded
        n = p.run(0x13cbd8, [33, 3, colour], limit=2000)[1]
        key = 33*5+colour
        stock = bytes(p.memory[PAL_ALL+(key*32+23)*32:PAL_ALL+(key*32+23)*32+32])
        after = bytes(p.memory[TABLE:TABLE+0x6180])
        want = bytearray(seeded); at = (key*3+2)*32
        want[at:at+32] = stock; want[at+32:at+64] = stock
        assert after == bytes(want)
        results.append(dict(colour=colour, overwritten_group=key*3+3, instructions=n))
    return results

def pure(exe):
    """115d40 decode prefix and the two preview placement functions against the native pure functions."""
    p = machine()
    tables = {PAL_ALL: 0, TABLE: 1, 0x3ec740: 2, 0x3f28c0: 3, 0x1232c80: 4, 0x1232ce0: 5}
    commands, expected, instructions = [], [], 0
    for owner in range(4):
        for selector in (0, 0x40000, 0x80000, 0xc0000):
            for character in range(52):
                for colour in (0, 4):
                    for bank in range(32):
                        key = owner << 16 | selector | (character*5+colour)
                        boundary = Boundary(0x115e04)
                        instructions += p.run(0x115d40, [key, bank], limit=200, stop_before=boundary)[1]
                        assert boundary.stopped
                        r = p.registers
                        group = signed(r[6], 32)
                        # The stock path leaves the bank outside the stored range in a2 as key*32 + bank.
                        expected.append([tables[r[4] & 0xffffffff], group, r[5] & 0xffffffff, group-(key & 0xffff)*(3 if tables[r[4] & 0xffffffff] in (1, 2, 3) else 32) if tables[r[4] & 0xffffffff] < 4 else group])
                        commands.append(f'K {key} {bank} 0 0 0')
    decode = len(commands)
    for at in (0x11d908, 0x17c228, 0x11dff8, 0x11d6c8, 0x11d868, 0x11d730): p.memory[at:at+8] = RETURN
    OBJ = 0x1e00000
    def run_object(fn, character, args, x0, loaded):
        nonlocal instructions
        p.memory[OBJ:OBJ+0x200] = bytes(0x200)
        p.write(OBJ+0x14, character, 4); p.write(OBJ+0x24, -2, 4); p.write(0x124a184, loaded, 4)
        p.floats[12] = struct.unpack('<I', struct.pack('<f', float(x0)))[0]
        calls = []
        def observe(pc):
            if pc == 0x11d908: calls.append((signed(p.registers[5], 32), signed(p.registers[6], 32), signed(p.registers[7], 32)))
        instructions += p.run(fn, [OBJ, *args], limit=2000, observe=observe)[1]
        assert len(calls) <= 1 and p.read(OBJ+0x104, 4) & 0x200
        return calls
    for character in range(51):
        for part in range(6):
            for visible, loaded, x0 in ((1, 1, 0x10), (1, 1, -0x130), (1, 1, -77), (0, 1, 0x10), (1, 0, 0x10)):
                colour = (character+part) % 5
                calls = run_object(0x13bfd0, character, [visible, part, colour], x0, loaded)
                hidden = p.read(OBJ+0x104, 4) >> 1 & 1
                if calls: assert calls[0][1:] == (1, 1)
                expected.append([hidden, p.read(OBJ+0x40, 4), p.read(OBJ+0x44, 4), calls[0][0] if calls else -1,
                                 p.read(OBJ+0x28, 4), p.read(OBJ+0x38, 4) >> 31, p.read(OBJ+0x20, 4)])
                commands.append(f'P {character} {int(visible and loaded)} {part} {colour} {x0}')
        for pose in range(3):
            for visible, loaded, x0 in ((1, 1, 0x10), (1, 1, -0x91), (0, 1, 0x10), (1, 0, 0x10)):
                colour = (character+pose) % 5
                calls = run_object(0x13c4f8, character, [visible, 0, colour, pose], x0, loaded)
                hidden = p.read(OBJ+0x104, 4) >> 1 & 1
                if calls: assert calls[0][1:] == (1, 0)
                expected.append([hidden, p.read(OBJ+0x40, 4), p.read(OBJ+0x44, 4), calls[0][0] if calls else -1,
                                 p.read(OBJ+0x28, 4), 0, p.read(OBJ+0x20, 4)])
                commands.append(f'Q {character} {int(visible and loaded)} {pose} {colour} {x0}')
    # src/character_select.cpp (129db0) stores 0x40000 + button + owner; the key adds character*5.
    for side in range(2):
        for button in range(5):
            for edited in range(2):
                commands.append(f'S {side} 33 {button} {edited} 0')
                expected.append([0x40000+33*5+button+(edited*(0x20000 if side else 0x10000))])
    native = subprocess.run([exe, ASSETS], input='\n'.join(commands)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(expected)
    for i, (a, b) in enumerate(zip(actual, expected)):
        assert a == b, (i, commands[i], a, b)
    return dict(palette_decodes=decode, preview_placements=len(commands)-decode-20, select_keys=20, instructions=instructions)

def main():
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == SOURCE_HASH
    walks = [((33, 0), 0), ((33, 4), 1), ((25, 2), 0), ((11, 3), 1), ((2, 1), 0), ((48, 4), 1), ((0, 0), 0), ((45, 2), 1), ((16, 3), 0)]
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp)/'check.cpp', Path(tmp)/'check'
        cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/color_edit.cpp',
                        ROOT/'src/console_menu.cpp', ROOT/'src/system_data.cpp', '-o', exe], check=True)
        specs = [(exe, 'walk', seat, 0x13b160+i, argument) for i, (argument, seat) in enumerate(walks)]
        specs += [(exe, 'wander', seed & 1, 0x13b1c8+seed, 4000) for seed in range(12)]
        with ProcessPoolExecutor(8) as pool:
            static = pool.submit(pure, exe)
            cases = list(pool.map(check, specs))
            static = static.result()
        overflow = reset_overflow()
    native = {name: hashlib.sha256((ROOT/'src'/name).read_bytes()).hexdigest() for name in ('color_edit.cpp', 'color_edit.hpp')}
    visits, instructions = sum(c['visits'] for c in cases), sum(c['instructions'] for c in cases)+static['instructions']
    report = dict(status='passed', elf_sha256=SOURCE_HASH, native_sha256=native,
                  asset_sha256=hashlib.sha256((ASSETS/'color_edit.bin').read_bytes()).hexdigest(),
                  visits=visits, instructions=instructions, cases=cases, static=static, character33_reset=overflow,
                  scope='Whole coroutine task 13b1c8 from its first instruction on the task stack, resumed behind each 112a28 yield '
                        'with the register file saved at the yield (the 112a28 context switch itself is not executed). Real: both pad '
                        'samplers 117fd8, 178f90, 118128, 17c210, every widget constructor and update (17f3xx, 20dff8..20e528, 20e570, '
                        '20e5d8, 20e738, 20e7f8, 20eae0, 20ee20, 20ee70, 20be68..20bf70, 20f4d8..20f5b8, 20f898..20fb50, 212820..2128f8), '
                        '13be98, 13bed0, 13c720, 13c880, 13c8f0, 13c928, 13ca58, 13cbd8, 13ccf0, 1159d0, 115d40, 116478 and libc. '
                        'Stubbed (jr ra) and recorded at entry: screen frame 1822a0/182318/182648/1826b0/1825b8/1827c0/1827d8/1827f0/'
                        '182828/181c10/182600; draws 20c038/20f680/20fb58/20ef38/20f360/2129d0; preview camera, resources and objects '
                        '13f8a8/11d448/11d4f8/11d488/11e2e8/11d528/11d668/11d570/11d908/17eab0 and the per-visit object updates '
                        '13bf00/13bfd0/13c4f8; sound 1e7b70; memory card 10f158; scene switch 1252f0. Compared every visit: both state '
                        'words, all seven widgets (rows, scroll, visible, active, slide position/remaining/target/state, list flags/'
                        'range/step/cursor/page), part rows and disabled bitmap, 15 swatches, slider fields/backup/clipboard/highlight, '
                        'preview arguments, the character id list, CRC-32 of the 6180-byte edit table and of the palette cache '
                        '(identity, reference, 512 colours), and the ordered request list. 13bfd0 and 13c4f8 run whole on a fixture '
                        'object with 11d908/17c228/11dff8/11d6c8/11d868/11d730 stubbed. The 115d40 comparison is the decode prefix '
                        '115d40..115e04 only (source table, group, cache identity); its lookup and allocation run whole inside the task.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(cases)} task traces; {visits} visits; {static['palette_decodes']} palette decodes; "
          f"{static['preview_placements']} preview placements; {instructions} instructions")

if __name__ == '__main__': main()
