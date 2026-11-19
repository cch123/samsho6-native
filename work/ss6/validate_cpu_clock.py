#!/usr/bin/env python3
"""Check 151e10's actor/CPU clocks against standard battle inputs and live AI decisions."""
import collections
import json
import subprocess
import tempfile
from pathlib import Path

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from mips_probe import Probe

LIB = ROOT/'work/ss6/build-native/libss6-runtime.a'
REPORT = ROOT/'outputs/ss6-feasibility/cpu_clock_validation.json'

DRIVER = r'''
#include "native_match.hpp"
#include "object_frame.hpp"
#include "cpu_execution.hpp"
#include <functional>
#include <iostream>
#include <set>

namespace ss6 {
namespace {
unsigned activeSeat=0, tick=0;
bool matrix=true;
struct ClockSample {
    int mode,raw,half,paused,delta;
    uint32_t flags;
    std::array<uint32_t,12> gauge;
    int body,actor,cpu;
};
std::array<ClockSample,2> live;
void writeClock(const ClockSample& x) {
    std::cout<<' '<<x.mode<<' '<<x.raw<<' '<<x.half<<' '<<x.flags<<' '<<x.paused<<' '<<x.delta;
    for(const auto word:x.gauge)std::cout<<' '<<word;
    std::cout<<' '<<x.body<<' '<<x.actor<<' '<<x.cpu;
}
}

// The production assignment is invoked inside this observer. Synthetic clocks
// are restored before the live round and AI logic resume.
void inspectCpuClock(unsigned seat,MatchFighter& f,BattleRoundState& b,const std::function<void()>& assign) {
    auto& a=f.actor;
    const auto snapshot=[&]{
        ClockSample x;
        x.mode=b.field140;x.raw=b.timers.rawDelta;x.half=a.timers[1];x.flags=a.flags23c;
        x.paused=b.gauges.paused46a940;x.delta=b.gauges.delta46a908;
        std::copy_n(b.gauges.words910.begin(),12,x.gauge.begin());
        x.body=f.body.delta30;x.actor=a.timerDelta;x.cpu=a.cpuTimerDelta08;
        return x;
    };
    if(matrix) {
        const auto oldG=b.gauges;
        const auto oldTimers=b.timers;
        const auto oldMode=b.field140;
        const auto oldHalf=a.timers[1];
        const auto oldFlags=a.flags23c;
        for(unsigned mode=0;mode<4;++mode)for(unsigned half:{0,1})for(unsigned immune:{0,1})for(int preset=0;preset<14;++preset) {
            auto& g=b.gauges;
            b.field140=mode;b.timers.rawDelta=battleSpeedDelta(mode);
            a.timers[1]=half?256:0;
            a.flags23c=immune?0x08000000:0;
            g={};g.delta46a908=85;
            // P2's bit slows P1. Borrowing reads the *other* seat's view of
            // those same bits, and setting both borrow words disables recursion.
            switch(preset) {
            case 0:break;
            case 1:g.words910[2+seat]=1;break;
            case 2:g.words910[3-seat]=1;break;
            case 3:g.words910[3-seat]=1;g.delta46a908=128;break;
            case 4:g.words910[3-seat]=1;g.delta46a908=0;break;
            case 5:g.words910[3-seat]=1;g.delta46a908=0;g.words910[seat]=5;break;
            case 6:g.words910[3-seat]=1;g.words910[6+seat]=1;break;
            case 7:g.words910[3-seat]=1;g.words910[10+seat]=1;break;
            case 8:g.words910[2+seat]=1;g.words910[10+seat]=1;break;
            case 9:g.words910[3-seat]=1;g.words910[10]=g.words910[11]=1;break;
            case 10:g.words910[2+seat]=1;g.words910[10+seat]=1;g.words910[7-seat]=1;break;
            case 11:g.words910[2+seat]=1;g.words910[10+seat]=1;g.words910[1-seat]=5;g.delta46a908=0;break;
            case 12:g.paused46a940=1;break;
            case 13:g.words910[3-seat]=2;break;
            }
            assign();
            const auto x=snapshot();
            // Use old timers near both bounds to include saturating and clamped visits.
            const uint32_t pre9=preset%2?0x1733d0:0, pre1=preset%3?42:1000;
            const auto saved9=a.controlTimers0c[9],saved1=a.controlTimers0c[1];
            a.controlTimers0c[9]=pre9;a.controlTimers0c[1]=pre1;
            cpuTimerUp(a,9);cpuTimerDown(a,1);
            std::cout<<"matrix "<<seat<<' '<<preset;
            writeClock(x);
            std::cout<<' '<<pre9<<' '<<a.controlTimers0c[9]<<' '<<pre1<<' '<<a.controlTimers0c[1]<<'\n';
            a.controlTimers0c[9]=saved9;a.controlTimers0c[1]=saved1;
        }
        b.gauges=oldG;b.timers=oldTimers;b.field140=oldMode;a.timers[1]=oldHalf;a.flags23c=oldFlags;
        if(seat==1)matrix=false;
    }
    assign();live[seat]=snapshot();
    if(int(b.timers.rawDelta)!=battleSpeedDelta(b.field140)) {
        static std::set<std::pair<int,int>> seen;
        if(seen.insert({b.timers.rawDelta,b.field140}).second) {
            std::cout<<"changed "<<seat<<' '<<tick;
            writeClock(live[seat]);std::cout<<'\n';
        }
    }
}

void inspectCpuDecisionTimers(unsigned seat,const StateEntryActor& a,uint32_t old9,uint32_t old1) {
    static std::set<std::array<unsigned,5>> seen;
    const auto& x=live[seat];
    if(a.cpuTimerDelta08==256 || !seen.insert({seat,unsigned(x.mode),unsigned(x.half!=0),unsigned(a.cpuTimerDelta08),unsigned(a.stateTable())}).second)
        return;
    std::cout<<"live "<<seat<<' '<<tick;
    writeClock(x);
    std::cout<<' '<<old9<<' '<<a.controlTimers0c[9]<<' '<<old1<<' '<<a.controlTimers0c[1]
             <<' '<<a.stateTable()<<' '<<a.stateIndex()<<' '<<a.fieldA30<<'\n';
}
}

int main(int argc,char** argv) {
    using namespace ss6;
    for(activeSeat=0;activeSeat<2;++activeSeat) {
        NativeMatch battle(argv[1],60);
        battle.enableCpu(activeSeat,3);
        uint32_t previous=0;
        for(tick=0;tick<18000 && !battle.finished;++tick) {
            const auto& cpu=battle.fighter(activeSeat).actor;
            const auto& human=battle.fighter(1-activeSeat).actor;
            const uint32_t forward=human.x>cpu.x?64:128;
            const uint32_t buttons=(tick%57)%7==2?1024:forward;
            std::array<NormalizedPadSample,2> pads{};
            pads[1-activeSeat]={buttons,buttons&~previous};previous=buttons;
            battle.tick(pads);
        }
        if(!battle.finished)return 1;
    }
}
'''


