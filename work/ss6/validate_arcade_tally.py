#!/usr/bin/env python3
"""Compare the native arcade score awards and state-9 tally with SLPS-25559 tick by tick."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from mips_probe import signed
from extract_console_versus_art import prepare, ORIGINAL
from extract_arcade_tally import build, NAME

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'outputs/ss6-feasibility/native-viewer/assets'
REPORT = ROOT/'outputs/ss6-feasibility/arcade_tally_validation.json'
G, BATTLE, HUD, SEATS, PADS, STATE = 0x4c3808, 0x1b00000, 0x132f3a0, 0x456890, 0x1237cc8, 0x582940
ACTOR = 0x1b10000
BAR = (0x00, 0x08, 0x10, 0x14, 0x54, 0x68, 0x7c, 0x94)
RETURN = 0x1ffff00
DRIVER = r'''
#include "arcade_tally.hpp"
#include <iostream>
using namespace ss6;
int main(int,char** argv) {
    ArcadeTallyTables tables(argv[1]);ArcadeTally t;ArcadeTallyWorld w;FreeSeatPrompt prompt;std::string op;
    auto state=[&](const ArcadeTallyTick& r,bool drawn=false){
        std::cout<<t.phase40<<' '<<t.active44<<' '<<t.done48<<' '<<t.exit4c<<' '<<w.finishBonus582950<<' '<<t.seconds54<<' '
                 <<t.life58<<' '<<t.straight5c<<' '<<t.payout60<<' '<<t.finishLatch64<<' '<<t.step68<<' '<<t.finish6c<<' '
                 <<t.time70<<' '<<t.life74<<' '<<t.straight78<<' '<<t.total7c<<' '<<t.perfect80<<' '<<t.wait84<<' '
                 <<t.seat88<<' '<<t.straightSeat8c<<' '<<t.sound90<<' '<<t.paused94<<' '<<w.roundClock114;
        for(auto& b:w.life)std::cout<<' '<<b.x00<<' '<<b.width08<<' '<<b.lag10<<' '<<b.life14<<' '<<b.mark54<<' '<<b.mark68<<' '<<b.mark7c<<' '<<b.kind94;
        std::cout<<' '<<w.score90<<' '<<w.postMatchMenuA4<<' '<<t.active()<<' '<<t.done()<<' '<<r.sounds<<' '<<r.musicRelease;
        const auto texts=drawn?t.draw.texts(tables):std::vector<ArcadeTallyText>{};std::cout<<' '<<texts.size();
        for(auto text:texts){for(auto& c:text.text)if(c==' ')c='_';std::cout<<' '<<text.x<<' '<<text.y<<' '<<text.colour<<' '<<text.text;}
        std::cout<<std::endl;
    };
    while(std::cin>>op) {
        if(op=="E") {
            int survival,option;
            std::cin>>w.clockOption13c>>w.roundClock114>>survival>>option;w.survival=survival;w.timeOption43d05d=uint8_t(option);
            for(auto& b:w.life)std::cin>>b.x00>>b.width08>>b.lag10>>b.life14>>b.mark54>>b.mark68>>b.mark7c>>b.kind94;
            std::cin>>w.wins28[0]>>w.wins28[1]>>w.required2c[0]>>w.required2c[1]>>w.seatRequired20[0]>>w.seatRequired20[1]
                    >>w.score90>>w.sceneSwitch18>>w.postMatchMenuA4>>w.finishBonus582950;
            t.enter(w);state({});
        } else if(op=="T") {
            std::array<uint32_t,2> pressed;std::cin>>pressed[0]>>pressed[1]>>w.sceneSwitch18;state(t.tick(pressed,w),true);
        } else if(op=="P") {int on;std::cin>>on;t.setPaused(on);state({});
        } else if(op=="L") {t.leave();state({});
        } else if(op=="A") {
            int mode,seat,kind;int32_t combo,score;std::cin>>mode>>seat>>kind>>combo>>score;
            const auto added=arcadeScoreAward(tables,mode,seat,kind,combo,score);std::cout<<added<<' '<<score<<std::endl;
        } else if(op=="F") {
            int mode,seat,index;int32_t word;std::cin>>mode>>seat>>index>>word;
            const bool ok=arcadeFinishBonus(tables,mode,seat,index,word);std::cout<<ok<<' '<<word<<std::endl;
        } else if(op=="K") {int c;std::cin>>c;std::cout<<arcadeBodyHitKind(c)<<' '<<arcadeObjectHitKind(c)<<std::endl;
        } else if(op=="C") {int g,o;std::cin>>g>>o;std::cout<<arcadeFinishClass(g,o)<<std::endl;
        } else if(op=="I") {int id;std::cin>>id;std::cout<<arcadeItemKind(id)<<std::endl;
        } else if(op=="D") {int32_t v;std::cin>>v;std::cout<<arcadeDigits(v)<<std::endl;
        } else if(op=="S") {
            ArcadeTallyWorld s;int survival;std::cin>>s.clockOption13c>>s.roundClock114>>survival;s.survival=survival;
            std::cout<<s.secondsLeft()<<std::endl;
        } else if(op=="B") {
            int n;std::cin>>n;prompt.reset();
            for(int i=0;i<n;++i)std::cout<<prompt.tick()<<' '<<prompt.count2230<<' ';
            std::cout<<std::endl;
        }
    }
}
'''

class Native:
    def __init__(self, exe):
        self.proc = subprocess.Popen([exe, ASSETS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def ask(self, line):
        self.proc.stdin.write(line+'\n'); self.proc.stdin.flush(); return self.proc.stdout.readline().split()
    def close(self):
        self.proc.stdin.close(); assert self.proc.wait() == 0

class Oracle:
    """The original functions in Probe. No instruction is patched: the global flag 3ec73c stops
    GS submission after the draw routines computed their packets, and the sound RPC is muted by
    the driver's own initial state. Calls are observed, never redirected."""
    def __init__(self):
        self.p = p = prepare()
        p.write(0x3ec73c, 1, 4); p.write(0x4d3d00, BATTLE, 4); p.write(0x345188, 0, 4)
        self.instructions = 0

    def run(self, pc, *args, limit=400000, observe=None):
        value, count = self.p.run(pc, args, limit=limit, observe=observe); self.instructions += count; return value

    def word(self, at): return signed(self.p.read(at, 4), 32)

    def load(self, w):
        p = self.p
        p.write(BATTLE+0x13c, w['option13c'], 4); p.write(BATTLE+0x114, w['clock'], 4)
        p.write(0x123a0c0, 2 if w['survival'] else 0, 1); p.write(0x43d05d, w['option43d05d'], 1)
        for seat in (0, 1):
            for off, value in zip(BAR, w['bars'][seat]): p.write(HUD+0x98*seat+off, value, 4)
            p.write(BATTLE+0x254+0x108*seat+0x28, w['wins'][seat], 4)
            p.write(BATTLE+0x254+0x108*seat+0x2c, w['required'][seat], 4)
            p.write(SEATS+0x30*seat+0x20, w['seat_required'][seat], 4)
        p.write(G+0x90, w['score'], 4); p.write(G+0x18, w['switch'], 4); p.write(G+0xa4, w['menu'], 4)
        p.write(0x582950, w['finish'], 4)

    def state(self, sounds=0, music=0, texts=()):
        row = [self.word(STATE+4*i) for i in range(22)]+[self.word(BATTLE+0x114)]
        for seat in (0, 1): row += [self.word(HUD+0x98*seat+off) for off in BAR]
        row += [self.word(G+0x90), self.word(G+0xa4), self.run(0x1c87e0), self.run(0x1c87f0), sounds, music, len(texts)]
        for text in texts: row += list(text)
        return [str(v) for v in row]

    def enter(self, w):
        self.load(w); seen = []
        def observe(pc):
            if pc in (0x112670, 0x112f30): seen.append((pc, [self.p.registers[i] & 0xffffffff for i in (4, 5, 6, 7)]))
        self.run(0x1c7ce8, observe=observe)
        # Task: priority 0x19, handler 1c7f08, 0x10 payload bytes, tag 0x177a; text colours 0 / ffffff.
        assert seen[0] == (0x112670, [0x19, 0x1c7f08, 0x10, 0x177a]) and seen[1][0] == 0x112f30 and seen[1][1][:2] == [0, 0xffffff], seen
        assert self.word(0x3d3aa0) == -1
        return self.state()

    def tick(self, pressed, switch):
        p = self.p; p.write(G+0x18, switch, 4)
        for seat in (0, 1): p.write(PADS+0xc*seat+4, pressed[seat], 4)
        sounds = []; texts = []; music = [0]; self.sprites = 0
        def observe(pc):
            if pc == 0x1e7b70: sounds.append((signed(p.registers[4], 32), p.registers[5] & 0xffffffff))
            elif pc == 0x1e7a78: music[0] += 1
            elif pc in (0x117de8, 0x114118): self.sprites += 1
            elif pc == 0x113028:
                at = p.registers[4] & 0xffffffff
                text = bytes(p.memory[at:at+32]).split(b'\0')[0].decode().replace(' ', '_')
                texts.append((p.registers[5] & 0xffffffff, p.registers[6] & 0xffffffff, p.registers[7] & 0xffffffff, text))
        for a in (0x345178, 0x345180): p.write(a, 0, 4)
        self.run(0x1c7f08, observe=observe)
        assert all(s == (-1, 0x42) for s in sounds), sounds
        return self.state(len(sounds), music[0], texts)

    def pause(self, on):
        self.run(0x1c9820 if on else 0x1c9810); return self.state()

    def leave(self):
        seen = []
        self.run(0x1c7d20, observe=lambda pc: seen.append(self.p.registers[4] & 0xffffffff) if pc == 0x112a70 else None)
        assert seen == [0x177a]
        return self.state()

