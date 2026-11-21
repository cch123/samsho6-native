#!/usr/bin/env python3
"""Compare the native arcade schedule, run flow, Continue, Game Over and name entry with SLPS-25559."""
from collections import Counter
import json
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from mips_probe import Probe, signed
from round_entry_oracle import buffered_stdout
from validate_dash_motion import ELF, PIN, ROOT, digest
from extract_arcade_run import NAME as TABLES

ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/arcade_run_validation.json'
G, P, S, T, O, PAD = 0x4c3808, 0x456890, 0x12d3668, 0x1239da0, 0x43d058, 0x1237cc8
HANDLE, OBJECT, PARAM, TASK, POOL = 0x1d00000, 0x1d10000, 0x1d20000, 0x1d30000, 0x4c8690
SCENE = (0x5823ac, 0x582398, 0x582528, 0x582444, 0x582448, 0x582238)
ENTRY = (0x133f7c0, 0x133f7c4, 0x133f7c8, 0x133f7cc, 0x582a4c, 0x582a50, 0x582a54, 0x582a58,
         0x582a5c, 0x582a60, 0x582a64, 0x582a68)
OPENING, MAP, DIALOGUE, PREFINAL, BATTLE, QUOTE, RESULT = 0x1c60c8, 0x1c1b20, 0x1c5290, 0x1c6cc0, 0x139760, 0x135e30, 0x136a60
SELECT, CONTINUE, GAMEOVER, ENDING, RANKING, UNLOCK = 0x128008, 0x1376d0, 0x138340, 0x182968, 0x1e8850, 0x1e5d88
RETURN_ZERO = struct.pack('<II', 0x03e00008, 0x0000102d)
RETURN_OBJECT = struct.pack('<II', 0x03e00008, 0x3c020000 | OBJECT >> 16)
# Probe has no MMI PSUBW, which the word-wise C library strcmp 31806c uses.
# 110bf8 (name filter) is run against this byte-wise routine of the same contract.
STRCMP = struct.pack('<11I', 0x90880000, 0x90a90000, 0x24840001, 0x15090005, 0x24a50001, 0x1500fffa, 0,
                     0x03e00008, 0x0000102d, 0x03e00008, 0x01091023)
# Rendering, object animation, camera, texture/disc loading, sound driver,
# memory card, debug print and the entry of a successor scene.
STUBS = dict(render=(0x117de8, 0x1148f0, 0x1135e8, 0x1132c0), objects=(0x11e3a0, 0x11d528, 0x11d570, 0x11d908,
             0x11d6c8, 0x11d868, 0x11d730), camera=(0x122e98, 0x122eb8), loading=(0x1142d8, 0x10add8, 0x1a4a98, 0x11d488),
             sound=(0x1e7c00, 0x1e7b70, 0x1e7d60, 0x1e7ad0, 0x1e7b40, 0x1e7af8), memory_card=(0x10f158,),
             debug_print=(0x323050, 0x316140), successor_scene=(UNLOCK,))
