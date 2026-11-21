#!/usr/bin/env python3
"""Match the native KEY CONFIGURATION window and key-mask helpers to SLPS-25559 visit by visit."""
from concurrent.futures import ProcessPoolExecutor
import json
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ELF, PIN, ROOT, digest

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/key_config_validation.json'
SOURCES = ['key_config.cpp', 'menu_widgets.cpp', 'console_menu.cpp', 'system_data.cpp']
MASKS, PRESET, G, PAD = 0x4eaac0, 0x12d26b0, 0x4c3808, 0x1237cc8
TASK, YIELD, RESUME, STACK_TOP = 0x13ce08, 0x112a28, 0x13cf40, 0x12721c0+0x2000
FRAME = STACK_TOP-0x240           # 13ce08 frame: guide window at +0, widget at +0x170
FAKE_TASKS = (0x1d00100, 0x1d00200, 0x1d00300)   # records behind 582f54 / 582f58 / 582f5c for 1da7e8
# Callees replaced by `jr ra; move v0,zero`. Everything else runs from the ELF.
STUBS = {
    'rendering': (0x182600, 0x17c718, 0x17db28, 0x17e428, 0x17e228, 0x17e038, 0x17d790),
    'texture and palette loading': (0x17eab0, 0x1142d8, 0x1163c0, 0x116478, 0x10add8),
    'page background animation setup': (0x1e1620, 0x1e2358, 0x1e2408, 0x1e23a0),
    'sound driver': (0x1e7b70, 0x1e7b40),
    'scene switch': (0x1252f0,),
    'debug print': (0x316140, 0x323050),
}
BUTTONS = (4, 2, 1, 0x400, 0x200, 0x100, 0x100000, 0x200000, 0x400000, 0x800000)
DRIVER = r'''
#include "key_config.hpp"
#include "console_menu.hpp"
#include <iostream>
#include <sstream>
using namespace ss6;
static uint32_t mix(uint32_t h,std::string_view s){for(unsigned char c:s)h=h*131+c;return h*131+0x100;}
static void panel(std::ostream& o,const SlidePanel& p){for(int v:p.words())o<<v<<' ';}
static void bar(std::ostream& o,const GuideBar& b){o<<b.shown<<' '<<b.open<<' '<<b.configured<<' ';panel(o,b.panel);o<<b.layout<<' ';}
static void guide(std::ostream& o,const GuideWindow& g){
    o<<g.initialised<<' '<<g.layout<<' '<<g.backdrop<<' ';
    bar(o,g.title);o<<g.titleRect<<' ';bar(o,g.message);o<<mix(0,g.messageText())<<' ';
    for(const GuideKeys* k:{&g.keys,&g.extra}){
        bar(o,*k);o<<k->width<<' '<<k->height<<' '<<k->textX<<' '<<k->textY<<' '
                  <<mix(0,k->text<0?std::string_view():std::string_view(g.data->keyHelp[k->text]))<<' ';
    }
}
int main(int,char** argv){
    SystemData data(argv[1]);
    MenuWidgetData tables(argv[1]);
    KeyConfigAssets assets(argv[1]);
    KeyConfigWindow window;
    MenuPadRepeat repeat;std::array<uint32_t,2> last{};
    std::string line;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);std::ostringstream o;std::string op;in>>op;
        auto num=[&]{long long v=0;in>>v;return v;};
        auto masks=[&]{for(unsigned i=0;i<16;++i)o<<keyMask(data,i/8,i%8)<<' ';};
        if(op=="I"){
            const unsigned mode=num(),owner=num(),edit=num();
            for(unsigned i=0;i<16;++i)data.setWord(SystemData::keyMasks+4*i,int32_t(num()));
            repeat=MenuPadRepeat();last={};
            window=KeyConfigWindow{};
            window.start(tables,KeyConfigWindow::operatingSeat(mode,owner,edit));
            o<<"0";
        } else if(op=="T"){
            const std::array<uint32_t,2> held{uint32_t(num()),uint32_t(num())};const bool option=num();
            const auto menu=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            const std::array<WidgetPad,2> pads{WidgetPad{held[0],menu[0].pressed,menu[0].repeat},
                                               WidgetPad{held[1],menu[1].pressed,menu[1].repeat}};
            std::vector<int> tones;
            const auto r=window.tick(pads,data,assets,option,tones);
            guide(o,window.guide);
            auto& w=window.widget;
            o<<w.shown<<' '<<w.active<<' ';panel(o,w.panel);
            for(auto& s:w.selector)o<<s.flags<<' '<<s.min<<' '<<s.max<<' '<<s.step<<' '<<s.current<<' '<<s.page<<' ';
            masks();
            o<<unsigned(w.presetId[0])<<' '<<unsigned(w.presetId[1])<<' '<<window.finished<<' '<<window.closing<<' '
             <<r.returnedToPause<<' '<<r.optionScene<<' '<<tones.size();
            for(int v:tones)o<<' '<<v;
            // 212478 as its sequence of primitive calls.
            std::vector<long long> d;
            const auto k=w.draw(data);
            if(k.visible){
                d.insert(d.end(),{1,k.boxX,k.boxY,528,286,0xc0000000u});
                d.insert(d.end(),{2,mix(0,assets.legend),k.legendX,k.legendY,1,0});
                for(int i=0;i<10;++i)d.insert(d.end(),{3,mix(0,assets.rows[i]),k.labelX,k.labelY[i],0,k.labelColour[i]});
                for(auto& column:k.cells)for(auto& c:column){
                    if(c.glyph<0)d.insert(d.end(),{3,mix(0,assets.unset),c.x,c.y,0,0xffffffffu});
                    else d.insert(d.end(),{4,c.glyph,c.x,c.y});
                    if(c.cursor)d.insert(d.end(),{5,c.cursorX,c.cursorY,48,29,c.cursorColour,0xffffffffu});
                }
            }
            o<<' '<<d.size();for(auto v:d)o<<' '<<v;
        } else if(op=="mk"){
            for(unsigned i=0;i<16;++i)data.setWord(SystemData::keyMasks+4*i,int32_t(num()));o<<"0";
        } else if(op=="as"){
            const unsigned p=num(),slot=num();const uint32_t mask=uint32_t(num());
            assignKeyMask(data,p,slot,mask);masks();
        } else if(op=="pr"){
            const unsigned p=num(),preset=num();applyKeyPreset(data,assets,p,preset);masks();
        } else if(op=="gl"){o<<keyGlyph(uint32_t(num()));
        } else if(op=="fa"){o<<keyMasksFactory(data,assets);
        } else if(op=="os"){const unsigned m=num(),ow=num(),e=num();o<<KeyConfigWindow::operatingSeat(m,ow,e);
        }
        std::cout<<o.str()<<'\n';
    }
}
'''

