#!/usr/bin/env python3
"""Probe comparisons for the battle-side rules that the SURVIVAL MODE integration ported
outside src/survival_run.*: the clock load 1406e0/140930, the life carry-over at the end
of 13fd80, the item producer 144f40 through StageItemSchedule::next, the CPU level rule of
158830, the maximum-combo and counter-hit event bytes and the mission bit 23 of 1576e8.
The native side is a driver linked against the runtime library of --build."""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from mips_probe import signed
from extract_collision_tables import SOURCE_HASH
import validate_survival_run as sr
from validate_survival_run import Oracle, A, B, G, S, T, RETURN, ROOT, ASSETS, ELF
import validate_finishing_blow as fb

REPORT = ROOT/'outputs/ss6-feasibility/survival_battle_validation.json'
DRIVER = r'''
#include "battle_round.hpp"
#include "native_match.hpp"
#include "finishing_blow.hpp"
#include "state_callbacks.hpp"
#include "collision.hpp"
#include "stage_item_schedule.hpp"
#include "stage_event.hpp"
#include "survival_run.hpp"
#include <iostream>
#include <sstream>
using namespace ss6;
int main(int,char** argv) {
    const std::filesystem::path assets=argv[1];
    const InputBindings bindings(assets);
    const StageItemSchedule schedule(assets);
    std::string line;
    while(std::getline(std::cin,line)) {
        std::istringstream in(line);std::ostringstream o;std::string op;in>>op;
        if(op=="set") {unsigned index;int ticks,paused;in>>index>>ticks>>paused;BattleTimers t;t.set(index,ticks,battleTimerDivisor(index,paused));o<<t.values[index];}
        else if(op=="clock") {int carried,paused;in>>carried>>paused;BattleTimers t;t.set(0,survivalRoundTicks(carried),battleTimerDivisor(0,paused));o<<t.values[0];}
        else if(op=="life") {int life,carried;unsigned control;in>>life>>control>>carried;o<<survivalRoundLife(life,control,carried);}
        else if(op=="combo") {unsigned best;int combo;in>>best>>combo;o<<unsigned(survivalMaxCombo(uint8_t(best),combo));}
        else if(op=="level") {int survival,raw,level;in>>survival>>raw>>level;o<<cpuFightLevel(survival,raw,level);}
        else if(op=="item") {
            BattleRoundState b;
            in>>b.gameMode>>b.matchEnd.metadataStage04>>b.random.mode>>b.random.gameSeed>>b.random.librarySeed;
            b.battleKind123a0c0=2;b.timers.values[3]=0;b.camera.projectionX=4000;
            const auto drop=schedule.next(b,StageEventPlayers{1000,2000,false});
            o<<bool(drop);
            if(drop)o<<' '<<drop->kind<<' '<<drop->fromRight<<' '<<(drop->targetX==1000?0:drop->targetX==2000?1:drop->targetX==1500?2:3)
                     <<' '<<(b.timers.values[3]>>8)<<' '<<b.random.gameSeed<<' '<<b.random.librarySeed;
        }
        else if(op=="finish") {
            int mode;StateEntryActor source{},target{};PlayerMatchStats stats{};ContactEvent event{};
            unsigned strength=0,weak=0;bool projectile=false;InputSystemConfig config;
            in>>mode>>source.state194>>source.state1a4>>strength>>source.flags23c>>source.flags244>>source.flags248
              >>target.state194>>target.state1a4>>target.flags23c>>target.flags240>>weak>>event.a.fields.group>>projectile
              >>target.pendingDamageA38>>target.fieldA30>>stats.hitCount0c>>stats.outcome1c>>stats.outcome20>>source.character
              >>config.system>>source.systemState13c;
            config.character=source.character;
            source.stateFlags19a=strength&255;source.aliasFlags1aa=strength>>8;event.b.fields.low7=weak;
            const bool counter=isCounterContact(target,stats,event);
            const bool concentration=StateCallbacks::hasSystemEffect(config)&&source.systemState13c==3;
            if(mode<2)recordContactFinish(source,target,stats,event,projectile,mode==1,counter,bindings,10,concentration);
            else recordScriptFinish(source,target,stats,projectile,mode==3,bindings,10,concentration);
            o<<counter<<' '<<source.flags244<<' '<<source.flags248<<' '<<stats.outcome1c<<' '<<stats.outcome20;
        }
        std::cout<<o.str()<<std::endl;
    }
}
'''

