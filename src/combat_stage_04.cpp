#include "combat_stage_04.hpp"
#include "game_random.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations at 532628..532820 after 1a7350. Picture 256 hides the row.
constexpr R fast[]{{0,3072},{1,3072},{2,3072}};                                         // 532628
constexpr R slow[]{{0,4608},{1,4608},{2,4608}};                                         // 532648
constexpr R row19[]{{0,6144},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,6144},{1,3072},{2,3072}}; // 532668
constexpr R row20[]{{0,3072},{1,3072},{0,3072},{0,3072},{1,3072},{0,6144}};             // 5326b8
constexpr R row21[]{{0,6144},{1,3072},{2,3072},{3,3072}};                               // 5326f0
constexpr R row22[]{{0,3072},{1,3072},{0,3072},{0,3072},{1,3072},{1,3072}};             // 532718
constexpr R row25[]{{0,3072},{1,3072},{2,3072},{3,3072}};                               // 532750
constexpr R row26[]{{0,3072},{1,3072},{2,3072},{0,6144},{1,3072},{2,3072}};             // 532778
constexpr R row29[]{{0,7680},{1,3072},{2,256},{2,256},{2,256},{2,1536},{3,3072}};       // 5327b0
constexpr R row30[]{{256,7680},{256,3072},{256,256},{0,256},{1,256},{256,1536},{256,3072}}; // 5327f0
struct Binding { unsigned row; std::span<const R> timeline; };
const Binding bindings[]{
    {2,slow},{3,fast},{5,slow},{6,fast},{7,fast},{8,fast},{10,slow},{11,slow},{12,fast},{15,fast},{16,fast},
    {19,row19},{20,row20},{21,row21},{22,row22},{25,row25},{26,row26},{29,row29},{30,row30}};
// 6531a8: sway amplitudes selected by the library RNG.
constexpr float amplitudes[5]{10,15,20,25,30};
// Row 27 (prologue type 2, 1abbc0) multiplies the shadow skew 510ce4/510ce8
// by its words +40/+44 for its own shadow only.
constexpr unsigned skewedRow=27;
constexpr float skewFactorX=1,skewFactorY=3;

// 1a5ba0: shift the projection; the horizon term keeps Y clamped at 120.
void shift(StageCamera& c,F dx,F dy) {
    const F y=scalar(c.projectionY).add(dy);
    const F ratio=scalar(c.depth).sub(scalar(c.depthOffset)).div(scalar(c.depth));
    c.projectionX=number(scalar(c.projectionX).add(dx));
    c.projectionY=number(y);
    const F floor=y.less(scalar(120))?scalar(120):y;
    c.verticalOffset=number(neg(y).mul(ratio).add(floor.sub(scalar(120)).mul(ratio)));
}
// 113be0: a screen rectangle whose sort key is the bare order number
// (114d78), so it lies behind every Z-keyed strip.
void backdrop(Projector& r,unsigned slot,F x,F y,F w,F h,F u,F v,F uw,F vh) {
    const F x1=x.add(w),y1=y.add(h);
    const auto below=[](F a){return number(a)<0;};
    // 114e98
    if((below(x)&&below(x1))||(number(x)>640&&number(x1)>640)||(below(y)&&below(y1))||(number(y)>480&&number(y1)>480))return;
    const float key=float(r.counter++);
    const F ts=scalar(slot==4||slot==5?1.f/1024.f:1.f/512.f); // 5dd448
    const F u0=u.mul(ts),v0=v.mul(ts),u1=u0.add(uw.mul(ts)),v1=v0.add(vh.mul(ts));
    CombatStageStrip strip{slot,r.color,key,{},r.mode};
    strip.vertices={{number(x),number(y),number(u0),number(v0)},{number(x),number(y1),number(u0),number(v1)},
                    {number(x1),number(y),number(u1),number(v0)},{number(x1),number(y1),number(u1),number(v1)}};
    r.strips.push_back(std::move(strip));
}
}

