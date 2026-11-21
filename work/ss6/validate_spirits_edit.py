#!/usr/bin/env python3
"""Match the native SPIRITS EDIT scene and edit widgets to SLPS-25559 visit by visit."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from pathlib import Path

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ELF, PIN, ROOT, digest
from extract_save_default import factory_image

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/spirits_edit_validation.json'
SOURCES = ['spirits_edit.cpp', 'edit_widgets.cpp', 'console_menu.cpp', 'system_data.cpp', 'game_random.cpp']
TABLE, OPTION, NETWORK, PAD = 0x4d7068, 0x43d058, 0x12d2308, 0x1237cc8
TASK, YIELD, RESUME, STACK_TOP = 0x13ada0, 0x112a28, 0x13af48, 0x124a1c0+0x6000
# Callees replaced by `jr ra; move v0,zero`. Everything else runs from the ELF.
STUBS = {
    'rendering': (0x20d9f8, 0x20ef38, 0x182600, 0x17eac8),
    'texture and palette loading': (0x17eab0, 0x1142d8, 0x1163c0, 0x116478, 0x10add8),
    'page background animation setup': (0x1e1620, 0x1e2358, 0x1e2408, 0x1e23a0),
    'sound driver': (0x1e7b70, 0x1e7b40),
    'scene switch': (0x1252f0,),
    'memory card': (0x10f158,),
    'debug print': (0x316140,),
}
DRIVER = r'''
#include "spirits_edit.hpp"
#include <iostream>
#include <memory>
#include <sstream>
using namespace ss6;
static uint32_t mix(uint32_t h,const std::string& s){for(unsigned char c:s)h=h*131+c;return h*131+0x100;}
static std::ostream& operator<<(std::ostream& o,const EditSlide& s){
    for(int v:{s.x,s.y,s.remaining,s.duration,s.startX,s.startY,s.targetX,s.targetY,s.retracted,s.outX,s.outY,s.inX,s.inY})o<<v<<' ';
    return o;
}
static std::ostream& operator<<(std::ostream& o,const EditListCursor& l){
    return o<<l.flags<<' '<<l.min<<' '<<l.max<<' '<<l.step<<' '<<l.cursor<<' '<<l.page<<' ';
}
static void menu(std::ostream& o,const EditListMenu& m){
    o<<m.width<<' '<<m.height<<' '<<m.visibleRows<<' '<<m.scroll<<' '<<m.visible<<' '<<m.active<<' '<<m.slide<<m.list;
    uint32_t h=0;for(int i=0;i<m.list.max&&i<0x200;++i)h=mix(h,m.rows[i]);
    o<<h<<' ';
}
static void panel(std::ostream& o,const SpiritPanel& p){
    o<<p.width<<' '<<p.height<<' '<<p.visibleRows<<' '<<p.scroll<<' '<<p.visible<<' '<<p.active<<' '<<p.slide<<p.list
     <<p.nameChars<<' '<<p.valueChars<<' ';
    uint32_t a=0,b=0;
    for(int i=0;i<32;++i){o<<p.cost[i]<<' ';a=mix(a,p.label[i]);b=mix(b,p.value[i]);}
    o<<a<<' '<<b<<' '<<mix(0,p.title)<<' ';
}
int main(int,char** argv){
    SystemData data(argv[1]);
    SpiritsEditAssets assets(argv[1]);
    EditWidgetAssets widgets(argv[1]);
    GameRandom random;
    std::unique_ptr<SpiritsEdit> scene;
    MenuPadRepeat repeat;std::array<uint32_t,2> last{};
    EditSlide slide;
    EditListMenu list(widgets);
    NetworkSpirits network;
    for(unsigned p=0;p<2;++p)for(unsigned s=0;s<8;++s)for(unsigned i=0;i<16;++i)network.players[p][s][i]=uint8_t(p*131+s*17+i*3+1);
    std::string line;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);std::ostringstream o;std::string op;in>>op;
        auto num=[&]{long long v=0;in>>v;return v;};
        auto desc=[&]{SpiritDescriptor d{};for(auto& v:d)v=uint8_t(num());return d;};
        if(op=="I"){
            data.option(0x95)=uint8_t(num());data.setAutoSave(int32_t(num()));
            unsigned long long seed;in>>seed;random.librarySeed=seed;
            for(unsigned i=0;i<128;++i)data.image()[SystemData::records4d7068+i]=uint8_t(num());
            repeat=MenuPadRepeat();last={};
            scene=std::make_unique<SpiritsEdit>(data,assets,widgets,random);
            o<<"0";
        } else if(op=="T"){
            const std::array<uint32_t,2> held{uint32_t(num()),uint32_t(num())};const unsigned seat=unsigned(num());
            const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            const auto r=scene->tick(pads[seat]);
            auto& s=*scene;auto& e=s.editor;
            o<<s.state<<' '<<s.next<<' '<<s.frameOpen<<' '<<s.helpId<<' '<<s.helpSub<<' '<<mix(0,s.helpText())<<' '
             <<s.chrome.variant<<' '<<random.librarySeed<<' ';
            menu(o,s.slots);panel(o,e.categories);panel(o,e.options);
            o<<e.options.list.disabled[0]<<' '<<e.slot<<' '<<e.focus<<' ';
            for(int v:e.first)o<<v<<' ';
            for(int v:e.descriptor)o<<v<<' ';
            o<<s.summary;
            for(unsigned i=0;i<128;++i)o<<unsigned(data.image()[SystemData::records4d7068+i])<<' ';
            const auto icons=s.summaryIcons();
            o<<icons.size()<<' ';for(auto i:icons)o<<i.group<<' '<<i.icon<<' ';
            o<<r.exitToTitle<<' '<<r.autoSave<<' '<<r.sounds.size();for(int v:r.sounds)o<<' '<<v;
        } else if(op=="sc"){
            const int a=num(),b=num(),c=num(),d=num(),f=num();slide.configure(a,b,c,d,f);o<<"0 "<<slide;
        } else if(op=="si"){slide.slideIn();o<<"0 "<<slide;
        } else if(op=="so"){slide.slideOut();o<<"0 "<<slide;
        } else if(op=="su"){const int r=slide.update();o<<r<<' '<<slide<<slide.settled();
        } else if(op=="ps"){const int a=num(),b=num(),c=num(),d=num(),e=num();o<<editPageScroll(a,b,c,d,e);
        } else if(op=="fs"){const int a=num(),b=num(),c=num(),d=num();o<<editFollowScroll(a,b,c,d);
        } else if(op=="lu"){
            EditListCursor l;l.flags=uint32_t(num());l.min=num();l.max=num();l.step=num();l.cursor=num();l.page=num();
            l.disabled[0]=uint32_t(num());l.disabled[1]=uint32_t(num());
            MenuPad pad;pad.pressed=uint32_t(num());pad.repeat=uint32_t(num());
            std::vector<int> sounds;const int e=l.update(pad,sounds);
            o<<e<<' '<<l.cursor<<' '<<sounds.size();for(int v:sounds)o<<' '<<v;
        } else if(op=="lr"){
            EditListCursor l;l.flags=uint32_t(num());l.cursor=num();
            const int a=num(),b=num(),c=num(),d=num();l.setRange(a,b,c,d);o<<l;
        } else if(op=="lc"){
            EditListCursor l;l.flags=uint32_t(num());l.min=num();l.max=num();l.cursor=num();l.setCursor(num());o<<l.cursor;
        } else if(op=="lb"){
            // attach, disable/enable one row, then test a row
            EditListCursor l;l.flags=uint32_t(num());const int row=num(),on=num(),probe=num();
            if(on)l.disableRow(row);else {l.disabled[0]=l.disabled[1]=~0u;l.enableRow(row);}
            o<<l.disabled[0]<<' '<<l.disabled[1]<<' '<<l.rowDisabled(probe);
        } else if(op=="cl"){
            const int visible=num(),first=num(),ex=num(),kuroko=num(),ending=num();
            for(unsigned i=0;i<0x98;++i)data.option(i)=uint8_t(num());
            list=EditListMenu(widgets);
            list.buildCharacterList(data,visible,first,ex,kuroko,ending);
            list.slide.configure(0,0,5,5,1);list.slide.slideIn();list.visible=list.active=1;
            menu(o,list);for(int v:list.characterIds)o<<v<<' ';o<<list.selected();
        } else if(op=="cm"){
            MenuPad pad;pad.pressed=uint32_t(num());pad.repeat=uint32_t(num());
            std::vector<int> sounds;const int e=list.update(pad,sounds);
            o<<e<<' ';menu(o,list);o<<list.selected()<<' '<<sounds.size();for(int v:sounds)o<<' '<<v;
        } else if(op=="cs"){
            list.select(int(num()));o<<list.list.cursor<<' '<<list.scroll<<' '<<list.selected();
        } else if(op=="ml"){
            // 20e738 on a plain list with one of the three layouts
            const int layout=num(),count=num(),visible=num();
            list=EditListMenu(widgets);
            if(layout)list.list.setFlag(layout==1?16:15,true);
            std::vector<std::string> rows;for(int i=0;i<count;++i)rows.push_back(assets.options[i].japanese);
            list.setStrings(rows,visible);
            list.slide.configure(0,0,5,5,1);list.slide.slideIn();list.visible=list.active=1;
            menu(o,list);
        } else if(op=="def"){
            restoreDefaultSpirits(data,assets);
            for(unsigned i=0;i<128;++i)o<<unsigned(data.image()[SystemData::records4d7068+i])<<' ';
        } else if(op=="pts"){
            const int slot=num();const auto d=desc();
            o<<spiritPointsUsed(assets,d)<<' '<<spiritPointsLeft(assets,d,slot);
        } else if(op=="ico"){
            const auto icons=spiritIcons(desc());
            o<<icons.size();for(auto i:icons)o<<' '<<i.group<<' '<<i.icon;
        } else if(op=="tab"){
            for(unsigned i=0;i<128;++i)data.image()[SystemData::records4d7068+i]=uint8_t(num());o<<"0";
        } else if(op=="acc"){
            const int sub=num(),system=num();const unsigned player=num(),slot=num(),category=num();
            const auto d=actorSpiritDescriptor(data,sub,system,player,slot,&network);
            o<<bool(d);for(unsigned i=0;i<16;++i)o<<' '<<(d?unsigned((*d)[i]):0u);
            o<<' '<<actorSpiritOption(data,sub,system,player,slot,category,&network);
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
        self.seed = p.read(0x5d1bf8, 4)+0xa8
        self.instructions = 0
        self.sounds = []
        self.commits = 0
        self.context = None
        self.last = [0, 0]
    def word(self, at): return signed(self.p.read(at, 4), 32)
    def words(self, at, n): return [self.word(at+4*i) for i in range(n)]
    def text(self, at):
        if not at: return b''
        m = self.p.memory; return bytes(m[at:m.index(0, at)])
    def run(self, pc, *args, limit=400000, observe=None, stop=()):
        value, count = self.p.run(pc, args, limit=limit, observe=observe or self.watch, stop_before=stop)
        self.instructions += count
        return value
    def watch(self, pc):
        p = self.p; r = p.registers
        if self.context is not None:
            # The EE kernel resumes the task thread with its saved context.
            if self.context == 'start': r[29] = STACK_TOP
            else: p.registers[:], p.registers_high[:], p.floats[:], p.lo, p.hi = self.context
            self.context = None
        if pc == 0x1e7b70:
            assert signed(r[4], 32) == -1; self.sounds.append(signed(r[5], 32))
        elif pc == 0x1252f0:
            assert [x & 0xffffffff for x in r[4:8]] == [1, 0, 0x13ad60, 0x127940]; self.exit = 1
        elif pc == 0x10f158: self.saved = int(p.read(0x5735c8, 4) != 0)
        elif pc == 0x1821f8: self.help = (signed(r[4], 32), signed(r[5], 32))
        elif pc == 0x20ee70: self.M = r[4] & 0xffffffff
        elif pc == 0x20d818: self.E = r[4] & 0xffffffff
        elif pc == 0x17f330 and r[31] == 0x13aec8: self.S = r[4] & 0xffffffff
        elif pc == 0x1822a0: self.F = r[4] & 0xffffffff
        elif pc == 0x152830: self.commits += 1
    def pad(self, held):
        for s, h in enumerate(held):
            self.p.write(0x443568+4*s, h, 4); self.p.write(0x443570+4*s, self.last[s], 4); self.run(0x117fd8, s)
        self.last = list(held)
    # Scene -----------------------------------------------------------------
    def enter(self, mode, slots8, autosave, seed, table):
        p = self.p
        p.write(0x4c3808, mode, 4); p.write(0x4c38a8, 0, 4); p.write(0x43d0ed, slots8, 1)
        p.write(0x5735c8, autosave, 4); p.write(self.seed, seed, 8)
        p.memory[TABLE:TABLE+128] = bytes(table)
        self.started = False; self.help = (-1, 0)
    def tick(self, held):
        p = self.p
        self.pad(held)
        self.sounds = []; self.exit = self.saved = 0
        # 13acd8 hands 13ada0 to an EE kernel thread (100e58) and 112a28
        # yields through kernel calls. The harness performs that switch:
        # each visit runs the original task from its yield return address to
        # the next call of 112a28 on the task's own zeroed stack.
        self.context = self.context_saved if self.started else 'start'
        self.run(RESUME if self.started else TASK, limit=3000000, stop=(YIELD,))
        r = p.registers
        assert r[31] == RESUME and self.context is None
        self.context_saved = (list(p.registers), list(p.registers_high), list(p.floats), p.lo, p.hi)
        self.started = True
        return self.row(signed(r[21], 32), signed(r[16], 32))
    def slide(self, at): return self.words(at, 13)
    def list(self, at): return [self.p.read(at, 4), *self.words(at+8, 5)]
    def menu(self, m):
        h = 0
        for i in range(min(self.word(m+0x5c), 0x200)): h = mix(h, self.text(self.p.read(m+0x6c+4*i, 4)))
        return [*self.words(m, 2), *self.words(m+0xc, 4), *self.slide(m+0x1c), *self.list(m+0x50), h]
    def panel(self, m):
        a = b = 0
        for i in range(32):
            a = mix(a, self.text(self.p.read(m+0xf4+4*i, 4))); b = mix(b, self.text(self.p.read(m+0x174+4*i, 4)))
        return [*self.words(m, 2), *self.words(m+0xc, 4), *self.slide(m+0x1c), *self.list(m+0x50),
                *self.words(m+0x6c, 2), *self.words(m+0x74, 32), a, b, mix(0, self.text(self.p.read(m+8, 4)))]
    def icons(self, slot):
        out = 0x1c08000
        self.run(0x152988, out, slot)
        pairs = []
        for i in range(17):
            g = signed(self.p.read(out+2*i, 2), 16)
            if g < 0: break
            pairs += [g, signed(self.p.read(out+0x22+2*i, 2), 16)]
        return [len(pairs)//2, *pairs]
    def row(self, state, nxt):
        p = self.p; M, E, S = self.M, self.E, self.S
        assert self.F == M-0x170 and E == M+0x870 and S == M+0xd10
        ident, sub = self.help
        index = next((i for i in range(207) if p.read(0x4ee870+8*i, 1) == ident), None)
        assert index is None or 0 <= index+sub < 207
        text = self.text(p.read(0x4ee870+8*(index+sub)+4, 4)) if index is not None else b''
        table = list(p.memory[TABLE:TABLE+128])
        icons = self.icons(self.word(M+0x64))
        return [state, nxt, self.word(self.F+0x14), ident, sub, mix(0, text), self.word(0x582b44), p.read(self.seed, 8),
                *self.menu(M), *self.panel(E), *self.panel(E+0x1f8), p.read(E+0x3ec, 4), self.word(E+0x3f0),
                self.word(E+0x3f4), *self.words(E+0x3fc, 16), *p.memory[E+0x440:E+0x450], *self.slide(S), *table,
                *icons, self.exit, self.saved, len(self.sounds), *self.sounds]

KEYS = [0x20]*6+[0x10]*4+[0x200]*5+[2, 8, 0x208]+[0x400]*2+[4, 0x40, 0x80, 0x100000, 0x400000, 0x200000, 0x800000,
        0x30, 0x220, 0x600, 0x410, 0x28, 0x100020, 0x80000, 1]

def gesture(rng, state, focus):
    """Next pad gesture, biased by the scene state so that sessions reach deep states."""
    kind = rng.random()
    if kind < 0.10: return [rng.choice(KEYS), 0]
    if kind < 0.14: return [rng.choice(KEYS) | rng.choice(KEYS)]+[0]*rng.randrange(0, 3)
    if kind < 0.20: return [0]*rng.randrange(1, 20)
    if kind < 0.26: return [rng.choice((0x10, 0x20, 0x20, 0x40, 0x80, 0x400000, 0x100000))]*rng.randrange(18, 50)
    confirm = rng.choice((0x200, 0x200, 2, 8)); cancel = rng.choice((0x400, 4))
    move = [rng.choice((0x20, 0x20, 0x20, 0x10, 0x10, 0x400000, 0x100000, 0x800000, 0x200000)), 0]
    odds = {7: (0.30, 0.02), 8: (0.45, 0.10) if focus else (0.40, 0.03)}.get(state, (0.2, 0.2))
    pick = rng.random()
    if pick < odds[0]: return [confirm, 0]
    if pick < odds[0]+odds[1]: return [cancel, 0]
    return move*rng.randrange(1, 4)

def random_table(rng, options, valid=True):
    table = []
    for _ in range(8):
        for c in range(16):
            mine = [i for i, o in enumerate(options) if o[0] == c]
            table.append(rng.choice(mine) if valid or rng.random() < 0.9 else rng.randrange(47))
    return table

def scripted(kind, slots):
    tap = lambda k: [k, 0]
    wait = [0]*18
    if kind == 'leave':
        return wait+tap(0x400)+[0]*30
    if kind == 'hold':
        return wait+[0x20]*70+tap(0x200)+wait+[0x20]*90+[0x10]*50+tap(0x404)+wait+tap(4)+[0]*30
    slot = slots-1 if kind == 'last' else 0
    seq = wait+tap(0x20)*slot+tap(0x200)+wait
    for c in range(16 if slot >= 6 else 15):
        # enter, move, commit; enter again, try the first row, leave
        seq += tap(0x200)+wait+tap(0x20)+tap(0x200)+[0]*3+tap(0x8)+wait+tap(0x10)+tap(0x200)+[0]*2
        seq += tap(0x200)+wait+tap(0x400)+[0]*2+tap(0x20)+wait
    return seq+tap(0x400)+wait+tap(0x400)+[0]*40

def scene_case(spec):
    exe, name, seat, slots8, autosave, seed, table, inputs = spec
    rng = random.Random(seed)
    o = Source()
    o.enter(0xf+seat, slots8, autosave, seed, table)
    cmds = [f'I {slots8} {autosave} {seed} '+' '.join(map(str, table))]; exp = [[0]]
    states = set(); exits = 0; sounds = 0; writes = 0; previous = bytes(table)
    queue = list(inputs) if isinstance(inputs, list) else []
    visits = 0; state = focus = 0; tail = None
    while True:
        if not queue:
            if isinstance(inputs, list) or visits >= inputs: break
            queue = gesture(rng, state, focus)
        if tail is not None:
            # Keep visiting for a while after the scene request, then stop.
            tail -= 1
            if tail < 0: break
        key = queue.pop(0); visits += 1
        # The other port is noise: only 178f90's seat may drive the scene.
        held = [rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8)), key] if seat else [key, rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8))]
        row = o.tick(held)
        cmds.append(f'T {held[0]} {held[1]} {seat}'); exp.append(row)
        state, focus = row[0], o.word(o.E+0x3f4)
        if o.exit and not isinstance(inputs, list): tail = 12
        states.add((state, focus)); exits += o.exit; sounds += len(o.sounds)
        now = bytes(o.p.memory[TABLE:TABLE+128]); writes += now != previous; previous = now
    native = subprocess.run([exe, ASSETS], input='\n'.join(cmds)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(exp), (name, len(actual), len(exp))
    for i, (a, b) in enumerate(zip(actual, exp)):
        assert a == b, (name, i, cmds[i][:40], len(a), len(b), [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12])
    return dict(case=name, seat=seat, slots=8 if slots8 else 6, visits=visits, states=sorted(map(list, states)),
                scene_requests=exits, sound_requests=sounds, option_commits=o.commits, table_changes=writes, instructions=o.instructions)

def direct(exe, options):
    """Whole original helpers called as functions; one native process answers the same queries."""
    rng = random.Random(0x20e128)
    o = Source(); p = o.p
    cmds = []; exp = []; counts = {}
    def add(kind, cmd, row):
        cmds.append(cmd); exp.append([int(v) for v in row]); counts[kind] = counts.get(kind, 0)+1
    S = 0x1c00000
    for _ in range(60):
        cfg = [rng.randrange(-700, 900) for _ in range(4)]+[rng.choice((1, 2, 3, 7, 16, 16, 30))]
        if rng.random() < 0.2: cfg[2:4] = cfg[0:2]
        o.run(0x17f428, S, *cfg); add('slide', 'sc '+' '.join(map(str, cfg)), [0, *o.slide(S)])
        for _ in range(rng.randrange(4, 60)):
            op = rng.choice(('si', 'so', 'su', 'su', 'su', 'su', 'su'))
            if op == 'su':
                value = o.run(0x17f330, S); add('slide', op, [value, *o.slide(S), o.run(0x17f400, S)])
            else:
                o.run(0x17f468 if op == 'si' else 0x17f4b0, S); add('slide', op, [0, *o.slide(S)])
    for _ in range(3000):
        a = [rng.randrange(0, 7), rng.randrange(-3, 60), rng.randrange(0, 20), rng.randrange(-4, 60), rng.randrange(1, 60)]
        add('scroll', 'ps '+' '.join(map(str, a)), [signed(o.run(0x17f528, *a), 32)])
        add('scroll', 'fs '+' '.join(map(str, a[1:])), [signed(o.run(0x17f560, *a[1:]), 32)])
    L = 0x1c01000
    def put_list(flags, lo, hi, step, cursor, page, bits=(0, 0)):
        for i, v in enumerate((flags, L+0x100, lo, hi, step, cursor, page)): p.write(L+4*i, v, 4)
        for i, v in enumerate(bits): p.write(L+0x100+4*i, v, 4)
    bits = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 17, 18)
    press = [0]*6+[0x200, 2, 8, 0x400, 4, 0x208, 0x600, 0x408, 0x20a, 0x404]
    for _ in range(12000):
        flags = sum(1 << b for b in bits if rng.random() < (0.7 if b in (0, 2) else 0.25))
        lo = rng.randrange(-2, 4); hi = lo+rng.randrange(1, 44); step = rng.randrange(1, 4)
        cursor = rng.randrange(lo, hi) if rng.random() < 0.9 else rng.randrange(lo-3, hi+4)
        page = rng.choice((-1, 0, 0, 1, 4, 8, 9, rng.randrange(0, hi+2)))
        mask = (rng.getrandbits(32) & rng.getrandbits(32), rng.getrandbits(32) & rng.getrandbits(32))
        pressed = rng.choice(press)
        repeat = pressed | (sum(rng.choice((0x10, 0x20, 0x40, 0x80, 0x100000, 0x200000, 0x400000, 0x800000))
                                for _ in range(rng.randrange(0, 3))) if rng.random() < 0.8 else 0)
        put_list(flags, lo, hi, step, cursor, page, mask)
        p.write(PAD+4, pressed, 4); p.write(PAD+8, repeat, 4)
        o.sounds = []; event = o.run(0x20e128, L, 0)
        add('list_update', f'lu {flags} {lo} {hi} {step} {cursor} {page} {mask[0]} {mask[1]} {pressed} {repeat}',
            [event, o.word(L+0x14), len(o.sounds), *o.sounds])
    for _ in range(2000):
        flags = rng.choice((5, 1, 0, 4, 0x10005, 2)); cursor = rng.randrange(-5, 40)
        a = [rng.randrange(-3, 20), rng.randrange(-3, 40), rng.randrange(0, 4), rng.randrange(-1, 44)]
        put_list(flags, 0, 1, 1, cursor, 0)
        o.run(0x20e028, L, *a); add('list_range', f'lr {flags} {cursor} '+' '.join(map(str, a)), o.list(L))
        lo = rng.randrange(-3, 5); hi = lo+rng.randrange(1, 30); value = rng.randrange(lo-6, hi+7)
        put_list(flags, lo, hi, 1, cursor, 0)
        o.run(0x20e0d0, L, value); add('list_range', f'lc {flags} {lo} {hi} {cursor} {value}', [o.word(L+0x14)])
        row = rng.randrange(-31, 64); on = rng.randrange(2); probe = rng.choice((row, rng.randrange(-31, 64)))
        flags = rng.choice((0x805, 0x805, 5))
        put_list(flags, 0, 64, 1, 0, 0, (0, 0) if on else (0xffffffff, 0xffffffff))
        o.run(0x20e4e0 if on else 0x20e528, L, row)
        add('list_bitmap', f'lb {flags} {row} {on} {probe}', [p.read(L+0x100, 4), p.read(L+0x104, 4), o.run(0x20e498, L, probe)])
    M = 0x1c02000
    def arm():
        o.run(0x17f428, M+0x1c, 0, 0, 5, 5, 1); o.run(0x17f468, M+0x1c); p.write(M+0x14, 1, 4); p.write(M+0x18, 1, 4)
    def chosen(): return signed(o.run(0x20ee20, M), 32)
    def drive(kind, updates):
        for _ in range(updates):
            if rng.random() < 0.1:
                ident = rng.choice((0, 5, 43, 48, 72, 75, 3, 60, rng.randrange(0, 76)))
                listed = [signed(p.read(0x1373830+2*i, 2), 16) for i in range(0x37)]
                # An unlisted id becomes the cursor itself; beyond row 54 the
                # original then indexes past 1373830, which is not modelled.
                if ident >= 0x37 and (ident not in listed or not p.read(M+0x50, 4) & 0x2000): continue
                o.run(0x20ed70, M, ident)
                add(kind, f'cs {ident}', [o.word(M+0x64), o.word(M+0x10), chosen()])
                continue
            pressed = rng.choice([0]*9+[0x200, 0x400, 8])
            repeat = pressed | rng.choice((0, 0x10, 0x20, 0x20, 0x20, 0x100000, 0x400000, 0x200000, 0x800000, 0x40, 0x80))
            p.write(PAD+4, pressed, 4); p.write(PAD+8, repeat, 4)
            o.sounds = []; event = o.run(0x20ee70, M, 0)
            add(kind, f'cm {pressed} {repeat}', [event, *o.menu(M), chosen(), len(o.sounds), *o.sounds])
    for case in range(48):
        block = [0]*0x98
        mode = case % 4
        for i in range(0x31):
            block[0x16+i] = int(rng.random() < (0, 0.15, 0.6, 0.3)[mode]); block[0x47+i] = int(rng.random() < (1, 0.8, 0.3, 0.5)[mode])*rng.choice((1, 1, 3))
        block[0x94] = rng.randrange(2)
        args = [rng.choice((6, 6, 9, 20, -1, 1)), rng.choice((0, 0, 0, 1, 2)), rng.randrange(2), rng.randrange(2), rng.randrange(2)]
        p.memory[OPTION:OPTION+0x98] = bytes(block)
        p.memory[M:M+0x86c] = bytes(0x86c)
        o.run(0x20e570, M); o.run(0x20eae0, M, *args, limit=2000000); arm()
        add('character_list', 'cl '+' '.join(map(str, args+block)), [*o.menu(M), *[signed(p.read(0x1373830+2*i, 2), 16) for i in range(0x37)], chosen()])
        drive('character_list', 50)
    strings = 0x1c06000
    for case in range(36):
        layout = case % 3; count = rng.randrange(1, 40); visible = rng.choice((-1, 5, 8, count, 60))
        # Row strings are the option names 0..count-1, written as a NULL-terminated pointer array.
        for i in range(count): p.write(strings+4*i, p.read(0x4d6e30+12*i+8, 4), 4)
        p.write(strings+4*count, 0, 4)
        p.memory[M:M+0x86c] = bytes(0x86c)
        o.run(0x20e570, M)
        if layout: o.run(0x20e0a0, M+0x50, 16 if layout == 1 else 15, 1)
        o.run(0x20e738, M, strings, visible, limit=2000000); arm()
        add('list_menu', f'ml {layout} {count} {visible}', o.menu(M))
        drive('list_menu', 60)
    # Table helpers
    o.run(0x152658, limit=100000)
    assert bytes(p.memory[TABLE:TABLE+128]) == bytes(p.memory[0x5735c8+0x633c:0x5735c8+0x633c+128]) == factory_image()[0x633c:0x633c+128]
    add('defaults', 'def', p.memory[TABLE:TABLE+128])
    D = 0x1c07000
    for _ in range(1500):
        d = random_table(rng, options, valid=rng.random() < 0.5)[:16] if rng.random() < 0.8 else [rng.randrange(47) for _ in range(16)]
        slot = rng.randrange(8)
        p.memory[D:D+16] = bytes(d)
        add('points', f'pts {slot} '+' '.join(map(str, d)), [signed(o.run(0x152908, D), 32), signed(o.run(0x152948, D, slot), 32)])
        p.write(0x4c38a8, 0, 4); p.memory[TABLE+16*slot:TABLE+16*slot+16] = bytes(d)
        add('icons', 'ico '+' '.join(map(str, d)), o.icons(slot))
    table = [rng.randrange(256) for _ in range(128)]
    p.memory[TABLE:TABLE+128] = bytes(table)
    for pl in range(2):
        for s in range(8):
            for i in range(16): p.write(NETWORK+(pl*8+s)*16+i, (pl*131+s*17+i*3+1) & 255, 1)
    add('accessor', 'tab '+' '.join(map(str, table)), [0])
    for sub in (0, 2, 5, 6):
        for system in range(9):
            for player in range(2):
                for slot in range(10):
                    category = rng.randrange(16)
                    p.write(0x4c38a8, sub, 4)
                    for i, v in enumerate((system, player, 0, slot)): p.write(D+4*i, v, 4)
                    at = o.run(0x14f4e0, D)
                    if at:
                        assert at == (NETWORK+(player*8+slot)*16 if sub == 6 else TABLE+16*slot) and system == 6 and slot < 8
                    data = list(p.memory[at:at+16]) if at else [0]*16
                    add('accessor', f'acc {sub} {system} {player} {slot} {category}', [int(bool(at)), *data, data[category] if at else -1])
    native = subprocess.run([exe, ASSETS], input='\n'.join(cmds)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(exp)
    for i, (a, b) in enumerate(zip(actual, exp)):
        assert a == b, (i, cmds[i][:120], [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12], len(a), len(b))
    return counts, o.instructions

def main():
    assert digest(ELF) == PIN
    raw = ELF.read_bytes()
    from extract_spirits_edit import Source as Tables, OPTIONS
    tables = Tables()
    options = [struct.unpack('<Bb', tables.bytes(OPTIONS+12*i, 2)) for i in range(47)]
    for name in ('spirits_edit.bin', 'edit_widgets.bin'):
        assert (ASSETS/name).read_bytes() == (ROOT/'work/ss6/extracted/resources'/name).read_bytes()
    default = list(factory_image()[0x633c:0x633c+128])
    rng = random.Random(0x13ada0)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; exe = Path(tmp)/'driver'; cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp,
                        *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        specs = []
        for kind in ('leave', 'hold', 'first', 'last'):
            for slots8 in (0, 1):
                seat = (len(specs)) % 2
                specs.append((exe, f'{kind}-{8 if slots8 else 6}', seat, slots8, len(specs) % 2, 1+len(specs), default,
                              scripted(kind, 8 if slots8 else 6)))
        for n in range(36):
            table = default if n % 4 == 0 else random_table(rng, options, valid=n % 4 != 3)
            specs.append((exe, f'random-{n}', n % 2, int(n % 3 != 0), int(n % 5 != 0), rng.getrandbits(40), table, 2600))
        with ProcessPoolExecutor(6) as pool:
            cases = list(pool.map(scene_case, specs))
        counts, direct_instructions = direct(exe, options)
    reached = sorted({tuple(s) for c in cases for s in c['states']})
    assert {(7, 0), (8, 0), (8, 1), (-1, 0), (-2, 0)} <= set(reached), reached
    assert sum(c['scene_requests'] for c in cases) >= 8 and sum(c['table_changes'] for c in cases) > 100
    assert sum(c['option_commits'] for c in cases) > 300
    report = dict(status='passed', elf_sha256=PIN,
                  native_sources={s: hashlib.sha256((ROOT/'src'/s).read_bytes()).hexdigest() for s in SOURCES},
                  scene_cases=len(cases), scene_visits=sum(c['visits'] for c in cases),
                  scene_requests=sum(c['scene_requests'] for c in cases),
                  sound_requests=sum(c['sound_requests'] for c in cases),
                  option_commits=sum(c['option_commits'] for c in cases),
                  table_changes=sum(c['table_changes'] for c in cases),
                  states_reached=[list(s) for s in reached], direct_comparisons=counts,
                  original_instructions=sum(c['instructions'] for c in cases)+direct_instructions,
                  stubbed={k: [hex(a) for a in v] for k, v in STUBS.items()},
                  scope='Original task 13ada0 executed visit by visit: every visit runs the unmodified loop body from the '
                        '112a28 return address to the next 112a28 call on the task stack, with 117fd8 pad sampling for both '
                        'ports before it. The EE kernel thread primitives behind 1126f0/112a28 (100e58, 100ec8) and the '
                        'scheduler are replaced by the harness context switch; 13acd8 itself is not run. Compared per visit: '
                        'state and next state, frame open flag, help id/sub/text, 1ce478 background variant and C library '
                        'seed, slot menu, category and option panels (geometry, slides, cursors, rows, costs, disabled '
                        'bitmap, title), editor slot/focus/first/descriptor, summary slide, the 128 table bytes, 152988 '
                        'icons of the highlighted slot, 1252f0/10f158 requests and ordered 1e7b70 sounds. Direct whole-'
                        'function comparisons cover the slide, scroll, list cursor, list menu, character list, table '
                        'defaults, point budget, icon list and the 14f4e0/152758 accessor. Stubbed callees are listed in '
                        '"stubbed"; frame sub-widget geometry (181788..182260) runs in the original but is not ported or '
                        'compared beyond the open flag and help request.',
                  cases=cases)
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(f"passed: {len(cases)} scene traces, {report['scene_visits']} visits, {sum(counts.values())} direct comparisons "
          f"{counts}, {report['original_instructions']} original instructions")

if __name__ == '__main__':main()