def scenario(rng, index):
    life = [rng.choice((200, 200, rng.randrange(1, 200), rng.randrange(1, 200), 0)) for _ in (0, 1)]
    if rng.random() < .15: life[1] = life[0]
    bars = [[rng.randrange(0, 400), rng.randrange(0, 400), life[s]+rng.randrange(0, 30), life[s], rng.randrange(0, 201),
             rng.randrange(0, 201), rng.randrange(0, 201), rng.randrange(0, 8)] for s in (0, 1)]
    option = rng.choice((0, 0, 1, 2, 3))
    clock = rng.choice((0, rng.randrange(1, 100)*0x5a00, rng.randrange(0, 99*0x5a00), rng.randrange(0, 99*0x5a00), 1, -rng.randrange(1, 0x12000)))
    if option == 3 and rng.random() < .7: clock = 0
    wins = [rng.randrange(0, 4), rng.randrange(0, 4)]; required = [rng.randrange(1, 4), rng.randrange(1, 4)]
    seat_required = [rng.randrange(0, 4), rng.randrange(0, 4)]
    if rng.random() < .45:
        # A straight match win of the seat 1c7d48 selects.
        s = rng.randrange(2); wins[s] = required[s] = seat_required[s] = rng.choice((2, 2, 3)); wins[s ^ 1] = 0
        if s == 1: wins[0] = 0
    world = dict(option13c=option, clock=clock, survival=rng.random() < .1,
                 option43d05d=rng.choice((0, 0, 1, 2, 3)), bars=bars, wins=wins, required=required,
                 seat_required=seat_required, score=rng.randrange(0, 600000), switch=0, menu=1,
                 finish=rng.choice((0, -1000, 2000, 2000, 4000, 6000, -1, 29, -31, rng.randrange(-5000, 5000))))
    style = index % 6
    steps = []
    for frame in range(420):
        pressed = [0, 0]; pause = None; switch = 0
        if style == 1 and rng.random() < .04: pressed[rng.randrange(2)] = 1 << rng.randrange(24)
        if style == 2: pressed = [rng.choice((0x200, 0x8, 0x400)) if frame % 3 == 0 else 0]*2
        if style == 3 and rng.random() < .03: pressed = [0x60f, 0x60f]
        if style == 4:
            if rng.random() < .04: pause = rng.random() < .6
            if rng.random() < .05: pressed[rng.randrange(2)] = rng.choice((1, 2, 4, 8, 0x200, 0x400, 0x10, 0x100000))
        if style == 5 and rng.random() < .3: switch = 1
        steps.append((pressed, pause, switch))
    return world, steps

