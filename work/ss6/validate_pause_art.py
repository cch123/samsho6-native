#!/usr/bin/env python3
"""Compare the drawing of the pause menu, KEY CONFIGURATION and SKILL LIST with SLPS-25559.

Each case drives the ORIGINAL task (pause task 1d9e10 per visit; coroutines 13ce08 and
13d680 on their own stacks up to the yield 112a28) and the native logic modules with the
same pad words.  After every visit the original 128-byte submission queue 68c3c0 is
decoded and must equal, entry by entry and with exact float bits, the MenuDrawList that
src/pause_art.cpp produces from the native logic state; the renderer globals left behind
are compared as well.  A subset of the visits is painted on both sides over the same
non-uniform 640x480 frame (reference painter of validate_menu_canvas.py, extended by the
four-colour strip of 17e0b0, against PauseArt::rasterise) and must give identical frames.
"""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from character_tiles_oracle import ROOT
from extract_console_versus_art import PACKETS, ORIGINAL
from validate_menu_canvas import paint, native_keys, bits
from validate_gallery_art import Oracle as GalleryOracle, RETURN, PACKAGE, ELF, OPTION, Painter
import extract_pause_art

REPORT = ROOT/'outputs/ss6-feasibility/pause_art_validation.json'
G, P, MENU = 0x4c3808, 0x456890, 0x582f30
POLL, TASK, RETURNED = 0x1d9b50, 0x1d9e10, 0x1da7e8
KEY_TASK, KEY_STACK, KEY_WORDS = 0x13ce08, 0x12721c0, 0x800
SKILL_TASK, SKILL_STACK, SKILL_WORDS = 0x13d680, 0x127a1c0, 0x4000
MASKS, PRESET = 0x4eaac0, 0x12d26b0
ACTORS, TASKS = 0x1e05000, 0x1e08000
# `jr ra` boundaries added to those of validate_gallery_art.py: music fade, network
# session and a debug print reached from the pause task. Nothing here draws.
EXTRA = (0x213be8, 0x11bd58, 0x323050)
BUTTONS = (4, 2, 1, 0x400, 0x200, 0x100, 0x100000, 0x200000, 0x400000, 0x800000)

