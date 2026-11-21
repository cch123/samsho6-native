#include "combat_stage_07.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// Durations at 56af10..56b0e0 after 1a7350 scaled them to 8.8 ticks.
constexpr R row7[]{{0,3072},{1,3072},{2,3072},{3,3072},{0,3072},{0,3072},{1,3072},{2,3072},{3,3072},{0,6144}};
constexpr R row8[]{{0,7680},{1,3072},{2,3072},{0,9216},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072}};
constexpr R row10[]{{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,6144},{1,3072},{2,3072},{0,6144}};
constexpr R row12[]{{0,7680},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,6144},
                    {0,3072},{1,3072},{2,6144}};
constexpr R row13[]{{0,15360},{1,3072},{2,3072},{1,3072},{0,6144},{0,3072},{1,3072},{2,3072}};
constexpr R row14[]{{0,46080},{1,3072},{2,3072}};
constexpr R row16[]{{0,3072},{1,3072},{2,3072},{1,3072},{0,3072}};
struct Binding { unsigned row; std::span<const R> timeline; };
const Binding bindings[]{{7,row7},{8,row8},{10,row10},{12,row12},{13,row13},{14,row14},{16,row16}};

// 1afbe8..1afcf4 (A) and 1afd20..1afe10 (B): wait on the ground until the
// timer reaches 0x1400, then follow a parabola until the height turns negative.
void hop(CombatStage07State::Hopper& o,uint32_t delta) {
    if(o.timer<0x1400) {
        o.timer=std::bit_cast<int32_t>(uint32_t(o.timer)+delta);
        // Picture 3 during the first ten ticks after landing, then 0.
        o.picture=o.timer/0xa00==0?3:0;
        return;
    }
    o.clock=std::bit_cast<int32_t>(uint32_t(o.clock)+delta);
    // 6536f4 = 1/256, 6536fc = 3, 6536f8 = 0.1; MULA then MSUB.
    const F t=F::integer(o.clock).mul(scalar(0.00390625f));
    const F rise=t.mul(scalar(3));
    const F height=rise.sub(t.mul(scalar(0.10000000149011612f)).mul(t));
    // A paused visit recomputes the height for the picture but keeps the
    // stored one, which alone decides the landing.
    if(delta)o.height=height.bits;
    o.picture=height.less(scalar(0))?2:1;
    if(F{o.height}.less(scalar(0))) {
        o.height=0;
        o.timer=0;
        o.clock=0;
    }
}
}

void CombatStage07State::reload(const CombatStage07State& previous) {
    // 56ac38 guards 1af510 (row descriptors) and 1af7f0 (hopper pictures).
    // 1af99c..1afa34 clear and seed the hoppers on every load.
    clocks=previous.clocks;
    pictures=previous.pictures;
    a={0,0xa00};
    b={0xf00,0x1400};
}

void CombatStage07State::visit(uint32_t delta,GameRandom&) {
    for(unsigned n=0;n<clocks.size();++n) {
        advanceStageClock(clocks[n],bindings[n].timeline,delta);
        pictures[bindings[n].row]=uint8_t(clocks[n].picture);
    }
    hop(a,delta);
    hop(b,delta);
}