def mix(h, s):
    for c in s: h = (h*131+c) & 0xffffffff
    return (h*131+0x100) & 0xffffffff

class Source:
    def __init__(self):
        self.p = p = Probe(ELF.read_bytes(), finite_model=True)
        for group in STUBS.values():
            for pc in group: p.memory[pc:pc+8] = struct.pack('<II', 0x03e00008, 0x0000102d)
        buffered_stdout(p)
        p.write(0x443150, 1, 4)
        for at, task in zip((0x582f54, 0x582f58, 0x582f5c), FAKE_TASKS): p.write(at, task, 4)
        self.instructions = 0
        self.context = None
        self.last = [0, 0]
        self.clear()
    def word(self, at): return signed(self.p.read(at, 4), 32)
    def words(self, at, n): return [self.word(at+4*i) for i in range(n)]
    def real(self, at): return int(struct.unpack_from('<f', self.p.memory, at)[0])
    def text(self, at):
        if not at: return b''
        m = self.p.memory; return bytes(m[at:m.index(0, at)])
    def run(self, pc, *args, limit=400000, stop=()):
        value, count = self.p.run(pc, args, limit=limit, observe=self.watch, stop_before=stop)
        self.instructions += count
        return value
    def clear(self):
        self.sounds = []; self.draw = []; self.returned = self.scene = 0; self.colour = 0
    def watch(self, pc):
        p = self.p; r = p.registers
        if self.context is not None:
            # The EE kernel resumes the task thread with its saved context.
            if self.context == 'start': r[29] = STACK_TOP
            else: p.registers[:], p.registers_high[:], p.floats[:], p.lo, p.hi = self.context
            self.context = None
        a = lambda n: signed(r[n], 32)
        u = lambda n: r[n] & 0xffffffff
        if pc == 0x1e7b70:
            assert a(4) == -1; self.sounds.append(a(5))
        elif pc == 0x1252f0:
            assert [u(4), u(5), u(6), u(7)] == [1, 0, 0x13cdc8, 0x1cfa10]; self.scene = 1
        elif pc == 0x1da7e8: self.returned = 1
        elif pc == 0x17db28: self.colour = u(4)
        elif pc == 0x17c718:
            s = u(4); self.draw += [1, self.real(s+0x14), self.real(s+0x18), self.real(s+0xc), self.real(s+0x10), p.read(s+0x24, 4)]
        elif pc == 0x17e428:
            self.draw += [2, mix(0, self.text(u(4))), int(p.float_value(12)), int(p.float_value(13)), a(5), a(6)]
        elif pc == 0x17e228: self.draw += [3, mix(0, self.text(u(4))), a(5), a(6), a(7), self.colour]
        elif pc == 0x17e038: self.draw += [4, a(4), int(p.float_value(12)), int(p.float_value(13))]
        elif pc == 0x17d790:
            s = u(4); self.draw += [5, self.real(s+0x14), self.real(s+0x18), self.real(s+0xc), self.real(s+0x10),
                                    p.read(s+0x1c, 4), p.read(s+0x20, 4)]
    def enter(self, mode, owner, edit, masks):
        p = self.p
        p.write(G, mode, 4); p.write(0x582f3c, owner, 4); p.write(0x12d35c4, edit, 4)
        for i, m in enumerate(masks): p.write(MASKS+4*i, m, 4)
        p.write(PRESET, 0, 2)
        for s in range(2):
            for at in (0x443568, 0x443570): p.write(at+4*s, 0, 4)
        p.memory[PAD:PAD+56] = bytes(56)
        p.memory[0x12721c0:STACK_TOP] = bytes(0x2000)
        self.last = [0, 0]; self.started = False
    def tick(self, held):
        p = self.p
        for s, h in enumerate(held):
            p.write(0x443568+4*s, h, 4); p.write(0x443570+4*s, self.last[s], 4); self.run(0x117fd8, s)
        self.last = list(held)
        self.clear()
        # 13cd50 hands 13ce08 to an EE kernel thread and 112a28 yields through
        # kernel calls. Each visit runs the original task from its yield
        # return address to the next call of 112a28 on the task's own stack.
        self.context = self.context_saved if self.started else 'start'
        self.run(RESUME if self.started else TASK, limit=3000000, stop=(YIELD,))
        r = p.registers
        assert r[31] == RESUME and self.context is None and r[29] == FRAME, (hex(r[31]), hex(r[29]))
        self.context_saved = (list(p.registers), list(p.registers_high), list(p.floats), p.lo, p.hi)
        self.started = True
        return self.row(signed(r[18], 32), signed(r[19], 32))
    def panel(self, at): return self.words(at, 13)
    def bar(self, at): return [self.word(at), self.word(at+4), self.word(at+8), *self.panel(at+0xc), self.word(at+0x40)]
    def guide(self, at):
        w = self.word
        out = [w(at), w(at+4), w(at+8), *self.bar(at+0x10), w(at+0x58), *self.bar(at+0x60), mix(0, self.text(self.p.read(at+0xa8, 4)))]
        for k in (at+0xac, at+0x108):
            out += [*self.bar(k), w(k+0x48), w(k+0x4c), w(k+0x50), w(k+0x54), mix(0, self.text(self.p.read(k+0x58, 4)))]
        return out
    def masks(self): return [self.p.read(MASKS+4*i, 4) for i in range(16)]
    def row(self, finished, closing):
        p = self.p; W = FRAME+0x170
        sel = lambda at: [p.read(at, 4), *self.words(at+8, 5)]
        return [*self.guide(FRAME), self.word(W), self.word(W+4), *self.panel(W+0xc), *sel(W+0x40), *sel(W+0x5c),
                *self.masks(), p.read(PRESET, 1), p.read(PRESET+1, 1), finished, closing, self.returned, self.scene,
                len(self.sounds), *self.sounds, len(self.draw), *self.draw]