def enter_line(w):
    values = [w['option13c'], w['clock'], int(w['survival']), w['option43d05d']]+w['bars'][0]+w['bars'][1]
    values += w['wins']+w['required']+w['seat_required']+[w['score'], w['switch'], w['menu'], w['finish']]
    return 'E '+' '.join(map(str, values))

def play(job):
    exe, seed, first, count = job
    rng = random.Random(seed); oracle = Oracle(); native = Native(exe)
    stats = dict(scenarios=0, ticks=0, sounds=0, texts=0, skipped=0, paused_ticks=0, finished=0, music=0,
                 phases=[0]*7, sprites=set())
    for index in range(first, first+count):
        world, steps = scenario(rng, index)
        def same(want, got, where):
            assert want == got, (index, where, world, want, got)
        same(oracle.enter(world), native.ask(enter_line(world)), 'enter')
        after = 0
        for frame, (pressed, pause, switch) in enumerate(steps):
            if pause is not None: same(oracle.pause(pause), native.ask(f'P {int(pause)}'), ('pause', frame))
            stats['phases'][min(oracle.word(STATE), 6)] += 1
            want = oracle.tick(pressed, switch)
            same(want, native.ask(f'T {pressed[0]} {pressed[1]} {switch}'), ('tick', frame))
            stats['ticks'] += 1; stats['sounds'] += int(want[43]); stats['music'] += int(want[44]); stats['texts'] += int(want[45])
            stats['sprites'].add(oracle.sprites); stats['paused_ticks'] += int(want[21] != '0')
            stats['skipped'] += bool((pressed[0] | pressed[1]) & 0x60f)
            if want[2] != '0':
                after += 1
                if after == 3: break
        stats['finished'] += after > 0
        same(oracle.leave(), native.ask('L'), 'leave'); stats['scenarios'] += 1
    native.close(); stats['sprites'] = sorted(stats['sprites']); stats['instructions'] = oracle.instructions
    return stats

