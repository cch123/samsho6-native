#!/usr/bin/env python3
"""Compare the native survival-mode module with the original SLPS-25559 functions in Probe."""
import hashlib
import json
import random
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from extract_collision_tables import SOURCE_HASH
from extract_save_default import factory_image
import extract_survival_run

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/survival_run_validation.json'
ELF = ROOT/'work/ss6/extracted/SLPS_255.59'

G, CFG, GS, IMAGE = 0x4c3808, 0x456890, 0x43d058, 0x5735c8
B, SETUP, A, O = 0x1b00000, 0x1b10000, 0x1c00000, 0x1c10000
S, T, WIN, SEL, ROWS = 0x12d4cbc, 0x12d3668, 0x12d4d48, 0x12d4eb0, 0x12d4f20
PADS, FLAGS = 0x1237cc8, 0x13430b0
RETURN = struct.pack('<II', 0x03e00008, 0x0000102d)   # jr ra; move v0,zero
# Rendering, sound driver and debug-print callees replaced by a bare return.
DRAW = {0x182600: 'window draw', 0x211e18: 'selector draw', 0x17c228: 'depth', 0x1145c0: 'rectangle',
        0x17db28: 'text colour', 0x17e228: 'text', 0x1e7b70: 'sound request', 0x1b5b80: 'life-gain effect',
        0x1e7df0: 'sound stop', 0x323050: 'kernel logger', 0x1252f0: 'scene switch'}
# Callees of other modules, recorded as events and not executed.
FOREIGN = {0x1b4e88: 'stage event placement', 0x1b4d90: 'stage event request', 0x11e3a0: 'object release by tag',
           0x112a70: 'task release by tag'}

