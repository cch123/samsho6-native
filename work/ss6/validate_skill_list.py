#!/usr/bin/env python3
"""Match the native SKILL LIST window (src/skill_list.*) to SLPS-25559 visit by visit."""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from mips_probe import signed
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_console_gallery import Oracle, RETURN, ASSETS, OPTION, fnv

REPORT = ROOT/'outputs/ss6-feasibility/skill_list_validation.json'
SOURCES = ('skill_list.cpp', 'menu_widgets.cpp', 'console_menu.cpp', 'system_data.cpp')
TASK, STACK, STACK_WORDS = 0x13d680, 0x127a1c0, 0x4000
COMMON, CHARACTER, CATEGORIES = 0x4caab0, 0x4cb190, 0x4ceef8
COMMON_MAP, COLOUR, ICON_RECTS = 0x1373818, 0x4ee548, 0x4ee6b8
ACTORS, SCRATCH, TEXT, WIDGET = 0x1c10000, 0x1c20000, 0x1c30000, 0x1c40000
PAUSE_TASKS = 0x1c50000
# Additional `jr ra` boundaries on top of the gallery validator's list.
EXTRA_RENDER = (0x182600, 0x20ef38, 0x17e0b0, 0x17e228, 0x17f090)
BAR, ICON, GLYPH, ASCII = range(4)