def build(tmp):
    tmp = Path(tmp)
    native = (ROOT/'src/native_match.cpp').read_text()
    first = native.index('        auto speed=', native.index('    auxiliaryPhase(ObjectPhase::Move);', native.index('void NativeMatch::tick(')))
    end = native.index('        ground_.prepareInput(',first)
    block = native[first:end]
    assert block.count('a.cpuTimerDelta08=') == 1
    hook = ('        extern void inspectCpuClock(unsigned,MatchFighter&,BattleRoundState&,const std::function<void()>&);\n'
            '        inspectCpuClock(i,f,b,[&]{\n' + block + '        });\n')
    (tmp/'native_match.cpp').write_text(native[:first]+hook+native[end:])
    cpu = (ROOT/'src/cpu_match_control.cpp').read_text()
    site = '    cpuTimerUp(actor,9);\n    if(cpuTimerDown(actor,1))return command();'
    assert cpu.count(site) == 1
    (tmp/'cpu_match_control.cpp').write_text(cpu.replace(site, '''
    extern void inspectCpuDecisionTimers(unsigned,const StateEntryActor&,uint32_t,uint32_t);
    const auto previous9=cpuTimerUp(actor,9);
    const auto previous1=cpuTimerDown(actor,1);
    inspectCpuDecisionTimers(seat,actor,previous9,previous1);
    if(previous1)return command();'''))
    (tmp/'driver.cpp').write_text(DRIVER)
    exe = tmp/'clock'
    subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',tmp/'driver.cpp',tmp/'cpu_match_control.cpp',
                    tmp/'native_match.cpp',LIB,'-o',exe],check=True)
    return exe