def score_checks(exe):
    oracle = Oracle(); p = oracle.p; native = Native(exe); rng = random.Random(0x14e838)
    counts = dict(award=0, finish=0, body_slices=0, object_slices=0, finish_slices=0, digits=0, seconds=0, blink=0, shrink=0)
    record = lambda seat: BATTLE+0x254+0x108*seat
    # Whole 14e838 / 14e8d8.
    for mode in (0, 1, 2, 3, 9, 11):
        for seat in (0, 1):
            for kind in range(24):
                for combo in (-1, 0, 1, 7):
                    score = rng.randrange(-1000, 900000)
                    p.write(G, mode, 4); p.write(G+0x90, score, 4); p.write(record(seat)+0xc, combo, 4)
                    added = signed(oracle.run(0x14e838, seat, kind), 32); after = oracle.word(G+0x90)
                    # The gate's refusal leaves v0 undefined; only the score word is compared then.
                    got = list(map(int, native.ask(f'A {mode} {seat} {kind} {combo} {score}')))
                    assert got[1] == after and (after == score or got[0] == added), (mode, seat, kind, combo, got, added, after)
                    counts['award'] += 1
            for index in range(6):
                word = rng.randrange(-9, 9)
                p.write(G, mode, 4); p.write(0x582950, word, 4); oracle.run(0x14e8d8, seat, index)
                got = list(map(int, native.ask(f'F {mode} {seat} {index} {word}')))
                assert got[1] == oracle.word(0x582950) and got[0] == ((mode, seat) in ((1, 0), (2, 1))), (mode, seat, index)
                counts['finish'] += 1
    table = lambda kind: signed(p.read(0x655588+4*kind, 4), 32)
    def slice_run(pc, registers, slot):
        # Explicit tail slice: the classifier's result register is preset and the
        # saved return address is planted where the skipped prologue would store it.
        p.write(0x1fff000+slot, RETURN, 8)
        for reg, value in registers.items(): p.put(reg, value)
        oracle.run(pc)
    for category in range(-1, 18):
        body, obj = map(int, native.ask(f'K {category}'))
        for flag in (0, 1):
            for combo in (0, 2):
                for mode, seat in ((1, 0), (2, 1), (1, 1)):
                    def expect(kind):
                        total = 0
                        for k in (kind,)+((16,) if flag else ()):
                            total += int(native.ask(f'A {mode} {seat} {k} {combo} 0')[0])
                        return total
                    p.write(G, mode, 4); p.write(record(seat)+0xc, combo, 4)
                    p.write(ACTOR+0xa24, seat, 4); p.write(ACTOR+0x244, 0, 4); p.write(G+0x90, 0, 4)
                    # 157a74: v0 = 14dac8(actor), s0 = actor, s1 = second-award flag.
                    slice_run(0x157a74, {2: category, 16: ACTOR, 17: flag}, 0x10)
                    assert oracle.word(G+0x90) == expect(body), ('body', category, flag, combo, mode, seat)
                    assert p.read(ACTOR+0x244, 4) == (0x80000000 if category == 11 else 0)
                    counts['body_slices'] += 1
                    p.write(ACTOR+0x244, 0, 4); p.write(G+0x90, 0, 4)
                    # 157b84: s1 = 14dc00(object), v0 = owner actor, s2 = 0x12 default, s3 = flag.
                    slice_run(0x157b84, {17: category, 2: ACTOR, 18: 0x12, 19: flag}, 0x20)
                    assert oracle.word(G+0x90) == expect(obj), ('object', category, flag, combo, mode, seat)
                    assert p.read(ACTOR+0x244, 4) == (0x80000000 if category == 11 else 0)
                    counts['object_slices'] += 1
    outcome = {13: 0, 11: 1, 12: 3, 7: 4, 8: 4, 9: 2}
    for category in range(-1, 16):
        for guard in (0, 1):
            for mode, seat in ((1, 0), (2, 1), (2, 0)):
                p.write(G, mode, 4); p.write(ACTOR+0xa24, seat, 4); p.write(ACTOR+0x244, 0, 4)
                p.write(record(seat)+0x1c, 5, 4); p.write(0x582950, 77, 4)
                # 1578d4: s2 = finish class of 14dac8/14dc00, s4 = record, fp = guard flag, s0 = actor.
                slice_run(0x1578d4, {18: category, 20: record(seat), 30: guard, 16: ACTOR}, 0x48)
                result = oracle.word(record(seat)+0x1c); assert result == outcome.get(category, 5)
                index = int(native.ask(f'C {guard} {result}')[0])
                got = list(map(int, native.ask(f'F {mode} {seat} {index} 77')))
                assert got[1] == oracle.word(0x582950), (category, guard, mode, seat, index)
                assert p.read(ACTOR+0x244, 4) == 0x08000000 | (0x10000000 if guard else 0)
                counts['finish_slices'] += 1
    assert [int(native.ask(f'I {i}')[0]) for i in range(8)] == [-1, -1, -1, -1, 13, 14, 15, -1]
    for value in [0, 1, 9, 10, 99, 100, -1, -9, -10, -1000, 123456, 99999999, 100000000, 999999999]+[rng.randrange(-10**8, 10**8) for _ in range(60)]:
        assert int(native.ask(f'D {value}')[0]) == oracle.run(0x1b9838, value), value; counts['digits'] += 1
    for case in range(200):
        option = rng.randrange(4); clock = rng.choice((0, 1, 0x5a00, 0x5a01, rng.randrange(-0x20000, 100*0x5a00))); survival = rng.random() < .3
        p.write(BATTLE+0x13c, option, 4); p.write(BATTLE+0x114, clock, 4); p.write(0x123a0c0, 2 if survival else 0, 1)
        assert int(native.ask(f'S {option} {clock} {int(survival)}')[0]) == signed(oracle.run(0x1407d0), 32); counts['seconds'] += 1
    # Free-seat prompt clock: 1ba120 then 1ba148 once per frame.
    oracle.run(0x1ba120); want = []
    for frame in range(400): want += [oracle.run(0x1ba148), oracle.word(0x582230)]
    assert list(map(int, native.ask('B 400'))) == want; counts['blink'] = 400
    native.close(); counts['instructions'] = oracle.instructions
    return counts