DRIVER = r'''
#include "survival_run.hpp"
#include <cstdio>
#include <iostream>
#include <sstream>
using namespace ss6;
static void slide(std::ostream& o,const SurvivalSlide& s) {
    for(int v:{s.x,s.y,s.remaining,s.duration,s.fromX,s.fromY,s.toX,s.toY,s.closed,s.closedX,s.closedY,s.openX,s.openY})o<<' '<<v;
}
static void rowsOut(std::ostream& o,const std::array<SurvivalCandidate,3>& rows) {
    for(auto& r:rows)o<<' '<<r.stage<<' '<<r.humanSpirit<<' '<<r.character<<' '<<r.colour<<' '<<r.reward<<' '<<r.mission;
}
static void dump(std::ostream& o,const SurvivalRun& r,const GameRandom& g) {
    o<<r.state<<' '<<r.prev<<' '<<r.delay<<' '<<r.fade<<' '<<r.savedLife<<' '<<r.savedClock<<' '<<r.humanSeat<<' '
     <<r.pendingReward<<' '<<r.lifeGain<<' '<<r.clockGain<<' '<<r.messageTimer<<' '<<r.wins<<' '<<r.elapsedFrames;
    for(int v:r.mission)o<<' '<<v;
    rowsOut(o,r.rows);
    auto& c=r.table.current;
    o<<' '<<r.table.wins<<' '<<c.stage<<' '<<c.humanSpirit<<' '<<c.character<<' '<<c.colour<<' '<<c.reward<<' '<<c.mission;
    for(int v:r.table.stageHistory)o<<' '<<v;
    for(int v:r.table.defeated)o<<' '<<v;
    for(auto* p:{&r.title,&r.message,&r.legend,&r.extra}) {o<<' '<<p->visible<<' '<<p->open;slide(o,p->slide);}
    o<<' '<<r.messageText<<' '<<r.legendText;
    slide(o,r.selectorSlide);
    o<<' '<<r.cursor<<' '<<r.scroll<<' '<<r.selectorActive<<' '<<r.selectorFocus<<' '<<g.gameSeed<<' '<<g.librarySeed;
}
static void events(std::ostream& o,const SurvivalEvents& e) {
    o<<' '<<e.pauseRequests<<' '<<e.continueFlag<<' '<<e.lifeEffect<<' '<<e.lifeEffectX<<' '<<e.reload<<' '<<e.sounds.size();
    for(int s:e.sounds)o<<' '<<s;
}
static void world(std::ostream& o,const std::array<SurvivalSeatConfig,2>& c,const SurvivalSetup& s) {
    for(auto& v:c)o<<' '<<v.character<<' '<<v.colour<<' '<<v.spiritChosen<<' '<<v.spirit<<' '<<v.arcadeProgress<<' '<<v.roundsToWin<<' '<<v.version;
    o<<' '<<s.level<<' '<<s.stage;
    for(auto* a:{&s.control,&s.character,&s.colour,&s.spirit,&s.rounds})for(int v:*a)o<<' '<<v;
}
int main(int,char** argv) {
    SurvivalAssets assets(argv[1]);
    SystemData data(argv[1]);
    SurvivalRun run(assets);
    GameRandom rng;
    std::array<SurvivalSeatConfig,2> config{};
    SurvivalSetup setup;
    SurvivalSessionFlags flags{};
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);
        std::ostringstream o;
        std::string op;in>>op;
        if(op=="seed") {in>>rng.mode>>rng.gameSeed>>rng.librarySeed;o<<"ok";}
        else if(op=="cfg") {int i;in>>i;auto& c=config[i];in>>c.character>>c.colour>>c.spiritChosen>>c.spirit>>c.arcadeProgress>>c.roundsToWin>>c.version;o<<"ok";}
        else if(op=="setup") {
            in>>setup.level>>setup.stage;
            for(auto* a:{&setup.control,&setup.character,&setup.colour,&setup.spirit,&setup.rounds})for(int& v:*a)in>>v;
            o<<"ok";
        }
        else if(op=="opt") {unsigned at,v;in>>at>>v;data.option(at)=uint8_t(v);o<<"ok";}
        else if(op=="flags") {for(auto& f:flags)in>>f;o<<"ok";}
        else if(op=="tset") {int i,stage,ch;in>>i>>stage>>ch;run.table.stageHistory[i]=int16_t(stage);run.table.defeated[i]=int16_t(ch);o<<"ok";}
        else if(op=="twins") {int n;in>>n;run.table.wins=int16_t(n);o<<run.table.cpuLevel();}
        else if(op=="gen") {
            int n,stage,ch,hc,low;in>>n>>stage>>ch>>hc>>low;bool failed=false;
            o<<run.table.generate(assets,rng,n,stage,ch,hc,low,run.rows,&failed)<<' '<<failed<<' ';dump(o,run,rng);
        }
        else if(op=="reward") {unsigned m;int sp,lt;in>>m>>sp>>lt;o<<survivalReward(assets,m,sp,lt);}
        else if(op=="admit") {
            int m,sp,row;in>>m>>sp>>row;std::array<SurvivalCandidate,3> rows{};
            for(auto& r:rows)in>>r.reward>>r.mission;
            o<<survivalAdmits(assets,m,sp,rows,row);
        }
        else if(op=="pred") {int c;in>>c;o<<survivalUnarmedBoss(c)<<' '<<survivalNoDeflect(c);}
        else if(op=="confirm") {int n,row;in>>n>>row;run.table.confirm(n,run.rows[row]);dump(o,run,rng);}
        else if(op=="apply") {int mode,inPlace;in>>mode>>inPlace;survivalApplyCandidate(run.table,rng,mode,config,setup,inPlace);dump(o,run,rng);world(o,config,setup);}
        else if(op=="begin") {int mode;in>>mode;auto e=run.begin(rng,mode,config[mode==0xb?0:1].character);dump(o,run,rng);events(o,e);}
        else if(op=="tick") {
            int skipped,mode;SurvivalPad pad;SurvivalHuman h;SurvivalBattle b;uint32_t x;
            in>>skipped>>mode>>pad.held>>pad.pressed>>pad.repeat>>h.seat>>h.flags23c>>h.life>>h.lifeA38>>h.word248>>x;
            std::memcpy(&h.x,&x,4);
            for(auto& v:h.events) {unsigned u;in>>u;v=uint8_t(u);}
            in>>b.state>>b.round>>b.winner>>b.clock>>b.finish>>b.special>>b.opponentWins>>b.opponentRequired;
            auto e=run.tick(skipped,pad,h,b,rng,mode,config,setup);
            dump(o,run,rng);events(o,e);
            o<<' '<<h.life;for(int v:h.events)o<<' '<<v;
            o<<' '<<b.clock;world(o,config,setup);
            auto lines=run.hudLines();
            o<<' '<<run.hud.visible<<' '<<run.hud.x<<' '<<run.hud.height<<' '<<run.hud.line<<' '<<lines.size();
            for(auto& l:lines) {o<<' ';for(unsigned char ch:l) {char t[3];std::snprintf(t,3,"%02x",ch);o<<t;}}
        }
        else if(op=="end") {
            int mode,winner,clock;in>>mode>>winner>>clock;
            auto e=survivalMatchEnd(run,rng,data,mode,winner,config,setup,clock,flags);
            o<<e.won<<' '<<e.finished<<' '<<e.cleared<<' '<<e.modeWord<<' '<<e.stage;for(int f:flags)o<<' '<<f;
            o<<' ';dump(o,run,rng);world(o,config,setup);
        }
        else if(op=="carry") o<<run.carriedLife()<<' '<<run.carriedClock()<<' '<<run.playSeconds()<<' '<<run.winCount()<<' '<<run.fading()
                               <<' '<<survivalRoundTicks(run.carriedClock());
        else if(op=="ticks") {int v;in>>v;o<<survivalRoundTicks(v);}
        else if(op=="display") {int v;in>>v;o<<survivalDisplayedClock(v);}
        else if(op=="winner") {int w,life,mode;in>>w>>life>>mode;o<<survivalRoundWinner(w,life,mode);}
        else if(op=="item") {int kind;in>>kind;auto d=survivalItemDrop(rng,kind);o<<d.kind<<' '<<d.side<<' '<<d.where<<' '<<d.nextDelay<<' '<<rng.gameSeed<<' '<<rng.librarySeed;}
        else if(op=="combo") {unsigned best;int combo;in>>best>>combo;o<<unsigned(survivalMaxCombo(uint8_t(best),combo));}
        else if(op=="sflags") {int mode,winner,c,count;in>>mode>>winner>>c>>count;survivalSessionFlags(data,mode,winner,c,count,flags);for(int f:flags)o<<f<<' ';}
        else if(op=="recset") {unsigned i;int wins;uint32_t secs;in>>i>>wins>>secs;data.image()[0x63fc+8*i]=uint8_t(wins);data.setWord(0x6400+8*i,int32_t(secs));o<<"ok";}
        else if(op=="record") {
            int mode,wins,secs;in>>mode>>wins>>secs;survivalStoreRecord(data,mode,config,wins,secs);
            const unsigned i=unsigned(survivalRecordIndex(config[mode==2?1:0]));auto r=survivalRecord(data,i);
            o<<i<<' '<<r.wins<<' '<<r.seconds;
        }
        else if(op=="menu") {int seat;in>>seat;auto m=survivalMenuConfirm(seat);o<<m.modeWord<<' '<<m.seatWord<<' '<<m.roundsToWin<<' '<<m.battleKind<<' '<<m.subMode;}
        else if(op=="select") {
            int mode;in>>mode;auto d=survivalSelectRules(mode);
            o<<d.active<<' '<<d.singleSided<<' '<<d.humanSeat<<' '<<d.recordPanel<<' '<<d.clearExVersions<<' '<<d.spiritPage;
        }
        std::cout<<o.str()<<std::endl;
    }
}
'''