DRIVER = r'''
#include "pause_art.hpp"
#include <bit>
#include <cstring>
#include <iostream>
#include <memory>
#include <sstream>
using namespace ss6;
template<class T> static void put(const T& v){std::cout.write(reinterpret_cast<const char*>(&v),sizeof v);}
int main(int,char** argv){
    SystemData system(argv[1]);MenuWidgetData widgets(argv[1]);
    MenuCanvas canvas(argv[1]);GalleryArt library(canvas,argv[1]);PauseArt art(canvas,library,argv[1]);
    PauseMenuAssets pauseAssets(argv[1]);KeyConfigAssets keyAssets(argv[1]);SkillListData skills(argv[1]);
    MenuDrawList list;MenuBackdrop backdrop;MenuChrome scene;GameRandom random;MenuPadRepeat repeat;
    PauseMenu menu(pauseAssets);ArcadeGameData game;std::array<ArcadePlayer,2> players{};PauseEdgePulse pulse;
    KeyConfigWindow keys;PauseWindowContext context;
    auto skill=std::make_unique<SkillListWindow>(skills,widgets,system);
    const MenuChrome* chrome=&scene;scene.setHelp(52);
    bool restore=false;
    std::array<uint32_t,2> last{};
    std::vector<uint8_t> pixels(640*480*4),base(pixels.size());
    for(int y=0;y<480;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
    std::string line,op;
    while(std::getline(std::cin,line)) try {
        std::istringstream in(line);in>>op;
        std::vector<long long> v;for(long long x;in>>x;)v.push_back(x);
        if(v.size()<8)v.resize(8);
        auto pads=[&]{
            std::array<uint32_t,2> held{uint32_t(v[0]),uint32_t(v[1])};
            auto m=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            return std::pair{m,std::array<WidgetPad,2>{WidgetPad{held[0],m[0].pressed,m[0].repeat},WidgetPad{held[1],m[1].pressed,m[1].repeat}}};
        };
        auto unlocks=[&]{context.unlocks=SkillUnlocks(system);};
        auto enterScene=[&](unsigned mode){
            // 1822a0 runs 1ce478 in a menu mode: 1802 library draws.
            chrome=&scene;
            if(GuideWindow::menuBackdrop(mode))scene.enter(backdrop.enter(random));
        };
        if(op=="option")system.option(size_t(v[0]))=uint8_t(v[1]);
        else if(op=="seed")random.librarySeed=uint64_t(v[0]);
        else if(op=="fade"){canvas.setFade(v[0]!=0,int(v[1]),uint32_t(v[2]));library.setFade(v[0]!=0,int(v[1]),uint32_t(v[2]));}
        else if(op=="bright"){canvas.setBrightness(int(v[0]));art.setBrightness(int(v[0]));}
        else if(op=="p_new"){
            menu=PauseMenu(pauseAssets);repeat=MenuPadRepeat();last={};chrome=&menu.chrome;
            std::memset(&game,0,sizeof game);std::memset(players.data(),0,sizeof players);
        } else if(op=="p_game"){
            int32_t words[42+24];for(size_t i=0;i<66;++i)words[i]=int32_t(v.at(i));
            std::memcpy(&game,words,sizeof game);std::memcpy(players.data(),words+42,sizeof players);
        } else if(op=="p_tick"){
            list.beginFrame();restore=false;
            const auto m=pads().first;
            menu.poll(game,m,v[2]!=0);
            if(menu.active){
                const auto r=menu.tick(game,players,m);
                art.drawPauseMenu(list,pauseAssets,r.draw,menu.chrome,game.submode==5,pulse);
            }
        } else if(op=="p_returned")menu.windowReturned();
        else if(op=="k_enter"){
            const unsigned mode=unsigned(v[0]);
            for(unsigned i=0;i<16;++i)system.setWord(SystemData::keyMasks+4*i,int32_t(v.at(3+i)));
            repeat=MenuPadRepeat();last={};
            context.gameMode=mode;context.seat=KeyConfigWindow::operatingSeat(mode,unsigned(v[1]),unsigned(v[2]));unlocks();
            keys=KeyConfigWindow{};keys.start(widgets,context.seat);
            enterScene(mode);
        } else if(op=="k_tick"){
            list.beginFrame();
            std::vector<int> tones;
            keys.tick(pads().second,system,keyAssets,GuideWindow::menuBackdrop(context.gameMode),tones);
            restore=art.drawKeyConfig(list,keyAssets,keys,system,context,backdrop,random,scene);
        } else if(op=="s_ctx"){skill->gameMode=unsigned(v[0]);skill->listId=int(v[1]);context.gameMode=unsigned(v[0]);}
        else if(op=="s_enter"){
            repeat=MenuPadRepeat();last={};context.seat=unsigned(v[0]);unlocks();
            skill->enter(context.seat);
            enterScene(context.gameMode);
        } else if(op=="s_tick"){
            list.beginFrame();
            const auto w=pads().second;
            skill->tick(w[skill->seat]);
            unlocks();
            restore=art.drawSkillList(list,*skill,context,backdrop,random,scene);
        } else if(op=="flush"){
            uint32_t n=uint32_t(list.records.size());put(n);
            for(auto& r:list.records){uint8_t head[6]={uint8_t(r.kind),uint8_t(r.font),r.slot,r.blend,uint8_t(r.additive),0};put(head);put(r.glyph);put(r.colour);put(r.z);
                float g[8]={r.x,r.y,r.w,r.h,r.u,r.v,r.uw,r.vh};put(g);put(r.corner);}
            uint32_t st[21]={list.colour,uint32_t(list.blend),uint32_t(list.depth),uint32_t(list.glyphs),uint32_t(list.textDepth),std::bit_cast<uint32_t>(list.cursor),
                uint32_t(chrome->helpX[0]),uint32_t(chrome->helpX[1]),uint32_t(chrome->helpDelay),uint32_t(random.librarySeed),uint32_t(random.librarySeed>>32),
                uint32_t(backdrop.target),uint32_t(backdrop.shown),uint32_t(backdrop.clock),uint32_t(chrome->band),uint32_t(chrome->content),uint32_t(chrome->legend),
                std::bit_cast<uint32_t>(list.asciiDepth),uint32_t(pulse.counter),uint32_t(pulse.reverse),uint32_t(restore)};put(st);
            if(v[0]){pixels=base;art.rasterise(list,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());}
            std::cout.flush();
        } else return 3;
    } catch(const std::exception& e){std::cerr<<line<<": "<<e.what()<<std::endl;return 4;}
}
'''