void CombatStage04State::reload(const CombatStage04State& previous) {
    // 5331b0 guards only the row clocks (1ab0e8), but the constructor resets
    // none of the sway and sea state either; the meshes it rebuilds are constant.
    *this=previous;
}

void CombatStage04State::visit(uint32_t delta,GameRandom& random) {
    // 1ab594: a new amplitude is drawn whenever the phase is exactly zero,
    // even on a paused visit.
    if(swayClock==0) {
        swayFrom=std::bit_cast<uint32_t>(amplitudes[swayIndex]);
        swayIndex=int32_t(((random.nextLibrary()&0x7fff)*5)>>15);
        swayTo=std::bit_cast<uint32_t>(amplitudes[swayIndex]);
    }
    phase=swayClock;
    // The first quarter of the period blends the old amplitude into the new one.
    const F from{swayFrom},to{swayTo};
    level=from.add(to.sub(from).mul(F::integer(swayClock<0x4001?swayClock:0x4000)).mul(scalar(1.f/16384.f))).bits;
    {
        int32_t t=std::bit_cast<int32_t>(uint32_t(swayClock)+(delta&0xffffffu));
        t-=((t<0?t+0xffff:t)>>16)<<16;
        swayClock=t;
    }
    seaFrame=unsigned(seaClock/0x1e00);
    seaClock=std::bit_cast<int32_t>(uint32_t(seaClock)+delta);
    if(seaClock>0xb3ff)seaClock=std::bit_cast<int32_t>(uint32_t(seaClock)-0xb400u);
    for(unsigned n=0;n<clocks.size();++n) {
        advanceStageClock(clocks[n],bindings[n].timeline,delta);
        pictures[bindings[n].row]=uint16_t(clocks[n].picture);
    }
}

void drawCombatStage04(Projector& r,const StageCommandGroups& groups,const CombatStage04State& state,const AngleTrig& trig) {
    const StageCamera saved=r.projection.camera;
    {
        const F to{state.swayTo};
        const F dx=to.mul(F{trig.cosine(uint32_t(state.phase+0x3fff))});
        const F dy=to.mul(F{trig.sine(uint32_t(state.phase<<1))}).add(F{state.level});
        shift(r.projection.camera,dx,dy);
    }
    const auto rows=[&](unsigned first,unsigned last) {
        for(unsigned row=first;row<last;++row) {
            const unsigned picture=state.pictures[row];
            if(picture&0x100)continue;
            if(row==skewedRow) {
                const float x=r.shadowSkewX,y=r.shadowSkewY;
                r.shadowSkewX=number(scalar(x).mul(scalar(skewFactorX)));
                r.shadowSkewY=number(scalar(y).mul(scalar(skewFactorY)));
                r.run(groups[1+row].at(picture));
                r.shadowSkewX=x;
                r.shadowSkewY=y;
            } else r.run(groups[1+row].at(picture));
        }
    };
    r.mode=0;
    r.run(groups[0].at(state.seaFrame)); // 1a5890 on sea mesh 5331d0 + frame * 2bd4
    {
        // 1ab748: the sky fills the screen down to the projected horizon.
        const F horizon=r.projection.point(scalar(0),scalar(-10),r.projection.scale(25000))[1];
        const F rows512=horizon.mul(scalar(0.7999999523162842f));
        backdrop(r,6,scalar(0),scalar(0),scalar(640),horizon,scalar(0),scalar(318).sub(rows512),scalar(512),rows512);
    }
    r.mode=1;
    rows(0,1);
    r.run(groups[33].front());
    rows(1,13);
    r.projection.camera=saved;
    const auto& beach=groups[34].front();
    r.mode=0;
    r.run(std::span(beach).first(1));
    r.mode=1;
    r.run(std::span(beach).subspan(1));
    rows(13,CombatStage04State::rowCount);
}
}
