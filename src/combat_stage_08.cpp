#include "combat_stage_08.hpp"
#include "game_random.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations at 56ecf8..56ee58 after 1a7350 scaled them.
constexpr R sway[]{{0,3072},{1,3072},{2,3072},{1,3072},{0,3072}};                             // 56ecf8
constexpr R blink[]{{0,512},{1,512},{0,512},{1,512},{0,2560},{0,512},{1,512},{0,2560}};       // 56ed28
constexpr R slowA[]{{0,6144},{1,3072},{2,3072},{1,3072},{0,3072}};                            // 56ed70, 56ee28
constexpr R slowB[]{{0,3072},{1,3072},{2,3072},{1,3072},{0,6144}};                            // 56eda0
constexpr R triple[]{{0,768},{1,768},{2,768},{0,768},{1,768},{2,768},{0,768},{1,768},{2,768},{0,3072}}; // 56edd0
constexpr R nine[]{{0,768},{1,768},{2,768},{3,768},{4,768},{5,768},{6,768},{7,768},{8,768},{0,3072}};   // 56ee58
struct Binding { unsigned row; std::span<const R> timeline; };
const Binding bindings[]{{5,sway},{6,sway},{13,blink},{14,slowA},{15,slowB},{16,triple},{17,slowA},{18,nine}};

// Amplitude choices copied to the stack at 1b08ac / 1b0abc / 1b0c10.
constexpr float swayAmplitudes[]{10,12,15,17,20};   // 6537b8
constexpr float orbitAmplitudes[]{10,15,20,25,30};  // 6537d0, 6537e8
constexpr float bounceLimits[2][2]{{100,300},{50,250}}; // 65383c/653840, 653844/653848
const F perTick=scalar(.00390625f); // 653824

// (rand & 7fff) * 5 >> 15
unsigned pick(GameRandom& random) {return unsigned(((random.nextLibrary()&0x7fff)*5)>>15);}
}

void CombatStage08State::reload(const CombatStage08State& previous) {
    // 1b0298 runs on every load and clears the seven descriptors (1a7290
    // zero-fills d4 bytes) before writing their start values. The row clocks
    // (1b0490, once) and the plain globals 56f46c..56f488 / 131aff0 are kept.
    *this=CombatStage08State{};
    clocks=previous.clocks;
    pictures=previous.pictures;
    swayAmplitude=previous.swayAmplitude;
    visits=previous.visits;
    for(unsigned n=0;n<orbits.size();++n) {
        orbits[n].amplitude=previous.orbits[n].amplitude;
        orbits[n].angle=previous.orbits[n].angle;
    }
}

void CombatStage08State::visit(uint32_t delta,GameRandom& random) {
    // The task converts 46a908 as an unsigned word; the scheduler only
    // publishes small non-negative values, which convert exactly.
    const F step=F::integer(int32_t(delta));
    // Object 0, 1b08d8..1b0ab0.
    if(!swayRolled) {
        swayRolled=true;
        swayAmplitude=scalar(swayAmplitudes[pick(random)]).bits;
    }
    // 1b0944: clock / delta. On a frozen frame the divisor is zero: the EE
    // returns the largest finite value and CVT.W saturates (MODEL, see
    // docs/combat-stages.txt), so the sine argument becomes unit ffff.
    swayAngle=delta?F::integer(swayClock).div(step).truncate():0x7fffffff;
    swayClock=std::bit_cast<int32_t>(uint32_t(swayClock)+(delta<<8));
    if(swayClock>0xffffff) {
        swayRolled=false;
        swayClock-=0x1000000;
    }
    if(++visits%50==0) {
        const int32_t divisor=int32_t(((random.nextLibrary()&0x7fff)*10)>>15)+5;
        riseStep=scalar(1).div(F::integer(divisor)).add(scalar(.3f)).mul(step).mul(perTick).bits;
    }
    {
        F y=F{riseY}.add(F{riseStep});
        if(scalar(1000).less(y))y=scalar(-400);
        riseY=y.bits;
    }
    // Objects 1 and 2, 1b0af0..1b0d34.
    for(unsigned n=0;n<orbits.size();++n) {
        auto& o=orbits[n];
        if(!o.rolled) {
            o.rolled=true;
            o.amplitude=scalar(orbitAmplitudes[pick(random)]).bits;
        }
        orbitAngles[n]=o.angle;
        o.angle=std::bit_cast<int32_t>(uint32_t(o.angle)+((delta<<7)>>8));
        if(o.angle>0xffff) {
            o.rolled=false;
            o.angle-=0x10000;
        }
    }
    // Objects 3 and 4, 1b0d3c..1b0e2c.
    for(unsigned n=0;n<bounceX.size();++n) {
        const F speed{bounceStep[n]},low=scalar(bounceLimits[n][0]),high=scalar(bounceLimits[n][1]);
        F x=F{bounceX[n]}.add(speed.mul(step).mul(perTick));
        if(x.less(low)){x=low;bounceStep[n]=neg(speed).bits;}
        else if(high.less(x)){x=high;bounceStep[n]=neg(speed).bits;}
        bounceX[n]=x.bits;
    }
    // Object 5, 1b0e34..1b0eb0: -0.5 per tick, wraps from -1000 to 1320.
    {
        F x=F{driftX[0]}.add(scalar(-.5f).mul(step).mul(perTick));
        if(x.less(scalar(-1000)))x=scalar(1320);
        driftX[0]=x.bits;
    }
    // Object 6, 1b0eb8..1b0f0c: -0.3 per VISIT (46a908 is not read), wraps
    // from -830 to 1150.
    {
        F x=F{driftX[1]}.add(scalar(-.30000001192092896f));
        if(x.less(scalar(-830)))x=scalar(1150);
        driftX[1]=x.bits;
    }
    // 1b10a0 row prologue, rows 5, 6, 13..18.
    for(unsigned n=0;n<clocks.size();++n) {
        advanceStageClock(clocks[n],bindings[n].timeline,delta);
        pictures[bindings[n].row]=uint8_t(clocks[n].picture);
    }
}