class Oracle(GalleryOracle):
    """Original pause-menu tasks with their drawing; boundaries as in validate_gallery_art.py."""
    def __init__(self, options=(), seed=1):
        super().__init__(0, options, seed=seed)
        p = self.p
        for pc in EXTRA:p.memory[pc:pc+8] = RETURN
        for i in range(3):p.write(0x582f54+4*i, TASKS+0x40*i, 4)

    def begin(self):
        super().begin()
        self.p.write(0x3451c8, 0, 4)   # 107208 latches and clears the frame flags

    def decode(self):
        """validate_menu_canvas.Oracle.decode plus the four-colour strip of 17e0b0."""
        p = self.p;count = p.read(0x345178, 4)
        strips = {}
        for i in range(count):
            a = PACKETS+i*128;q = struct.unpack_from('<16Q', p.memory, a)
            if q[0] & 0xfff != 0xff3 or q[15] != 4:continue
            colours = [q[1+2*j] & 0xffffffff for j in range(4)]
            if len(set(colours)) == 1:continue
            assert colours[0] == colours[2] and colours[1] == colours[3], [hex(c) for c in colours]
            strips[i] = colours[1]
            # The base decoder accepts one colour per entry: give it the left one.
            for j in (1, 3):p.write(a+8+16*j, (q[1+2*j] & ~0xffffffff) | colours[0], 8)
        out = super().decode()
        for i, right in strips.items():
            q = out[i];x, y, x1, y1 = q['rect']
            left = q['colour']
            q.update(kind='strip', right=right, key=('strip', left, right, bits(q['z']), x, y, x1-x, y1-y))
            a = PACKETS+i*128
            for j in (1, 3):p.write(a+8+16*j, (p.read(a+8+16*j, 8) & ~0xffffffff) | right, 8)
        return out

    def state(self):
        p = self.p
        return super().state()+(p.read(0x3d3aac, 4), p.read(0x582f60, 4), p.read(0x582f64, 4), p.read(0x3451c8, 4) >> 4 & 1)

    # --- pause menu (as validate_pause_menu.Source) ----------------------
    def pause_boundaries(self):
        # 1126f0 starts an EE kernel thread for the two child windows. The replacement
        # returns one fixed record per tag: lui v0,0x1e0; sll t1,t1,3; jr ra; addu v0,v0,t1.
        self.p.memory[0x1126f0:0x1126f0+16] = struct.pack('<4I', 0x3c0201e0, 0x000948c0, 0x03e00008, 0x00491021)
    def pause_new(self):
        p = self.p
        for i in range(12):p.write(MENU+4*i, 0, 4)
        p.write(MENU+0x10, 1, 4)
        p.memory[G:G+0xa8] = bytes(0xa8);p.memory[P:P+0x60] = bytes(0x60)
        for at, v in ((0x582994, 0), (0x43d048, 0), (0x582b38, 0), (0x582b3c, 0), (0x582b28, 0x10), (0x582b2c, 0), (0x582b30, 0)):
            p.write(at, v, 4)
        self.go(0x112570)
        for s in range(2):
            for at in (0x443568, 0x443570):p.write(at+4*s, 0, 4)
        p.memory[0x1237cc8:0x1237cc8+56] = bytes(56)
        self.last = [0, 0]
    def pause_game(self, words):
        for i, w in enumerate(words[:42]):self.p.write(G+4*i, w, 4)
        for i, w in enumerate(words[42:]):self.p.write(P+4*i, w, 4)
    def pause_tick(self, held, fade):
        p = self.p
        self.sample(held);self.begin()
        p.write(0x123a0c4, 0, 4);p.write(0x12d4cc8, fade, 4)
        assert self.go(POLL) == 0
        if p.read(MENU+8, 4):assert self.go(TASK) == 0

    # --- child windows ---------------------------------------------------
    def pads_reset(self):
        p = self.p
        for s in range(2):
            for at in (0x443568, 0x443570):p.write(at+4*s, 0, 4)
        p.memory[0x1237cc8:0x1237cc8+56] = bytes(56)
        self.last = [0, 0]
    def window_context(self, mode, owner, menu_seat):
        p = self.p
        p.write(G, mode, 4);p.write(0x582f3c, owner, 4);p.write(0x12d35c4, menu_seat, 4)
        for i in range(3):p.write(TASKS+0x40*i+4, 0x55, 4)
        p.write(0x582f30, 3, 4);p.write(0x582f50, 1, 4)
    def key_enter(self, mode, owner, edit, masks):
        p = self.p
        self.window_context(mode, owner, edit)
        for i, m in enumerate(masks):p.write(MASKS+4*i, m, 4)
        p.write(PRESET, 0, 2)
        self.pads_reset()
        p.memory[KEY_STACK:KEY_STACK+4*KEY_WORDS] = bytes(4*KEY_WORDS)
        self.start(KEY_TASK, KEY_STACK, KEY_WORDS)
    def skill_context(self, mode, owner, menu_seat, seat, list_id, alternate):
        p = self.p
        self.window_context(mode, owner, menu_seat)
        p.write(0x4d3d08, ACTORS, 4)
        actor = ACTORS+0xf2c*seat
        p.write(actor+0xa14, list_id, 4);p.write(actor+0x23c, 0x100000 if alternate else 0x20, 4)
    def window_tick(self, held):
        self.sample(held);self.begin()
        assert self.visit() == 3