DRIVER = r'''
#include "arcade_run.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
#include <vector>
using namespace ss6;
int main(int,char** argv) {
    std::ifstream file(std::string(argv[1])+"/arcade_run.bin",std::ios::binary);
    const std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)),{});
    const ArcadeTables tables(bytes);
    SystemData system(argv[1]);GameRandom rng;ArcadeRun run(tables,system,rng);
    ArcadeCountdown countdown;ArcadeContinue cont;ArcadeGameOver over;ArcadeNameEntry entry;
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);std::string op;in>>op;
        std::vector<long long> a;for(long long v;in>>v;)a.push_back(v);
        std::vector<long long> extra;
        auto words=[](auto& object) {return reinterpret_cast<int32_t*>(&object);};
        if(op=="g")words(run.game)[a[0]]=int32_t(a[1]);
        else if(op=="p")words(run.players[a[0]])[a[1]]=int32_t(a[2]);
        else if(op=="o")system.option(a[0])=uint8_t(a[1]);
        else if(op=="c")run.versusCounters[a[0]/2][a[0]%2]=int32_t(a[1]);
        else if(op=="r")rng={int32_t(a[0]),uint32_t(a[1]),uint64_t(a[2])};
        else if(op=="s")(a[0]==0?run.intruderFight:a[0]==1?run.mapStageIndex:a[0]==2?run.dialoguePostFight:
                         a[0]==3?run.startHoldCounter:a[0]==4?run.startHoldFlag:a[0]==5?run.scoreShadow:run.rankingHighlight)=int32_t(a[1]);
        else if(op=="build")run.buildSchedule(int(a[0]),a[1]!=0,uint32_t(a[2]));
        else if(op=="prep")run.prepareFight();
        else if(op=="confirm")run.confirmMenu(unsigned(a[0]));
        else if(op=="selexit")run.selectExit(uint32_t(a[0]));
        else if(op=="setup") {
            const auto b=run.battleSetup(int(a[0]));
            extra={b.stageIndex,b.stage,b.control[0],b.control[1],b.character[0],b.character[1],b.colour[0],b.colour[1],
                   b.spirit[0],b.spirit[1],b.roundWins[0],b.roundWins[1]};
        }
        else if(op=="end")run.matchEnd(int(a[0]));
        else if(op=="wq")run.winQuoteExit(uint32_t(a[0]));
        else if(op=="vr")run.versusResultExit(uint32_t(a[0]));
        else if(op=="poll")extra={run.pollChallenger({uint32_t(a[0]),uint32_t(a[1])},uint32_t(a[2]))};
        else if(op=="idle")run.idleRandom();
        else if(op=="mid") {std::vector<int32_t> pool(a.begin(),a.end());run.transitionMidpoint(pool);}
        else if(op=="fin")run.transitionFinished();
        else if(op=="roundwin")run.addRoundWin(int(a[0]),int(a[1]));
        else if(op=="special")run.disableSpecialOpponents();
        else if(op=="versus")run.recordVersus();
        else if(op=="query")extra={run.opponentAt(int(a[0])),run.intruderDue(),run.versusLimitReached(),run.scoreQualifies()};
        else if(op=="stage")extra={run.stageAt(int(a[0]))};
        else if(op=="cinit")countdown={};
        else if(op=="center") {cont.enter(run,countdown);extra={cont.draw.loserSeat,cont.draw.loserCharacter,cont.draw.loserColour,cont.music};}
        else if(op=="ctick") {
            countdown.tick();
            const int sound=cont.tick(run,countdown,{uint32_t(a[0]),uint32_t(a[1])});
            extra={sound,cont.fadeRequested,cont.draw.frame,cont.draw.remaining};
        }
        else if(op=="cleave")cont.leave(run);
        else if(op=="genter") {over.enter(run);extra={over.draw.loserSeat,over.draw.loserCharacter,over.draw.stageBackground,over.music};}
        else if(op=="gtick") {
            const auto next=over.tick(run,uint32_t(a[0]),a[1]!=0);
            extra={uint32_t(next),over.fadeRequested,over.voiceRequested,over.soundStopped,over.autosave,over.draw.frame};
        }
        else if(op=="gleave")ArcadeGameOver::leave(run,a[0]!=0);
        else if(op=="ninit")entry={};
        else if(op=="nbegin")extra={entry.begin(run)};
        else if(op=="ntick")extra={entry.tick(run,uint32_t(a[0]))};
        else if(op=="score") {
            const char name[4]={char(a[1]),char(a[2]),char(a[3]),0};
            run.recordScore(unsigned(a[0]),name);
        }
        else return 2;
        std::ostringstream out;
        auto put=[&](long long v) {out<<v<<' ';};
        for(int i=0;i<42;++i)put(words(run.game)[i]);
        for(auto& p:run.players)for(int i=0;i<12;++i)put(words(p)[i]);
        const auto& s=run.schedule;
        for(auto v:s.stages)put(v);for(auto v:s.opponents)put(v);for(auto v:s.rolls)put(v);
        for(auto v:s.bonus)put(v);for(auto v:s.wins)put(v);
        put(s.intruderDisabled);put(s.substitutionDisabled);put(s.word11c);put(s.word11e);
        for(auto v:s.characterRolls)put(v);for(auto v:s.characterOrder)put(v);
        for(auto v:{run.intruderFight,run.mapStageIndex,run.dialoguePostFight,run.startHoldCounter,run.startHoldFlag,
                    run.scoreShadow,int32_t(run.battleKind),run.rankingHighlight})put(v);
        put(run.transition.kind);put(run.transition.speed);put(run.transition.destructor);put(uint32_t(run.transition.next));
        put(rng.mode);put(rng.gameSeed);out<<rng.librarySeed<<' ';
        for(auto& seat:run.versusCounters)for(auto v:seat)put(v);
        const auto image=system.image();
        for(int i=0;i<5;++i) {const auto at=SystemData::ranking+8*i;put(uint32_t(system.word(at)));put(image[at+4]);put(image[at+5]);}
        for(int i=0;i<20;++i) {
            const auto at=SystemData::ranking+0x28+12*i;put(uint32_t(system.word(at)));
            for(int k:{4,5,6,7,9})put(image[at+k]);
        }
        put(countdown.count);put(countdown.paused);put(countdown.limit);put(countdown.delay);
        put(cont.frame);put(cont.accepted);put(cont.latch);put(cont.entryMode);put(over.frame);
        for(char c:entry.name)put(uint8_t(c));
        for(auto v:{entry.glyph,entry.cursor,entry.seconds,entry.secondFrame,entry.blinkShown,entry.erase,entry.blinkOn,
                    entry.blinkCounter,entry.finished,entry.commitFrames,entry.filtered,int32_t(entry.active)})put(v);
        for(auto v:extra)put(v);
        std::cout<<out.str()<<std::endl;
    }
}
'''