def random_masks(rng):
    kind = rng.random()
    if kind < 0.4: return [0x400, 0x200, 2, 4, 0x400000, 0x800000, 0x100000, 0x200000]*2
    if kind < 0.6: return [rng.choice(BUTTONS+(0, 0)) for _ in range(16)]
    out = []
    for _ in range(2):
        side = list(BUTTONS); rng.shuffle(side); out += [m if rng.random() < 0.85 else 0 for m in side[:8]]
    return out

def gesture(rng):
    kind = rng.random()
    if kind < 0.40: return [rng.choice(BUTTONS), 0]
    if kind < 0.62: return [rng.choice((0x20, 0x20, 0x20, 0x10)), 0]*rng.randrange(1, 4)
    if kind < 0.70: return [rng.choice((0x20, 0x10))]*rng.randrange(18, 40)
    if kind < 0.78: return [rng.choice((0x40, 0x80)), 0]
    if kind < 0.84: return [rng.choice((0x200, 2, 8, 0x400, 4)), 0]
    if kind < 0.86: return [0x80000, 0]
    if kind < 0.93: return [rng.choice(BUTTONS) | rng.choice(BUTTONS+(0x20, 0x10, 0x40, 0x80000, 8)), 0]
    return [0]*rng.randrange(1, 12)