class Native:
    def __init__(self, tmp, build):
        cpp = Path(tmp)/'survival_battle_driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, build/'libss6-runtime.a', '-o', exe], check=True)
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def ints(self, *parts):
        self.proc.stdin.write(' '.join(str(x) for x in parts)+'\n'); self.proc.stdin.flush()
        return [int(x) for x in self.proc.stdout.readline().split()]
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0

def clock_tests(o, n, rng, counts):
    p = o.p
    # 140930 whole (11f450 and 143228 as real callees) for every timer, with and without the global pause 46a940.
    for case in range(280):
        index, ticks, paused = case % 7, rng.choice((0, 1, 30, 600, 99*180, rng.randrange(1 << 15))), (case//7) % 2
        p.write(0x46a940, paused, 4)
        o.run(0x140930, index, ticks)
        assert n.ints('set', index, ticks, paused) == [signed(p.read(B+0x104+0x10+4*index, 4), 32)], (index, ticks, paused)
        counts['whole_140930'] += 1
    # 1406e0 whole in survival: carried clock 180ec8 -> timer 0, also under the pause the reload runs in.
    for case in range(240):
        v = rng.choice((-1, 0, 1, 0xff, 0x100, 0x101, 0x459c00, 0x459bff, 0xb400*40, rng.randrange(0x45a000)))
        wins, paused = rng.choice((0, 1, 5)), case % 2
        p.write(B+0x13c, 2, 4); p.write(T+0x3c, wins, 2); p.write(S+0x14, v, 4); p.write(0x46a940, paused, 4)
        p.write(B+0x114, 0x12345, 4)
        o.run(0x1406e0)
        carried = o.run(0x180ec8)[0]
        assert carried == (v if wins > 0 else -1)
        assert n.ints('clock', carried, paused) == [signed(p.read(B+0x114, 4), 32)], (v, wins, paused)
        counts['whole_1406e0_survival'] += 1
    p.write(0x46a940, 0, 4); p.write(S+0x14, 0, 4); p.write(T+0x3c, 0, 2)

def life_tests(o, n, rng, counts):
    p = o.p
    # 13ff90..13ffe4: the survival tail of 13fd80 with 180e98 as a real callee.
    for case in range(160):
        wins, saved = rng.choice((0, 0, 1, 7)), rng.choice((-1, 0, 1, 57, 178, 200))
        lives = [rng.choice((200, 120)), rng.choice((200, 33))]
        control = [rng.randrange(2), rng.randrange(2)]
        p.write(T+0x3c, wins, 2); p.write(S+0x10, saved, 4)
        for i in range(2):
            p.write(A+0xf2c*i+0xa30, lives[i], 4); p.write(A+0xf2c*i+0xa20, control[i], 4)
        o.run(0x13ff90, stop=(0x13ffe4, 0x13ffe8))
        carried = o.run(0x180e98)[0]
        assert carried == (saved if wins > 0 else -1)
        for i in range(2):
            assert n.ints('life', lives[i], control[i], carried) == [signed(p.read(A+0xf2c*i+0xa30, 4), 32)], (case, i)
        counts['slice_13ff90_13ffe4'] += 1
    p.write(T+0x3c, 0, 2); p.write(S+0x10, 0, 4)
    for i in range(2):
        p.write(A+0xf2c*i+0xa20, 0, 4)

def item_tests(o, n, rng, counts):
    p = o.p
    saved = {at: bytes(p.memory[at:at+8]) for at in (0x140fa0, 0x148368, 0x1b5800, 0x1408e0)}
    # 140fa0 (live item census), 1408e0 (timer 3 read) and 1b5800 (item spawn) are replaced; 148368 returns
    # its selector so the anchor choice is observable. 14ea68 and the timer store 140930 run as real callees.
    for at in saved:
        p.memory[at:at+8] = RETURN
    p.memory[0x148368:0x148370] = struct.pack('<II', 0x03e00008, 0x0080102d)   # jr ra; move v0,a0
    o.watch |= {0x1b5800}
    for case in range(480):
        seeds = [rng.choice((0, 1)), rng.randrange(1, 1 << 31), rng.getrandbits(64)]
        o.seed(*seeds)
        stage, mode = case % 12, rng.choice((0xb, 0xc))
        p.write(G, mode, 4); p.write(B+0x10, stage, 4); p.write(B+0x104+0x10+12, 0x7777, 4)
        _, hits = o.run(0x144f40, B)
        spawn = [h for h in hits if h[0] == 0x1b5800][0][1]
        want = [1, spawn[0], spawn[2], spawn[1], signed(p.read(B+0x104+0x10+12, 4), 32) >> 8]+o.rng()
        assert n.ints('item', mode, stage, *seeds) == want, (case, stage)
        counts['whole_144f40_vs_schedule'] += 1
    o.watch -= {0x1b5800}
    for at, code in saved.items():
        p.memory[at:at+8] = code

def actor_tests(o, n, rng, counts):
    p = o.p
    # 158830 whole outside practice: the level stored in AI+0x100.
    for kind in (0, 2):
        p.write(0x123a0c0, kind, 1)
        for raw in list(range(0x34)):
            level = rng.randrange(9)
            o.run(0x158830, A, 1, raw, level)
            assert n.ints('level', int(kind == 2), raw, level) == [signed(p.read(A+0x100, 4), 32)], (kind, raw)
            assert p.read(A+0xc0, 4) == 0x23
            counts['whole_158830'] += 1
    p.write(0x123a0c0, 2, 1)
    # 1498d0..1495e8: the survival maximum-combo byte actor+f22 inside the actor update 1494f0.
    for case in range(200):
        best, combo, seat = rng.randrange(0x70), rng.choice((0, 1, 2, 5, 0x62, 0x63, 0x64, 200)), rng.randrange(2)
        p.write(A+0xa24, seat, 4); p.write(A+0xf22, best, 1); p.write(B+0x254+0x108*seat+0xc, combo, 4)
        o.run(0x1498d0, stop=(0x1495e8, 0x1495ec), registers={17: A})
        assert n.ints('combo', best, combo) == [p.read(A+0xf22, 1)], case
        counts['slice_1498d0_combo'] += 1
    p.write(A+0xa24, 0, 4)
    # 155c80..155c98: the counter-hit byte actor+f27 saturates at 99.
    for value in range(0, 0x70):
        p.write(A+0xf27, value, 1)
        o.run(0x155c80, stop=(0x155c98,), registers={21: A})
        assert p.read(A+0xf27, 1) == (value+1 if value < 99 else value), value
        counts['slice_155c80_counter_byte'] += 1

class Finishes(fb.Comparison):
    """validate_finishing_blow's matrix with the attacker's system word (actor+10c) and its
    system-effect state (actor+13c) varied: 1576e8 sets flags248 bit 23 from 14eb78."""
    def matrix(self, n, counts):
        p = self.p
        rng = random.Random(0x15787c)
        for case in range(1920):
            slot = case % 2; victim = 1-slot
            a, b = fb.actor(slot), fb.actor(victim)
            for i in range(2):
                fb.put(p, fb.actor(i), [(0, fb.OBJECTS[i]), (0xa24, i), (0x134, 25600), (0x138, 25600), (0xa30, 200), (0xa34, 200)])
                fb.put(p, fb.OBJECTS[i], [(0xc, i), (0x10, i), (0xcc, i)])
            character = (case//96+slot) % 2
            fb.put(p, a, [(0xa10, character)]); fb.put(p, b, [(0xa10, 1-character)])
            mode = rng.randrange(4)
            index = case % 96
            main = fb.state(1, index)
            flags = rng.choice([0, 0x1000, 0x1800])
            system, effect = rng.choice([0, 1, 2, 3, 4, 4, 4, 5]), rng.choice([0, 1, 3, 3, 4])
            fb.put(p, a, [(0x194, main), (0x1a4, fb.state(rng.choice([0, 1, 2]), rng.randrange(20))), (0x23c, flags), (0x244, 0x100),
                          (0x248, 0x40000000 if case % 3 == 0 else 8), (0x10c, system), (0x13c, effect)])
            p.write(a+0x19a, rng.randrange(8), 1); p.write(a+0x1aa, rng.randrange(8), 1)
            fb.put(p, b, [(0x194, fb.state(rng.randrange(3), 0)), (0x1a4, fb.state(rng.randrange(3), 1)), (0x240, rng.randrange(2)),
                          (0x23c, 0x1000), (0xa30, 20), (0xa38, rng.choice([0, 19, 20, 22]))])
            fb.put(p, fb.stats(slot), [(12, rng.choice([0, 0, 1, 4])), (0x1c, -1), (0x20, -1)])
            projectile = bool(case % 7 == 0)
            fb.put(p, fb.CHILD, [(0xc, slot), (0x10, slot), (0xcc, 2), (0xd0, (case//7) % 2)])
            srcobj = fb.CHILD if projectile else fb.OBJECTS[slot]
            fb.put(p, fb.EVENT, [(0x20, 36 if projectile else 12), (0x24, rng.randrange(6)), (0x40, srcobj),
                                 (0x48, rng.randrange(1, 4)), (0x60, rng.randrange(4)), (0x68, fb.OBJECTS[victim])])
            counter = self.run(0x157fa8, [b, fb.EVENT+0x48])
            cmd = self.native_case(mode, slot, fb.EVENT, projectile)
            if mode < 2:
                self.run(0x1575d0, [fb.EVENT, int(not projectile), mode, counter if mode == 0 else 0])
            else:
                self.run(0x1413d8, [victim, 8, srcobj, int(mode == 3)])
                cmd[14] = p.read(b+0xa38, 4)
            want = [counter, *self.metadata(slot)]
            assert n.ints('finish', *cmd, system, effect) == want, (case, cmd, system, effect, want)
            latched = want[1] & 0x08000000
            counts['whole_1576e8_finish'] += bool(latched)
            counts['finish_bit23_set'] += bool(want[2] & 0x800000)
            assert bool(want[2] & 0x800000) == bool(latched and system == 4 and effect == 3), (case, system, effect)
            fb.put(p, a, [(0x10c, 0), (0x13c, 0)])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', default=str(ROOT/'work/ss6/build-native'))
    args = parser.parse_args()
    build = Path(args.build)
    if not build.is_absolute():
        build = ROOT/build
    rng = random.Random(0x13a6c0)
    assert hashlib.sha256(ELF.read_bytes()).hexdigest() == SOURCE_HASH
    counts = Counter()
    o = Oracle()
    with tempfile.TemporaryDirectory() as tmp:
        n = Native(tmp, build)
        clock_tests(o, n, rng, counts)
        life_tests(o, n, rng, counts)
        item_tests(o, n, rng, counts)
        actor_tests(o, n, rng, counts)
        finishes = Finishes()
        finishes.matrix(n, counts)
        n.close()
    assert counts['finish_bit23_set'] > 20
    sources = ('battle_round.hpp', 'battle_round.cpp', 'stage_item_schedule.cpp', 'finishing_blow.cpp', 'native_match.hpp', 'round_control.cpp')
    report = dict(status='passed', elf_sha256=SOURCE_HASH,
                  native_sha256={f: hashlib.sha256((ROOT/'src'/f).read_bytes()).hexdigest() for f in sources},
                  counts=dict(sorted(counts.items())), original_instructions=o.instructions+finishes.instructions,
                  scope='Whole 140930 (11f450, 143228), whole 1406e0 in survival, whole 144f40 in survival against '
                        'StageItemSchedule::next (14ea68 and 140930 real; 140fa0, 1408e0 and 1b5800 replaced by a bare return, '
                        '148368 returning its selector), whole 158830 outside practice, whole 1575d0/1413d8 -> 1576e8 with the '
                        'system word and system-effect state varied. Explicit slices: 13ff90..13ffe4 (life carry-over), '
                        '1498d0..1495e8 (actor+f22), 155c80..155c98 (actor+f27). The fixtures are memory states, not original '
                        'battle frames; the position of each rule inside the native frame is exercised by validate_survival_session.py.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('status', 'counts', 'original_instructions')}))

if __name__ == '__main__':main()
