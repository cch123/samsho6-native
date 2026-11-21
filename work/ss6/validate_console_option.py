#!/usr/bin/env python3
"""Match the native OPTION MODE pages to the original SLPS-25559 handlers visit by visit."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile

from mips_probe import signed
from validate_console_versus_menu import Oracle
from validate_dash_motion import ELF, PIN, ROOT, digest
from validate_versus_result import T, HANDLE, ALPHA

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/console_option_validation.json'
IMAGE, OPTION, SETTING, MIXER = 0x5735c8, 0x43d058, 0x43d050, 0x5a9e78
TOP, GAME, KEY, SOUND, SAVE, TITLE = 1, 2, 3, 4, 5, 6
ENTRY = {0x1cfa10: TOP, 0x1d00b8: GAME, 0x13cdb0: KEY, 0x1dba30: SOUND, 0x1d30b0: SAVE, 0x127940: TITLE}
HANDLER = {TOP: 0x1cfa98, GAME: 0x1d01b8, SOUND: 0x1dbb00, SAVE: 0x1d3140}
START = {v: k for k, v in ENTRY.items()}
CURSOR = {TOP: 0x582c38, GAME: 0x582c68, SOUND: 0x582ff0, SAVE: 0x582de8}
FRAME = {GAME: 0x582c70, SOUND: 0x582ff8, SAVE: 0x582df4}
BANNER = {0x1cfdb0, 0x1d0e68, 0x1dc470, 0x1d3550}
# Rendering primitives, texture loads and the animated background layer.
RENDER = (0x1142d8, 0x1163c0, 0x116478, 0x10add8, 0x1e1620, 0x1e2358, 0x1e23a0, 0x1e2408, 0x1ce570,
          0x1145c0, 0x1135e8, 0x10a460, 0x113f98, 0x1cf8f8, 0x1ced08, 0x1cf2a8)
# Sound driver requests, debug printf/puts, card dialogs, scenes outside this slice.
DRIVER_CALLS = (0x1e7b70, 0x1e7b40, 0x213c08, 0x213180, 0x316140, 0x316218, 0x10f958, 0x10f088, 0x13cdb0, 0x127940)
# Original branch targets every run must reach in total (coverage evidence).
COVERAGE = {0x1d0840: 'game defaults', 0x1d0920: 'game increment', 0x1d0ad8: 'game decrement',
            0x1d0c98: 'gauge +2', 0x1d0d80: 'gauge -2', 0x1d02e0: 'game discard', 0x1d0584: 'gauge discard',
            0x1d03b8: 'game commit', 0x1d0800: 'game leave', 0x1d1e20: 'page slide', 0x1d0a70: 'bright wrap up',
            0x1d0c30: 'bright wrap down', 0x1dc0e0: 'sound commit', 0x1dc2b0: 'sound revert',
            0x1dbee8: 'sound defaults', 0x1dc060: 'volume up', 0x1dc0a0: 'volume down', 0x1dbf60: 'sound toggle a',
            0x1dbfe0: 'sound toggle b', 0x1dbea8: 'sound leave', 0x10f958: 'save', 0x10f088: 'load',
            0x10f18c: 'auto-save', 0x1d3458: 'save page leave', 0x1d32b8: 'auto-save commit',
            0x1d3288: 'auto-save cancel', 0x1cfc88: 'exit to title', 0x1cfd58: 'key config dispatch',
            0x1dc1c8: 'volume commit', 0x1dc378: 'volume revert'}

DRIVER = r'''
#include "console_option.hpp"
#include <cstdio>
#include <iostream>
#include <sstream>
using namespace ss6;
static std::string hex(const uint8_t* p,size_t n) {
    static const char* d="0123456789abcdef";std::string s;
    for(size_t i=0;i<n;++i){s+=d[p[i]>>4];s+=d[p[i]&15];}
    return s.empty()?"-":s;
}
static std::string hex(const std::string& s){return hex(reinterpret_cast<const uint8_t*>(s.data()),s.size());}
template<class V> static std::string list(const V& v) {
    std::string s;for(int x:v){if(!s.empty())s+=',';s+=std::to_string(x);}
    return s.empty()?"-":s;
}
int main(int,char** argv) {
    SystemData data(argv[1]);ConsoleOptionTables tables(argv[1]);ConsoleOption o(tables,data);
    MenuPadRepeat repeat;std::array<MenuPad,2> pads{};SceneFade fade;OptionScene pending=OptionScene::None;
    std::vector<std::pair<size_t,unsigned>> patch;
    o.load=[&]{for(auto [at,v]:patch)data.image()[at]=uint8_t(v);};
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);char op;in>>op;
        if(op=='R')o.resetTopCursor();
        else if(op=='E'){int scene,rnd;in>>scene>>rnd;o.enter(OptionScene(scene),rnd);}
        else if(op=='F'){while(fade.active())fade.tick();}
        else if(op=='S'){unsigned a,b,c,d;in>>a>>b>>c>>d;pads=repeat.sample({a,b},{c,d});}
        else if(op=='P'||op=='L') {
            patch.clear();size_t at;unsigned v;
            while(in>>at>>v)patch.push_back({at,v});
            if(op=='P') {
                // The fixture unpacks the image as 1b8b88 does at boot.
                for(auto [a,x]:patch)data.image()[a]=uint8_t(x);
                o.mixerVolume=ConsoleOption::unpackedMixerVolume(tables,data.setting(4));
                patch.clear();
            }
        } else if(op=='T') {
            int rnd;in>>rnd;
            const auto r=o.tick(pads);
            const auto& d=o.draw;const auto& c=o.chrome;
            std::ostringstream out;
            out<<"sc="<<int(d.scene)<<" cur="<<d.cursor<<" st="<<d.state<<" fr="<<d.frame<<" tc="<<o.topCursor()
               <<" pg="<<o.page()<<" sn="<<o.slideCounter()<<" ss="<<o.slideState()
               <<" cb="<<c.band<<" cc="<<c.content<<" cl="<<c.legend<<" cv="<<c.variant
               <<" hx0="<<c.helpX[0]<<" hx1="<<c.helpX[1]<<" hd="<<c.helpDelay
               <<" mix="<<o.mixerVolume<<" as="<<data.autoSave()<<" sw="<<o.autoSaveWork()
               <<" gw="<<hex(o.gameWork().data(),0x98)<<" gl="<<hex(&data.image()[SystemData::gameOption],0x98)
               <<" ow="<<hex(o.soundWork().data(),7)<<" ol="<<hex(&data.image()[SystemData::systemSetting],7)
               <<" snd="<<list(r.sounds)<<" req="<<int(r.request)<<" sv="<<r.saveRequests<<" ld="<<r.loadRequests
               <<" au="<<int(r.autoSave)<<" out="<<list(r.soundOutputs)
               <<" wh="<<int(d.whiteScreen)<<" fd=";
            if(d.frameDrawn)out<<int(d.showPage)<<':'<<d.page<<':'<<d.pageTotal<<':'<<d.band<<':'<<d.legend;else out<<'-';
            out<<" bn="<<d.banner<<':'<<d.alpha<<" hp=";
            for(int i=0;i<d.helpCopies;++i)if(d.helpVisible[i])out<<d.helpX[i]<<':'<<d.alpha<<':'<<hex(*d.help)<<';';
            out<<"| sl=";
            if(d.sliding)out<<d.slideCounter<<':'<<d.slideOutX<<':'<<d.slideInX;else out<<'-';
            for(const auto& t:d.texts) {
                if(t.highlight)out<<" H:"<<hex(t.text)<<':'<<t.x<<':'<<t.y<<':'<<d.frame;
                out<<" T:"<<hex(t.text)<<':'<<t.x<<':'<<t.y<<':'<<t.argb;
            }
            // The successor entry runs after the page update, as task 1251d0 does.
            int entered=0;
            if(r.request!=OptionScene::None){fade.begin(true);pending=r.request;}
            if(fade.active()&&fade.tick()) {
                entered=int(pending);
                if(pending!=OptionScene::KeyConfig&&pending!=OptionScene::Title)o.enter(pending,rnd);
            }
            std::cout<<"ent="<<entered<<" fl="<<fade.level()<<' '<<out.str()<<'\n';
        }
    }
}
'''

def valid_image(rng):
    """Random in-range option values: out-of-range bytes index past the original value tables."""
    even = lambda hi: rng.randrange(0, hi+1, 2)
    game = {4: rng.randint(1, 8), 5: rng.randrange(3), 6: rng.randrange(2), 7: rng.randrange(15),
            8: rng.randint(1, 5), 9: rng.randrange(0, 201, 10), 0x10: rng.randrange(3), 0x11: even(200),
            0x12: even(200), 0x13: rng.randrange(3), 0x14: even(200), 0x15: even(200),
            0: rng.randrange(256), 3: rng.randrange(256)}
    patch = [(0x618c+k, v) for k, v in game.items()]
    patch += [(0x618c+0xc+i, b) for i, b in enumerate(struct.pack('<i', rng.randrange(0x38, 0x101, 2)))]
    patch += [(0x6184+k, v) for k, v in {0: rng.randrange(256), 3: rng.randrange(2), 4: rng.randrange(101),
                                         5: rng.randrange(2), 6: rng.randrange(2)}.items()]
    return patch+[(0, rng.randrange(2))]

class OptionOracle(Oracle):
    def __init__(self):
        super().__init__()
        p = self.p
        for a in RENDER+DRIVER_CALLS:
            p.memory[a:a+8] = struct.pack('<II', 0x03e00008, 0x0000102d)
        # 10f158 tests the auto-save flag and packs the live blocks (1b8cf0)
        # before its blocking card sequence; return from there.
        p.memory[0x10f194:0x10f19c] = struct.pack('<II', 0x08000000 | 0x10f320 >> 2, 0)
        self.run(0x10f000); self.run(0x1b8b88)
        self.scene = 0; self.entries = 0; self.library_draws = []; self.load_patch = []
        self.reached = Counter(); self.rects = [tuple(p.read(0x4c7660+0x18*n+4*i, 4) for i in (0, 1)) for n in range(8)]

    def run(self, pc, *args, stop=(), observe=None):
        from validate_input_lifecycle import Boundary
        boundary = Boundary(*stop) if stop else ()
        val, n = self.p.run(pc, args, limit=3000000, stop_before=boundary, observe=observe)
        if stop:assert boundary.stopped in stop
        self.calls[hex(pc)] += 1; self.instructions += n; return val

    def poke(self, patch):
        for at, v in patch:self.p.write(IMAGE+at, v, 1)
        self.run(0x1b8b88)

    def enter(self, scene):
        draws = []
        self.run(START[scene], observe=lambda pc: draws.append(pc) if pc == 0x316b90 else None)
        self.scene = scene; self.entries += 1; self.library_draws.append(len(draws))
        return (self.p.read(0x582b44, 4)-1) << 14

    def finish_fade(self):
        # 116b9c applies the level step that 1251d0 requests each frame.
        for _ in range(40):
            if not self.p.read(T+4, 4):return
            self.run(0x1251d0, HANDLE); self.run(0x116b9c, stop=(0x116bf0, 0x116bf4))
        raise AssertionError('fade did not finish')

    def visit(self):
        p = self.p; r = p.registers
        e = dict(snd=[], req=0, sv=0, ld=0, au=0, out=[], wh=0, fd='-', bn=None, hp='', sl=None, tx=[], out_x=None)
        text = lambda a: bytes(p.memory[a:p.memory.index(0, a)]).hex() or '-'
        s32 = lambda n: signed(r[n], 32)
        def obs(pc):
            if pc in COVERAGE:self.reached[pc] += 1
            if pc == 0x1e7b70:
                assert r[4] & 0xffffffff == 0xffffffff; e['snd'].append(r[5])
            elif pc == 0x1252f0:
                assert (r[4], r[5]) == (1, 0) and not e['req']; e['req'] = ENTRY[r[7]]
            elif pc == 0x1135e8:e['tx'].append(f'T:{text(r[4])}:{s32(5)}:{s32(6)}:{r[7] & 0xffffffff}')
            elif pc == 0x1cf8f8:e['tx'].append(f'H:{text(r[4])}:{s32(5)}:{s32(6)}:{s32(7)}')
            elif pc == 0x10a460:
                assert s32(6) == 0x198 and r[7] == r[8] == r[9] == 0xff
                e['hp'] += f'{s32(5)}:{s32(10)}:{text(r[4])};'
            elif pc in BANNER:e['bn'] = [s32(4), None]
            elif pc == 0x113f98:
                assert r[4] == 0x2e and e['bn'][1] is None
                e['bn'][1] = self.rects.index((int(p.float_value(17)), int(p.float_value(18))))
            elif pc == 0x1145c0 and r[8] & 0xffffffff == 0xffffffff and (r[6], r[7]) == (0x280, 0x1c0):e['wh'] = 1
            elif pc == 0x1ce660:
                e['fd'] = f'{r[4]}:{r[5]}:{r[6]}:{p.read(0x582b34, 4)}:{p.read(0x582b3c, 4)}'
            elif pc == 0x1d1e20:e['sl'] = [s32(4)]
            elif pc in (0x1d1f50, 0x1d205c):e['sl'].append(s32(2))
            elif pc == 0x213c08:e['out'].append(r[4])
            elif pc == 0x10f18c:e['au'] = 1
            elif pc == 0x10f958:e['sv'] += 1
            elif pc == 0x10f088:
                # Stand-in for the card read: a successful load replaces image
                # bytes, a failed one leaves the image as 10f088 restores it.
                e['ld'] += 1
                for at, v in self.load_patch:p.write(IMAGE+at, v, 1)
        scene = self.scene
        # 1251d0 publishes the level that the following frame draws.
        shown = p.read(ALPHA, 4)
        self.run(HANDLER[scene], observe=obs)
        rd = lambda a: p.read(a, 4)
        row = [f'sc={scene}', f'cur={rd(CURSOR[scene])}', f'st={rd(CURSOR[scene]+4)}',
               f'fr={signed(rd(FRAME[scene]), 32)-1 if scene in FRAME else 0}', f'tc={rd(0x582c38)}',
               f'pg={rd(0x133f9f8)}', f'sn={rd(0x133f9fc)}', f'ss={rd(0x133fa00)}']
        row += [f'cb={rd(0x582b34)}', f'cc={rd(0x582b38)}', f'cl={rd(0x582b3c)}', f'cv={rd(0x582b44)}',
                f'hx0={signed(rd(0x582b28), 32)}', f'hx1={signed(rd(0x582b2c), 32)}', f'hd={signed(rd(0x582b30), 32)}',
                f'mix={signed(rd(MIXER), 32)}', f'as={signed(rd(IMAGE), 32)}', f'sw={signed(rd(0x582df0), 32)}',
                f'gw={bytes(p.memory[0x582c78:0x582c78+0x98]).hex()}', f'gl={bytes(p.memory[OPTION:OPTION+0x98]).hex()}',
                f'ow={bytes(p.memory[0x133fa38:0x133fa3f]).hex()}', f'ol={bytes(p.memory[SETTING:SETTING+7]).hex()}',
                'snd='+(','.join(map(str, e['snd'])) or '-'), f'req={e["req"]}', f'sv={e["sv"]}', f'ld={e["ld"]}',
                f'au={e["au"]}', 'out='+(','.join(map(str, e['out'])) or '-'), f'wh={e["wh"]}', f'fd={e["fd"]}', f'bn={e["bn"][1]}:{e["bn"][0]}',
                f'hp={e["hp"]}|', 'sl='+(':'.join(map(str, e['sl'])) if e['sl'] else '-')]+e['tx']
        entered = []
        if p.read(T+4, 4):
            draws = []
            def fade(pc):
                if pc in ENTRY:entered.append(ENTRY[pc])
                elif pc == 0x316b90:draws.append(pc)
            self.run(0x1251d0, HANDLE, observe=fade)
            if entered and entered[0] in HANDLER:self.library_draws.append(len(draws))
        self.run(0x116b9c, stop=(0x116bf0, 0x116bf4))
        if entered:
            assert len(entered) == 1; self.scene = entered[0] if entered[0] in HANDLER else 0; self.entries += 1
        row = [f'ent={entered[0] if entered else 0}', f'fl={shown}']+row
        variant = (rd(0x582b44)-1) << 14 if entered else 0
        return row, variant, entered[0] if entered else 0

class Session:
    """Drives the original and records the equivalent native command stream."""
    def __init__(self, name, seat=0, seed=0, poke=()):
        self.o = OptionOracle(); self.name = name; self.seat = seat; self.rng = random.Random(seed)
        self.commands = []; self.rows = []; self.scenes = Counter(); self.entered = Counter()
        if poke:
            self.o.poke(poke); self.commands.append('P '+' '.join(f'{a} {v}' for a, v in poke))
        self.top(reset=True)

    def top(self, reset=False):
        if reset:
            self.o.run(0x1cfda0); self.commands.append('R')
        self.commands.append(f'E {TOP} {self.o.enter(TOP)}')

    def load_patch(self, patch):
        self.o.load_patch = list(patch); self.commands.append('L '+' '.join(f'{a} {v}' for a, v in patch))

    def visit(self, left=0, right=0):
        o = self.o
        edges = (left & ~o.last[0], right & ~o.last[1])
        o.sample((left, right)); self.commands.append(f'S {left} {right} {edges[0]} {edges[1]}')
        self.scenes[o.scene] += 1
        row, variant, entered = o.visit()
        self.commands.append(f'T {variant}'); self.rows.append(row)
        if entered:self.entered[entered] += 1
        if entered in (KEY, TITLE):
            # Those scenes are outside this slice. Let the white fade finish,
            # then come back as the KEY CONFIG close or the mode menu would.
            o.finish_fade(); self.commands.append('F')
            self.top(reset=entered == TITLE)
        return entered

    def own(self, key=0, other=0):
        return self.visit(*((other, key) if self.seat else (key, other)))
    def tap(self, key, other=0):
        self.own(key, other); return self.own()
    def wait(self, n=1):
        for _ in range(n):self.own()
    def ready(self):
        # 15 band + 15 content visits; the scene fade overlaps the first ones.
        while not self.o.run(0x1cf750):self.own()
    def until_entered(self):
        for _ in range(40):
            entered = self.own()
            if entered:return entered
        raise AssertionError('scene change did not complete')
    def state(self):
        p = self.o.p; s = self.o.scene
        return s, p.read(CURSOR[s], 4), p.read(CURSOR[s]+4, 4)

UP, DOWN, LEFT, RIGHT, PREV, NEXT = 0x10, 0x20, 0x40, 0x80, 0x100000, 0x400000
CONFIRMS, CANCELS = (0x200, 0x8, 0x2), (0x400, 0x4)

def game_script(s):
    """Every GAME OPTION row: edit, change in both directions, commit or discard, both slides."""
    s.ready(); s.tap(CONFIRMS[0]); assert s.until_entered() == GAME
    s.ready(); o = s.o; p = o.p
    work = lambda off: p.read(0x582c78+off, 1)
    for item in range(13):
        if item == 7:
            s.tap(NEXT); assert p.read(0x133fa00, 4) == 0x1 and p.read(0x133f9f8, 4) == 1
            s.ready(); assert s.state() == (GAME, 7, 0)
        assert s.state() == (GAME, item, 0), (item, s.state())
        before = bytes(p.memory[OPTION:OPTION+0x98])
        s.tap(CONFIRMS[item % 3]); assert s.state()[2] == 1
        for key in (UP, RIGHT, UP, DOWN, LEFT, LEFT, LEFT):s.tap(key)
        # Hold a direction through the auto-repeat delay to wrap the value.
        for _ in range(70 if item in (5, 6, 8, 9, 11, 12) else 30):s.own(UP if item % 2 else LEFT)
        s.own()
        if item in (2, 6, 9):
            s.tap(CANCELS[item % 2]); assert bytes(p.memory[OPTION:OPTION+0x98]) == before, item
        else:
            s.tap(CONFIRMS[0])
        assert s.state()[2] == 0 and bytes(p.memory[0x582c78:0x582c78+0x98]) == bytes(p.memory[OPTION:OPTION+0x98])
        s.tap(DOWN)
    assert s.state() == (GAME, 13, 0)
    s.tap(CONFIRMS[1]); assert (work(0x11), work(0x12), work(0x14), work(0x15)) == (32, 20, 32, 20)
    s.tap(UP); s.tap(UP); assert s.state()[1] == 11
    s.tap(DOWN); s.tap(DOWN); s.tap(DOWN); s.tap(DOWN); assert s.state()[1] == 7      # EXIT wraps to row 7
    s.tap(UP); assert s.state()[1] == 14
    s.tap(PREV); s.ready(); assert s.state() == (GAME, 0, 0) and p.read(0x133f9f8, 4) == 0
    s.tap(UP); s.tap(UP); assert s.state()[1] == 13
    s.tap(CONFIRMS[2]); assert (work(4), work(8), work(9), p.read(OPTION+0xc, 4)) == (4, 2, 100, 0x100)
    # Bright decrement from 0x38 wraps; hold right on GAME LEVEL with the idle seat pressing noise.
    s.tap(UP)
    assert s.state()[1] == 6
    s.tap(CONFIRMS[0]); s.tap(RIGHT); assert p.read(OPTION+0xc, 4) == 0x38
    s.tap(LEFT); assert p.read(OPTION+0xc, 4) == 0x100
    s.tap(DOWN); s.tap(CANCELS[0]); assert p.read(OPTION+0xc, 4) == 0x100
    s.tap(PREV); s.wait(4); s.tap(NEXT, other=CONFIRMS[0]); s.ready()
    for _ in range(3):s.tap(DOWN)
    s.own(DOWN | CONFIRMS[0]); s.own(); s.tap(CONFIRMS[0])
    while s.state()[1] != 14:s.tap(DOWN)
    s.tap(CONFIRMS[0]); assert s.state()[2] == 4
    assert s.until_entered() == TOP and s.state()[1] == 0
    # Re-enter and leave with cancel while the other seat confirms on the same visit.
    s.ready(); s.tap(CONFIRMS[0]); assert s.until_entered() == GAME; s.ready()
    s.own(CANCELS[1], other=CONFIRMS[0])
    if s.seat:
        # Seat 0 is served first: its confirm opened the edit that this cancel discarded.
        assert s.state() == (GAME, 0, 0); s.own(); s.own(CANCELS[1])
    assert s.state()[2] == 4 and s.until_entered() == TOP

def sound_script(s):
    s.ready(); s.tap(DOWN); s.tap(DOWN); s.tap(CONFIRMS[1]); assert s.until_entered() == SOUND
    s.ready(); p = s.o.p
    live = lambda off: p.read(SETTING+off, 1)
    for item, off in ((0, 3), (1, 4), (2, 6), (3, 5)):
        assert s.state() == (SOUND, item, 0)
        s.tap(CONFIRMS[0])
        for key in (UP, DOWN, LEFT, RIGHT, RIGHT):s.tap(key)
        if item == 1:
            for _ in range(45):s.own(DOWN)
            s.own()
        value = p.read(0x133fa38+off, 1)
        s.tap(CONFIRMS[2]); assert live(off) == value and s.state()[2] == 0
        s.tap(CONFIRMS[0]); s.tap(LEFT)
        if item == 1:
            for _ in range(30):s.own(RIGHT)
            s.own()
        s.tap(CANCELS[item % 2]); assert live(off) == value == p.read(0x133fa38+off, 1)
        s.tap(DOWN)
    assert s.state() == (SOUND, 4, 0)
    s.tap(CONFIRMS[0]); assert bytes(p.memory[SETTING:SETTING+7]) == bytes((0, 0, 0, 0, 100, 0, 0))
    assert signed(p.read(MIXER, 4), 32) == 0x3fff
    s.tap(UP); s.tap(UP); s.tap(UP); s.tap(CONFIRMS[0]); s.tap(LEFT); s.tap(CONFIRMS[0])
    assert live(4) == 99 and signed(p.read(MIXER, 4), 32) == 16220
    for _ in range(4):s.tap(DOWN)
    assert s.state() == (SOUND, 5, 0)
    s.tap(DOWN); s.tap(UP); s.tap(CONFIRMS[0]); assert s.until_entered() == TOP and s.state()[1] == 2
    s.ready(); s.tap(CONFIRMS[0]); assert s.until_entered() == SOUND; s.ready()
    s.tap(CANCELS[0]); assert s.until_entered() == TOP

def save_script(s):
    rng = s.rng
    s.ready(); s.tap(UP); s.tap(UP); assert s.state()[1] == 3
    s.tap(CONFIRMS[0]); assert s.until_entered() == SAVE
    s.ready(); p = s.o.p
    s.tap(CONFIRMS[0]); assert 'sv=1' in s.rows[-2]
    s.tap(DOWN)
    s.load_patch([]); s.tap(CONFIRMS[1])                       # refused or failed read
    loaded = valid_image(rng); s.load_patch(loaded); s.tap(CONFIRMS[0])
    for at, v in loaded:
        assert p.read(IMAGE+at, 1) == v
    s.tap(DOWN); assert s.state() == (SAVE, 2, 0)
    flag = p.read(IMAGE, 4)
    s.tap(CONFIRMS[0]); s.tap(RIGHT); s.tap(CANCELS[0]); assert p.read(IMAGE, 4) == flag
    s.tap(CONFIRMS[0])
    if not flag:s.tap(LEFT)
    else:
        s.tap(UP); s.tap(DOWN)
    s.tap(CONFIRMS[2]); assert p.read(IMAGE, 4) == 1 and s.state() == (SAVE, 2, 0)
    s.tap(DOWN); s.own(DOWN | CONFIRMS[0]); s.own()            # EXIT with a direction in the same word
    assert s.until_entered() == TOP
    s.ready(); assert s.state()[1] == 3
    s.tap(DOWN); s.tap(CONFIRMS[0]); assert s.until_entered() == TITLE   # EXIT row, auto-save on
    assert any('au=1' in row for row in s.rows[-20:])
    s.ready(); s.tap(DOWN); s.tap(CONFIRMS[0]); assert s.until_entered() == KEY
    s.ready(); assert s.state()[1] == 1                         # cursor kept after KEY CONFIG
    for _ in range(26):s.own(DOWN)                              # held repeat with wrap
    s.own()
    while s.state()[1] != 3:s.tap(UP)
    s.tap(CONFIRMS[0]); assert s.until_entered() == SAVE; s.ready()
    s.tap(UP); s.tap(UP); s.tap(CONFIRMS[0]); s.tap(DOWN); s.tap(CONFIRMS[0]); assert p.read(IMAGE, 4) == 0
    s.tap(DOWN); s.tap(DOWN); assert s.state()[1] == 0
    s.own(CANCELS[1] | CONFIRMS[0]); assert s.until_entered() == TOP
    s.ready(); s.tap(CANCELS[0]); assert s.until_entered() == TITLE      # cancel, auto-save off
    assert not any('au=1' in row for row in s.rows[-20:])

def random_script(s, visits):
    """Random held words on both seats; follows whatever scenes the original enters."""
    rng = s.rng
    held = [0, 0]; life = [0, 0]
    singles = [UP, DOWN, LEFT, RIGHT]
    for n in range(visits):
        scene = s.o.scene
        for seat in range(2):
            if life[seat] > 0:
                life[seat] -= 1; continue
            x = rng.random()
            # The acting seat is busier; the other one injects simultaneous input.
            idle = 0.35 if seat == s.seat else 0.8
            if x < idle:word = 0
            elif x < idle+(1-idle)*0.55:word = rng.choice(singles)
            elif x < idle+(1-idle)*0.80:word = rng.choice(CONFIRMS)
            elif x < idle+(1-idle)*0.85:word = rng.choice(CANCELS)
            elif x < idle+(1-idle)*0.93:word = rng.choice((PREV, NEXT)) if scene == GAME else rng.choice(singles)
            else:word = rng.choice(singles) | rng.choice(CONFIRMS+CANCELS+(PREV, NEXT, UP, DOWN))
            held[seat] = word; life[seat] = rng.choice((0, 0, 0, 1, 2, 3, 25, 40)) if word & 0xf0 else rng.choice((0, 1))
        if rng.random() < 0.02:s.load_patch(valid_image(rng) if rng.random() < 0.7 else [])
        s.visit(*held)

def run_case(spec):
    exe, kind, seat, seed = spec
    rng = random.Random(seed)
    poke = valid_image(rng) if kind == 'random' or seed % 2 else ()
    s = Session(kind, seat, seed, poke)
    if kind == 'game':game_script(s)
    elif kind == 'sound':sound_script(s)
    elif kind == 'save':save_script(s)
    else:random_script(s, 3000)
    native = subprocess.run([exe, ASSETS], input='\n'.join(s.commands)+'\n', text=True, capture_output=True, check=True)
    actual = [line.split() for line in native.stdout.splitlines()]
    assert len(actual) == len(s.rows), (kind, seat, len(actual), len(s.rows))
    for i, (a, b) in enumerate(zip(actual, s.rows)):
        if a != b:
            diff = [(x, y) for x, y in zip(a, b) if x != y][:6]
            raise AssertionError((kind, seat, seed, i, len(a), len(b), diff, s.rows[i-1][:8] if i else None))
    o = s.o
    assert set(o.library_draws) == {1}, o.library_draws
    return dict(case=kind, acting_seat=seat, seed=seed, visits=len(s.rows),
                visits_by_scene={str(k): v for k, v in sorted(s.scenes.items())},
                scene_entries={str(k): v for k, v in sorted(s.entered.items())},
                reached={hex(k): v for k, v in sorted(o.reached.items())}, instructions=o.instructions,
                text_submissions=sum(sum(t.startswith('T:') for t in row) for row in s.rows),
                highlights=sum(sum(t.startswith('H:') for t in row) for row in s.rows),
                sound_requests=sum(len(t[4:].split(',')) for row in s.rows for t in row if t.startswith('snd=') and t != 'snd=-'))

def library_draws():
    """Count 316b90 calls of one real page entry with the animated background initialisers restored."""
    from mips_probe import Probe
    o = OptionOracle(); original = Probe(ELF.read_bytes(), finite_model=True).memory
    for a in (0x1e1620, 0x1e2358, 0x1e23a0, 0x1e2408):o.p.memory[a:a+8] = original[a:a+8]
    callers = []
    o.run(0x1d00b8, observe=lambda pc: callers.append(o.p.registers[31]) if pc == 0x316b90 else None)
    own = [i for i, ra in enumerate(callers) if 0x1ce478 <= ra < 0x1ce570]
    assert len(own) == 1
    return dict(per_entry=len(callers), variant_draw_index=own[0])

def main():
    assert digest(ELF) == PIN
    draws = library_draws()
    asset = ASSETS/'console_option.bin'
    from extract_console_option import build
    assert asset.read_bytes() == build(ELF.read_bytes())[0], 'run extract_console_option.py'
    quick = '--quick' in sys.argv
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'option.cpp'; exe = Path(tmp)/'option'; cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp,
                        *(ROOT/'src'/f for f in ('console_option.cpp', 'console_menu.cpp', 'system_data.cpp',
                                                 'scalar_float.cpp')), '-o', exe], check=True)
        specs = [(exe, kind, seat, 11+seat) for kind in ('game', 'sound', 'save') for seat in (0, 1)]
        specs += [(exe, 'random', n % 2, 100+n) for n in range(2 if quick else 12)]
        with ProcessPoolExecutor(8) as pool:cases = list(pool.map(run_case, specs))
    reached = Counter()
    for c in cases:
        for k, v in c['reached'].items():reached[int(k, 16)] += v
    missing = [name for pc, name in COVERAGE.items() if not reached[pc]]
    assert not missing, missing
    totals = dict(visits=sum(c['visits'] for c in cases), instructions=sum(c['instructions'] for c in cases),
                  text_submissions=sum(c['text_submissions'] for c in cases),
                  visits_by_scene={k: sum(c['visits_by_scene'].get(k, 0) for c in cases) for k in '1245'},
                  scene_entries={k: sum(c['scene_entries'].get(k, 0) for c in cases) for k in '123456'})
    report = dict(status='passed', elf_sha256=PIN, asset_sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),
                  totals=totals, library_random_draws=draws, coverage={COVERAGE[k]: v for k, v in sorted(reached.items())}, cases=cases,
                  scope='Whole original handlers 1cfa98, 1d01b8, 1dbb00 and 1d3140 with their real entries (1cfa10, 1d00b8, '
                        '1dba30, 1d30b0 through 1ce478), both raw pad samplers 117fd8/118128, the task allocation and the '
                        '1252f0/1251d0 white fade that runs each destructor and entry. Compared every visit: cursor, state, '
                        'frame and slide counters, work and live blocks, auto-save flag, mixer word 5a9e78, chrome counters '
                        'and help marquee words, sound ids, scene requests and entry visit, fade level, every 1135e8 text and '
                        '1cf8f8 highlight argument, help submissions, banner rectangle, 1ce660 arguments and both 1d21a0 '
                        'slide offsets. Stubbed: texture/palette loads 1142d8/1163c0/116478/10add8, animated background '
                        '1e1620/1e2358/1e23a0/1e2408/1ce570, primitives 1145c0/1135e8/10a460/113f98/1cf8f8/1ced08/1cf2a8 '
                        '(arguments observed), sound driver 1e7b70/1e7b40/213c08/213180, debug print 316140/316218, card '
                        'dialogs 10f958/10f088 and the blocking tail of 10f158 after its flag test and 1b8cf0, and the '
                        'successor scene entries 13cdb0 (KEY CONFIGURATION) and 127940 (title). With the background stubs each '
                        'entry makes one 316b90 call (the variant); library_random_draws records the unstubbed count. A load is modelled by '
                        'replacing image bytes where 10f088 would; card IO itself is not exercised.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(len(cases), 'cases;', totals['visits'], 'visits;', totals['instructions'], 'original instructions;',
          totals['text_submissions'], 'text submissions; all', len(COVERAGE), 'coverage targets reached')

if __name__ == '__main__':main()