def strip_paint(q, frame):
    """Horizontal colour ramp sampled at pixel centres, blended like a flat entry."""
    x, y, x1, y1 = q['rect'];w = x1-x
    if w <= 0 or y1 <= y:return
    left = np.array([(q['colour'] >> k) & 255 for k in (0, 8, 16, 24)], np.int64)
    right = np.array([(q['right'] >> k) & 255 for k in (0, 8, 16, 24)], np.int64)
    px = np.arange(max(0, x), min(640, x1));top, bottom = max(0, y), min(480, y1)
    if not len(px) or bottom <= top:return
    value = left[None, :]+((2*(px-x)+1)[:, None]*(right-left)[None, :])//(2*w)
    view = frame[top:bottom, px[0]:px[-1]+1, :3]
    view[:] = np.clip(view+((value[None, :, :3]-view)*value[None, :, 3:])//128, 0, 255)

def paint_all(oracle, prims, frame):
    for q in sorted(prims, key=lambda item:item['z']):
        if q['kind'] == 'strip':strip_paint(q, frame)
        else:paint(oracle, [q], frame)
    return frame

def keys_of(blob, oracle):
    out = []
    for at in range(0, len(blob), 80):
        record = blob[at:at+80]
        kind, _, _, _, _, _, marker, colour, z, x, y, w, h = struct.unpack_from('<6BHIf4f', record)
        if kind == 0 and marker == 1:
            c = struct.unpack_from('<4f', record, 48)
            right = sum(int(v) << 8*i for i, v in enumerate(c))
            out.append(('strip', colour, right, bits(z), int(x), int(y), int(w), int(h)))
        else:out += native_keys(record, oracle)
    return out


class Session:
    """One original task and one native driver process, compared visit by visit."""
    def __init__(self, exe, oracle, name, compared):
        self.proc = subprocess.Popen([exe, PACKAGE], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.o = oracle;self.name = name;self.lines = [];self.compared = compared
        y, x = np.mgrid[:480, :640];self.base = np.stack((x+3*y, x ^ y, 4*x+y, np.full_like(x, 255)), axis=-1).astype(np.uint8)
        self.visits = self.frames = self.primitives = self.restores = self.drawn = 0;self.kinds = {};self.hashes = hashlib.sha256()
    def send(self, *parts):self.lines.append(' '.join(str(v) for v in parts))
    def read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n:raise RuntimeError(f'Native driver stopped in {self.name}')
        return data
    def compare(self, label, painted):
        o = self.o;prims = o.decode()
        painted = painted and bool(prims)
        self.send('flush', int(painted));self.proc.stdin.write(('\n'.join(self.lines)+'\n').encode());self.proc.stdin.flush();self.lines = []
        count = struct.unpack('<I', self.read(4))[0];blob = self.read(count*80);state = struct.unpack('<21I', self.read(84))
        frame = np.frombuffer(self.read(self.base.size), np.uint8).reshape(self.base.shape) if painted else None
        native = keys_of(blob, o);expected = [q['key'] for q in prims]
        short = lambda k:k[:-1] if k[0] == 'glyph' else k
        if native != expected:
            for i, (a, b) in enumerate(zip(native, expected)):
                if a != b:raise AssertionError((self.name, label, 'primitive', i, len(native), len(expected), short(a), short(b)))
            raise AssertionError((self.name, label, 'primitive count', len(native), len(expected),
                                  [short(k) for k in (native if len(native) > len(expected) else expected)[min(len(native), len(expected)):][:3]]))
        original = o.state()
        bad = [(i, state[i], original[i]) for i in self.compared if state[i] != original[i]]
        if bad:raise AssertionError((self.name, label, 'state', bad))
        for q in prims:self.kinds[q['kind']] = self.kinds.get(q['kind'], 0)+1
        self.primitives += len(prims);self.visits += 1;self.restores += original[20];self.drawn += bool(prims)
        if painted:
            o.refresh()
            wanted = paint_all(o, prims, self.base.astype(np.int64)).astype(np.uint8)
            if not np.array_equal(frame, wanted):
                wrong = np.any(frame != wanted, axis=-1);y, x = map(int, np.argwhere(wrong)[0])
                raise AssertionError((self.name, label, 'pixels', int(wrong.sum()), x, y, frame[y, x].tolist(), wanted[y, x].tolist()))
            self.frames += 1;self.hashes.update(wanted.tobytes())
        return prims
    def fade(self, enabled, level, colour):
        self.o.fade = (enabled, level, colour);self.o.refresh();self.send('fade', int(enabled), level, colour)
    def bright(self, value):
        self.o.p.write(0x43d064, value, 4);self.send('bright', value)
    def close(self):
        self.proc.stdin.close();assert self.proc.wait() == 0
    def result(self, **extra):
        return dict(case=self.name, visits=self.visits, drawn_visits=self.drawn, frames=self.frames, queue_entries=self.primitives,
                    entries_by_kind=self.kinds, restore_requests=self.restores, frames_sha256=self.hashes.hexdigest(),
                    instructions=self.o.instructions, **extra)

# State words: 0..5 renderer globals, 6..8 marquee, 9..10 library seed, 11..13 overlay
# population, 14..16 menu counters, 17 ASCII depth, 18..19 edge pulse, 20 restore flag.
PAUSE_STATE = (0, 1, 2, 3, 4, 5, 6, 7, 8, 15, 16, 17, 18, 19, 20)
WINDOW_STATE = tuple(range(21))

PAUSE_KEYS = [0x80000]*4+[0x20]*8+[0x10]*5+[0x200]*8+[2, 8, 0x400, 0x400, 4, 0x40, 0x80, 0x80000 | 0x200, 0x220, 0x410, 0x100000, 1]

def game_words(rng, mode, sub, locks):
    g = [rng.randrange(0, 60) for _ in range(42)]
    g[0] = mode;g[0xa0//4] = sub;g[0x2c//4], g[0x30//4], g[0xa4//4] = locks
    return g+[rng.randrange(0, 50) for _ in range(24)]

def pause_rows(spec):
    """Every row of both row sets and both owners: menu, both prompts, WINDOW OFF, child windows."""
    exe, mode, sub, seat, quick = spec
    rng = random.Random(mode*64+sub*8+seat)
    o = Oracle();o.pause_boundaries()
    s = Session(exe, o, f'pause/rows/mode_{mode:x}_sub_{sub}_seat_{seat}', PAUSE_STATE);paint_now = Painter(4)
    rows = 4 if sub == 5 else 6
    if mode == 2:s.bright(0xb0)   # option BRIGHT below its maximum
    seen = dict(menu=0, dialog=0, hidden=0, child=0)
    def tick(key=0, force=False):
        held = [0, key] if seat else [key, 0]
        o.pause_tick(held, 0);s.send('p_tick', held[0], held[1], 0)
        prims = s.compare(('rows', s.visits), paint_now(tuple(held)) or force)
        state = o.p.read(MENU+4, 4);active = o.p.read(MENU+8, 4)
        if active and prims:
            seen['menu'] += 1;seen['dialog'] += state in (2, 6)
        seen['hidden'] += bool(active and state == 5 and not prims)
    def tap(key, idle=1):
        tick(key, True)
        for i in range(idle):tick(force=i == 0)
    def start(row, back=False):
        words = game_words(rng, mode, sub, (0, 0, 0))
        o.pause_new();s.send('p_new');o.pause_game(words);s.send('p_game', *words)
        tap(0x80000, 11)
        assert o.p.read(MENU+8, 4) == 1, (mode, sub, seat)
        for _ in range((rows-row) % rows if back else row):tap(0x10 if back else 0x20)
        assert o.p.read(MENU, 4) == row
    question = (1, 5) if rows == 6 else (3,)
    window = (2, 3) if rows == 6 else (1, 2)
    for row in range(rows):
        for back in (False, True):
            if quick and back:continue
            start(row, back)
            tap(rng.choice((0x200, 2, 8)), 11)
            if row == 0:assert o.p.read(MENU+8, 4) == 0
            elif row in question:
                tap(0x200, 11);tap(0x200, 11);tap(0x400, 11);tap(0x200, 11)
                tap(rng.choice((0x10, 0x20, 0x40, 0x80)), 2)
                tick(0x200, True)
                for _ in range(rng.randrange(1, 15)):tick(rng.choice((0, 0x200, 0x80000)))
            elif row in window:
                assert o.p.read(MENU+0x20, 4) == 1;seen['child'] += 1
                for _ in range(rng.randrange(1, 6)):tick(rng.choice((0, 0x200, 0x80000, 0x20)))
                o.go(RETURNED, 1);s.send('p_returned')
                for key in (0x200, 0, 0, 0x20, 0, 0, 0, 0, 0, 0, 0, 0, 0x20, 0, 0x400, 0, 0):tick(key)
                assert o.p.read(MENU+8, 4) == 0
            else:
                for key in (0x200, 0x10, 0x20, 0x40, 0x80, 0x400):
                    assert o.p.read(MENU+4, 4) == 5
                    tap(key, 11);assert o.p.read(MENU+4, 4) == 0 and o.p.read(MENU, 4) == 4
                    tap(0x200, 11)
                tap(0x80000, 2);assert o.p.read(MENU+8, 4) == 0
    # The scene fade 117288 reaches every colour of the menu and the 116588 CLUTs.
    start(1);tap(0x200, 3)
    for state in ((True, 96, 0xff000000), (True, 200, 0xffffffff), (False, 0, 0)):
        s.fade(*state)
        for _ in range(2):tick(force=True)
    s.close()
    assert seen['menu'] and seen['dialog'] and (rows == 4 or seen['hidden']), seen
    return s.result(scene='pause menu', **seen)

def pause_random(spec):
    exe, name, seed, visits = spec
    rng = random.Random(f'pause{name}{seed}')
    o = Oracle();o.pause_boundaries()
    s = Session(exe, o, f'pause/random/{name}/{seed}', PAUSE_STATE);paint_now = Painter(9)
    def fresh():
        mode = rng.choice((1, 2, 3, 3, 3, 0xb, 0xc, 0, 9, 6));sub = rng.choice((0, 1, 2, 2, 3, 4, 5, 6))
        if name == 'land':mode, sub = rng.choice((1, 2)), 5
        if name == 'versus':mode, sub = 3, rng.choice((1, 2))
        words = game_words(rng, mode, sub, rng.choice(((0, 0, 0),)*8+((1, 0, 0), (0, 1, 0), (0, 0, 1))))
        o.pause_new();s.send('p_new');o.pause_game(words);s.send('p_game', *words)
        return mode
    mode = fresh();queue = [0x80000, 0];wait = leave = None;opens = 0;closed = 0
    for _ in range(visits):
        # Game data that refuses the menu is replaced after a while.
        if closed > 40 and leave is None:leave = 0
        if leave is not None:
            leave -= 1
            if leave < 0:
                mode = fresh();queue = [0x80000, 0];wait = leave = None;closed = 0
        if wait is not None:
            wait -= 1
            if wait < 0:
                o.go(RETURNED, 1);s.send('p_returned');wait = None
        if not queue:
            kind = rng.random()
            if kind < 0.12:queue = [0]*rng.randrange(1, 14)
            elif kind < 0.18:queue = [rng.choice((0x10, 0x20))]*rng.randrange(18, 40)
            else:queue = [rng.choice(PAUSE_KEYS), 0]*rng.randrange(1, 3)
        key = queue.pop(0)
        seat = rng.randrange(2) if mode == 3 else (1 if mode in (2, 0xc) else 0)
        held = [0, key] if seat else [key, 0]
        fade = int(rng.random() < 0.05)
        before = o.p.read(MENU+8, 4), o.p.read(MENU+0x20, 4), o.p.read(MENU+0x14, 4)
        o.pause_tick(held, fade);s.send('p_tick', held[0], held[1], fade)
        s.compare(('random', s.visits), paint_now(tuple(held)))
        after = o.p.read(MENU+8, 4), o.p.read(MENU+0x20, 4), o.p.read(MENU+0x14, 4)
        opens += after[0] and not before[0];closed = 0 if after[0] else closed+1
        if after[1] and not before[1]:wait = rng.randrange(0, 12)
        # 582f44: a scene request was made; the battle is torn down a few frames later.
        if after[2] and not before[2] and leave is None:leave = rng.randrange(0, 16)
    s.close()
    return s.result(scene='pause menu', opens=opens)

def random_masks(rng):
    kind = rng.random()
    if kind < 0.4:return [0x400, 0x200, 2, 4, 0x400000, 0x800000, 0x100000, 0x200000]*2
    if kind < 0.6:return [rng.choice(BUTTONS+(0, 0)) for _ in range(16)]
    out = []
    for _ in range(2):
        side = list(BUTTONS);rng.shuffle(side);out += [m if rng.random() < 0.85 else 0 for m in side[:8]]
    return out

def key_gesture(rng):
    kind = rng.random()
    if kind < 0.40:return [rng.choice(BUTTONS), 0]
    if kind < 0.62:return [rng.choice((0x20, 0x20, 0x20, 0x10)), 0]*rng.randrange(1, 4)
    if kind < 0.70:return [rng.choice((0x20, 0x10))]*rng.randrange(18, 40)
    if kind < 0.78:return [rng.choice((0x40, 0x80)), 0]
    if kind < 0.84:return [rng.choice((0x200, 2, 8, 0x400, 4)), 0]
    if kind < 0.86:return [0x80000, 0]
    if kind < 0.93:return [rng.choice(BUTTONS) | rng.choice(BUTTONS+(0x20, 0x10, 0x40, 0x80000, 8)), 0]
    return [0]*rng.randrange(1, 12)

def key_case(spec):
    exe, name, mode, seed, visits = spec
    rng = random.Random(f'key{name}{mode}{seed}')
    options = ((0x7e, seed & 1),)
    o = Oracle(options, seed=seed)
    s = Session(exe, o, f'key config/{name}/mode_{mode:x}/{seed}', WINDOW_STATE);paint_now = Painter(7)
    for a, b in options:s.send('option', a, b)
    s.send('seed', seed)
    if seed % 3 == 0:s.bright(0x90)
    stats = dict(windows=0, icon_entries=0)
    def enter():
        owner, edit = rng.randrange(2), rng.randrange(2)
        masks = random_masks(rng)
        o.key_enter(mode, owner, edit, masks);s.send('k_enter', mode, owner, edit, *masks)
        stats['windows'] += 1
    enter()
    queues = [[], []];tail = None
    for visit in range(visits):
        if tail is not None:
            tail -= 1
            if tail < 0:
                enter();queues = [[], []];tail = None
        held = []
        for q in queues:
            if not q:q.extend(key_gesture(rng) if rng.random() < 0.75 else [0]*rng.randrange(1, 20))
            held.append(q.pop(0))
        if visit < 20:held = [0, 0]   # slide-in
        if visit in (40, 43, 46):s.fade(*((True, 128, 0xff204080), (True, 230, 0xffffffff), (False, 0, 0))[(visit-40)//3])
        o.window_tick(held);s.send('k_tick', *held)
        prims = s.compare(('key', s.visits), paint_now(tuple(held)) or 40 <= visit < 46)
        stats['icon_entries'] += sum(q['kind'] == 'quad' and q['slot'] == 0x2e for q in prims)
        # 1da7e8 rewrites the scheduler words of the pause tasks when the window returns.
        if tail is None and mode != 0x11 and o.p.read(TASKS+4, 4) != 0x55:tail = rng.randrange(2, 9)
        if tail is None and mode == 0x11 and visit % 300 == 299:tail = 0
    s.close()
    return s.result(scene='key configuration', **stats)

def option_set(rng, kind):
    out = []
    for c in range(49):
        locked = {'factory': None, 'open': 0, 'sparse': int(rng.random() < 0.6)}[kind]
        if locked is not None:out.append((0x16+c, locked))
    spirits = {'factory': (0, 0, 0), 'open': (1, 1, 1)}.get(kind) or tuple(rng.randrange(2) for _ in range(3))
    out += [(0x7e+i, v) for i, v in enumerate(spirits)]
    out.append((0x94, {'factory': 0, 'open': 1}.get(kind, rng.randrange(2))))
    return out

def skill_gesture(rng, state):
    kind = rng.random()
    if kind < 0.05:return [rng.choice((0x40, 0x80, 0x1000, 0x8000, 0x80000, 0x220, 0x600, 0x410, 0x28, 1)), 0]
    if kind < 0.12:return [0]*rng.randrange(1, 24)
    if kind < 0.20:return [rng.choice((0x10, 0x20, 0x20, 0x400000, 0x100000))]*rng.randrange(18, 60)
    move = [rng.choice((0x20, 0x20, 0x20, 0x10, 0x10, 0x400000, 0x100000, 0x800000, 0x200000)), 0]*rng.randrange(1, 5)
    confirm, cancel = [rng.choice((0x200, 0x200, 2, 8)), 0], [rng.choice((0x400, 4)), 0]
    odds = {0: (0.35, 0.06), 1: (0.40, 0.10), 2: (0.05, 0.10)}.get(state, (0.2, 0.2))
    pick = rng.random()
    if pick < odds[0]:return confirm
    if pick < odds[0]+odds[1]:return cancel
    return move

def skill_case(spec):
    exe, name, mode, owner, menu_seat, kind, seed, visits = spec
    rng = random.Random(f'skill{name}{seed}')
    options = option_set(rng, kind)
    o = Oracle(options, seed=seed)
    s = Session(exe, o, f'skill list/{name}', WINDOW_STATE);paint_now = Painter(11)
    for a, b in options:s.send('option', a, b)
    s.send('seed', seed)
    seat = {1: 0, 2: 1, 3: int(owner == 1), 0xb: 0, 0xc: 1, 0xd: menu_seat, 0xe: menu_seat}[mode]
    fighter = lambda:(rng.choice((rng.randrange(49), rng.randrange(49), 1, 0x16, 0x19, 0x2b)), rng.random() < 0.15)
    list_id, alternate = fighter()
    o.skill_context(mode, owner, menu_seat, seat, list_id, alternate);o.pads_reset()
    s.send('s_ctx', mode, list_id+(0x32 if alternate else 0));s.send('s_enter', seat)
    o.start(SKILL_TASK, SKILL_STACK, SKILL_WORDS)
    if seed % 4 == 1:s.bright(0xa0)
    queue = [];state = 0;tail = None;pages = 0;strips = 0;states = set();faded = None
    for visit in range(visits):
        if not queue:queue = skill_gesture(rng, state)
        key = queue.pop(0)
        noise = rng.choice((0, 0, 0x200, 0x400, 0x20, 0x10, 8))
        held = [noise, key] if seat else [key, noise]
        woke = o.p.read(TASKS+4, 4)
        if faded is not None and faded < 6:
            if faded % 2 == 0:s.fade(*((True, 128, 0xff204080), (True, 230, 0xffffffff), (False, 0, 0))[faded//2])
            faded += 1
        o.window_tick(held);s.send('s_tick', *held)
        state = struct.unpack('<i', struct.pack('<I', o.p.registers[17] & 0xffffffff))[0];states.add(state)
        prims = s.compare(('skill', s.visits, state), paint_now(tuple(held)) or (state == 2 and visit % 3 == 0) or (faded or 9) < 7)
        n = sum(q['kind'] == 'strip' for q in prims);strips += n;pages += bool(n)
        # The scene fade while heading strips are on screen: 17e0b0 bypasses 117288.
        if n and faded is None:faded = 0
        if o.p.read(TASKS+4, 4) != woke:
            # 1da7e8 suspended the task; a later pause wakes it, possibly with another fighter.
            list_id, alternate = fighter()
            o.skill_context(mode, owner, menu_seat, seat, list_id, alternate)
            s.send('s_ctx', mode, list_id+(0x32 if alternate else 0))
        if mode in (0xd, 0xe) and state < 0 and tail is None:tail = 12
        if tail is not None:
            tail -= 1
            if tail < 0:break
    s.close()
    return s.result(scene='skill list', states=sorted(states), page_visits=pages, heading_strips=strips, faded=faded is not None)


def main():
    cli = argparse.ArgumentParser();cli.add_argument('--only');cli.add_argument('--quick', action='store_true')
    cli.add_argument('--jobs', type=int, default=6)
    args = cli.parse_args()
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == ORIGINAL
    blob, _ = extract_pause_art.extract()
    assert extract_pause_art.OUT.read_bytes() == blob == (PACKAGE/'pause_art.bin').read_bytes(), 'run extract_pause_art.py first'
    q = args.quick
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp';exe = Path(tmp)/'driver'
        cpp.write_text(DRIVER)
        sources = [ROOT/'src'/n for n in ('pause_art.cpp', 'pause_menu.cpp', 'key_config.cpp', 'skill_list.cpp', 'gallery_art.cpp',
                                         'console_gallery.cpp', 'menu_widgets.cpp', 'menu_canvas.cpp', 'console_menu.cpp',
                                         'system_data.cpp', 'game_random.cpp', 'scalar_float.cpp')]
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, *sources, '-o', exe], check=True)
        jobs = []
        jobs += [(pause_rows, (exe, m, sub, seat, q)) for m, sub, seat in
                 ((1, 1, 0), (2, 1, 1), (3, 1, 0), (3, 1, 1), (3, 2, 1), (0xb, 4, 0), (1, 5, 0), (2, 5, 1))]
        jobs += [(pause_random, (exe, name, 3+i, 300 if q else 1500)) for i, name in enumerate(('mixed', 'versus', 'land', 'mixed'))]
        jobs += [(key_case, (exe, name, mode, 11+i, 200 if q else 900)) for i, (name, mode) in
                 enumerate((('pause', 1), ('pause', 2), ('pause', 3), ('pause', 0xb), ('pause', 0xc), ('option', 0x11), ('option', 0x11)))]
        contexts = [(1, 0, 0, 'factory'), (2, 0, 0, 'open'), (3, 0, 1, 'sparse'), (3, 1, 0, 'open'), (0xb, 0, 0, 'sparse'),
                    (0xc, 0, 0, 'factory'), (0xd, 0, 0, 'open'), (0xd, 0, 1, 'sparse')]
        jobs += [(skill_case, (exe, f'{mode:x}-{owner}{menu_seat}-{kind}', mode, owner, menu_seat, kind, 40+n, 250 if q else 1300))
                 for n, (mode, owner, menu_seat, kind) in enumerate(contexts)]
        if args.only:jobs = [j for j in jobs if j[0].__name__.startswith(args.only)]
        if args.jobs == 1:cases = [fn(spec) for fn, spec in jobs]
        else:
            with ProcessPoolExecutor(args.jobs) as pool:
                futures = [pool.submit(fn, spec) for fn, spec in jobs]
                cases = [f.result() for f in futures]
    total = {k: sum(c[k] for c in cases) for k in ('visits', 'drawn_visits', 'frames', 'queue_entries', 'restore_requests', 'instructions')}
    if args.quick:
        for c in cases:print({k: v for k, v in c.items() if k not in ('frames_sha256',)})
    if not args.only and not q:
        skill = [c for c in cases if c['scene'] == 'skill list'];key = [c for c in cases if c['scene'] == 'key configuration']
        assert all(c['heading_strips'] and 2 in c['states'] for c in skill) and sum(c['faded'] for c in skill) >= 6
        assert all(c['icon_entries'] for c in key)
        assert total['restore_requests'] > 1000
        REPORT.write_text(json.dumps(dict(status='passed', elf_sha256=ORIGINAL, cases=cases, identical_primitive_lists=total['visits'],
            visits_with_entries=total['drawn_visits'], identical_640x480_frames=total['frames'], original_queue_entries=total['queue_entries'],
            restore_requests=total['restore_requests'], original_instructions=total['instructions'],
            asset_sha256=hashlib.sha256(blob).hexdigest(), scope=SCOPE), indent=2)+'\n')
    print(len(cases), 'EE/native pause drawing traces;', total['visits'], 'identical primitive lists', f"({total['drawn_visits']} non-empty);",
          total['frames'], 'identical frames;', total['queue_entries'], 'queue entries;', total['restore_requests'], '109de8 requests;',
          total['instructions'], 'instructions')

SCOPE = ('Japanese SLPS-25559. Pause menu: whole original open poll 1d9b50 and task visits 1d9e10 with the unmodified draw routines '
         '1daca8 (1c1528 edges), 1da918, 1da9c0, 1dab38, 1dae00, 1ced08 and 1cf598, in game modes 0, 1, 2, 3, 6, 9, b, c with sub-modes '
         '0..6: every row of both row sets reached forwards and backwards for both owners, both prompts with both answers, WINDOW OFF, '
         'child-window suspension and 1da7e8, three scene-fade states and BRIGHT b0, plus random sessions. KEY CONFIGURATION: coroutine '
         '13ce08 (182600 + 212478 with 17c718, 17e428, 17e228, 17e038, 17d790) in game modes 1, 2, 3, b, c (battle behind the window) '
         'and 0x11 (17ea48: page backdrop 1ce478 / 1ce570), random key masks, both cursors, slide-in and slide-out, scene fade and BRIGHT. '
         'SKILL LIST: coroutine 13d680 (dim plane, 182600, 20ef38 x 2, 210298 -> 13d0d0 with 17e0b0, 17e038, 17e428, 17f090) in game '
         'modes 1, 2, 3 (both owners), b, c and d (both menu seats) over factory, open and sparse unlock bytes, common and character '
         'groups, scrolling pages, scene fade while heading strips are shown, BRIGHT a0. The coroutines are PS2 kernel threads: their '
         'bodies run on their own stacks up to the yield entry 112a28 and are resumed at the saved return address; pads go through '
         '117fd8. After every visit the original submission queue 68c3c0 is decoded and compared entry by entry, in submission order '
         'and with exact float bits, with the MenuDrawList of src/pause_art.cpp built from the native logic state (pause_menu, '
         'key_config, skill_list, menu_widgets driven by the same pad words); glyph entries compare the cached texel block; the '
         'four-colour strip of 17e0b0 compares both colours. Renderer globals compared after every visit: 3db900, 3db8fc, 3db8f4, '
         '345180, 348a8c, depth cursor 12d3850, ASCII depth 3d3aac, the help marquee, the edge pulse words 582f60 / 582f64, bit 4 of '
         '3451c8 (the 109de8 request), and for the child windows the library RNG seed, the overlay population words and the menu '
         'counters. The painted subset uses the reference painter of validate_menu_canvas.py for the original queue (ascending depth, '
         'pixel-centre sampling; the queue-to-GS translation 106c08 and GS rasterisation are not executed), extended by a horizontal '
         'colour ramp for the 17e0b0 strip (GS Gouraud interpolation not verified), against PauseArt::rasterise over the same '
         'non-uniform 640x480 frame. Everything executes unmodified except the boundaries of validate_gallery_art.py (sound driver '
         'entries 1e7b70 1e7ba0 1e79c8 1e7d60 1e7ad0 1e7b40 1e8298 213180 213238, debug prints 316140 316218, thread creation 100e58, '
         'scene switch 1252f0, 182858 1828c0 120110 as jr ra; texture load 1142d8 and the disc read 102810 served with the archive '
         'members), plus 213be8 (music fade), 11bd58 (network session) and 323050 (debug print) as jr ra, and in the pause-menu cases '
         '1126f0 (kernel-thread creation of the two child tasks) replaced by a stub returning one fixed record per tag. Not covered: '
         'the exit executor 1da210 and the battle teardown (a scene request is followed by fresh game data), the GS frame-buffer copy '
         'that 109de8 requests and the battle scene behind the windows, the practice-menu owner of the key widget, the scheduler order '
         'between the battle thread and the three tasks, icons 33..47 of the slot 5 sheet (unreachable here).')

if __name__ == '__main__':main()