DRIVER = r'''
#include "skill_list.hpp"
#include "console_menu.hpp"
#include <iostream>
#include <memory>
#include <sstream>
using namespace ss6;
static uint32_t fnv(uint32_t h,unsigned byte){return (h^(byte&255))*16777619u;}
static uint32_t text(std::string_view s){uint32_t h=2166136261u;for(unsigned char c:s)h=fnv(h,c);return h;}
static std::ostream& panel(std::ostream& o,const SlidePanel& p){for(int v:p.words())o<<v<<' ';return o;}
static void list(std::ostream& o,const ListWidget& w){
    o<<w.width<<' '<<w.height<<' '<<w.visible<<' '<<w.top<<' '<<w.shown<<' '<<w.active<<' ';panel(o,w.panel);
    auto& s=w.selector;o<<s.flags<<' '<<s.min<<' '<<s.max<<' '<<s.step<<' '<<s.current<<' '<<s.page<<' '<<w.selected()<<' ';
    uint32_t h=2166136261u;
    for(int i=0;i<s.max&&i<int(ListWidget::capacity);++i){
        if(!w.items[i].data())h=fnv(h,255);
        else {for(unsigned char c:w.items[i])h=fnv(h,c);h=fnv(h,0);}
    }
    o<<h<<' ';
}
static void bar(std::ostream& o,const GuideBar& b){o<<b.shown<<' '<<b.open<<' '<<b.configured<<' ';panel(o,b.panel)<<b.layout<<' ';}
static void guide(std::ostream& o,const GuideWindow& g){
    o<<g.initialised<<' '<<g.layout<<' '<<g.backdrop<<' ';
    bar(o,g.title);o<<g.titleRect<<' ';bar(o,g.message);o<<text(g.messageText())<<' ';
    for(const GuideKeys* k:{&g.keys,&g.extra}){
        bar(o,*k);o<<k->width<<' '<<k->height<<' '<<k->textX<<' '<<k->textY<<' '
                  <<text(k->text<0?std::string_view():std::string_view(g.data->keyHelp[k->text]))<<' ';
    }
}
static void detail(std::ostream& o,const SkillDetail& d){
    o<<d.width<<' '<<d.visible<<' '<<d.top<<' '<<d.shown<<' '<<d.active<<' ';panel(o,d.panel);
    auto& s=d.selector;o<<s.flags<<' '<<s.min<<' '<<s.max<<' '<<s.step<<' '<<s.current<<' '<<s.page<<' '
     <<d.category<<' '<<d.selection<<' '<<d.table<<' '<<d.first<<' ';
}
static void draws(std::ostream& o,const std::vector<SkillDraw>& v,bool full){
    o<<v.size()<<' ';
    uint32_t h=2166136261u;
    for(auto& d:v){
        const long long f[8]={d.kind,d.id,d.x,d.y,d.w,d.h,d.size,(long long)d.colour};
        if(full)for(auto x:f)o<<x<<' ';
        else for(auto x:f)for(int b=0;b<4;++b)h=fnv(h,unsigned(uint32_t(x)>>8*b));
    }
    if(!full)o<<h<<' ';
}
int main(int,char** argv){
    SystemData system(argv[1]);MenuWidgetData widgets(argv[1]);SkillListData data(argv[1]);
    MenuPadRepeat repeat;std::array<uint32_t,2> last{};
    auto window=std::make_unique<SkillListWindow>(data,widgets,system);
    auto single=std::make_unique<ListWidget>();CharacterRows singleRows{};CommonRows commonRows{};
    std::string line,op;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);in>>op;
        std::ostream& o=std::cout;
        if(op=="line"){
            long long size,plain,x,y;unsigned long long colour;std::string hex;in>>size>>plain>>x>>y>>colour>>hex;
            std::string s;for(size_t i=0;i+1<hex.size();i+=2)s.push_back(char(std::stoi(hex.substr(i,2),nullptr,16)));
            std::vector<SkillDraw> out;
            const size_t next=skillLayoutLine(data,s,0,int(x),int(y),int(size),plain!=0,SkillUnlocks(system),uint32_t(colour),out);
            o<<(next==std::string::npos?-1:(long long)next)<<' ';draws(o,out,true);o<<'\n';
            continue;
        }
        std::vector<long long> v;for(long long x;in>>x;)v.push_back(x);
        v.resize(16);
        if(op=="opt")system.option(size_t(v[0]))=uint8_t(v[1]);
        else if(op=="ctx"){window->gameMode=unsigned(v[0]);window->listId=int(v[1]);}
        else if(op=="enter"){repeat=MenuPadRepeat();last={};window->enter(unsigned(v[0]));}
        else if(op=="tick"){
            std::array<uint32_t,2> held{uint32_t(v[0]),uint32_t(v[1])};
            auto m=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            auto& w=*window;
            const auto r=w.tick({held[w.seat],m[w.seat].pressed,m[w.seat].repeat});
            const auto d=w.draw();
            o<<w.state<<' '<<w.last<<' '<<w.dim<<' '<<w.seat<<' ';guide(o,w.guide);list(o,w.list);list(o,w.sub);
            o<<commonSelection(w.sub,w.commonRows)<<' ';detail(o,w.detail);
            o<<r.event<<' '<<r.tones.size()<<' ';for(int t:r.tones)o<<t<<' ';
            draws(o,d.page,false);
            o<<d.scrollBar<<' '<<d.scrollX<<' '<<d.scrollY<<' '<<d.scrollTotal<<' '<<d.scrollTop<<' '
             <<data.scrollBarWidth<<' '<<data.scrollBarHeight<<'\n';
        } else if(op=="group"){
            const int first=data.find(int(v[0]),int(v[1]));
            o<<first<<' '<<data.lines(int(v[0]),first,int(v[1]))<<'\n';
        } else if(op=="page"){
            std::vector<SkillDraw> out;
            skillPage(data,int(v[0]),data.find(int(v[0]),int(v[1])),int(v[1]),int(v[2]),int(v[3]),int(v[4]),int(v[5]),int(v[6]),
                      SkillUnlocks(system),out);
            draws(o,out,true);o<<'\n';
        } else if(op=="rows"){
            single->init(widgets,singleRows);
            fillCommonRows(*single,data,system,commonRows,int(v[0]));
            list(o,*single);
            for(int c=0;c<single->count();++c){single->selector.current=c;o<<commonSelection(*single,commonRows)<<' ';}
            o<<'\n';
        }
    }
}
'''