namespace {
// 1a6d90: a multi-piece picture stretched between two projected world
// points. Every piece goes through 113f98 (cull, then an order number); its
// depth argument is the third 123020 output, 30000 - z (5df4dc).
void stretched(Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const auto& header=cmd.pieces.front();
    const F scale=r.projection.scale(p[4]);
    const auto from=r.projection.point(scalar(p[0]),scalar(p[1]),scale);
    const auto to=r.projection.point(scalar(p[2]),scalar(p[3]),scale);
    const float z=number(scalar(30000).sub(scalar(p[4])));
    const F dx=to[0].sub(from[0]),dy=to[1].sub(from[1]);
    const F w=scalar(header[2]),h=scalar(header[3]);
    const unsigned callerMode=r.mode;
    for(size_t i=cmd.pieces.size()!=1?1:0;i<cmd.pieces.size();++i) {
        const auto& pc=cmd.pieces[i];
        const F x=from[0].add(scalar(pc[0]-header[0]).mul(dx).div(w));
        const F y=from[1].add(scalar(pc[1]-header[1]).mul(dy).div(h));
        r.mode=int(pc[4])&0x200?0:1;
        r.rectangle(cmd.slot,z,x,y,dx.mul(scalar(pc[2])).div(w),dy.mul(scalar(pc[3])).div(h),
                    scalar(pc[0]),scalar(pc[1]),scalar(pc[2]),scalar(pc[3]));
    }
    r.mode=callerMode;
}
// 1a5f68 with the stage's own skew (510ce4 / 510ce8); the shared
// Projector::meshShadow assumes the 0 / 0.1 of the earlier stages.
void meshShadow(Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const auto origin=r.projection.point(scalar(p[0]),scalar(p[1]),r.projection.scale(p[2]));
    const F scale=r.projection.artworkScale(p[2]);
    const F width=scalar(p[3]).mul(scale),height=scalar(p[4]).mul(scale).mul(scalar(r.shadowSkewY));
    const float key=r.depth(p[2]);
    const size_t n=size_t(p[5]);
    for(size_t at=0;at<cmd.pieces.size();at+=n) {
        // 1a607c: the X skew is weighted by the column's first vertex.
        const F left=origin[0].add(height.mul(scalar(r.shadowSkewX)).mul(scalar(cmd.pieces[at][0])));
        CombatStageStrip strip{cmd.slot,r.shadowColor,key,{},1};
        for(size_t i=0;i<n;++i) {
            const auto& v=cmd.pieces[at+i];
            strip.vertices.push_back({number(left.add(width.mul(scalar(v[0])))),
                                      number(origin[1].add(height.mul(scalar(v[1])))),v[3],v[4]});
        }
        r.strips.push_back(std::move(strip));
    }
}
void row(Projector& r,const std::vector<StageCommand>& commands) {
    for(const auto& cmd:commands) {
        if(cmd.kind==3) {
            // The exporter records the skew in force: prologue 2 (1b0188)
            // scales 510ce4 / 510ce8 by row +40 / +44 around the call.
            const float x=r.shadowSkewX,y=r.shadowSkewY;
            r.shadowSkewX=cmd.pieces.at(0)[0];
            r.shadowSkewY=cmd.pieces.at(0)[1];
            r.shadow(cmd);
            r.shadowSkewX=x;
            r.shadowSkewY=y;
        } else if(cmd.kind==5)meshShadow(r,cmd);
        else r.run(std::span(&cmd,1));
    }
}
StageCommand shadowOf(const StageCommand& sprite,F x,float y,F z) {
    const auto& header=sprite.pieces.front();
    return {3,sprite.slot,{number(x),y,number(z),header[0],header[1],header[2],header[3]},{}};
}
StageCommand raised(const StageCommand& sprite,uint32_t height) {
    StageCommand cmd=sprite;
    cmd.parameters[1]=number(scalar(sprite.parameters[1]).add(F{height}));
    return cmd;
}
}

void drawCombatStage07(Projector& r,const StageCommandGroups& groups,const CombatStage07State& state,const AngleTrig&) {
    r.shadowColor=0x60000000;                 // 50e048
    r.shadowSkewX=0;                          // 510ce4
    r.shadowSkewY=0.20000000298023224f;       // 510ce8 = 6536bc
    r.mode=0;
    {
        // 1afa9c..1afb68: atlas rectangle 567110 = {0, 0, 1023, 586} of slot 4
        // at Z 3000, anchored at X -2080 and with its bottom edge at Y 201.
        const F scale=r.projection.scale(3000);
        const F stretch=scale.div(scalar(0.11764705181121826f));
        const F x=r.projection.point(scalar(-2080),scalar(0),scale)[0];
        const F y=r.projection.point(scalar(0),scalar(201),scale)[1];
        const F height=scalar(586).mul(stretch);
        r.rectangle(4,30000,x,y.sub(height),scalar(1023).mul(stretch),height,scalar(0),scalar(0),scalar(1023),scalar(586));
    }
    const auto& head=groups[0].front();
    r.run(std::span(head).first(1));          // 1a5868 floor, alpha mode 0
    r.mode=1;
    stretched(r,head.at(1));
    for(unsigned n=0;n<CombatStage07State::rowCount;++n)row(r,groups[1+n].at(state.pictures[n]));
    {
        // Hopper A: 1a5428 shadow one unit behind it, then the raised sprite.
        const auto& art=groups[2+CombatStage07State::rowCount].at(state.a.picture).front();
        const auto& p=art.parameters;
        const F z=scalar(p[2]).add(scalar(1));
        const F x=z.add(scalar(400)).mul(scalar(.0025f)).mul(scalar(p[0]).sub(scalar(320))).add(scalar(320));
        r.shadow(shadowOf(art,x,p[1],z));
        r.sprites(raised(art,state.a.height));
    }
    {
        // Hopper B: 1a4f40 directly at X 608 (6536cc, record +8), no parallax
        // correction; the sprite itself is anchored at 497.23 (653704).
        const auto& art=groups[3+CombatStage07State::rowCount].at(state.b.picture).front();
        const auto& p=art.parameters;
        r.shadow(shadowOf(art,scalar(608),p[1],scalar(p[2])));
        r.sprites(raised(art,state.b.height));
    }
}
}