def compare(lines):
    p = Probe(ELF.read_bytes())
    battle, base_actor, base_body = 0x1a00000, 0x1c00000, 0x1d00000
    p.write(0x4d3d00,battle,4)
    statistics = collections.Counter()
    branches = collections.Counter()
    live, speed_modes, gauges = [], {}, {}
    for line in lines:
        kind, *values = line.split()
        seat, tag, mode, cached_raw, half, flags, paused, factor, *rest = map(int, values)
        words, expected = rest[:12], rest[12:]
        a, o = base_actor + seat*0xf2c, base_body + seat*0x1000
        p.write(battle+0x140,mode,4)
        p.write(a,o,4)
        p.write(a+0xa24,seat,4)
        p.write(a+0xa20,1,4)
        p.write(a+0x23c,flags,4)
        p.write(a+0x1b4,half,4)
        p.write(0x46a940,paused,4)
        p.write(0x46a908,factor,4)
        for i,word in enumerate(words):
            p.write(0x46a910+4*i,word,4)
        for pointer in (o+0x30,a+0x1ac,a+8):
            p.write(pointer,0xbad00ded,4)
        direct, nested = [], []
        def record_calls(pc):
            if pc == 0x11f450:
                ret = p.registers[31]
                target = nested if ret == 0x11f4dc else direct
                target.append((ret,p.registers[4],p.registers[5]))
        _,instructions = p.run(0x151e10,[a],observe=record_calls)
        statistics['clock_instructions'] += instructions
        assert direct == [(0x14cfd4,expected[0],seat),(0x15dddc,expected[0],seat)], (line,direct)
        assert all(row == (0x11f4dc,256,1-seat) for row in nested), (line,nested)
        should_borrow = not paused and words[10+seat] and not words[11-seat]
        assert len(nested) == 2*bool(should_borrow), (line,nested)
        branches['direct_actor_and_cpu_scaling_calls'] += len(direct)
        branches['recursive_other_seat_scaling_calls'] += len(nested)
        original = [p.read(o+0x30,4),p.read(a+0x1ac,4),p.read(a+8,4)]
        assert original == expected[:3], (line,direct,original)
        if kind == 'changed':
            statistics['clock_phase_changed_before_actor'] += 1
            continue
        prev9,post9,prev1,post1 = expected[3:7]
        p.write(a+0x0c+9*4,prev9,4)
        p.write(a+0x0c+1*4,prev1,4)
        # 158990 returns immediately if timer 1's *old* value was positive.
        # For a zero value, stop just before the first tactical selector; the
        # two elapsed-time operations have already executed inside their real caller.
        observed = []
        def record_timers(pc):
            if pc in (0x1589ac,0x1589b8):
                observed.append(p.registers[2])
        _,instructions = p.run(0x158990,[a+8],stop_before=(0x1589c0,),observe=record_timers)
        statistics['timer_instructions'] += instructions
        assert observed == [prev9,prev1], (line,observed)
        assert [p.read(a+0x0c+9*4,4),p.read(a+0x0c+1*4,4)] == [post9,post1], line
        statistics[kind] += 1
        if kind == 'live':
            table, state, life = expected[7:10]
            live.append(dict(cpu_seat=seat+1, world_update=tag, mode=mode, decision_delta=original[2],
                             actor_delta=original[1], body_delta=original[0], hit_slow_timer=half,
                             timer9_before=prev9, timer9_after=post9, timer1_before=prev1,
                             timer1_after=post1, state=[table,state], hp=life))
        else:
            assert kind == 'matrix'
            if seat==0 and not half and not flags:
                if tag==0:speed_modes[mode]=original[2]
                if mode==0:gauges[tag]=original[2]
    assert statistics['matrix'] == 448 and speed_modes == {0:256,1:128,2:85,3:0}
    assert gauges == {0:256,1:256,2:85,3:128,4:0,5:64,6:256,7:256,8:85,9:85,10:256,11:64,12:0,13:256}
    for seat in (1,2):
        assert any(v['cpu_seat']==seat and v['hit_slow_timer'] and v['state'][0]==2 and
                   v['timer9_after']-v['timer9_before']==v['decision_delta']==128 for v in live), live
    return dict(status='passed',elf_sha256=PIN,native_library_sha256=digest(LIB),statistics=dict(statistics),
                scaling_calls=dict(branches),original_speed_modes=speed_modes,
                gauge_presets=dict(zip(('baseline','own_flag','opponent_flag_85','opponent_flag_128',
                    'opponent_freeze','mode5_freeze_minimum','ignore_opponent','borrow_unaffected_opponent',
                    'borrow_slowed_opponent','both_borrow','borrow_ignoring_opponent','borrow_mode5_minimum',
                    'global_pause','unrelated_flag'),(gauges[i] for i in range(14)))),
                live_cpu_visits=live)


def main():
    assert digest(ELF) == PIN
    with tempfile.TemporaryDirectory(prefix='ss6-cpu-clock-') as tmp:
        exe = build(tmp)
        run = subprocess.run([exe,ASSETS],capture_output=True,text=True,check=True)
    report = compare(run.stdout.splitlines())
    REPORT.write_text(json.dumps(report,indent=2)+'\n')
    print(report['statistics'], report['scaling_calls'])
    for visit in report['live_cpu_visits']:
        print(visit)


if __name__ == '__main__':
    main()