def main():
    raw = (ROOT/'work/ss6/extracted/SLPS_255.59').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ORIGINAL
    asset = (ASSETS/NAME).read_bytes(); assert asset == build(raw)[0]
    scenarios = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    workers = min(os.cpu_count() or 2, 8)
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp)/'driver.cpp'; cpp.write_text(DRIVER); exe = cpp.with_suffix('')
        subprocess.run(['c++', '-std=c++20', '-ffp-contract=off', '-O2', '-I', ROOT/'src', cpp, ROOT/'src/arcade_tally.cpp', '-o', exe], check=True)
        scores = score_checks(str(exe))
        per = -(-scenarios//workers)
        jobs = [(str(exe), 0x1c7f08+i, i*per, min(per, scenarios-i*per)) for i in range(workers) if i*per < scenarios]
        with ProcessPoolExecutor(workers) as pool: parts = list(pool.map(play, jobs))
    total = {k: sum(part[k] for part in parts) for k in ('scenarios', 'ticks', 'sounds', 'texts', 'skipped', 'paused_ticks', 'finished', 'music', 'instructions')}
    phases = [sum(part['phases'][i] for part in parts) for i in range(7)]
    sprites = sorted(set().union(*(part['sprites'] for part in parts)))
    assert total['scenarios'] == scenarios and all(phases) and total['finished'] > scenarios//2
    report = dict(status='passed', elf_sha256=ORIGINAL, asset=NAME, asset_sha256=hashlib.sha256(asset).hexdigest(),
                  tally_scenarios=total['scenarios'], tally_ticks=total['ticks'], ticks_per_phase=phases,
                  finished_scenarios=total['finished'], sound_requests=total['sounds'], music_release_calls=total['music'],
                  compared_text_draws=total['texts'], ticks_with_skip_bits=total['skipped'], paused_ticks=total['paused_ticks'],
                  panel_sprite_calls_per_tick=sprites,
                  whole_14e838=scores['award'], whole_14e8d8=scores['finish'], tail_slices_157a74=scores['body_slices'],
                  tail_slices_157b84=scores['object_slices'], tail_slices_1578d4=scores['finish_slices'],
                  whole_1b9838=scores['digits'], whole_1407d0=scores['seconds'], whole_1ba148=scores['blink'],
                  original_instructions=total['instructions']+scores['instructions'],
                  scope='Whole 1c7ce8 (task 112670, 1c7d48, 1c7e00), whole handler 1c7f08 called directly once per frame '
                        '(not through the scheduler 112838), 1c9810/1c9820, 1c87e0/1c87f0 and 1c7d20, with every callee '
                        'executed: no instruction is patched or stubbed. GS submission is suppressed by the game flag '
                        '3ec73c=1 and the sound driver is idle (345188=0); 1e7b70, 1e7a78 and the 113028 text arguments '
                        'are observed read-only. Each tick compares 582940..582994, battle timer 0, both HUD life '
                        'records (8 words), gameData+0x90/+0xa4, sound and music-release counts and every text draw '
                        '(string, x, y, colour). Whole 14e838, 14e8d8, 1b9838, 1407d0 and 1ba120/1ba148. The kind '
                        'selection of 157a58, 157b50 and the finish class of 1576e8 are explicit tail slices with '
                        'the classifier result register preset (14dac8/14dc00 are not executed); they are not '
                        'whole-function evidence. Panel sprites are counted, not compared.')
    REPORT.write_text(json.dumps(report, indent=2)+'\n'); print(report)

if __name__ == '__main__':main()
