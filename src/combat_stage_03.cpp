#include "combat_stage_03.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations as 1a7350 leaves them in the tables 51cc38..51ceb8.
constexpr R t38[]{{0,3072},{1,3072},{2,3072},{3,3072},{0,3072},{1,1024},{2,1024},{0,1024},{2,1024},{3,7680}}; // 51cc38
constexpr R t90[]{{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,6144},{1,3072},{2,3072},{0,6144}}; // 51cc90, 51cde0
constexpr R te8[]{{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,6144},{0,3072},{1,3072},{2,3072},{0,6144}}; // 51cce8, 51ce38
constexpr R t48[]{{0,6144},{1,3072},{0,15360},{1,3072},{0,6144}}; // 51cd48
constexpr R t78[]{{0,3072},{1,3072}}; // 51cd78
constexpr R td90[]{{0,6144},{1,3072},{2,3072},{0,6144},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072}}; // 51cd90
constexpr R t98[]{{0,3072},{1,3072},{2,3072}}; // 51ce98
constexpr R tb8[]{{0,3072},{1,3072},{2,3072},{3,3072}}; // 51ceb8
struct Binding { unsigned row; std::span<const R> timeline; };
// Visit order is row order: 1aad60 advances a row's clock just before it
// draws that row. Every animated row owns its clock.
const Binding bindings[]{
    {6,t38},{7,t90},{8,t90},{9,te8},{10,t48},{12,t78},{14,td90},{16,t90},{18,te8},{20,t98},
    {21,t98},{22,t98},{23,td90},{24,td90},{25,td90},{26,td90},{27,tb8},{28,tb8}};

// 1aaa38: the two vertices of one vertical edge of a wall strip. X takes the
// same parallax correction as the sprite helpers; the depth key is 114dc8
// (current order number, not advanced).
void edge(Projector& r,CombatStageStrip& strip,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const float z=p[2];
    const F x=scalar(z).add(scalar(400)).mul(scalar(.0025f)).mul(scalar(p[0]).sub(scalar(320))).add(scalar(320));
    const F art=r.projection.artworkScale(z);
    const auto base=r.projection.point(x,scalar(p[1]),r.projection.scale(z));
    const F height=scalar(p[3]).mul(art);
    const float key=r.depth(z);
    const F v1=scalar(p[5]).add(scalar(p[3]).mul(scalar(1.f/1024.f)));
    strip.vertices.push_back({number(base[0]),number(base[1].sub(height)),p[4],p[5]});
    strip.vertices.push_back({number(base[0]),number(base[1]),p[4],number(v1)});
    strip.depths.push_back(key);
    strip.depths.push_back(key);
}
// 1a55c0 -> 1a6938: a multi-piece sprite scaled by (factor x perspective
// scale) about its projected anchor; every piece goes through 113f98.
void link(Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const auto& header=cmd.pieces.front();
    const auto anchor=r.projection.point(scalar(p[0]),scalar(p[1]),r.projection.scale(p[2]));
    const F s=scalar(p[3]).mul(r.projection.scale(p[2]));
    const F half=scalar(.5f),w0=scalar(header[2]),h0=scalar(header[3]);
    const F y=anchor[1].sub(h0.mul(s).mul(half)),x=anchor[0].sub(w0.mul(s).mul(half));
    const F width=w0.mul(s),height=h0.mul(s),top=y.sub(height);
    const unsigned callerMode=r.mode;
    for(size_t i=cmd.pieces.size()>1?1:0;i<cmd.pieces.size();++i) {
        const auto& pc=cmd.pieces[i];
        const F dy=scalar(pc[1]-header[1]).mul(height).div(h0);
        const F dx=scalar(pc[0]-header[0]).mul(width).div(w0);
        r.mode=int(pc[4])&0x200?0:1;
        r.rectangle(cmd.slot,p[2],x.add(dx),top.add(dy),scalar(pc[2]).mul(s),scalar(pc[3]).mul(s),
                    scalar(pc[0]),scalar(pc[1]),scalar(pc[2]),scalar(pc[3]));
    }
    r.mode=callerMode;
}
}

void CombatStage03State::reload(const CombatStage03State& previous) {
    // 51c920 guards 1a9f30 (the clocks). 1aa118 (floor mesh) and 1a9fa0
    // (four shadow meshes) rebuild constant tables on every load.
    clocks=previous.clocks;
    pictures=previous.pictures;
}

void CombatStage03State::visit(uint32_t delta,GameRandom&) {
    unsigned n=0;
    for(const auto& b:bindings) {
        advanceStageClock(clocks[n],b.timeline,delta);
        pictures[b.row]=uint8_t(clocks[n].picture);
        ++n;
    }
}

void drawCombatStage03(Projector& r,const StageCommandGroups& groups,const CombatStage03State& state,const AngleTrig&) {
    r.shadowSkewX=0;      // 510ce4
    r.shadowSkewY=.2f;    // 510ce8 <- 652fb4
    r.mode=0;
    {
        // 1aa42c..1aa514: the sky, anchored at two world points at Z 4000.
        // Atlas rectangle 51bd20 = {0, 587, 720, 437}.
        const F scale=r.projection.scale(4000);
        const F x=r.projection.point(scalar(-2048),scalar(0),scale)[0];
        const F unit=scale.div(scalar(0.09090908616781235f));
        const F wide=unit.mul(scalar(1.2f));
        const F y=r.projection.point(scalar(0),scalar(282),scale)[1];
        const F height=scalar(437).mul(unit);
        r.rectangle(4,29999,x,y.sub(height),scalar(720).mul(wide),height,scalar(0),scalar(587),scalar(720),scalar(437));
    }
    r.run(groups[0].front());
    r.mode=1;
    const auto rows=[&](unsigned first,unsigned last) {
        for(unsigned row=first;row<last;++row)r.run(groups[1+row].at(state.pictures[row]));
    };
    const auto& tail=groups[1+CombatStage03State::rowCount].front();
    rows(0,3);
    r.run(std::span(tail).first(1));
    for(unsigned n=0;n<4;++n) {
        // Two 1aaa38 edges, then 1149d0 directly: no cull, no order number.
        CombatStageStrip strip{4,0xffffffff,0,{},1};
        edge(r,strip,tail[1+2*n]);
        edge(r,strip,tail[2+2*n]);
        strip.z=strip.depths.front();
        r.strips.push_back(std::move(strip));
    }
    rows(3,7);
    // 1aabc0 x6: seventeen links each, tail[9..].
    for(size_t i=9;i<tail.size();++i)link(r,tail[i]);
    rows(7,CombatStage03State::rowCount);
}
}