def words(p, at, n, size=4):
    return [signed(p.read(at+size*i, size), size*8) for i in range(n)]

class Oracle:
    def __init__(self):
        self.p = p = Probe(ELF.read_bytes(), finite_model=True)
        buffered_stdout(p)
        self.reent = p.read(0x5d1bf8, 4)
        for at in list(DRAW)+list(FOREIGN):
            p.memory[at:at+8] = RETURN
        for at, value in [(0x4d3d00, B), (0x4d3d04, SETUP), (0x4d3d08, A), (A, O), (A+0xf2c, O+0x1000),
                          (A+0xa24, 0), (A+0xf2c+0xa24, 1), (G+0xa0, 4)]:
            p.write(at, value, 4)
        p.write(0x123a0c0, 2, 1)
        factory = factory_image()
        p.memory[IMAGE:IMAGE+len(factory)] = factory
        p.memory[GS:GS+0x98] = factory[0x618c:0x618c+0x98]
        self.instructions = 0
        self.calls = Counter()
        self.watch = set(DRAW)|set(FOREIGN)|{0x1392e8, 0x13a6c0, 0x316140, 0x1ce478, 0x109de8}
        # Message pointers of 1821f8 and the three legends.
        self.text = {self.run(0x1821f8, 0x22, 7)[0]: -1}
        for key in range(0x31, 0x36):
            self.text[self.run(0x1821f8, key, 0)[0]] = key-0x31
        for r in range(9):
            self.text[self.run(0x1821f8, 0x36, r)[0]] = 5+r
        self.legend = {0x5f2100: 0, 0x5f2118: 1, 0x5f22c0: 2, 0: 2}   # 0: window not built yet
        self.text[0] = -1

    def run(self, pc, *args, limit=400000, stop=(), registers=None):
        p = self.p
        buffered_stdout(p)   # rewind the string-backed stdout
        hits = []
        def observe(at):
            if at in self.watch:
                r = p.registers
                text = ''
                if at == 0x17e228:
                    start = r[4]&0xffffffff
                    text = bytes(p.memory[start:p.memory.index(0, start)]).hex()
                hits.append((at, [signed(r[i], 32) for i in (4, 5, 6, 7, 8)], r[31]&0xffffffff, list(p.floats[12:15]), text))
        for reg, value in (registers or {}).items():
            p.registers[reg] = value
        result, count = p.run(pc, args, limit=limit, stop_before=stop, observe=observe)
        self.instructions += count
        self.calls[hex(pc)] += 1
        assert not any(at in (0x1ce478, 0x109de8) for at, *_ in hits), 'menu background reached'
        return signed(result, 32), hits

    def seed(self, mode, game, library):
        p = self.p
        p.write(0x443150, mode, 4); p.write(0x3d2e80, game, 4); p.write(self.reent+0xa8, library, 8)

    def rng(self):
        return [self.p.read(0x3d2e80, 4), self.p.read(self.reent+0xa8, 8)]

    def slide(self, at):
        return words(self.p, at, 13)

    def dump(self):
        p = self.p
        out = words(p, S, 13)+words(p, S+0x34, 22)+words(p, ROWS, 18)
        out += words(p, T+0x3c, 1, 2)+words(p, T+0x104, 6)+words(p, T+0x3e, 49, 2)+words(p, T+0xa0, 49, 2)
        for base in (0x10, 0x60, 0xac, 0x108):
            out += words(p, WIN+base, 2)+self.slide(WIN+base+0xc)
        out += [self.text[p.read(WIN+0xa8, 4)], self.legend[p.read(WIN+0x104, 4)]]
        out += self.slide(SEL+0x1c)+words(p, SEL+0x64, 1)+words(p, SEL+0x10, 3)
        return out+self.rng()

    def world(self):
        p = self.p
        out = []
        for i in range(2):
            out += [signed(p.read(CFG+0x30*i+off, 4), 32) for off in (0, 4, 8, 0xc, 0x14, 0x20, 0x2c)]
        return out+words(p, SETUP, 12)

    def set_cfg(self, i, values):
        for off, v in zip((0, 4, 8, 0xc, 0x14, 0x20, 0x2c), values):
            self.p.write(CFG+0x30*i+off, v, 4)

class Native:
    def __init__(self, tmp):
        cpp = Path(tmp)/'survival_driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/survival_run.cpp',
                        ROOT/'src/system_data.cpp', ROOT/'src/game_random.cpp', '-o', exe], check=True)
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def ask(self, *parts):
        self.proc.stdin.write(' '.join(str(x) for x in parts)+'\n'); self.proc.stdin.flush()
        return self.proc.stdout.readline().split()
    def ints(self, *parts):
        return [int(x) for x in self.ask(*parts)]
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0

def same(got, want, what):
    if got != want:
        diff = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w][:12]
        raise AssertionError(f'{what}: lengths {len(got)}/{len(want)}, first differences (index, native, original) {diff}')

ORDINARY = [c for c in range(0x28) if c not in (0xb, 0xd, 0x1a, 0x1b)]
HIDDEN = [0x28, 0x29, 0x2a, 0x2c, 0x2d, 0x2e, 0x2f]