void drawCombatStage08(Projector& r,const StageCommandGroups& groups,const CombatStage08State& state,const AngleTrig& trig) {
    // 1b0790..1b0870: the sky, one 113f98 rectangle of atlas 5 (56e8b0)
    // anchored at world (-1103, 376) on the Z 2001 plane, order key Z 30000.
    r.mode=0;
    {
        const F scale=r.projection.scale(2001);
        const F unit=scalar(0.16659724712371826f); // 653800
        const F x=r.projection.point(scalar(-1103),scalar(0),scale)[0];
        const F stretch=scale.div(unit).mul(scalar(1.2f));
        const F y=r.projection.point(scalar(0),scalar(376),scale)[1];
        const F width=scalar(781).mul(stretch),height=scalar(442).mul(scale.div(unit));
        r.rectangle(5,30000,x,y.sub(height),width,height,scalar(243),scalar(129),scalar(781),scalar(442));
    }
    r.run(groups[0].front()); // 1a5868(5, 32, 4): the floor mesh 50e110
    r.mode=1;
    const auto rows=[&](unsigned first,unsigned end) {
        for(unsigned row=first;row<end;++row)r.run(groups[1+row].at(state.pictures[row]));
    };
    rows(0,3);
    {
        // The seven moving objects; the exported commands carry Z and atlas
        // pieces, X and Y come from the state.
        const auto& moving=groups[2+CombatStage08State::rowCount].front();
        std::array<std::array<F,2>,7> at;
        // 1b0958..1b09a8: 320 - width / 4 + amplitude * sine.
        const F width=scalar(moving[0].pieces.front()[2]);
        at[0]={scalar(320).sub(width.mul(scalar(.25f))).add(F{state.swayAmplitude}.mul(F{trig.sine(uint32_t(state.swayAngle))})),
               F{state.riseY}};
        constexpr float centers[2][2]{{500,82},{160,160}}; // 653830/653834, 653838
        for(unsigned n=0;n<2;++n) {
            const uint32_t angle=uint32_t(state.orbitAngles[n]);
            const F amplitude{state.orbits[n].amplitude};
            at[1+n]={amplitude.mul(F{trig.cosine((angle+0x3fff)&0xffff)}).add(scalar(centers[n][0])),
                     amplitude.mul(F{trig.sine((angle<<1)&0xffff)}).add(scalar(centers[n][1]))};
        }
        at[3]={F{state.bounceX[0]},scalar(260)};
        at[4]={F{state.bounceX[1]},scalar(200)};
        at[5]={F{state.driftX[0]},scalar(455)};
        at[6]={F{state.driftX[1]},scalar(560)};
        for(unsigned n=0;n<7;++n) {
            StageCommand cmd=moving.at(n);
            cmd.parameters[0]=number(at[n][0]);
            cmd.parameters[1]=number(at[n][1]);
            if(n<5)r.sprites(cmd);  // 1a6210
            else r.quarter(cmd);    // 1a6f90
        }
    }
    rows(3,CombatStage08State::rowCount);
}
}
