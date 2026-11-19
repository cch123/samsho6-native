#!/usr/bin/env python3
"""PS2 and native CPU knockdown callbacks, then pad-only full matches on each seat and spirit."""
from itertools import product
import json
import struct
import subprocess
import tempfile
from pathlib import Path

from knockdown_oracle import ASSETS, CTX, ROOT, fixture
from mips_probe import signed
from validate_knockdown import FIELDS, main as compare_fall
from validate_dash_motion import ELF, PIN, digest

BUILD = ROOT / 'work/ss6/build-native'
REPORT = ROOT / 'outputs/ss6-feasibility/cpu_knockdown_battle.json'


def standard_spirit_falls(command, snapshot):
    traces = []
    for spirit, dead in product(range(6), (False, True)):
        direction = spirit % 2
        command('reset')
        command('flags', 0x10000000 | (direction << 19), 0x340, 0, 0x1000 | (int(dead) << 7), 0, 0, 0)
        command('motion', 4096, 12345, 256, 8192, -16384, -512, 320, -2)
        command('state', 2, 63)
        command('input', 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 400, spirit, 0)
        command('choice', 0, 0)
        command('heavy')
        command('commit')
        transitions = []
        holding = 0
        phased = []
        for frame in range(260):
            for op in ('animate', 'move'):
                command(op, 256)
            command('callback')
            command('commit')
            phase = snapshot()[0]
            if not phased or phased[-1][1] != phase:
                phased.append((frame + 1, phase))
            table, index = snapshot()[9:11]
            if table != -1:
                transitions.append([frame + 1, table, index])
                if table == 0:
                    break
                assert table == 2 and index in (7, 16), (spirit, transitions)
                command('state', table, index)
                command('down' if index == 16 else 'rise')
                command('commit')
            if phase == 9:
                # The KO callback must keep the displayed landing frame past completion.
                holding += 1
                if holding == 10:
                    break
        else:
            raise AssertionError((spirit, dead, phased))
        assert [row[2] for row in transitions] == ([16] if dead else [16, 7, 0]), (spirit, dead, transitions)
        assert holding == (10 if dead else 0)
        traces.append(dict(spirit=spirit, ko=dead, steps=frame+1, phases=phased, requests=transitions))

    # Recovery is sampled on descent only. The same CPU pad edge chooses a different
    # 0/54 or 0/55 roll depending on the original unmerged BACK predicate.
    for spirit, back in product(range(6), (0, 1)):
        command('reset')
        command('flags', 0x10000000, 0x200, 0, 0x1000, 0, 0, 0)
        command('motion', 0, 0, 0, 0, -256, 0, 320, 20)
        command('state', 2, 63)
        command('input', 1, back, 0, 1, 0, 0, 0, 0, 0, 0, 0, 400, spirit, 0)
        command('choose')
        assert snapshot()[8] == 1 + back
        command('input', 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 400, spirit, 0)
        command('choose')
        command('request')
        assert snapshot()[9:11] == [0, 54 + back]
    return dict(falls=traces, recovery_inputs=12)


def standard_knockouts():
    phases = {0: 0, 0x172be8: 1, 0x172c50: 2, 0x172cb0: 3, 0x169a50: 4}
    commands, expected, summaries = [], [], []
    for spirit in range(6):
        p, actor, obj, _battle = fixture()
        p.write(actor+0xa20, 1, 4)
        # The KO probe keeps the original object's creation flag and adds the shared mute bit.
        p.write(obj+0x104, 0x40000200, 4)
        p.write(actor+0x10c, spirit, 4)
        # The six cases cover all three ground variants with two airborne overrides.
        variant = spirit % 3
        airborne = spirit in (2, 4)
        flags = 0x1080 | (int(airborne) << 4)
        p.write(actor+0x23c, 0x1080, 4)
        def original(fn, *args):
            p.run(fn, list(args), limit=500000)
        def emit(op, *args, dust=0):
            commands.append(' '.join(map(str, (op, *args))))
            expected.append([p.read(actor+0x23c, 4), phases[p.read(actor+0x260, 4)], dust, *[
                signed(p.read(obj+offset, 4), 32) if 0x4c <= offset < 0x64
                else p.read(obj+offset, 2 if offset == 0xfe else 4) for offset in FIELDS]])
        emit('reset')
        motion = (4096,12345,256,8192,-16384,-512,320,64 if airborne else -2)
        for offset, value in zip(range(0x4c,0x64,4), motion[:6]):
            p.write(obj+offset, value, 4)
        for offset, value in zip((0x40,0x44), motion[6:]):
            p.write(obj+offset, struct.unpack('<I', struct.pack('<f', value))[0], 4)
        emit('motion', *motion)
        p.write(actor+0x23c, flags, 4)
        original(0x172b38, CTX, variant)
        original(0x149918, actor)
        emit('begin', flags, variant)
        original(0x11d8e0, obj)
        emit('commit')
        changes = []
        dust_frames = []
        for frame in range(180):
            p.write(obj+0x30, 256, 4)
            original(0x11d730, obj)
            emit('animate', 256)
            original(0x11d6c8, obj)
            emit('move', 256)
            pool = p.read(0x46a904, 4)
            cb = p.read(actor+0x260, 4)
            original(0x168aa0, CTX)
            original(cb, CTX)
            dust = pool - p.read(0x46a904, 4)
            emit('callback', dust=dust)
            phase = phases[p.read(actor+0x260, 4)]
            if not changes or phase != changes[-1][1]:
                changes.append((frame+1, phase))
            if dust:
                dust_frames.append(frame+1)
            if phase == 4 and frame + 1 > changes[-1][0] + 10:
                break
        assert [v[1] for v in changes] == [1,2,3,4] and len(dust_frames) == 1, (spirit, changes, dust_frames)
        summaries.append(dict(spirit=spirit, air=airborne, variant=variant, updates=frame+1,
                              phases=changes, landing_effect=dust_frames[0]))
    result = subprocess.run([BUILD/'ss6-knockout-probe', ASSETS], input='\n'.join(commands)+'\n', text=True,
                            capture_output=True, check=True)
    actual = [list(map(int,row.split())) for row in result.stdout.splitlines()]
    assert len(actual) == len(expected)
    for n, (a,e) in enumerate(zip(actual, expected)):
        assert a == e, (n, commands[max(0,n-3):n+1], [(j,x,y) for j,(x,y) in enumerate(zip(a,e)) if x!=y])
    return dict(cases=summaries, snapshots=len(actual))