def pure_tests(o, n, rng, counts):
    p = o.p
    # 17b9e8 over every mission, spirit and turn; 17ba88 over random earlier rows.
    for m in range(0x19):
        for sp in range(9):
            for lt in (0, 1):
                want, _ = o.run(0x17b9e8, m, sp, lt)
                assert n.ints('reward', m, sp, lt) == [want], (m, sp, lt); counts['whole_17b9e8'] += 1
    for case in range(600):
        m, sp, row = rng.randrange(0x16), rng.randrange(9), rng.randrange(4)
        rows = [(rng.randrange(9), rng.randrange(0x16)) for _ in range(3)]
        for i, (reward, mission) in enumerate(rows):
            p.write(ROWS+0x18*i+0x10, reward, 4); p.write(ROWS+0x18*i+0x14, mission, 4)
        want, _ = o.run(0x17ba88, m, sp, ROWS, row)
        assert n.ints('admit', m, sp, row, *[v for r in rows for v in r]) == [want], case; counts['whole_17ba88'] += 1
    for c in range(-2, 0x36):
        want = [o.run(0x169388, c)[0], o.run(0x1693c0, c)[0]]
        assert n.ints('pred', c) == want, c; counts['whole_169388_1693c0'] += 1
    for wins in range(-3, 0x48):
        p.write(T+0x3c, wins, 2)
        want, _ = o.run(0x17b890)
        assert o.run(0x17b880)[0] == wins
        assert n.ints('twins', wins) == [want], wins; counts['whole_17b890'] += 1
    for v in [-1, 0, 1, 0xff, 0x100, 0x101, 0x459c00, 0x459bff, -0x100, -0x101, -0x1ff, -2]+[rng.randrange(-0x2000, 0x45a000) for _ in range(120)]:
        # 1406e0 whole, 140930 (timer store through 11f450/143228) observed at entry.
        p.write(B+0x13c, 2, 4); p.write(T+0x3c, 1, 2); p.write(S+0x14, v, 4)
        _, hits = o.run(0x1406e0, stop=(0x140930,))
        assert o.run(0x180ec8)[0] == v
        r = p.registers
        assert signed(r[4], 32) == 0 and n.ints('ticks', v) == [signed(r[5], 32)], v; counts['slice_1406e0_to_140930'] += 1
        if v >= 0:
            p.write(B+0x114, v, 4)
            assert n.ints('display', v) == [o.run(0x1407d0)[0]], v; counts['whole_1407d0'] += 1
    # 143f84..143fd4: the round winner once the life comparison is done.
    for case in range(96):
        mode, winner, life = rng.choice((0xb, 0xc)), rng.randrange(2), rng.choice((0, 0, 1, 57, 200, -3))
        p.write(G, mode, 4)
        stack = 0x1fff000
        for seat in range(2):
            p.write(stack+4*seat, A+0xf2c*seat, 4)
            p.write(A+0xf2c*seat+0xa30, life if seat != winner else 120, 4); p.write(A+0xf2c*seat+0xa34, 200, 4)
        o.run(0x143f84, stop=(0x143fd4,), registers={20: winner, 17: (1-winner)*4, 18: B})
        assert n.ints('winner', winner, life, mode) == [signed(p.registers[20], 32)], case
        assert p.registers[16] == p.registers[20]*4; counts['slice_143f84_143fd4'] += 1
    for case in range(64):
        best, combo = rng.randrange(0x70), rng.choice((0, 1, 2, 5, 0x62, 0x63, 0x64, 200))
        want = best if combo == 0 or best >= combo else min(combo, 0x63)
        assert n.ints('combo', best, combo) == [want]
    for seat in (0, 1):
        # 1ccfb8, 111710 and 139280 as called by the SURVIVAL menu row.
        p.write(G, 0, 4); p.write(CFG+0x20, 9, 4); p.write(CFG+0x50, 9, 4); p.write(0x123a0c0, 0, 1)
        o.run(0x1ccfb8, 0xb, 0xc, seat); o.run(0x111710); o.run(0x139280, 2)
        want = [p.read(G, 4), seat ^ 1, p.read(CFG+0x20, 4), p.read(0x123a0c0, 1), 4]
        assert p.read(CFG+0x50, 4) == want[2] and o.run(0x1393a0)[0] == 1
        assert n.ints('menu', seat) == want, seat; counts['menu_confirm'] += 1
    p.write(0x123a0c0, 2, 1); p.write(S+0x14, 0, 4)

def item_tests(o, n, rng, counts):
    p = o.p
    saved = {at: bytes(p.memory[at:at+8]) for at in (0x140fa0, 0x148368, 0x1b5800, 0x140930, 0x1408e0)}
    # 140fa0 (live item census), 1408e0 (timer 3 read), 148368 (position
    # lookup), 1b5800 (item spawn) and 140930 (timer store) are battle
    # services outside this module: inputs fixed to 0, outputs observed.
    for at in saved:
        p.memory[at:at+8] = RETURN
    p.memory[0x148368:0x148370] = struct.pack('<II', 0x03e00008, 0x0080102d)   # jr ra; move v0,a0
    o.watch |= {0x1b5800, 0x140930}
    for case in range(400):
        mode = rng.choice((0, 1))
        seeds = [rng.randrange(1, 1 << 31), rng.getrandbits(64)]
        o.seed(mode, *seeds); n.ask('seed', mode, *seeds)
        stage = rng.randrange(0xe)
        p.write(G, rng.choice((0xb, 0xc)), 4); p.write(B+0x10, stage, 4)
        kind = o.run(0x14ea68, stage)[0]
        _, hits = o.run(0x144f40, B)
        spawn = [h for h in hits if h[0] == 0x1b5800][0][1]
        timer = [h for h in hits if h[0] == 0x140930][0][1]
        same(n.ints('item', kind), [spawn[0], spawn[2], spawn[1], timer[1]]+o.rng(), f'item {case}')
        assert timer[0] == 3; counts['whole_144f40_survival'] += 1
    o.watch -= {0x1b5800, 0x140930}
    for at, code in saved.items():
        p.memory[at:at+8] = code

