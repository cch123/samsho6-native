#!/usr/bin/env python3
"""Match the native in-battle pause menu to SLPS-25559 visit by visit."""
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
REPORT = ROOT/'outputs/ss6-feasibility/pause_menu_validation.json'
SOURCES = ['pause_menu.cpp', 'console_menu.cpp', 'menu_widgets.cpp', 'system_data.cpp']
G, P, MENU, CHROME = 0x4c3808, 0x456890, 0x582f30, 0x582b28
POLL, TASK, RETURNED, EXIT, ABORT = 0x1d9b50, 0x1d9e10, 0x1da7e8, 0x1da210, 0x1da4d8
FAKE_TASKS = (0x1d0a5b0, 0x1d0a8d8)   # values returned by the 1126f0 replacement for tags 14b6 / 151b
# Callees replaced by `jr ra; move v0,zero`. Everything else runs from the ELF.
STUBS = {
    'rendering primitives': (0x1145c0, 0x1c1528, 0x113f98, 0x113828, 0x1135e8, 0x113838, 0x114d88, 0x10a460,
                             0x109f08, 0x1ced08),
    'sound driver': (0x1e7b70, 0x213be8),
    'scene switch': (0x1252f0,),
    'network session': (0x11bd58,),
    'debug print': (0x323050, 0x316140),
}
DRIVER = r'''
#include "pause_menu.hpp"
#include <cstring>
#include <iostream>
#include <sstream>
using namespace ss6;
static uint32_t mix(uint32_t h,const std::string& s){for(unsigned char c:s)h=h*131+c;return h*131+0x100;}
int main(int,char** argv){
    PauseMenuAssets assets(argv[1]);
    PauseMenu menu(assets);
    ArcadeGameData game;std::array<ArcadePlayer,2> players{};
    MenuPadRepeat repeat;std::array<uint32_t,2> last{};
    std::string line;
    while(std::getline(std::cin,line)){
        std::istringstream in(line);std::ostringstream o;std::string op;in>>op;
        auto num=[&]{long long v=0;in>>v;return v;};
        PauseTick r;bool ticked=false;
        if(op=="G"){
            int32_t words[42+24];for(auto& w:words)w=int32_t(num());
            std::memcpy(&game,words,sizeof game);std::memcpy(players.data(),words+42,sizeof players);
        } else if(op=="N"){
            menu=PauseMenu(assets);repeat=MenuPadRepeat();last={};
            std::memset(&game,0,sizeof game);std::memset(players.data(),0,sizeof players);
        } else if(op=="S"){
            menu.cursor=num();menu.state=num();menu.owner=num();menu.choice=num();
        } else if(op=="T"){
            const std::array<uint32_t,2> held{uint32_t(num()),uint32_t(num())};const bool fade=num();
            const auto pads=repeat.sample(held,{held[0]&~last[0],held[1]&~last[1]});last=held;
            menu.poll(game,pads,fade);
            if(menu.active){r=menu.tick(game,players,pads);ticked=true;}
        } else if(op=="W")menu.windowReturned();
        else if(op=="X"){menu.teardown();menu.exitScene(game,players);}
        else if(op=="A")menu.abort(game,players);
        o<<menu.cursor<<' '<<menu.state<<' '<<menu.active<<' '<<menu.owner<<' '<<menu.choice<<' '<<menu.locked<<' '
         <<menu.delay<<' '<<menu.window<<' '<<menu.suspended<<' '<<menu.tallyPaused<<' '<<menu.abortHook<<' '
         <<menu.windowTask[0]<<' '<<menu.windowTask[1]<<' '<<menu.chrome.content<<' '<<menu.chrome.legend<<' '
         <<menu.chrome.helpX[0]<<' '<<menu.chrome.helpX[1]<<' '<<menu.chrome.helpDelay<<' ';
        int32_t words[42+24];std::memcpy(words,&game,sizeof game);std::memcpy(words+42,players.data(),sizeof players);
        for(auto w:words)o<<w<<' ';
        o<<ticked<<' '<<unsigned(r.scene)<<' '<<r.musicFade<<' '<<r.networkCancel<<' '<<r.sounds.size();
        for(int v:r.sounds)o<<' '<<v;
        // The draw calls of the visit, in original order.
        std::vector<long long> d;
        const auto& w=r.draw;const bool land=game.submode==5;
        if(w.menu){
            const uint32_t a=w.owner?0xc0ff0000u:0xc00000ffu,b=w.owner?0xc0400000u:0xc0000040u;
            const int h=w.frameHeight;
            d.insert(d.end(),{1,0xb4,0x78,0x118,h});
            for(auto e:{std::array<int,4>{0xb0,0x74,0x120,4},{0xb0,h+0x78,0x120,4},{0xb0,0x78,4,h},{0x1cc,0x78,4,h}})
                d.insert(d.end(),{2,e[0],e[1],e[2],e[3],a,b});
            d.insert(d.end(),{3,0x2e});
            for(int i=0;i<w.rows;++i)
                d.insert(d.end(),{4,mix(0,land?assets.items5[i]:assets.items[i]),0xcc,0xb4+0x18*i,i==w.cursor?0xffff0000u:0xffffffffu});
            d.insert(d.end(),{1,0,0x174,0x280,0x24});
            if(w.helpX<0x280)d.insert(d.end(),{5,mix(0,land?assets.help5[w.cursor]:assets.help[w.cursor]),w.helpX,0x17a});
            d.insert(d.end(),{1,0x14c,0x19a,0x134,0x1c});
            d.insert(d.end(),{6,0,0x19d});
        }
        if(w.dialog){
            d.insert(d.end(),{1,0,0x64,0x280,0xf0});
            if(land)d.insert(d.end(),{7,mix(0,assets.askLand),0x9a,0xc8,0xff,0xff,0xff,0xff});
            else if(w.dialog==2)d.insert(d.end(),{7,mix(0,assets.askSelect),0x80,0xc8,0xff,0xff,0xff,0xff});
            else d.insert(d.end(),{7,mix(0,assets.askTitle),0xbe,0xc8,0xff,0xff,0xff,0xff});
            for(int i=0;i<2;++i){
                const int c=i==w.choice?0:0xff;
                d.insert(d.end(),{7,mix(0,assets.answers[i]),assets.answerX[i],0xf8,0xff,c,c,0xff});
            }
        }
        o<<' '<<d.size();for(auto v:d)o<<' '<<v;
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
        # 1126f0 starts an EE kernel thread for the two child windows (ports of
        # their own). The replacement returns a distinct task record per tag so
        # that the menu's writes to task word +4 stay observable:
        # lui v0,0x1d0; sll t1,t1,3; jr ra; addu v0,v0,t1.
        p.memory[0x1126f0:0x1126f0+16] = struct.pack('<4I', 0x3c0201d0, 0x000948c0, 0x03e00008, 0x00491021)
        buffered_stdout(p)
        p.write(0x443150, 1, 4)
        self.run(0x112570)
        self.instructions = 0
        self.last = [0, 0]
    def word(self, at): return signed(self.p.read(at, 4), 32)
    def words(self, at, n): return [self.word(at+4*i) for i in range(n)]
    def text(self, at):
        m = self.p.memory; return bytes(m[at:m.index(0, at)])
    def run(self, pc, *args, limit=400000):
        value, count = self.p.run(pc, args, limit=limit, observe=self.watch)
        self.instructions = getattr(self, 'instructions', 0)+count
        return value
    def watch(self, pc):
        p = self.p; r = p.registers
        a = lambda n: signed(r[n], 32)
        u = lambda n: r[n] & 0xffffffff
        if pc == 0x1e7b70:
            assert a(4) == -1; self.sounds.append(a(5))
        elif pc == 0x1252f0:
            assert [u(4), u(5), u(6)] == [2, 0, EXIT]; self.scene = u(7)
        elif pc == 0x213be8:
            assert a(4) == 3; self.fade = 1
        elif pc == 0x11bd58: self.cancel = 1
        elif pc == 0x1145c0: self.draw += [1, a(4), a(5), a(6), a(7)]
        elif pc == 0x1c1528: self.draw += [2, a(4), a(5), a(6), a(7), u(8), u(9)]
        elif pc == 0x113f98: self.draw += [3, a(4)]
        elif pc == 0x1135e8: self.draw += [4, mix(0, self.text(u(4))), a(5), a(6), u(7)]
        elif pc == 0x10a460:
            assert [a(7), a(8), a(9), a(10)] == [0xff]*4
            self.draw += [5, mix(0, self.text(u(4))), a(5), a(6)]
        elif pc == 0x1ced08: self.draw += [6, a(4), a(5)]
        elif pc == 0x109f08: self.draw += [7, mix(0, self.text(u(4))), a(5), a(6), a(7), a(8), a(9), a(10)]
    def clear(self):
        self.sounds = []; self.draw = []; self.scene = self.fade = self.cancel = 0
        self.p.write(0x123a0c4, 0, 4)
    def new(self):
        p = self.p
        for i in range(12): p.write(MENU+4*i, 0, 4)
        p.write(MENU+0x10, 1, 4)
        p.memory[G:G+0xa8] = bytes(0xa8); p.memory[P:P+0x60] = bytes(0x60)
        for at, v in ((0x582994, 0), (0x43d048, 0), (0x582b38, 0), (0x582b3c, 0), (0x582b28, 0x10), (0x582b2c, 0), (0x582b30, 0)):
            p.write(at, v, 4)
        for t in FAKE_TASKS: p.write(t+4, 0x21, 4)
        self.run(0x112570)
        for s in range(2):
            for at in (0x443568, 0x443570): p.write(at+4*s, 0, 4)
            p.memory[0x1237cc8+12*s:0x1237cc8+12*s+12] = bytes(12)
        # 117fd8 keeps its repeat counters next to the pad block.
        p.memory[0x1237cc8+24:0x1237cc8+24+32] = bytes(32)
        self.last = [0, 0]
        self.clear()
    def set(self, words):
        for i, w in enumerate(words[:42]): self.p.write(G+4*i, w, 4)
        for i, w in enumerate(words[42:]): self.p.write(P+4*i, w, 4)
        self.clear()
    def poke(self, cursor, state, owner, choice):
        for off, v in ((0, cursor), (4, state), (0xc, owner), (0x10, choice)): self.p.write(MENU+off, v, 4)
        self.clear()
    def tick(self, held, fade):
        p = self.p
        for s, h in enumerate(held):
            p.write(0x443568+4*s, h, 4); p.write(0x443570+4*s, self.last[s], 4); self.run(0x117fd8, s)
        self.last = list(held)
        self.clear()
        p.write(0x12d4cc8, fade, 4)
        self.run(POLL)
        # The task is an ordinary 112670 function task; a visit is one call.
        if p.read(MENU+8, 4): self.run(TASK)
    def row(self):
        p = self.p; w = self.word
        tasks = [w(t+4) for t in FAKE_TASKS]
        return [*self.words(MENU, 9), w(0x582994), int(p.read(0x43d048, 4) == ABORT), *tasks, w(0x582b38), w(0x582b3c),
                w(0x582b28), w(0x582b2c), w(0x582b30), *self.words(G, 42), *self.words(P, 24), w(0x123a0c4),
                self.scene, self.fade, self.cancel, len(self.sounds), *self.sounds, len(self.draw), *self.draw]

MODES = (1, 2, 3, 3, 3, 0xb, 0xc, 0, 9, 6)
SUBS = (0, 1, 2, 2, 3, 4, 5, 6)
KEYS = [0x80000]*4+[0x20]*8+[0x10]*5+[0x200]*8+[2, 8, 0x400, 0x400, 4, 0x40, 0x80, 0x80000 | 0x200, 0x220, 0x410, 0x100000, 1]

def game_words(rng, mode, sub, locks):
    g = [rng.randrange(0, 60) for _ in range(42)]
    g[0] = mode; g[0xa0//4] = sub; g[0x2c//4], g[0x30//4], g[0xa4//4] = locks
    return g+[rng.randrange(0, 50) for _ in range(24)]

def session(spec):
    exe, name, seed, visits = spec
    rng = random.Random(seed)
    o = Source()
    cmds = []; exp = []
    stats = dict(opens=0, closes=0, scenes=0, windows=0, exits=0, sounds=0, draws=0, aborts=0)
    def add(cmd):
        cmds.append(cmd); exp.append(o.row())
    def fresh():
        mode = rng.choice(MODES); sub = rng.choice(SUBS)
        if name == 'land': mode, sub = rng.choice((1, 2)), 5
        if name == 'versus': mode, sub = 3, rng.choice((1, 2))
        if name == 'survival': mode, sub = rng.choice((0xb, 0xc)), 4
        if name == 'arcade': mode, sub = rng.choice((1, 2)), 1
        locks = rng.choice(((0, 0, 0),)*8+((1, 0, 0), (0, 1, 0), (1, 0, 1), (0, 1, 1), (0, 0, 1)))
        words = game_words(rng, mode, sub, locks)
        o.new(); add('N')
        o.set(words); add('G '+' '.join(map(str, words)))
        return mode
    mode = fresh()
    queue = []; wait = None; leave = None; done = 0
    while done < visits:
        if leave is not None:
            leave -= 1
            if leave < 0:
                # Fade midpoint: 1252f0 runs the destructor it was given.
                o.clear(); o.run(EXIT, limit=3000000); add('X'); stats['exits'] += 1
                mode = fresh(); queue = []; wait = leave = None
                continue
        if wait is not None:
            wait -= 1
            if wait < 0:
                o.clear(); o.run(RETURNED, 1); add('W'); wait = None
                continue
        if rng.random() < 0.002:
            o.clear(); o.run(ABORT, limit=3000000); add('A'); stats['aborts'] += 1
            continue
        if not queue:
            kind = rng.random()
            if kind < 0.12: queue = [0]*rng.randrange(1, 14)
            elif kind < 0.18: queue = [rng.choice((0x10, 0x20))]*rng.randrange(18, 40)
            elif kind < 0.24: queue = [rng.choice(KEYS) | rng.choice(KEYS), 0]
            else: queue = [rng.choice(KEYS), 0]*rng.randrange(1, 3)
        key = queue.pop(0)
        noise = rng.choice((0,)*6+(0x80000, 0x200, 0x20, 0x400))
        seat = rng.randrange(2) if mode == 3 else (1 if mode in (2, 0xc) else 0)
        if rng.random() < 0.05: seat ^= 1
        held = [noise, key] if seat else [key, noise]
        fade = int(rng.random() < 0.05)
        before = o.word(MENU+8), o.word(MENU+0x20)
        o.tick(held, fade); add(f'T {held[0]} {held[1]} {fade}'); done += 1
        after = o.word(MENU+8), o.word(MENU+0x20)
        stats['opens'] += after[0] and not before[0]; stats['closes'] += before[0] and not after[0]
        stats['sounds'] += len(o.sounds); stats['draws'] += bool(o.draw)
        if after[1] and not before[1]: wait = rng.randrange(0, 12); stats['windows'] += 1
        if o.scene and leave is None: leave = rng.randrange(0, 16); stats['scenes'] += 1
    return finish(exe, name, cmds, exp, o, stats)

def finish(exe, name, cmds, exp, o, stats):
    native = subprocess.run([exe, ASSETS], input='\n'.join(cmds)+'\n', text=True, capture_output=True, check=True)
    actual = [list(map(int, line.split())) for line in native.stdout.splitlines()]
    assert len(actual) == len(exp), (name, len(actual), len(exp))
    for i, (a, b) in enumerate(zip(actual, exp)):
        assert a == b, (name, i, cmds[i][:60], len(a), len(b), [(k, v, w) for k, (v, w) in enumerate(zip(a, b)) if v != w][:12])
    return dict(case=name, snapshots=len(exp), **stats, instructions=o.instructions)

def scripted(spec):
    """Every row of every menu variant: open, reach the row, confirm, and follow each branch to its end."""
    exe, mode, sub, seat = spec
    rng = random.Random(mode*64+sub*8+seat)
    o = Source(); cmds = []; exp = []
    stats = dict(opens=0, scenes=0, windows=0, exits=0, sounds=0, draws=0)
    rows = 4 if sub == 5 else 6
    def add(cmd):
        cmds.append(cmd); exp.append(o.row())
    def tick(key=0):
        held = [0, key] if seat else [key, 0]
        before = o.word(MENU+8)
        o.tick(held, 0); add(f'T {held[0]} {held[1]} 0')
        stats['opens'] += o.word(MENU+8) and not before; stats['sounds'] += len(o.sounds); stats['draws'] += bool(o.draw)
    def tap(key, idle=1):
        tick(key)
        for _ in range(idle): tick()
    def start(row, back=False):
        words = game_words(rng, mode, sub, (0, 0, 0))
        o.new(); add('N'); o.set(words); add('G '+' '.join(map(str, words)))
        tap(0x80000, 11)
        assert o.word(MENU+8) == 1, (mode, sub, seat)
        for _ in range((rows-row) % rows if back else row): tap(0x10 if back else 0x20)
        assert o.word(MENU) == row
    question = (1, 5) if rows == 6 else (3,)
    window = (2, 3) if rows == 6 else (1, 2)
    for row in range(rows):
        for back in (False, True):
            start(row, back)
            tap(rng.choice((0x200, 2, 8)), 11)
            if row == 0: assert o.word(MENU+8) == 0
            elif row in question:
                # no, cancel, then yes through each of the four toggle directions
                tap(0x200, 11); tap(0x200, 11); tap(0x400, 11); tap(0x200, 11)
                tap(rng.choice((0x10, 0x20, 0x40, 0x80)), 2)
                tick(0x200)
                assert o.scene, (mode, sub, row); stats['scenes'] += 1
                for _ in range(rng.randrange(1, 15)): tick(rng.choice((0, 0x200, 0x80000)))
                o.clear(); o.run(EXIT, limit=3000000); add('X'); stats['exits'] += 1
            elif row in window:
                assert o.word(MENU+0x20) == 1; stats['windows'] += 1
                for _ in range(rng.randrange(1, 6)): tick(rng.choice((0, 0x200, 0x80000, 0x20)))
                o.clear(); o.run(RETURNED, 1); add('W')
                for key in (0x200, 0, 0, 0x20, 0, 0, 0, 0, 0, 0, 0, 0, 0x20, 0, 0x400, 0, 0): tick(key)
                assert o.word(MENU+8) == 0
            else:
                # WINDOW OFF: each way back to the list, then close while hidden
                for key in (0x200, 0x10, 0x20, 0x40, 0x80, 0x400):
                    assert o.word(MENU+4) == 5
                    tap(key, 11); assert o.word(MENU+4) == 0 and o.word(MENU) == 4
                    tap(0x200, 11)
                tap(0x80000, 2); assert o.word(MENU+8) == 0
    return finish(exe, f'rows_mode_{mode:x}_sub_{sub}_seat_{seat}', cmds, exp, o, stats)

def exits(spec):
    """1da210 over every state, mode, sub-mode and owner with arbitrary game data."""
    exe, state = spec
    rng = random.Random(0x1da210+state)
    o = Source(); cmds = []; exp = []
    o.new(); cmds.append('N'); exp.append(o.row())
    for mode in (0, 1, 2, 3, 6, 9, 0xa, 0xb, 0xc, 0x11):
        for sub in range(0, 8):
            for owner in range(2):
                words = game_words(rng, mode, sub, (rng.randrange(2), rng.randrange(2), rng.randrange(2)))
                o.set(words); cmds.append('G '+' '.join(map(str, words))); exp.append(o.row())
                poke = [rng.randrange(6), state, owner, rng.randrange(2)]
                o.poke(*poke); cmds.append('S '+' '.join(map(str, poke))); exp.append(o.row())
                o.clear(); o.run(EXIT, limit=3000000); cmds.append('X'); exp.append(o.row())
    return finish(exe, f'exit_state_{state}', cmds, exp, o, dict(exits=len(cmds)//3))

def main():
    assert digest(ELF) == PIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'check.cpp'; exe = Path(tmp)/'check'
        cpp.write_text(DRIVER)
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp,
                        *[ROOT/'src'/s for s in SOURCES], '-o', exe], check=True)
        specs = [(exe, name, 0x1d9e10+17*i, 2500) for i, name in
                 enumerate(('mixed', 'mixed', 'arcade', 'versus', 'survival', 'land', 'mixed', 'versus'))]
        with ProcessPoolExecutor(8) as pool:
            sessions = list(pool.map(session, specs))
            direct = list(pool.map(exits, [(exe, s) for s in (0, 1, 2, 5, 6)]))
            rows = list(pool.map(scripted, [(exe, m, sub, seat) for m, sub, seat in
                                            ((1, 1, 0), (2, 1, 1), (3, 1, 0), (3, 1, 1), (3, 2, 0), (3, 2, 1), (0xb, 4, 0),
                                             (0xc, 4, 1), (1, 5, 0), (2, 5, 1), (1, 0, 0), (2, 2, 1))]))
    sessions += rows
    total = lambda rows, k: sum(r.get(k, 0) for r in rows)
    report = dict(status='passed', elf_sha256=PIN, sessions=sessions, exit_executor=direct,
                  snapshots=total(sessions+direct, 'snapshots'), instructions=total(sessions+direct, 'instructions'),
                  stubs={k: [hex(a) for a in v] for k, v in STUBS.items()},
                  scope='Whole original 1d9b50 open poll (with 181778 and 1d9cd8/1d9da0/1da860), whole 1d9e10 task visits '
                        'including 1dae40, 1da508, 1da430, 1da110 and the draw routines 1daca8/1da918/1da9c0/1dab38/1dae00/'
                        '1cf598, 1da7e8, the exit executor 1da210 with the real battle teardown 139778, and 1da4d8; pads through '
                        '117fd8. Replaced by an empty return: the rendering primitives called by the draw routines (their '
                        'arguments are compared as the draw list), 1e7b70 and 213be8 (sound), 1252f0 (scene switch, arguments '
                        'compared), 11bd58 (network session), 323050 and 316140 (debug print). 1126f0 (kernel-thread task '
                        'creation of the two child windows) is replaced by a stub returning one fixed record per tag. The '
                        'child windows themselves and the scheduler order between the battle thread and task 178b are '
                        'outside this comparison.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(f"pause menu: {len(sessions)} sessions ({len(rows)} scripted row sweeps) + {len(direct)} exit sweeps; {report['snapshots']} snapshots; "
          f"{total(sessions, 'opens')} opens, {total(sessions, 'scenes')} scene requests, {total(sessions, 'windows')} child windows, "
          f"{total(direct, 'exits')+total(sessions, 'exits')} exit executions; {report['instructions']} instructions")

if __name__ == '__main__':main()