def session(spec):
    exe, name, seed, visits = spec
    rng = random.Random(seed)
    o = Source()
    cmds = []; exp = []
    stats = dict(windows=0, returns=0, option_exits=0, sounds=0, mask_changes=0, rows_seen=set())
    def enter():
        option = name == 'option' or (name == 'mixed' and rng.random() < 0.3)
        mode = 0x11 if option else rng.choice((1, 2, 3, 3, 0xb, 0xc, 9, 0xa))
        owner, edit = rng.randrange(2), rng.randrange(2)
        masks = random_masks(rng)
        o.enter(mode, owner, edit, masks)
        cmds.append(f'I {mode} {owner} {edit} '+' '.join(map(str, masks))); exp.append([0])
        stats['windows'] += 1
        return option
    option = enter()
    queues = [[], []]; done = 0; tail = None
    previous = o.masks()
    while done < visits:
        if tail is not None:
            tail -= 1
            if tail < 0:
                option = enter(); queues = [[], []]; tail = None; previous = o.masks()
                continue
        held = []
        for q in queues:
            if not q: q.extend(gesture(rng) if rng.random() < 0.75 else [0]*rng.randrange(1, 20))
            held.append(q.pop(0))
        row = o.tick(held); done += 1
        cmds.append(f'T {held[0]} {held[1]} {int(option)}'); exp.append(row)
        stats['sounds'] += len(o.sounds); stats['returns'] += o.returned; stats['option_exits'] += o.scene
        now = o.masks(); stats['mask_changes'] += now != previous; previous = now
        W = FRAME+0x170
        stats['rows_seen'] |= {o.word(W+0x54), o.word(W+0x70)}
        if o.scene and tail is None: tail = rng.randrange(2, 10)
        if o.returned and rng.random() < 0.3 and tail is None: tail = rng.randrange(0, 4)
    stats['rows_seen'] = sorted(stats['rows_seen'])
    return finish(exe, name, cmds, exp, o, dict(visits=done, **stats))