def generation_tests(o, n, rng, counts):
    p = o.p
    def generate(count, stage, defeated, hc, low, mode, label):
        p.write(G, mode, 4); p.write(CFG+(0 if mode == 0xb else 0x30), hc, 4)
        want, hits = o.run(0x17aca8, count, stage, defeated, ROWS, low)
        failed = int(any(h[0] == 0x316140 for h in hits))
        got = n.ints('gen', count, stage, defeated, hc, low)
        same(got, [want, failed]+o.dump(), label)
        counts['whole_17aca8'] += 1; counts['assertion_paths'] += failed
        return words(p, ROWS, 18)
    humans = ORDINARY+HIDDEN+[0xb, 0xd, 0x1a, 0x1b, 0x2b, 0x30]
    # Consistent runs: every win count 0..31 in order, the defeated
    # character taken from a generated row.
    for trial in range(40):
        rmode = trial % 2
        seeds = [rng.randrange(1, 1 << 31), rng.getrandbits(64)]
        o.seed(rmode, *seeds); n.ask('seed', rmode, *seeds)
        hc, mode = rng.choice(humans), rng.choice((0xb, 0xc))
        stage = character = 0
        for count in range(0x32):
            low = int(rng.random() < 0.3)
            rows = generate(count, stage, character, hc, low, mode, f'run {trial} n {count}')
            pick = rng.randrange(3)
            stage, character = rows[6*pick], rows[6*pick+2]
    # Arbitrary histories: short pools (2, 1 and 0 characters) and the assertion path.
    for trial in range(500):
        rmode = rng.choice((0, 1))
        seeds = [rng.randrange(1, 1 << 31), rng.getrandbits(64)]
        o.seed(rmode, *seeds); n.ask('seed', rmode, *seeds)
        count = rng.choice([c for c in range(1, 0x31) if c not in (9, 0x13, 0x1d, 0x27, 0x2f, 0x30)])
        pool = ORDINARY if count < 0x28 else HIDDEN
        keep = rng.choice((0, 0, 1, 2, 2, 3, 4))
        gone = rng.sample(pool, max(0, len(pool)-keep))
        history = (gone+[rng.randrange(0x33) for _ in range(count)])[:count-1]
        rng.shuffle(history)
        for i, c in enumerate(history):
            st = rng.randrange(0xc)
            p.write(T+0x3e+2*i, st, 2); p.write(T+0xa0+2*i, c, 2); n.ask('tset', i, st, c)
        last = gone[-1] if len(gone) >= count else rng.choice(pool)
        generate(count, rng.randrange(0xc), last, rng.choice(humans), rng.randrange(2), rng.choice((0xb, 0xc)), f'history {trial}')
    # 17b840 and the six accessors.
    for trial in range(24):
        count, row = rng.randrange(0x31), rng.randrange(3)
        o.run(0x17b840, count, ROWS+0x18*row)
        same(n.ints('confirm', count, row), o.dump(), f'confirm {trial}')
        assert [o.run(at)[0] for at in (0x17b988, 0x17b998, 0x17b9a8, 0x17b9b8, 0x17b9c8, 0x17b9d8)] == words(p, ROWS+0x18*row, 6)
        counts['whole_17b840_accessors'] += 1
        # 13a6c0 and the survival branch of 1398c0 with the confirmed row.
        for inplace in (1, 0):
            mode = rng.choice((0xb, 0xc))
            p.write(G, mode, 4)
            seeds = [rng.randrange(1, 1 << 31), rng.getrandbits(64)]
            o.seed(1, *seeds); n.ask('seed', 1, *seeds)
            for i in range(2):
                values = [rng.choice([p.read(T+0x10c, 4), rng.randrange(0x31)]), rng.randrange(5), rng.randrange(8), rng.randrange(9), rng.randrange(9), rng.randrange(1, 4), rng.randrange(2)]
                o.set_cfg(i, values); n.ask('cfg', i, *values)
            p.memory[SETUP:SETUP+0x30] = bytes(0x30); n.ask('setup', *[0]*12)
            for at in (0x123a0cc, 0x123a0d0, 0x123a0d4, 0x50e04c):
                p.write(at, 0, 4)
            _, hits = o.run(0x13a6c0 if inplace else 0x1398c0, *([] if inplace else [SETUP]))
            same(n.ints('apply', mode, inplace), o.dump()+o.world(), f'apply {trial} {inplace}')
            if inplace:
                assert [(h[0], h[1][0]) for h in hits if h[0] in FOREIGN] == [(0x11e3a0, 0xfa1), (0x112a70, 0xfa1)]
                assert [p.read(at, 4) for at in (0x123a0cc, 0x123a0d0, 0x123a0d4, 0x50e04c)] == [1, 1, 1, 1]
            counts['whole_13a6c0' if inplace else 'whole_1398c0_survival'] += 1

def session_tests(o, n, rng, counts):
    p = o.p
    for case in range(300):
        mode, winner = rng.choice((0xb, 0xc, 0xb, 0xc, 1, 3)), rng.randrange(2)
        c, count = rng.choice([0x28, 0x29, 0x2a, 0x2c, 0x2d, 0x2e, 0x2f, 5, 0x2b]), rng.choice((1, 0x30, 0x31, 0x32))
        for off in range(0x3e, 0x47):
            v = rng.randrange(2); p.write(GS+off, v, 1); n.ask('opt', off, v)
        p.memory[FLAGS:FLAGS+0x20] = bytes(0x20); n.ask('flags', *[0]*8)
        p.write(G, mode, 4); p.write(G+8, winner, 4)
        p.write(CFG, c if mode != 0xb else 0, 4); p.write(CFG+0x30, c if mode == 0xb else 0, 4)
        o.run(0x1e3fd0, count)
        same(n.ints('sflags', mode, winner, c, count), words(p, FLAGS, 8), f'session {case}'); counts['whole_1e3fd0'] += 1
    for off in range(0x3e, 0x47):
        p.write(GS+off, 1, 1); n.ask('opt', off, 1)