class Source(Oracle):
    def __init__(self, options=(), seat=0, seed=1):
        super().__init__(seat, options, seed=seed)
        p = self.p
        for pc in EXTRA_RENDER: p.memory[pc:pc+8] = RETURN
        self.tones = []; self.draws = []; self.event = 0; self.scroll = None; self.overlay = None
        self.icon_width = [p.read(p.read(ICON_RECTS+4*i, 4)+8, 4) for i in range(0x33)]
    def set_option(self, offset, value): self.p.write(OPTION+offset, value, 1)
    def set_context(self, mode, owner, menu_seat, seat, list_id, alternate):
        p = self.p
        p.write(0x4c3808, mode, 4); p.write(0x582f3c, owner, 4); p.write(0x12d35c4, menu_seat, 4)
        p.write(0x4d3d08, ACTORS, 4)
        actor = ACTORS+0xf2c*seat
        p.write(actor+0xa14, list_id, 4); p.write(actor+0x23c, 0x100000 if alternate else 0x20, 4)
        # 1da7e8 writes the scheduler word of the three pause-menu task records.
        for i in range(3):
            p.write(0x582f54+4*i, PAUSE_TASKS+0x40*i, 4); p.write(PAUSE_TASKS+0x40*i+4, 0x55, 4)
        p.write(0x582f30, 3, 4); p.write(0x582f50, 1, 4)
    def observe(self, pc):
        p = self.p; r = p.registers
        f = lambda n: int(p.float_value(n))
        if pc == 0x1e7b70:
            assert signed(r[4], 32) == -1; self.tones.append(signed(r[5], 32))
        elif pc == 0x1252f0:
            assert [x & 0xffffffff for x in r[4:8]] == [1, 0, 0x13d640, 0x1cfa10]; self.event = 2
        elif pc == 0x1da7e8: self.event = 1
        elif pc == 0x17e0b0: self.draws.append((BAR, signed(r[4], 32), f(12), f(13), signed(r[5], 32), signed(r[6], 32), 0, 0))
        elif pc == 0x17e038:
            icon = signed(r[4], 32)
            width = 0 if icon == 0x2d and not p.read(OPTION+0x7e, 1) else self.icon_width[icon]
            self.draws.append((ICON, icon, f(12), f(13), width, 0, 0, 0))
        elif pc in (0x10a710, 0x10a1c0):
            self.draws.append((GLYPH, r[4] & 0xffff, signed(r[5], 32), signed(r[6], 32), 0, 0, 1 if pc == 0x10a710 else 2, p.read(COLOUR, 4)))
        elif pc == 0x17e228:
            which = {0x5f2000: 0, 0x5f2008: 1}[r[4] & 0xffffffff]
            self.draws.append((ASCII, which, signed(r[5], 32), signed(r[6], 32), 0, 0, signed(r[7], 32), p.read(COLOUR, 4)))
        elif pc == 0x17f090:
            box = struct.unpack('<4f', p.memory[(r[4] & 0xffffffff)+0xc:(r[4] & 0xffffffff)+0x1c])
            assert signed(r[6], 32) == 1 and signed(r[8], 32) == 0xc
            self.scroll = [1, int(box[2]), int(box[3]), signed(r[5], 32), signed(r[7], 32), int(box[0]), int(box[1])]
        elif pc == 0x1145c0:
            assert [signed(x, 32) for x in r[4:8]] == [0, 0, 0x280, 0x1c0] and not r[8] & 0xffffff
            self.overlay = (r[8] >> 24) & 0xff
    def clear(self): self.tones = []; self.draws = []; self.event = 0; self.scroll = None; self.overlay = None
    def call(self, pc, *args, limit=4000000):
        return self.run(pc, *args, observe=self.observe, limit=limit)
    def flat_draws(self, full):
        if full: return [len(self.draws), *[v for d in self.draws for v in d]]
        h = 2166136261
        for d in self.draws:
            for v in d: h = fnv(struct.pack('<I', v & 0xffffffff), h)
        return [len(self.draws), h]
    def handle(self, pointer):
        if not pointer: return [-1, -1]
        if COMMON <= pointer < CHARACTER: return [0, (pointer-COMMON)//0x14]
        assert CHARACTER <= pointer < CATEGORIES
        return [1, (pointer-CHARACTER)//0x14]
    def detail(self, at):
        w = self.word; p = self.p
        return [w(at), w(at+0xc), w(at+0x10), w(at+0x14), w(at+0x18), *self.panel(at+0x1c), p.read(at+0x50, 4), w(at+0x58),
                w(at+0x5c), w(at+0x60), w(at+0x64), w(at+0x68), w(at+0x6c), w(at+0x70), *self.handle(p.read(at+0x74, 4))]
    def common_selection(self, at):
        p = self.p; cur = self.word(at+0x64)
        if not p.read(at+0x50, 4) & 0x1000: return cur
        return signed(p.read(COMMON_MAP+2*cur, 2), 16)+1 if 0 <= cur < 10 else -1
    # One visit of task 13d680: pad sampling, then the loop body up to 112a28.
    def start_task(self): self.start(TASK, STACK, STACK_WORDS)
    def tick(self, held):
        p = self.p
        self.sample(held); self.clear()
        assert self.visit() == 0x112a28
        frame = self.frame; state, last, dim, seat = (self.reg(n) for n in (17, 18, 16, 19))
        assert (self.overlay or 0) == dim and (self.overlay is None) == (dim <= 0)
        if self.event == 1:
            assert [p.read(PAUSE_TASKS+0x40*i+4, 4) for i in range(3)] == [0x10, 0x21, 0x21]
            assert p.read(0x582f30, 4) == 0 and p.read(0x582f50, 4) == 0
        L, S, D = frame+0x170, frame+0x9e0, frame+0x1250
        return [state, last, dim, seat, *self.guide(frame), *self.list(L), *self.list(S), self.common_selection(S),
                *self.detail(D), self.event, len(self.tones), *self.tones, *self.flat_draws(False),
                *(self.scroll or [0, 0, 0, 0, 0, 14, 368])]

def compare(name, commands, expected, exe):
    native = subprocess.run([exe, ASSETS], input='\n'.join(commands)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(expected), (name, len(actual), len(expected))
    for i, (a, b) in enumerate(zip(actual, expected)):
        assert a == list(b), (name, i, len(a), len(b), [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12])

def option_set(rng, kind):
    """(offset, value) pairs: fighter locks 16.., spirit unlocks 7e..80, extra fighters 94."""
    out = []
    for c in range(49):
        locked = {'factory': None, 'open': 0, 'sparse': int(rng.random() < 0.6), 'mixed': int(rng.random() < 0.3)}[kind]
        if locked is not None: out.append((0x16+c, locked))
    spirits = {'factory': (0, 0, 0), 'open': (1, 1, 1)}.get(kind) or tuple(rng.randrange(2) for _ in range(3))
    out += [(0x7e+i, v) for i, v in enumerate(spirits)]
    out.append((0x94, {'factory': 0, 'open': 1}.get(kind, rng.randrange(2))))
    return out

CONFIRM, CANCEL = (0x200, 0x200, 2, 8), (0x400, 4)

def gesture(rng, state):
    kind = rng.random()
    if kind < 0.05: return [rng.choice((0x40, 0x80, 0x1000, 0x8000, 0x80000, 0x220, 0x600, 0x410, 0x28, 1)), 0]
    if kind < 0.12: return [0]*rng.randrange(1, 24)
    if kind < 0.20: return [rng.choice((0x10, 0x20, 0x20, 0x400000, 0x100000))]*rng.randrange(18, 60)
    move = [rng.choice((0x20, 0x20, 0x20, 0x10, 0x10, 0x400000, 0x100000, 0x800000, 0x200000)), 0]*rng.randrange(1, 5)
    confirm, cancel = [rng.choice(CONFIRM), 0], [rng.choice(CANCEL), 0]
    # (confirm, cancel) odds per state; state 2 is left by either key.
    odds = {0: (0.35, 0.06), 1: (0.40, 0.10), 2: (0.05, 0.10)}.get(state, (0.2, 0.2))
    pick = rng.random()
    if pick < odds[0]: return confirm
    if pick < odds[0]+odds[1]: return cancel
    return move

def task_case(spec):
    exe, name, mode, owner, menu_seat, kind, seed, visits = spec
    rng = random.Random(f'task{name}{seed}')
    options = option_set(rng, kind)
    o = Source(options, seed=seed)
    seat = {1: 0, 2: 1, 3: int(owner == 1), 0xb: 0, 0xc: 1, 0xd: menu_seat, 0xe: menu_seat}[mode]
    fighter = lambda: (rng.choice((rng.randrange(49), rng.randrange(49), 1, 0x16, 0x19, 0x2b)), rng.random() < 0.15)
    list_id, alternate = fighter()
    o.set_context(mode, owner, menu_seat, seat, list_id, alternate)
    commands = [f'opt {a} {b}' for a, b in options]+[f'ctx {mode} {list_id+(0x32 if alternate else 0)}', f'enter {seat}']
    expected = []
    o.start_task()
    states = set(); events = [0, 0, 0]; tones = 0; pages = 0; groups = set(); queue = []; state = 0; tail = None
    for visit in range(visits):
        if not queue: queue = gesture(rng, state)
        key = queue.pop(0)
        noise = rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8))
        held = [noise, key] if seat else [key, noise]
        row = o.tick(held)
        assert row[3] == seat
        commands.append(f'tick {held[0]} {held[1]}'); expected.append(row)
        state = row[0]; states.add(state); events[o.event] += 1; tones += len(o.tones)
        if o.draws:
            pages += 1
            D = o.frame+0x1250; groups.add((o.word(D+0x6c), o.word(D+0x70)))
        if o.event == 1:
            # 1da7e8 suspends the task here; a later pause wakes it with a possibly different fighter.
            list_id, alternate = fighter()
            o.set_context(mode, owner, menu_seat, seat, list_id, alternate)
            commands.append(f'ctx {mode} {list_id+(0x32 if alternate else 0)}')
        if o.event == 2 and tail is None: tail = 12
        if tail is not None:
            tail -= 1
            if tail < 0: break
    compare(name, commands, expected, exe)
    return dict(name=name, mode=mode, seat=seat, options=kind, snapshots=len(expected), instructions=o.instructions,
                states=sorted(states), pause_returns=events[1], scene_requests=events[2], tones=tones, page_visits=pages,
                groups=sorted(groups))

def groups_of(o, base):
    out = []; at = base
    while signed(o.p.read(at, 2), 16) != -2:
        ident = signed(o.p.read(at, 2), 16)
        if ident >= 0: out.append(ident)
        at += 0x14
    return out

def page_case(spec):
    """13cf88/13cfc0, 13cff8 and 13d0d0 called directly for every group."""
    exe, table, part, parts, seed = spec
    rng = random.Random(f'page{table}{part}{seed}')
    o = Source(seed=seed); p = o.p
    commands = []; expected = []; calls = 0
    ids = groups_of(o, COMMON if table == 0 else CHARACTER)[part::parts]
    unlock = (0, 0, 0)
    def unlocks(bits):
        nonlocal unlock
        if bits != unlock:
            unlock = bits
            for i, v in enumerate(bits): o.set_option(0x7e+i, v); commands.append(f'opt {0x7e+i} {v}')
    def page(ident, handle, x, y, scroll, lines, gap):
        nonlocal calls
        o.clear(); p.write(COLOUR, 0x12345678, 4)
        o.call(0x13d0d0, handle, x, y, ident, scroll, lines, gap)
        commands.append(f'page {table} {ident} {x} {y} {scroll} {lines} {gap}'); expected.append(o.flat_draws(True)); calls += 1
    for ident in ids:
        handle = o.call(0x13cf88 if table == 0 else 0x13cfc0, ident) & 0xffffffff
        count = signed(o.call(0x13cff8, handle, ident), 32)
        commands.append(f'group {table} {ident}'); expected.append([o.handle(handle)[1], count]); calls += 2
        for bits in ((0, 0, 0), (1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1)):
            unlocks(bits); page(ident, handle, 0x38, 0x28, 0, 0xc, 8)
        unlocks(tuple(rng.randrange(2) for _ in range(3)))
        # Every reachable scroll position of the window, then arbitrary windows.
        for scroll in range(1, max(1, count-0xb)): page(ident, handle, 0x38, 0x28, scroll, 0xc, 8)
        for _ in range(6):
            page(ident, handle, rng.randrange(-40, 300), rng.randrange(-40, 300), rng.randrange(-2, count+3),
                 rng.randrange(0, count+4), rng.randrange(0, 20))
        # A handle that does not open the requested group draws nothing and counts zero.
        other = ident+1
        o.clear(); o.call(0x13d0d0, handle, 0x38, 0x28, other, 0, 0xc, 8)
        assert not o.draws and signed(o.call(0x13cff8, handle, other), 32) == 0
    compare(f'page-{table}-{part}', commands, expected, exe)
    return dict(name=f'page-{table}-{part}', groups=len(ids), snapshots=calls, instructions=o.instructions)

CODES = [b'I'+bytes([c]) for c in b'123456789ABCDEZWH0XQ']+[b'G'+bytes([c]) for c in b'1234567890A']+ \
        [b'L1', b'L2', b'L3', b'R1', b'R2', b'R0', b'SC', b'ST', b'SL', b'SX', b'BO', b'BX', b'BT', b'BS', b'BP', b'BQ',
         b'OR', b'OP', b'PL', b'PR', b'EX', b'EXIT', b'MS', b'CR', b'C', b'R', b'M', b'S', b' ', b'  ', b'.', b'A', b'x',
         b'\x82\x6d', b'\x81\x45', b'\x93\x43', b'\x83\x43', b'\x83\x52', b'\x82\x4d\x53', b'\x88\x43\x52']

def line_case(spec):
    """17e428 and 17e3d8 over synthetic lines that reach every code branch."""
    exe, part, seed, count = spec
    rng = random.Random(f'line{part}{seed}')
    o = Source(seed=seed); p = o.p
    commands = []; expected = []
    matsuri = 0
    for n in range(count):
        if n % 97 == 0:
            matsuri ^= 1; o.set_option(0x7e, matsuri); commands.append(f'opt {0x7e} {matsuri}')
        text = b''.join(rng.choice(CODES) for _ in range(rng.randrange(0, 14)))
        if rng.random() < 0.2: text += bytes([rng.randrange(0x81, 0xa0)])   # dangling lead byte
        size, plain, x, y = rng.choice((1, 2)), rng.randrange(2), rng.randrange(-50, 600), rng.randrange(-50, 400)
        colour = rng.getrandbits(32)
        p.memory[TEXT:TEXT+len(text)+1] = text+b'\0'
        p.write(COLOUR, colour, 4); p.write(0x4ee85c, rng.randrange(2), 4); p.write(0x4ee860, rng.randrange(2), 4)
        o.clear(); p.put_exact_float(12, float(x)); p.put_exact_float(13, float(y))
        end = o.call(0x17e428, TEXT, size, plain) & 0xffffffff
        commands.append(f'line {size} {plain} {x} {y} {colour} {text.hex() or "-"}')
        expected.append([end-TEXT if end else -1, *o.flat_draws(True)])
        # 17e3d8 from every offset agrees with the first "CR" the port finds.
        nxt = o.call(0x17e3d8, TEXT) & 0xffffffff
        assert (nxt-TEXT if nxt else -1) == next_line(text), text
    compare(f'line-{part}', commands, expected, exe)
    return dict(name=f'line-{part}', snapshots=len(expected), instructions=o.instructions)

def next_line(text):
    """Independent transcription of 17e3d8 (bytewise scan, the byte after a 'C' is skipped)."""
    at = 0
    def byte(i): return text[i] if i < len(text) else 0
    c = byte(at); at += 1
    if not c: return -1
    while True:
        if c == 0x43:
            d = byte(at); at += 1
            if not d: return -1
            if d == 0x52: return at
        c = byte(at)
        if not c: return -1
        at += 1

def rows_case(spec):
    """20e570 + 20e8c0 + 20ea88 over every lock combination that 20e8c0 reads."""
    exe, seed = spec
    o = Source(seed=seed); p = o.p
    commands = []; expected = []
    current = {}
    def opt(offset, value):
        if current.get(offset) != value:
            current[offset] = value; o.set_option(offset, value); commands.append(f'opt {offset} {value}')
    for bits in range(1 << 7):
        for i, offset in enumerate((0x7e, 0x7f, 0x80, 0x42, 0x43, 0x44, 0x45)): opt(offset, bits >> i & 1)
        for visible in (9, 4, -1):
            p.memory[WIDGET:WIDGET+0x900] = bytes(0x900)
            o.call(0x20e570, WIDGET); o.call(0x20e8c0, WIDGET, visible)
            row = o.list(WIDGET)
            for cursor in range(o.word(WIDGET+0x5c)):
                p.write(WIDGET+0x64, cursor, 4); row.append(signed(o.call(0x20ea88, WIDGET), 32))
            commands.append(f'rows {visible}'); expected.append(row)
    compare('rows', commands, expected, exe)
    return dict(name='rows', snapshots=len(expected), instructions=o.instructions)

def main():
    cli = argparse.ArgumentParser(); cli.add_argument('--only'); cli.add_argument('--jobs', type=int, default=6)
    args = cli.parse_args()
    assert digest(ELF) == PIN
    assert (ASSETS/'skill_list.bin').read_bytes() == (ROOT/'work/ss6/extracted/resources/skill_list.bin').read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; exe = Path(tmp)/'driver'
        cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp,
                        *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        jobs = []
        # (mode word, 582f3c pause owner, 12d35c4 menu seat)
        contexts = [(1, 0, 0), (2, 0, 0), (3, 0, 1), (3, 1, 0), (0xb, 0, 0), (0xc, 0, 0), (0xd, 0, 0), (0xd, 0, 1)]
        for n, (mode, owner, menu_seat) in enumerate(contexts):
            for k, kind in enumerate(('factory', 'open', 'sparse', 'mixed')):
                jobs.append((task_case, (exe, f'task-{mode:x}-{owner}{menu_seat}-{kind}', mode, owner, menu_seat, kind, 40+4*n+k, 1500)))
        jobs += [(page_case, (exe, 0, part, 2, 7)) for part in range(2)]
        jobs += [(page_case, (exe, 1, part, 12, 9)) for part in range(12)]
        jobs += [(line_case, (exe, part, 11, 700)) for part in range(4)]
        jobs.append((rows_case, (exe, 13)))
        if args.only: jobs = [j for j in jobs if j[0].__name__.startswith(args.only)]
        with ProcessPoolExecutor(args.jobs) as pool:
            futures = [pool.submit(fn, spec) for fn, spec in jobs]
            cases = [f.result() for f in futures]
    total = sum(c['snapshots'] for c in cases); instructions = sum(c['instructions'] for c in cases)
    tasks = [c for c in cases if 'states' in c]
    if not args.only:
        states = sorted({s for c in tasks for s in c['states']})
        assert states == [-2, -1, 0, 1, 2], states
        assert sum(c['pause_returns'] for c in tasks) > 20 and sum(c['scene_requests'] for c in tasks) >= 4
        shown = {tuple(g) for c in tasks for g in c['groups']}
        assert len({g for g in shown if g[0] == 0}) == 10 and len({g for g in shown if g[0] == 1}) >= 40, len(shown)
        REPORT.write_text(json.dumps(dict(
            status='passed', elf_sha256=PIN, snapshots=total, instructions=instructions,
            task_visits=sum(c['snapshots'] for c in tasks), states_reached=states,
            pause_returns=sum(c['pause_returns'] for c in tasks), scene_requests=sum(c['scene_requests'] for c in tasks),
            tones=sum(c['tones'] for c in tasks), page_visits=sum(c['page_visits'] for c in tasks), groups_shown=len(shown),
            native_sources={s: hashlib.sha256((ROOT/'src'/s).read_bytes()).hexdigest() for s in SOURCES},
            assets={n: hashlib.sha256((ASSETS/n).read_bytes()).hexdigest() for n in ('skill_list.bin', 'menu_widgets.bin')},
            scope=SCOPE, cases=cases), indent=2)+'\n')
    print(f'passed: {len(cases)} EE/native skill-list traces; {total} snapshots '
          f'({sum(c["snapshots"] for c in tasks)} task visits); {instructions} instructions')

SCOPE = ('Japanese SLPS-25559. Task 13d680 (pause-menu SKILL LIST, tag 151b) in game modes 1, 2, 3 (both pause owners), b, c '
         'and d (both menu seats): the task is a PS2 kernel thread, so the validator keeps the thread register file, runs the '
         'unmodified prologue and loop body on the task stack up to the yield entry 112a28 and resumes at the saved return '
         'address, with 117fd8 pad sampling of both ports before every visit. Compared per visit: state, previous state, '
         'overlay alpha and seat (s1, s2, s0, s3), the complete guide window, both list widgets (slide panels, selector, item '
         'texts, selected id), the 20ea88 selection, the detail object (geometry, panel, selector, category, selection, record '
         'pointer), the ordered 1e7b70 tones, the 1da7e8 / 1252f0 close request (1da7e8 runs and its five writes are checked), '
         'the 1145c0 overlay argument, the 17f090 scroll-bar arguments and a hash of every leaf draw request issued by 210298. '
         'Direct whole-function comparisons: 13cf88/13cfc0 + 13cff8 + 13d0d0 for all 10 common and 54 character groups over '
         'five unlock combinations, every reachable scroll position and random windows, each leaf request compared in order '
         '(17e0b0 bar type/size/position, 17e038 icon id/position, 10a710/10a1c0 glyph code/position/size/colour word, 17e228 '
         'literal/position/size); 17e428 and 17e3d8 over 2,800 synthetic lines covering every code pair; 20e570 + 20e8c0 + '
         '20ea88 over all 128 combinations of the seven option bytes they read. Stubbed (jr ra) on top of the gallery '
         'validator boundaries (rendering leaves 113f98 1145c0 1147d8 10a460 10a568 10a710 10a1c0 109f08 1135e8, texture and '
         'palette loads 1142d8 1163c0 116478 10add8 112f30 17eda0, menu background 1ce570 1ce628 1e1620 1e2358 1e23a0 1e2408, '
         '182858 1828c0 120110, sound driver 1e7b70 and siblings, debug prints 316140 316218, thread creation 100e58, scene '
         'switch 1252f0): guide-window draw 182600, list draw 20ef38, heading bar 17e0b0, ASCII string draw 17e228 and '
         'scroll-bar draw 17f090; their arguments are compared where the port models them. The icon pen advance is the '
         'value 17df90 returns (rect width), checked through the positions of the following requests. Not compared: draw '
         'depth (17c228 sequence), the list and guide draw routines, the scheduler (1126f0, task suspension by the +4 word).')

if __name__ == '__main__':main()