def s32(v): return signed(v, 32)

class Oracle:
    """The original functions in Probe plus the native driver, compared after every operation."""
    def __init__(self, exe):
        self.p = p = Probe(ELF.read_bytes(), finite_model=True)
        buffered_stdout(p)
        for group in STUBS.values():
            for at in group: p.memory[at:at+8] = RETURN_ZERO
        p.memory[0x11e2e8:0x11e2f0] = RETURN_OBJECT  # object allocation for the loser sprite
        p.memory[0x31806c:0x31806c+len(STRCMP)] = STRCMP
        for a, v in ((T-8, HANDLE), (0x3ec73c, 1), (0x43d064, 256), (0x32ce08, 1), (0x3a9c20, 0x1a00000), (0x443150, 1)):
            p.write(a, v, 4)
        image = (ASSETS/'save_default.bin').read_bytes()
        p.memory[O:O+0x98] = image[0x618c:0x618c+0x98]
        p.memory[0x43d0f0:0x43d0f0+0x118] = image[0x6224:0x6224+0x118]
        self.reent = p.read(0x5d1bf8, 4)
        self.calls = Counter(); self.instructions = 0; self.checks = Counter(); self.events = []; self.cover = Counter()
        self.native = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.run(0x112570); self.run(0x124d50); self.run(0x127eb0); self.run(0x1c98a0)
        self.send('cinit'); self.send('ninit')
        self.scene(6, s32(p.read(0x582450, 4)))
        self.rng(1, 1, p.read(self.reent+0xa8, 8))
        self.check('init')

    def close(self):
        self.native.stdin.close(); assert self.native.wait() == 0

    # --- plumbing ---
    def run(self, pc, *args, stop=None, limit=400000):
        self.events = []
        p = self.p
        def observe(at):
            if at in (0x1e7b70, 0x1e7c00, 0x1e7d60, 0x1e7b40, 0x1170d8, 0x10f158, UNLOCK, 0x11d488, 0x1a4a98, 0x137d20,
                      0x138af0, 0x1389ac, 0x138a78, 0x137db8, 0x316b90):
                self.events.append((at, s32(p.registers[4]), s32(p.registers[5]), p.registers[31] & 0xffffffff,
                                    s32(p.registers[2]), self.remaining()))
        value, count = p.run(pc, args, limit=limit, stop_before=(stop,) if stop else (), observe=observe)
        self.calls[hex(pc)] += 1; self.instructions += count
        return value

    def seen(self, pc): return [e for e in self.events if e[0] == pc]
    def send(self, *command):
        self.native.stdin.write(' '.join(map(str, command))+'\n'); self.native.stdin.flush()
        self.last = list(map(int, self.native.stdout.readline().split()))
    def w(self, at): return s32(self.p.read(at, 4))
    def remaining(self): return (self.p.read(0x4c8288, 4)-self.p.read(0x4c8280, 4)) & 0xffffffff

    def state(self):
        p = self.p; h = lambda at: signed(p.read(at, 2), 16)
        row = [self.w(G+4*i) for i in range(42)]+[self.w(P+4*i) for i in range(24)]
        row += [h(S+2*i) for i in range(7)]+[h(S+0xe+2*i) for i in range(7)]
        row += [p.read(S+off+i, 1) for off in (0x1c, 0x23, 0x2a) for i in range(7)]
        row += [self.w(S+0x34), self.w(S+0x38), h(S+0x11c), h(S+0x11e)]
        row += [h(S+0x120+2*i) for i in range(49)]+[h(S+0x182+2*i) for i in range(49)]
        row += [self.w(a) for a in SCENE]+[p.read(0x123a0c0, 1), self.w(0x582450)]
        row += [self.w(T), self.w(T+0xc), p.read(T+0x10, 4), p.read(T+0x14, 4)]
        row += [self.w(0x443150), p.read(0x3d2e80, 4), p.read(self.reent+0xa8, 8)]
        row += [self.w(0x4c37f8+4*i) for i in range(4)]
        # Bytes 6..7 of a streak row and the tail of a score row are copied
        # from uninitialised stack words by 1c4f80/1c5150; only fields compare.
        for i in range(5): row += [p.read(0x43d0f0+8*i, 4), p.read(0x43d0f4+8*i, 1), p.read(0x43d0f5+8*i, 1)]
        for i in range(20):
            at = 0x43d118+12*i; name = bytes(p.memory[at+5:at+8]); name = name[:name.index(0)] if 0 in name else name
            row += [p.read(at, 4), p.read(at+4, 1), *name.ljust(3, b'\0'), p.read(at+9, 1)]
        row += [p.read(0x4c8280+4*i, 4) for i in range(4)]+[self.w(0x4ca1f4+4*i) for i in range(4)]+[self.w(0x4ca204)]
        row += list(p.memory[0x133f7d0:0x133f7d4])+[self.w(a) for a in ENTRY]
        return row

    def check(self, label, extra=()):
        want = self.state()+[int(v) for v in extra]
        assert self.last == want, (label, [(i, a, b) for i, (a, b) in enumerate(zip(self.last, want)) if a != b][:8],
                                   len(self.last), len(want))
        self.checks[label] += 1
        p = self.p
        if label.startswith(('match_end', 'win_quote', 'versus_result', 'select_exit', 'continue_tick', 'game_over_tick')) and p.read(T+4, 4) == 1:
            self.cover[f'{label}: kind {self.w(T)} -> {p.read(T+0x14, 4):x}'] += 1
        if label.startswith('battle_setup'):
            cpu = self.w(P+0x30*(self.human() ^ 1)) if self.mode() in (1, 2) else -1
            self.cover['fight mode %d' % self.mode()] += 1
            for name, hit in (('intruder 33 fight', self.w(0x5823ac) == 1 and cpu == 33), ('Kuroko 48 fight', cpu == 48),
                              ('final 43 fight', cpu == 43), ('boss slot fight', self.mode() in (1, 2) and self.player(self.human(), 5) == 6)):
                self.cover[name] += int(hit)

    # --- fixtures applied to both sides ---
    def g(self, index, value): self.p.write(G+4*index, value, 4); self.send('g', index, value)
    def pl(self, seat, index, value): self.p.write(P+0x30*seat+4*index, value, 4); self.send('p', seat, index, value)
    def option(self, offset, value): self.p.write(O+offset, value, 1); self.send('o', offset, value)
    def scene(self, index, value):
        self.p.write((*SCENE, 0x582450)[index], value, 4); self.send('s', index, value)
    def rng(self, mode, seed, library):
        p = self.p; p.write(0x443150, mode, 4); p.write(0x3d2e80, seed, 4); p.write(self.reent+0xa8, library, 8)
        self.send('r', mode, seed, library)
    def pads(self, held=(0, 0), pressed=(0, 0)):
        for seat in (0, 1):
            self.p.write(PAD+12*seat, held[seat], 4); self.p.write(PAD+12*seat+4, pressed[seat], 4)
    def mode(self): return self.w(G)
    def human(self): return int(self.mode() == 2)
    def player(self, seat, index): return self.w(P+0x30*seat+4*index)
    def target(self): return self.p.read(T+0x14, 4)

    # --- operations: original first, then the native command with observed inputs ---
    def build(self, character, reroll, held):
        self.pads(held=held); self.run(0x17a2c8, character, reroll)
        self.send('build', character, reroll, held[self.human()]); self.check('schedule_17a2c8')
    def prep(self):
        self.run(0x1c2420); self.send('prep'); self.check('prepare_1c2420')
    def confirm(self, seat):
        # 1ccfd0 item 0, composed from its callees in the original order.
        p = self.p
        self.run(0x1252f0, 1, 0, 0x127d70, SELECT); self.run(0x1ccfb8, seat+1, 0, 0); self.run(0x139280, 0)
        p.write(G+0xa0, 1, 4); self.run(0x111508)
        self.send('confirm', seat); self.check('menu_confirm')
    def selexit(self, held):
        p = self.p; self.pads(held=held)
        for at in (0x4c8d10, 0x4c8d88, 0x4c8d8c): p.write(at, 0, 4)
        p.put(17, 0x4d0000)
        p.write(T+4, 0, 4)
        self.run(0x12f124, stop=0x12f204); assert p.read(0x4c8d10, 4) == 1
        self.send('selexit', held[self.human()]); self.check('select_exit_12f124')
        return self.target()
    def setup(self):
        p = self.p; p.memory[PARAM:PARAM+0x30] = bytes(0x30)
        self.run(0x1398c0, PARAM)
        self.send('setup', 10); self.check('battle_setup_1398c0', [self.w(PARAM+4*i) for i in range(12)])
    def end(self, bonus):
        self.p.write(T+4, 0, 4)
        self.run(0x145628, bonus)
        self.send('end', bonus); self.check('match_end_145628')
        return self.target()
    def wq(self, held):
        self.pads(held=held); self.p.write(T+4, 0, 4); self.run(0x1362d8); self.send('wq', held[self.human()]); self.check('win_quote_exit_1362d8')
        return self.target()
    def vr(self, held):
        self.pads(held=held); self.p.write(T+4, 0, 4); self.run(0x136fc8); self.send('vr', held[self.human()]); self.check('versus_result_exit_136fc8')
        return self.target()
    def poll(self, pressed, destructor):
        p = self.p; self.pads(pressed=pressed); p.write(0x43d20c, destructor, 4)
        before = (self.w(T), p.read(T+0x10, 4), self.w(G+0x18))
        self.run(0x118188, stop=0x11822c)
        started = self.w(G+0x18) == 1 and before[2] == 0
        self.send('poll', *pressed, destructor); self.check('challenger_poll_118188', [started])
        return started
    def idle(self):
        self.run(0x118298); self.send('idle'); self.check('frame_random_118298')
    def mid(self, pool):
        p = self.p; other = self.w(G+0x10) ^ 1
        if other in (0, 1):
            p.write(0x4c8830+4*other, len(pool), 4)
            for i, c in enumerate(pool): p.write(POOL+0xd0*other+4*i, c, 4)
        self.run(0x1253e0); self.send('mid', *pool); self.check('transition_midpoint_1253e0')
    def fin(self):
        # Tail of 1251d0 state 3 (1252e4/1252ec), applied as a fixture.
        self.g(0x94//4, 0); self.g(0x2c//4, 0)
    def roundwin(self, index, amount):
        self.run(0x17a718, index, amount); self.send('roundwin', index, amount); self.check('round_win_17a718')
    def special(self):
        self.run(0x17a5f0); self.run(0x17a708); self.send('special'); self.check('disable_17a5f0_17a708')
    def versus(self):
        self.run(0x124da0); self.send('versus'); self.check('versus_record_124da0')
    def query(self, index):
        got = [s32(self.run(0x17a350, index)), self.run(0x17a548), self.run(0x124f98),
               int(self.run(0x1c4e38, self.w(G+0x90)) != 0)]
        self.send('query', index); self.check('accessors', got)
        got = [s32(self.run(0x17a410, index))]
        self.send('stage', index); self.check('stage_17a410', got)

    def center(self):
        p = self.p; self.run(0x112570); p.write(OBJECT+0x20, -1, 4)
        self.run(0x1376d0, limit=2000000)
        loaded = self.seen(0x11d488); music = self.seen(0x1e7c00)
        extra = [loaded[0][1], loaded[0][2], self.w(OBJECT+0x20)] if loaded else [-1, 0, 0]
        self.send('center'); self.check('continue_enter_1376d0', extra+[music[0][1]])
    def ctick(self, pressed):
        p = self.p; self.pads(pressed=pressed); p.write(T+4, 0, 4)
        self.run(0x127f00); self.run(0x137978)
        sound = [e[2] for e in self.seen(0x1e7b70)]
        assert all(e[1] == -1 for e in self.seen(0x1e7b70)) and len(sound) <= 1
        fade = any(e[3] == 0x137a60 for e in self.seen(0x1170d8))
        frame = self.seen(0x137d20)[0][1]; shown = self.seen(0x137db8)[0][5]
        requested = p.read(T+0x14, 4) if p.read(T+4, 4) == 1 else 0
        self.send('ctick', *pressed); self.check('continue_tick_137978', [sound[0] if sound else -1, fade, frame, shown])
        return requested
    def cleave(self):
        self.run(0x137c68); self.send('cleave'); self.check('continue_leave_137c68')
    def genter(self):
        self.run(0x112570)
        self.run(0x138340, limit=2000000)
        loaded = self.seen(0x11d488); music = self.seen(0x1e7c00)
        extra = [loaded[0][1], loaded[0][2]] if loaded else [-1, 0]
        self.send('genter'); self.check('game_over_enter_138340', extra+[len(self.seen(0x1a4a98)), music[0][1]])
    def gtick(self, pressed):
        p = self.p; seat = (self.w(G+0x10) if self.mode() == 3 else self.w(G+8)) ^ 1
        self.pads(pressed=[pressed if s == seat else 0 for s in (0, 1)])
        # 118128((g+8)^1) with g+8 == -1 addresses the words before the pad table.
        pressed = p.read(PAD+12*seat+4, 4)
        p.write(T+4, 0, 4)
        self.run(0x1387b8, limit=2000000)
        unlock = self.seen(0x1389ac); pending = int(bool(unlock) and unlock[0][4] == 1)
        fade = any(e[3] in (0x13886c, 0x138e40) for e in self.seen(0x1170d8))
        voice = self.seen(0x1e7d60); assert all(e[1:3] == (0x31, 0x4b) for e in voice)
        stopped = any(e[3] == 0x138854 or e[3] == 0x138a34 for e in self.seen(0x1e7b40))
        nxt = UNLOCK if self.seen(UNLOCK) else p.read(T+0x14, 4) if p.read(T+4, 4) == 1 else 0
        self.send('gtick', pressed, pending)
        self.check('game_over_tick_1387b8', [nxt, fade, bool(voice), stopped, bool(self.seen(0x10f158)), self.seen(0x138af0)[0][1]])
        return nxt
    def gleave(self):
        self.run(0x138a48, limit=2000000); pending = self.seen(0x138a78)[0][4]
        self.send('gleave', pending); self.check('game_over_leave_138a48')
    def nbegin(self):
        p = self.p; self.run(0x112570); assert p.read(0x582a68, 4) == 0
        self.run(0x1c9830)
        started = p.read(0x582a68, 4) == 1
        self.send('nbegin'); self.check('name_entry_begin_1c9830', [started])
        return started
    def ntick(self, pressed):
        p = self.p; self.pads(pressed=[pressed if s == self.human() else 0 for s in (0, 1)]); p.write(TASK+4, 0x10, 4)
        self.run(0x1c9928, TASK, limit=2000000)
        done = p.read(TASK+4, 4) == 0x12
        self.send('ntick', pressed); self.check('name_entry_tick_1c9928', [done])
        return done


CHARACTERS = [c for c in range(41) if c != 33]+[44, 45, 46, 47, 48]
HELD = (0, 0, 0, 0x10, 0x20, 0x40, 0x80, 0x30, 0xf0)

def schedules(o, rng, quick):
    """Whole 17a2c8 over every table key, unknown keys, all RNG modes and held directions."""
    keys = list(range(52))+[60, -1]
    for round_ in range(1 if quick else 6):
        for character in keys:
            mode = (1, 1, 0, -2, 5)[rng.randrange(5)]
            o.rng(mode, rng.randrange(1, 2**31), rng.getrandbits(63))
            o.g(0, rng.choice((1, 2))); o.g(0xa0//4, 1)
            held = [rng.choice(HELD), rng.choice(HELD)]
            o.build(character, rng.randrange(2) if round_ else 1, held)
            for seat in (0, 1): o.pl(seat, 5, rng.randrange(9)); o.pl(seat, 8, rng.randrange(1, 4))
            if rng.randrange(3) == 0: o.roundwin(rng.randrange(0, 9), rng.randrange(1, 4))
            for index in (-2, -1, *range(8)): o.query(index)
            o.prep()

def select_human(o, rng, seat, fresh):
    c = rng.choice(CHARACTERS)
    if not fresh and rng.randrange(2): c = o.player(seat, 0)
    for index, value in ((0, c), (1, rng.randrange(5)), (2, rng.randrange(6)), (3, rng.randrange(6)), (4, 1),
                         (9, int(rng.randrange(5) == 0))):
        o.pl(seat, index, value)

def challenge(o, rng, destructor):
    """Other seat's START during an arcade scene; returns True when mode 3 was entered."""
    seat = o.human() ^ 1; pressed = [0, 0]; pressed[seat] = rng.choice((8, 8, 0x208, 2)); pressed[seat ^ 1] = rng.choice((0, 8))
    if not o.poll(pressed, destructor): return False
    o.mid([rng.choice(CHARACTERS) for _ in range(rng.randrange(1, 40))]); o.fin()
    select_human(o, rng, seat, True)
    return True

def walk(o, rng, steps):
    """Random arcade session following the destinations requested by the original."""
    visits = Counter(); state = 'menu'; held = [0, 0]
    for step in range(steps):
        visits[state] += 1
        if rng.randrange(7) == 0: o.idle()
        if state == 'menu':
            o.rng(rng.choice((1, 1, 1, 0)), rng.randrange(1, 2**31), rng.getrandbits(63))
            for offset, value in ((0, int(rng.randrange(6) == 0)), (1, rng.choice((0, 0, 1, 2))), (2, int(rng.randrange(25) == 0)),
                                  (7, rng.randrange(15)), (8, rng.randrange(1, 6))):
                o.option(offset, value)
            o.g(0x34//4, 0); o.g(0x1c//4, 0)
            seat = rng.randrange(2); o.confirm(seat); o.fin(); select_human(o, rng, seat, True); state = 'select'
        elif state == 'select':
            held = [rng.choice(HELD), rng.choice(HELD)]
            if o.mode() == 3: o.fin(); state = 'battle'; continue   # 125e10 faceoff is ported elsewhere
            if rng.randrange(8) == 0 and challenge(o, rng, 0x129110): continue
            state = {OPENING: 'opening', MAP: 'map', BATTLE: 'battle'}[o.selexit(held)]; o.fin()
        elif state == 'opening':
            # 1c6328 and 1c2420 of the opening entry; +18 = 1 at its hand-off.
            h = o.human(); o.build(o.player(h, 0), 1, held); o.g(0x98//4, 1); o.prep(); o.pl(h, 6, 1); state = 'map'
        elif state == 'map':
            h = o.human()
            if o.player(h, 6) != 1: o.prep()
            o.pl(h, 6, 2)
            if rng.randrange(6) == 0 and challenge(o, rng, 0x1c1de8): state = 'select'; continue
            state = 'battle'   # walk-in and the pre-fight dialogue change no run state
        elif state == 'prefinal':
            o.prep(); o.pl(0, 7, 1); o.pl(1, 7, 1); state = 'battle'
        elif state == 'battle':
            o.fin(); o.setup(); mode = o.mode()
            if mode == 3:
                o.g(2, rng.choice((0, 0, 1, 1, -1)))
            else:
                h = mode-1; index = o.player(h, 5)
                if rng.randrange(8) == 0 and challenge(o, rng, 0x139778): state = 'select'; continue
                won = rng.randrange(100) < 78
                for _ in range(rng.randrange(0, 4) if won else rng.randrange(0, 2)): o.roundwin(index, 1)
                if rng.randrange(3) == 0: o.special()   # 1451f0: the CPU kept a round
                o.g(2, h if won else rng.choice((h ^ 1, h ^ 1, -1)))
            nxt = o.end(rng.randrange(0, 24))
            state = {QUOTE: 'quote', DIALOGUE: 'dialogue', ENDING: 'ending', CONTINUE: 'continue', GAMEOVER: 'gameover'}[nxt]
        elif state == 'quote':
            o.fin()
            if o.w(G+0x1c) == 0 and rng.randrange(6) == 0 and challenge(o, rng, 0x136288): state = 'select'; continue
            nxt = o.wq(held)
            if o.mode() in (1, 2): o.g(0x1c//4, 0)   # destructor 136288
            state = {OPENING: 'opening', MAP: 'map', RESULT: 'result'}[nxt]; o.fin()
        elif state == 'result':
            state = {OPENING: 'opening', MAP: 'map', PREFINAL: 'prefinal', BATTLE: 'battle'}[o.vr(held)]; o.fin()
        elif state == 'dialogue':
            o.fin(); o.scene(2, 0)   # destructor 1c53e0
            state = 'prefinal' if o.player(o.human(), 5) == 7 else 'map'
        elif state == 'ending':
            # 182968 owns the ending; only its score overlay and exit are driven here.
            o.g(0x90//4, rng.choice((0, 150000, 5000, 250000, 12345))+step); o.g(0x30//4, 1)
            if o.nbegin():
                keys = [rng.choice((0x40, 0x80, 0x80, 2, 4, 0x200, 0x400, 8, 0, 0, 0)) for _ in range(rng.randrange(1, 60))]
                if rng.randrange(4): keys.append(8)
                for _ in range(2400):
                    if o.ntick(keys.pop(0) if keys else 0): break
                else: raise AssertionError('name entry never committed')
            o.g(0x34//4, 1); state = 'gameover'
        elif state == 'continue':
            o.fin(); o.center(); action = rng.choice(('start', 'start', 'timeout', 'hurry'))
            h = o.human(); nxt = 0
            for frame in range(1400):
                pressed = [0, 0]
                if action != 'timeout' and frame >= rng.randrange(20, 90):
                    pressed[h] = 8 if action == 'start' and rng.randrange(5) == 0 else rng.choice((2, 0x200, 4, 0, 0))
                    pressed[h ^ 1] = rng.choice((0, 0, 8, 2))
                if action == 'timeout' and frame % 3 == 0: pressed[h] = rng.choice((0, 0x202, 4))
                nxt = o.ctick(pressed)
                if nxt: break
            for _ in range(3): o.ctick([8, 8])   # the latch ignores later input
            o.cleave(); o.fin()
            if nxt == SELECT: select_human(o, rng, o.human(), False); state = 'select'
            else: assert nxt == GAMEOVER; state = 'gameover'
        elif state == 'gameover':
            o.fin()
            if rng.randrange(3) == 0: o.option(0x48, rng.randrange(2))   # an input of 1e6180's first predicate
            o.genter(); skip = rng.choice((None, None, rng.randrange(0, 0x130)))
            for frame in range(0x130):
                nxt = o.gtick(4 if frame == skip or (skip is not None and frame == skip+40) else 0)
                if nxt: break
            if nxt == RANKING: o.gleave()
            else: assert nxt == UNLOCK
            o.option(0x48, 0); o.fin(); state = 'menu'
    return visits

def directed(o, rng):
    """Branches a random session reaches rarely: mode-3 Continue, console VS bookkeeping, score table."""
    for mode, loser in ((3, 0), (3, 1), (1, 0), (2, 1), (7, 0)):
        o.g(0, mode); o.g(0xa0//4, 1); o.g(0x10//4, loser ^ 1); o.g(0x34//4, 0)
        for seat in (0, 1):
            for index in range(12): o.pl(seat, index, rng.randrange(1, 7))
        o.center()
        for frame in range(80): o.ctick([0, 0])
        o.ctick([2, 0x200]); o.ctick([0x200, 2]); o.ctick([8, 8]); o.ctick([0, 0]); o.cleave(); o.fin()
    for case in range(60):
        o.g(0, 3); o.g(0xa0//4, 2); o.g(2, rng.choice((0, 1, -1))); o.g(0x14//4, rng.randrange(2))
        if case % 20 == 5:
            for i in range(4): o.p.write(0x4c37f8+4*i, 998, 4); o.send('c', i, 998)   # clamp at 999
        for seat in (0, 1): o.pl(seat, 0, rng.choice(CHARACTERS)); o.pl(seat, 2, rng.randrange(6))
        o.versus(); o.end(0)
    for case in range(40):
        o.g(0x90//4, rng.choice((1, 9999, 60000, 100000, 100001, 205000, 300000))+case); o.g(0, rng.choice((1, 2)))
        seat = rng.randrange(2); o.pl(seat, 0, rng.choice(CHARACTERS)); o.pl(seat, 2, rng.randrange(9))
        name = bytes(rng.choice(b'ABCXYZ09 !') for _ in range(rng.randrange(1, 4)))
        o.p.memory[PARAM:PARAM+4] = name.ljust(4, b'\0')
        o.run(0x1c5150, seat, PARAM)
        o.send('score', seat, *name.ljust(3, b'\0')); o.check('score_insert_1c5150')
    # Name filter and fallbacks: SEX is the first filtered word; an empty name and a timeout.
    for keys in ([0x80]*18+[2]+[0x40]*14+[2]+[0x80]*19+[2, 2], [8], [0x80, 2, 0x200, 0x400, 8], []):
        o.g(0, rng.choice((1, 2))); o.g(0x90//4, 400000); o.pl(o.human(), 0, rng.choice(CHARACTERS))
        assert o.nbegin(); keys = list(keys)
        for _ in range(2400):
            if o.ntick(keys.pop(0) if keys else 0): break
        else: raise AssertionError('name entry never committed')
    o.g(0x90//4, 0); assert not o.nbegin()

def main():
    quick = '--quick' in sys.argv
    assert digest(ELF) == PIN
    assert (ASSETS/TABLES).read_bytes() == (ROOT/'work/ss6/extracted/resources'/TABLES).read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'arcade.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_run.cpp',
                        ROOT/'src/system_data.cpp', ROOT/'src/game_random.cpp', '-o', exe], check=True)
        rng = random.Random(0x17a2c8)
        o = Oracle(exe)
        schedules(o, rng, quick)
        visits = Counter()
        for session in range(2 if quick else 10):
            visits += walk(o, rng, 60 if quick else 400)
            o.g(0, 0); o.g(0x2c//4, 0); o.g(0x30//4, 0); o.g(0x34//4, 0)
        directed(o, rng)
        o.close()
    report = dict(status='passed', original_elf_sha256=PIN, checks=dict(o.checks), comparisons=sum(o.checks.values()),
                  scene_visits=dict(visits), coverage=dict(sorted(o.cover.items())), original_calls=dict(o.calls), original_instructions=o.instructions,
                  stubs={k: [hex(a) for a in v] for k, v in STUBS.items()} | {'object_allocation': ['0x11e2e8']},
                  scope='Whole 17a2c8/17a350/17a410/17a548/17a718/1c2420/1398c0/145628/124da0/1362d8/136fc8/1253e0/'
                        '1376d0/127f00+137978/137c68/138340/1387b8/138a48/1c9830/1c9928/1c5150 with every state word of '
                        'g_GameData, both player records, the schedule record, RNG seeds, both ranking tables, the countdown '
                        'and the scene counters compared after each call. Explicit slices: 12f124..12f204 (select exit), '
                        '118188..11822c (challenger poll); the menu confirm is composed from 1252f0, 1ccfb8, 139280 and '
                        '111508. Stubbed: rendering, object animation/allocation, camera, texture and disc loading, sound '
                        'driver, memory card, debug print and the 1e5d88 successor entry; the C library strcmp 31806c is a byte-wise equivalent (Probe lacks MMI PSUBW). Presentation scenes between the '
                        'requests are fixtures that apply only their documented run-state writes. Submodes 5/6 and '
                        'survival are outside this port.')
    if not quick: REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(f"passed: {sum(o.checks.values())} state comparisons, {o.instructions} original instructions, visits {dict(visits)}")

if __name__ == '__main__': main()