def record(o, n, mode, counts):
    """1384f8..138610: the survival record update of the Game Over scene."""
    p = o.p
    wins, secs = o.run(0x181488)[0], o.run(0x181468)[0]
    o.run(0x1384f8, stop=(0x138610, 0x138614), registers={16: 0x4c0000, 17: 1})
    seat = 1 if mode == 2 else 0
    index = p.read(CFG+0x30*seat, 4)
    if p.read(CFG+0x30*seat+0x2c, 4) == 1 and 0x16 <= index <= 0x19:
        index += 0x1b
    got = n.ints('record', mode, wins, secs)
    at = IMAGE+0x63fc+8*index
    same(got, [index, signed(p.read(at, 1), 8), p.read(at+4, 4)], 'record'); counts['slice_1384f8_record'] += 1

class Session:
    """One battle scene: the controller ticked against a scripted battle."""
    def __init__(self, o, n, rng, counts):
        self.o, self.n, self.rng, self.counts = o, n, rng, counts
        self.ticks = 0

    def begin(self, mode, hc, version=0):
        o, n, p, rng = self.o, self.n, self.o.p, self.rng
        self.mode, self.seat = mode, 0 if mode == 0xb else 1
        self.human, self.other = A+0xf2c*self.seat, A+0xf2c*(1-self.seat)
        p.write(G, mode, 4)
        for i in range(2):
            values = [hc if i == self.seat else rng.randrange(0x31), rng.randrange(5), rng.randrange(6), rng.randrange(6), 0, 1, version]
            o.set_cfg(i, values); n.ask('cfg', i, *values)
        _, hits = o.run(0x180510)
        o.run(0x17ac98)
        pauses = sum(h[0] == 0x1392e8 for h in hits)
        same(n.ints('begin', mode), o.dump()+[pauses, 0, 0, 0, 0, 0], 'begin'); self.counts['whole_180510'] += 1
        self.skipped = 1
        self.round_reset(first=True)

    def round_reset(self, first=False):
        """The effect of 13fd80/149008 on the fields the controller reads."""
        o, n, p, rng = self.o, self.n, self.o.p, self.rng
        life, clock = o.run(0x180e98)[0], o.run(0x180ec8)[0]
        got = n.ints('carry')
        p.write(B+0x13c, 2, 4)
        o.run(0x1406e0, stop=(0x140930,))
        ticks = signed(p.registers[5], 32)
        same(got, [life, clock, o.run(0x181468)[0], o.run(0x181488)[0], o.run(0x181778)[0], ticks], 'carry')
        self.counts['carry_180e98_180ec8_1406e0'] += 1
        p.write(self.human+0xa30, 200 if life == -1 else life, 4)
        p.write(self.human+0xa38, 0, 4); p.write(self.human+0x23c, 0, 4); p.write(self.human+0x248, 0, 4)
        p.memory[self.human+0xf22:self.human+0xf2b] = bytes(9)
        for seat in range(2):
            stats = B+0x254+0x108*seat
            for off, v in ((0x1c, 0), (0x20, 0), (0x28, 0), (0x2c, 1)):
                p.write(stats+off, v, 4)
        p.write(B, 3, 4); p.write(B+0x18, 0, 4); p.write(B+0x24, -1, 4); p.write(B+0x114, ticks << 8, 4)
        self.fight = 0
        self.length = rng.randrange(8, 90)

    def environment(self, brisk):
        """Mutate the battle the way a running match would, between ticks."""
        p, rng = self.o.p, self.rng
        state = signed(p.read(S, 4), 32)
        if self.skipped or state != 0:
            return
        if p.read(B, 4) == 3:
            if rng.random() < 0.2:
                p.write(B, 4, 4)
            return
        if p.read(B, 4) != 4:
            return
        self.fight += 1
        p.write(B+0x114, max(0, signed(p.read(B+0x114, 4), 32)-rng.choice((0x100, 0x100, 0x4000, 0x20000))), 4)
        h = self.human
        if rng.random() < 0.15:
            p.write(h+0xa30, rng.choice((1, 20, 90, 150, 199, 200, rng.randrange(1, 201))), 4)
        if rng.random() < 0.05:
            p.write(h+0xa38, rng.choice((0, 0, 0, 250)), 4)
        if rng.random() < 0.05:
            p.write(h+0x23c, rng.choice((0, 0, 0x80, 0x7f)), 4)
        if rng.random() < 0.2:
            p.write(h+0x248, p.read(h+0x248, 4) ^ 1 << rng.randrange(15, 26), 4)
        stats = B+0x254+0x108*self.seat
        if rng.random() < 0.1:
            p.write(stats+0x1c, rng.randrange(-1, 5), 4); p.write(stats+0x20, rng.randrange(3), 4)
        for i in range(9):
            if rng.random() < (0.12 if i >= 4 else 0.05):
                p.write(h+0xf22+i, min(0x63, p.read(h+0xf22+i, 1)+rng.choice((1, 1, 2))), 1)
        if rng.random() < 0.2:
            p.write(p.read(h, 4)+0x40, struct.unpack('<I', struct.pack('<f', rng.choice((-200.0, 37.5, 320.0, 611.25, 0.0))))[0], 4)
        if rng.random() < 0.03:
            p.write(B+0x18, rng.randrange(2), 4); p.write(B+0x24, rng.randrange(-1, 2), 4)

    def pad(self, brisk):
        p, rng = self.o.p, self.rng
        state, delay = signed(p.read(S, 4), 32), p.read(S+8, 4)
        pressed = 0
        if rng.random() < (0.5 if brisk else 0.12):
            pressed = rng.choice((0x200, 0x8, 0x2, 0x200, 0x400, 0x4, 0x10, 0x20, 0x40, 0x80, 0x10, 0x20) if not brisk else (0x200, 0x8, 0x2, 0x20, 0x10))
        if rng.random() < 0.03:
            pressed |= rng.choice((0x200, 0x10, 0x20, 0x404, 0x100000))
        repeat = pressed | (rng.choice((0x10, 0x20)) if rng.random() < 0.06 else 0)
        held = pressed | repeat | (rng.choice((0x200, 0x2, 0x400)) if rng.random() < 0.3 else 0)
        return held, pressed, repeat

    def tick(self, brisk=False):
        o, n, p = self.o, self.n, self.o.p
        self.environment(brisk)
        held, pressed, repeat = self.pad(brisk)
        port = 1 if self.mode == 0xc else 0
        assert o.run(0x178f90)[0] == port
        for i, v in enumerate((held, pressed, repeat)):
            p.write(PADS+0xc*port+4*i, v, 4); p.write(PADS+0xc*(1-port)+4*i, 0x20a if i else 0, 4)
        p.write(0x123a0c4, 0, 4); p.write(G+0x2c, 0, 4)
        h, stats, other = self.human, B+0x254+0x108*self.seat, B+0x254+0x108*(1-self.seat)
        line = [self.skipped, self.mode, held, pressed, repeat, self.seat, *words(p, h+0x23c, 1), *words(p, h+0xa30, 1),
                *words(p, h+0xa38, 1), *words(p, h+0x248, 1), p.read(p.read(h, 4)+0x40, 4), *p.memory[h+0xf22:h+0xf2b],
                *words(p, B, 1), *words(p, B+0x18, 1), *words(p, B+0x24, 1), *words(p, B+0x114, 1), *words(p, stats+0x1c, 2),
                *words(p, other+0x28, 2)]
        for at in (0x123a0cc, 0x123a0d0, 0x123a0d4, 0x50e04c):
            p.write(at, 0, 4)
        _, hits = o.run(0x180630, self.skipped)
        self.counts['whole_180630'] += 1; self.ticks += 1
        sounds = [x[1][1] for x in hits if x[0] == 0x1e7b70]
        assert all(x[1][0] == -1 for x in hits if x[0] == 0x1e7b70)
        effect = [x[1] for x in hits if x[0] == 0x1b5b80]
        assert len(effect) < 2 and all(e[0] == 0 and e[2] == 0x50 for e in effect)
        reload = int(any(x[0] == 0x13a6c0 for x in hits))
        order = [x[0] for x in hits if x[0] in (0x1e7df0, 0x1b4e88, 0x1b4d90, 0x13a6c0, 0x11e3a0, 0x112a70)]
        if reload:
            assert order == [0x1e7df0, 0x1b4e88, 0x1b4d90, 0x13a6c0, 0x11e3a0, 0x112a70], order
            place = [x for x in hits if x[0] == 0x1b4e88][0]
            assert place[3] == [0x43a00000, 0, 0x42c80000] and [x[1][:2] for x in hits if x[0] == 0x1b4d90] == [[2, 1]]
            assert [p.read(at, 4) for at in (0x123a0cc, 0x123a0d0, 0x123a0d4, 0x50e04c)] == [1, 1, 1, 1]
            self.counts['reloads'] += 1
        else:
            assert not order
        pauses = sum(x[0] == 0x1392e8 for x in hits)
        assert (pauses > 0) == p.read(0x123a0c4, 4)
        want = o.dump()+[pauses, p.read(G+0x2c, 4), len(effect), effect[0][1] if effect else 0, reload, len(sounds), *sounds]
        want += words(p, h+0xa30, 1)+list(p.memory[h+0xf22:h+0xf2b])+words(p, B+0x114, 1)+o.world()
        # HUD 1810f8: rectangle, colours and texts requested by the draw routine.
        hud = [x for x in hits if 0x1810f8 <= x[2] < 0x181468 and x[0] in (0x1145c0, 0x17db28, 0x17e228)]
        rect = [x[1] for x in hud if x[0] == 0x1145c0]
        fade = [x[1] for x in hits if x[0] == 0x1145c0 and 0x180630 <= x[2] < 0x1807b0]
        level = signed(p.read(S+0xc, 4), 32)
        assert fade == ([[0, 0, 0x280, 0x1c0, signed(level << 24, 32)]] if level > 0 else []), fade
        if rect:
            texts = [x for x in hud if x[0] == 0x17e228]
            colours = [x[1][0] & 0xffffffff for x in hud if x[0] == 0x17db28]
            x0, height = rect[0][0], rect[0][3]
            assert rect[0][1:3] == [0x56, 0x146] and rect[0][4] == signed(0xc0000000, 32) and colours[0] == 0xffffffff
            assert [t[1][1:4] for t in texts] == [[x0+8, 0x5a+0x14*i, 1] for i in range(len(texts))]
            kind = {(): 0, (0xffffff80,): 1, (0xff80ff80,): 2}[tuple(colours[1:])]
            strings = []
            strings = [t[4] for t in texts]   # the sprintf stack buffer, read at the call
            want += [1, x0, height, kind, len(texts)]
            got = n.ask('tick', *line)
            tail = got[len(want):]
            same([int(v) for v in got[:len(want)]], want, f'tick {self.ticks}')
            assert tail == strings, (tail, strings)
            self.counts['hud_frames'] += 1
        else:
            got = n.ask('tick', *line)
            # The HUD word after "visible" (x, height, line) is unspecified when nothing is drawn.
            same([int(v) for v in got[:len(want)+1]], want+[0], f'tick {self.ticks}')
            assert got[-1] == '0'
        self.counts['sounds'] += len(sounds)
        self.counts[f'state_{signed(p.read(S, 4), 32)}_ticks'] += 1
        self.skipped = int(pauses > 0) if self.rng.random() < 0.93 else self.rng.randrange(2)
        if reload:
            self.round_reset()
        return reload

    def finish(self, human_wins):
        """145628 at the end of the single-round match."""
        o, n, p, rng = self.o, self.n, self.o.p, self.rng
        winner = self.seat if human_wins else rng.choice((1-self.seat, 1-self.seat, -1))
        p.write(G+8, winner, 4); p.write(B+0x24, winner, 4); p.write(B, 10, 4); p.write(G+0x34, 0, 4); p.write(G+4, 0x77, 4)
        if not human_wins:
            p.write(B+0x254+0x108*(1-self.seat)+0x28, 1, 4)
        for i in range(2):
            p.write(CFG+0x30*i+0x14, 5, 4)
        world = o.world()
        n.ask('cfg', 0, *world[:7]); n.ask('cfg', 1, *world[7:14])
        p.memory[FLAGS:FLAGS+0x20] = bytes(0x20); n.ask('flags', *[0]*8)
        clock = signed(p.read(B+0x114, 4), 32)
        _, hits = o.run(0x145628, B+0x2c)
        switch = [x[1][:4] for x in hits if x[0] == 0x1252f0]
        finished = int(bool(switch))
        if finished:
            assert switch == [[2, 0, 0x139778, 0x138340]]
        won = int(human_wins)
        want = [won, finished, p.read(G+0x34, 4), p.read(G, 4), p.read(G+4, 4) if finished else 0, *words(p, FLAGS, 8)]
        same(n.ints('end', self.mode, winner, clock), want+o.dump()+o.world(), 'match end')
        assert p.read(0x4c38ac, 4) == 0 and p.read(G+0xa0, 4) == 4
        self.counts['whole_145628_survival'] += 1
        if finished:
            self.counts['runs_cleared' if p.read(G+0x34, 4) else 'runs_lost'] += 1
            record(o, n, p.read(G, 4), self.counts)
        return finished

    def play(self, target, brisk):
        """Run until `target` wins followed by a loss, or until the run is cleared."""
        p, rng = self.o.p, self.rng
        while True:
            self.tick(brisk)
            state, delay = signed(p.read(S, 4), 32), p.read(S+8, 4)
            if state == 0 and delay == 0 and p.read(B, 4) == 4 and self.fight >= self.length:
                wins = signed(p.read(T+0x3c, 2), 16)
                if self.finish(wins < target):
                    return wins
                # The battle now idles in its ending states until the reload.
                p.write(B, rng.choice((5, 7, 8, 10)), 4)

