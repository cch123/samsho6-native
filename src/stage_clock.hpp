#pragma once
#include <bit>
#include <cstdint>
#include <span>

namespace ss6 {
// One frame-animation descriptor created by 1a7290 for an object row with
// flag 0x100. Rows that reference the same descriptor advance it once each.
struct StageClock {
    int32_t elapsed=0;      // +0, 8.8 ticks inside the current record
    unsigned picture=0;     // +4
    unsigned step=0;        // +2c
};
struct StageClockRecord { int picture; int32_t duration; };

// The row prologue shared by the stage tasks (1a7ce8, 1a93d0, ...). The
// remainder carries over but at most one record is consumed per visit, so an
// expired record can still change picture at delta zero. A negative picture
// terminates the table and restarts at record zero.
inline void advanceStageClock(StageClock& clock,std::span<const StageClockRecord> timeline,uint32_t delta) {
    const int32_t duration=timeline[clock.step].duration;
    if(clock.elapsed>=duration) {
        clock.elapsed-=duration;
        if(++clock.step==timeline.size())clock.step=0;
    }
    clock.picture=unsigned(timeline[clock.step].picture);
    clock.elapsed=std::bit_cast<int32_t>(uint32_t(clock.elapsed)+delta);
}
}
