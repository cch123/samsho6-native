"""Test the Japanese Issen backdrop, next-tick stage suppression and fighter tints."""
from functools import lru_cache
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from extract_versus_draw_stage import capture, prepare
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_ten_explosion import scenario

LIB = ROOT / 'work/ss6/build-native/libss6-runtime.a'
REPORT = ROOT / 'outputs/ss6-feasibility/issen_backdrop_validation.json'
BLACK, WHITE = 0xff000000, 0xffffffff

DRIVER = r'''
#include "native_match.hpp"
#include <iostream>
int main(int argc,char** argv) {
    std::array<unsigned,2> spirits{};
    spirits.at(std::stoi(argv[2]))=3;
    ss6::NativeMatch match(argv[1],-1,ss6::VersusMode::Console,nullptr,spirits);
    unsigned count;
    std::array<unsigned,2> held{},prev{};
    while(std::cin>>count>>held[0]>>held[1])while(count--) {
        std::array<ss6::NormalizedPadSample,2> pads;
        for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~prev[i]};
        prev=held;match.tick(pads);
        const auto& battle=match.battle();
        const auto& stage=match.combatStage();
        std::cout<<match.updates<<' '<<battle.flags138<<' '<<battle.timers.values[4]
                 <<' '<<match.battleBackdropColor()<<' '<<stage.suppressGeometry;
        for(unsigned i=0;i<2;++i) {
            const auto& f=match.fighter(i);
            std::cout<<' '<<f.actor.state194<<' '<<f.actor.fieldA2c<<' '<<f.body.color8c;
        }
        std::cout<<'\n';
    }
}
'''


def original_packets():
    p = prepare()
    b, actors = 0x1920000, 0x1940000
    p.write(0x4d3d08, actors, 4)
    p.write(0x4d3d00, b, 4)

    @lru_cache(None)
    def draw(flags, timer):
        p.write(b + 0x138, flags, 4)
        p.write(b + 0x124, timer, 4)
        for i in range(2):
            p.write(actors + i * 0xf2c + 0xa2c, 2+i, 4)
        # This write at 140140 precedes the actor queue. Start at the
        # subsequent selection after the original has collected that queue.
        p.write(0x50e04c, 0, 4)
        colors = []

        def record(pc):
            if pc != 0x114c10:
                return
            ptr, count, kind = p.registers[4:7]
            assert (count, kind) == (4, 1)
            vertices = [struct.unpack_from('<3fI', p.memory, ptr+16*i) for i in range(4)]
            color = vertices[0][3]
            assert vertices == [(x,y,9995756.,color) for x,y in ((0,0),(0,480),(640,0),(640,480))]
            colors.append(color)

        p.run(0x1401e0, stop_before=[0x141dd0], observe=record)
        poses = tuple(p.read(actors + i*0xf2c + 0xa2c,4) for i in range(2))
        assert len(colors) <= 1 and p.read(0x50e04c,4) == bool(colors)
        return (colors or [0])[0], poses

    # Timer 4 has higher priority even when Issen is active. A white
    # backdrop alone overwrites the two different incoming color selectors.
    assert draw(0x10, 0) == (WHITE, (7, 7))
    assert draw(0x10, 0x100) == draw(0, 0x100) == (BLACK, (2, 3))
    assert draw(0, 0) == (0, (2, 3))
    return draw


def original_stage():
    p = prepare()
    states = [p.read(p.read(0x513138+72*i+0x28,4),4) for i in (1,2,15,16,18,21,22)]
    counts = []
    for tick, flag in enumerate((0,1,1,0), 1):
        p.write(0x50e04c, flag, 4)
        counts.append(len(capture(p)))
        assert [p.read(state,4) for state in states] == [tick*256]*7
    assert counts == [137,0,0,137]
    return counts


def original_release(slot):
    p = prepare()
    actors = [0x1920000, 0x1920f2c]
    bodies = [0x1940000, 0x1941000]
    ctx = 0x1930000
    for i,(actor,body) in enumerate(zip(actors,bodies)):
        p.memory[actor:actor+0xf2c] = bytes(0xf2c)
        p.memory[body:body+0x140] = bytes(0x140)
        for offset,value in ((0,body),(0x194,0x260001 if i==slot else 0x3a0002),
                             (0xa2c,7),(0x10c,3 if i==slot else 0)):
            p.write(actor+offset,value,4)
    p.write(ctx,actors[1-slot],4)
    p.write(ctx+4,actors[slot],4)
    # On the terminal visit the victim requests the downed state and clears
    # the attacker's tint. 140410 visits P1 before P2, including 14b190.
    for i in range(2):
        if i != slot:
            p.registers[16] = ctx
            p.write(0x1fff008,0x1ffff00,8)  # Return address of the callback's caller.
            p.run(0x172ad8)
        p.run(0x14b190,[actors[i]])
    return [p.read(actors[i]+0xa2c,4) for i in range(2)], [p.read(b+0x8c,4) for b in bodies]


def run(exe, draw, slot, name):
    if name == 'skip':
        segments = [(70,0,0),(1,0,8) if slot else (1,8,0),(75,0,0)]
    else:
        pre, pads = scenario(slot, name)
        segments = pre + pads
    inputs = ''.join('%d %d %d\n'%s for s in segments)
    result = subprocess.run([exe,ASSETS,str(slot)],input=inputs,text=True,capture_output=True,check=True)
    rows = [list(map(int,row.split())) for row in result.stdout.splitlines()]
    previous = 0
    white, black, suppressed = [], [], []
    for row in rows:
        tick, flags, timer, color, hidden = row[:5]
        expected, poses = draw(flags&0x10, timer)
        assert color == expected and hidden == bool(previous), (slot,name,row,hex(previous))
        if hidden:
            suppressed.append(tick)
        if color == WHITE:
            assert tuple(row[6::3]) == poses == (7,7)
            if previous == WHITE:
                assert row[7::3] == [BLACK,BLACK], (slot,name,row)
            else:
                assert all(c != BLACK for c in row[7::3]), (slot,name,row)
            white.append(tick)
        if color == BLACK:
            black.append(tick)
        previous = color
    if name == 'late':
        assert white == list(range(1334,1517)) and suppressed == list(range(1335,1518))
        assert rows[1516][3] == 0 and rows[1516][4] == 1 and rows[1517][4] == 0
        assert (rows[1516][6::3], rows[1516][7::3]) == original_release(slot)
        assert rows[1517][6::3] == [0,0] and rows[1517][7::3] == [0xff808080]*2
    elif name == 'skip':
        assert black == [72,73,74,75] and suppressed == [73,74,75,76] and not white
    else:
        assert not white and not black
    return dict(player=slot+1, case=name, ticks=len(rows), white=[white[0],white[-1]] if white else [],
                black=black, suppressed=[suppressed[0],suppressed[-1]] if suppressed else [])


def main():
    assert digest(ELF) == PIN
    draw = original_packets()
    with tempfile.TemporaryDirectory() as td:
        source, exe = (Path(td)/n for n in ('source.cpp','probe'))
        source.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-I',ROOT/'src',source,LIB,'-o',exe],check=True)
        cases=[run(exe,draw,slot,name) for slot in range(2) for name in ('late','guard','miss','skip')]
    report=dict(status='passed', elf_sha256=PIN, runtime_sha256=digest(LIB), cases=cases,
                stage_strips=original_stage(), source_z=9995756,
                source='1401e0..141dd0 decision and full 1419b0/1145c0 rectangle, 1493b8 color writes, entire stage 1a7810')
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