def controller_tests(o, n, rng, counts):
    plan = [(0xb, 0x31, True), (0xc, 0x31, True)]+[(rng.choice((0xb, 0xc)), rng.choice((0, 1, 2, 3, 5, 8, 11, 14)), False) for _ in range(16)]
    reached = []
    for index, (mode, target, brisk) in enumerate(plan):
        seeds = [rng.randrange(1, 1 << 31), rng.getrandbits(64)]
        rmode = index % 2
        o.seed(rmode, *seeds); n.ask('seed', rmode, *seeds)
        session = Session(o, n, rng, counts)
        hc = rng.choice(ORDINARY+ORDINARY+HIDDEN+[0x2b, 0x30, 0x16, 0x17])
        session.begin(mode, hc, version=rng.randrange(2))
        reached.append(session.play(target, brisk))
        counts['sessions'] += 1
    return reached

def main():
    rng = random.Random(0x180630)
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == SOURCE_HASH
    data = extract_survival_run.build()[0]
    assert (ASSETS/'survival_run.bin').read_bytes() == data, 'run extract_survival_run.py first'
    counts = Counter()
    o = Oracle()
    with tempfile.TemporaryDirectory() as tmp:
        n = Native(tmp)
        pure_tests(o, n, rng, counts)
        item_tests(o, n, rng, counts)
        session_tests(o, n, rng, counts)
        generation_tests(o, n, rng, counts)
        reached = controller_tests(o, n, rng, counts)
        n.close()
    report = dict(status='passed', elf_sha256=SOURCE_HASH, asset_sha256=hashlib.sha256(data).hexdigest(),
                  native_sha256={f: hashlib.sha256((ROOT/'src'/f).read_bytes()).hexdigest() for f in ('survival_run.hpp', 'survival_run.cpp')},
                  counts=dict(sorted(counts.items())), wins_reached=reached, original_calls=dict(sorted(o.calls.items())),
                  original_instructions=o.instructions,
                  stubbed={hex(k): v for k, v in sorted({**DRAW, **FOREIGN}.items())},
                  scope='Whole 17aca8/17b9e8/17ba88/17b890/17b840/13a6c0/1398c0(survival)/1e3fd0/180510/180630/145628(survival) with '
                        'real callees (17f3xx slides, 1822a0..1827c0 window, 211c30/211d48/20e128 selector, 1815f0, 180ef8, 180fd0, '
                        '181498, 1810f8 with libc sprintf, 180e28). Replaced by a bare return: window/selector/rectangle/text draw '
                        'callees, sound request 1e7b70 and sound stop 1e7df0, effect spawn 1b5b80, kernel logger 323050, scene '
                        'switch 1252f0; recorded as events: stage-event 1b4e88/1b4d90 and tag release 11e3a0/112a70. The battle '
                        '(actor, statistics, clock, round state) is a scripted memory fixture, not the original 140270 update. '
                        '1406e0 stops before 140930; 143f84..143fd4 and 1384f8..138610 are explicit slices; 144f40 runs whole with '
                        '140fa0, 1408e0, 148368, 1b5800 and 140930 replaced. The 211e18 selector rows are not compared as draws.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'counts', 'wins_reached', 'original_instructions')}))

if __name__ == '__main__':main()