def finish(exe, name, cmds, exp, o, stats):
    native = subprocess.run([exe, ASSETS], input='\n'.join(cmds)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(exp), (name, len(actual), len(exp))
    for i, (a, b) in enumerate(zip(actual, exp)):
        assert a == b, (name, i, cmds[i][:60], len(a), len(b), [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12])
    return dict(case=name, snapshots=len(exp), **stats, instructions=o.instructions)

def direct(exe):
    """Whole original helpers called as functions."""
    rng = random.Random(0x178d50)
    o = Source(); p = o.p; cmds = []; exp = []; counts = {}
    def add(kind, cmd, row):
        cmds.append(cmd); exp.append([int(v) for v in row]); counts[kind] = counts.get(kind, 0)+1
    def put(masks):
        for i, m in enumerate(masks): p.write(MASKS+4*i, m, 4)
        add('fixture', 'mk '+' '.join(map(str, masks)), [0])
    for _ in range(4000):
        put(random_masks(rng))
        for _ in range(rng.randrange(1, 5)):
            player, slot = rng.randrange(2), rng.randrange(8)
            mask = rng.choice(BUTTONS+(0, 0, 0x80000, 8, 0x20000, 0x402))
            o.run(0x178d50, player, slot, mask); add('assign_178d50', f'as {player} {slot} {mask}', o.masks())
        o.run(0x177140); add('factory_177140', 'fa', [o.p.registers[2] & 0xffffffff])
        if rng.random() < 0.3:
            player, preset = rng.randrange(2), rng.choice((0, 0, 1, 2, 3, 7))
            o.run(0x178e50, player, preset); add('preset_178e50', f'pr {player} {preset}', o.masks())
            o.run(0x177140); add('factory_177140', 'fa', [o.p.registers[2] & 0xffffffff])
    for mask in sorted({1 << b for b in range(32)} | {0, 3, 0x402, 0x600, 0x300000} | set(BUTTONS)):
        p.write(MASKS+4*11, mask, 4)
        add('glyph_212780', f'gl {mask}', [signed(o.run(0x212780, 1, 3), 32)])
    for mode in range(0, 0x16):
        for owner in range(2):
            for edit in range(2):
                p.write(G, mode, 4); p.write(0x582f3c, owner, 4); p.write(0x12d35c4, edit, 4)
                add('seat_178f90', f'os {mode} {owner} {edit}', [o.run(0x178f90) & 0xffffffff])
    return finish(exe, 'direct', cmds, exp, o, dict(calls=counts))

def main():
    assert digest(ELF) == PIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'check.cpp'; exe = Path(tmp)/'check'
        cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp,
                        *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        specs = [(exe, name, 0x2121c8+29*i, 2500) for i, name in
                 enumerate(('pause', 'pause', 'option', 'mixed', 'mixed', 'pause', 'mixed'))]
        with ProcessPoolExecutor(8) as pool:
            helpers = pool.submit(direct, exe)
            sessions = list(pool.map(session, specs))
            helpers = helpers.result()
    rows = sessions+[helpers]
    total = lambda k: sum(r.get(k, 0) for r in rows)
    report = dict(status='passed', elf_sha256=PIN, sessions=sessions, helpers=helpers, snapshots=total('snapshots'),
                  instructions=total('instructions'), stubs={k: [hex(a) for a in v] for k, v in STUBS.items()},
                  scope='Whole original coroutine 13ce08 run on its own task stack between calls of the yield 112a28 '
                        '(prologue with 178f90, 1822a0, 182318, 182648, 212110, 17f428, 17f468; loop with 1825b8, 2121c8, '
                        '17f400, 17ea48, 1da7e8, 17f4b0, 1826b0 and the draw routine 212478), pads through 117fd8, and whole '
                        '178d50, 178e50, 177140, 212780, 178f90 as direct calls. Replaced by an empty return: 182600 (guide '
                        'window draw), the text and box primitives called by 212478 (their arguments are compared as the '
                        'draw list), texture/palette loading and the page background set-up reached from 1822a0 in the '
                        'option scene, 1e7b70 and 1e7b40 (sound), 1252f0 (scene switch, arguments compared), 316140 and '
                        '323050 (debug print). The task sleep after 1da7e8 (task word +4 = 0x21) is modelled by continuing '
                        'the same context; the practice-menu owner of the widget is outside this comparison.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(f"key config: {len(sessions)} sessions; {report['snapshots']} snapshots; {total('visits')} coroutine visits, "
          f"{total('mask_changes')} mask changes, {total('returns')} returns to pause, {total('option_exits')} option exits; "
          f"{sum(helpers['calls'].values())} helper calls; {report['instructions']} instructions")

if __name__ == '__main__':main()