BATTLE_DRIVER = r'''
#include "native_match.hpp"
#include <cstdlib>
#include <iostream>
using namespace ss6;

int main(int argc, char** argv) {
    const unsigned seat=std::stoul(argv[2]), spirit=std::stoul(argv[3]);
    std::array<unsigned,2> styles{};
    styles[seat]=spirit;
    NativeMatch fight(argv[1],60,VersusMode::FixedMatch,nullptr,styles);
    fight.enableCpu(seat,3);
    unsigned prevButtons=0, prevState=~0u;
    bool oldDead=false;
    for(unsigned tick=0; tick<24000; ++tick) {
        const auto& cpu=fight.fighter(seat);
        const auto& human=fight.fighter(1-seat);
        const unsigned forward=human.actor.x>cpu.actor.x ? 64 : 128;
        const unsigned buttons=(tick%57)%7==2 ? 1024 : forward;
        std::array<NormalizedPadSample,2> pads{};
        pads[1-seat]={buttons, buttons&~prevButtons};
        prevButtons=buttons;
        fight.tick(pads);
        const auto& b=fight.battle();
        const auto& a=cpu.actor;
        const bool dead=a.flags23c&0x80;
        if(prevState!=a.state194 || dead!=oldDead) {
            std::cout<<"state "<<tick<<' '<<b.match.roundIndex<<' '<<a.stateTable()<<' '<<a.stateIndex()
                     <<' '<<a.fieldA30<<' '<<human.hits<<' '<<dead<<' '<<a.y<<'\n';
            prevState=a.state194;
            oldDead=dead;
        }
        if(fight.finished) {
            std::cout<<"result "<<tick<<' '<<unsigned(b.resultScreen.scene)<<' '<<b.resultScreen.winner
                     <<' '<<b.match.players[0].wins<<' '<<b.match.players[1].wins<<'\n';
            return 0;
        }
    }
    std::cerr<<"Match did not reach a result scene\n";
    return 1;
}
'''


def completed_battles():
    matches = []
    with tempfile.TemporaryDirectory(prefix='ss6-cpu-knockdown-') as tmp:
        src, exe = Path(tmp)/'battle.cpp', Path(tmp)/'battle'
        src.write_text(BATTLE_DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',src,BUILD/'libss6-runtime.a',
                        '-o',exe], check=True)
        for seat, spirit in product(range(2), range(6)):
            rows = subprocess.check_output([exe, ASSETS, str(seat), str(spirit)], text=True).splitlines()
            label, ticks, scene, winner, p1, p2 = rows.pop().split()
            ticks, scene, winner, p1, p2 = map(int, (ticks, scene, winner, p1, p2))
            assert label == 'result' and scene == 0x135e30 and (p1,p2)[winner] == 2, (seat,spirit,scene,winner,p1,p2)
            falls, kos = [], []
            falling = None
            was_dead = False
            for row in rows:
                label, tick, rnd, table, state, life, hits, dead, y = row.split()
                tick, rnd, table, state, life, hits, dead = map(int,(tick,rnd,table,state,life,hits,dead))
                if dead and not was_dead:
                    assert life == 0, (seat,spirit,tick,life)
                    kos.append(dict(round=rnd, tick=tick, state=[table,state]))
                was_dead = dead
                if falling is not None and (dead or falling['round'] != rnd):
                    falling = None
                if table == 2 and state == 63 and life > 0 and hits:
                    falling = dict(round=rnd, hit=tick, life=life)
                elif falling is not None:
                    if table == 2 and state == 16:
                        falling['down'] = tick
                    elif table == 2 and state == 7 and 'down' in falling:
                        falling['rise'] = tick
                    elif table == 0 and state in (0,1,4,5) and 'rise' in falling:
                        falling['standing'] = tick
                        falls.append(falling)
                        falling = None
            matches.append(dict(cpu_seat=seat+1, spirit=spirit, ticks=ticks+1, score=[p1,p2],
                                winner=winner+1, result_scene=hex(scene), land_and_rise=len(falls),
                                first_recovery=falls[0] if falls else None, cpu_kos=kos))
    for m in matches:
        assert m['land_and_rise'] and m['cpu_kos'], (m['cpu_seat'], m['spirit'], m['score'])
    return matches


if __name__ == '__main__':
    assert digest(ELF) == PIN
    report = dict(elf_sha256=PIN, native_library_sha256=digest(BUILD/'libss6-runtime.a'),
                  matchup='Haohmaru mirror, stage 0, round timer 60, CPU level 3, game difficulty 4',
                  standard_falls=compare_fall(63,scenarios=standard_spirit_falls),
                  standard_knockouts=standard_knockouts(), native_matches=completed_battles())
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{report['standard_falls']['snapshots']} fall and {report['standard_knockouts']['snapshots']} KO snapshots, "
          f"{len(report['native_matches'])} native matches to the winner screen")

