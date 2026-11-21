#include "combat_stage_05.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"
#include <span>
#include <stdexcept>

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations after 1a7350 scaled the tick tables (544318, 544330, 544350, 544380, 5443b0).
constexpr R row2[]{{0,1536},{1,1536}};
constexpr R row3[]{{0,1536},{1,1536},{2,1536}};
constexpr R row4[]{{0,3072},{1,3072},{2,3072},{3,3072},{0,15360}};
constexpr R row5[]{{0,1536},{1,1536},{2,1536},{2,1536},{0,7680}};
// Pictures 0x100/0x101 select the piece tables of the second descriptor 12f1668.
constexpr R tailTimeline[]{{0x100,1536},{0x101,1536},{0,1536},{1,1536},{2,1536},{3,1536},{4,1536},{5,1536},
                           {6,1536},{7,1536},{8,1536},{9,1536},{10,1536},{11,1536},{0,11520}};
constexpr std::span<const R> rowTimelines[]{row2,row3,row4,row5};
constexpr unsigned firstAnimatedRow=2;
constexpr unsigned middleGroup=8,tailGroup=7;
}

void CombatStage05State::reload(const CombatStage05State& previous) {
    // 544618 guards 1abcd8 (the five clocks); 1abd80 resets the drift on every load.
    clocks=previous.clocks;
    tail=previous.tail;
    pictures=previous.pictures;
    tailVariant=previous.tailVariant;
    driftX=0;
}

void CombatStage05State::visit(uint32_t delta,GameRandom&) {
    // 1acbbc: X += speed (-1, 12f14d4) * delta * 1/256; the delta word is
    // converted as an unsigned value. Below -1100 the sprite re-enters at 1100.
    F ticks;
    if(std::bit_cast<int32_t>(delta)>=0)ticks=F::integer(std::bit_cast<int32_t>(delta));
    else {
        const F half=F::integer(std::bit_cast<int32_t>((delta>>1)|(delta&1)));
        ticks=half.add(half);
    }
    F x=F{driftX}.add(scalar(-1).mul(ticks).mul(scalar(.00390625f)));
    if(x.less(scalar(-1100)))x=scalar(1100);
    driftX=x.bits;
    for(unsigned n=0;n<clocks.size();++n) {
        advanceStageClock(clocks[n],rowTimelines[n],delta);
        pictures[firstAnimatedRow+n]=uint8_t(clocks[n].picture);
    }
    advanceStageClock(tail,tailTimeline,delta);
    tailVariant=tail.picture&0x100?12+(tail.picture&0xff):tail.picture;
}

namespace {
struct Corner { F x,y,u,v,key; };
using Wall=std::array<Corner,4>;

// 1ace00: the top and bottom vertex of one vertical edge. X receives the
// same parallax correction as the sprite helpers; the key is 114dc8(z).
void edge(const Projector& r,const StageCommand& cmd,Corner* out) {
    if(cmd.kind!=11)throw std::logic_error("Stage 5 expects a wall edge");
    const auto& p=cmd.parameters;
    const float z=p[2];
    const F x=scalar(z).add(scalar(400)).mul(scalar(.0025f)).mul(scalar(p[0]).sub(scalar(320))).add(scalar(320));
    const F art=r.projection.artworkScale(z);
    const auto base=r.projection.point(x,scalar(p[1]),r.projection.scale(z));
    const F key=scalar(r.depth(z));
    const F u=scalar(p[5]),v=scalar(p[6]);
    out[0]={base[0],base[1].sub(scalar(p[3]).mul(art)),u,v,key};
    out[1]={base[0],base[1],u,v.add(scalar(p[4]).mul(scalar(1.f/1024.f))),key};
}
Wall wall(const Projector& r,std::span<const StageCommand> edges) {
    Wall w;
    edge(r,edges[0],&w[0]);
    edge(r,edges[1],&w[2]);
    return w;
}
// 1ac5c0 etc.: 114dc8(z) replaces the key of all four vertices.
void flatten(const Projector& r,Wall& w,float z) {
    for(auto& c:w)c.key=scalar(r.depth(z));
}
// A direct 1149d0 submission of the four wall vertices (no cull, no order number).
void submit(Projector& r,unsigned slot,const Wall& w) {
    CombatStageStrip strip{slot,0xffffffff,number(w[0].key),{},1};
    for(const auto& c:w)strip.vertices.push_back({number(c.x),number(c.y),number(c.u),number(c.v)});
    r.strips.push_back(std::move(strip));
}
// 1af1f8: atlas pieces placed inside the wall quadrilateral. Record zero is
// the bounding rectangle. X and the depth key follow the top edge only; Y is
// interpolated between the top and bottom edges. Submitted directly.
void pieces(Projector& r,const StageCommand& cmd,const Wall& w) {
    if(cmd.kind!=12||cmd.pieces.size()!=size_t(cmd.parameters[0]))throw std::logic_error("Stage 5 expects wall pieces");
    const F size=scalar(cmd.slot<6?1024.f:512.f); // 6535a0[slot]
    const F dx=w[2].x.sub(w[0].x),dyTop=w[2].y.sub(w[0].y),dyBottom=w[3].y.sub(w[1].y),dz=w[2].key.sub(w[0].key);
    const auto& box=cmd.pieces.front();
    const F U=scalar(box[0]),V=scalar(box[1]),W=scalar(box[2]),H=scalar(box[3]);
    for(size_t i=1;i<cmd.pieces.size();++i) {
        const auto& pc=cmd.pieces[i];
        const F u=scalar(pc[0]),v=scalar(pc[1]);
        const F u1=u.add(scalar(pc[2])),v1=v.add(scalar(pc[3]));
        const F a=u.sub(U).div(W),b=u1.sub(U).div(W),c=v.sub(V).div(H),d=v1.sub(V).div(H);
        const F topA=w[0].y.add(dyTop.mul(a)),spanA=w[1].y.add(dyBottom.mul(a)).sub(topA);
        const F topB=w[0].y.add(dyTop.mul(b)),spanB=w[1].y.add(dyBottom.mul(b)).sub(topB);
        const F key=w[0].key.add(dz.mul(a));
        const float xa=number(w[0].x.add(dx.mul(a))),xb=number(w[0].x.add(dx.mul(b)));
        const float tu0=number(u.div(size)),tu1=number(u1.div(size)),tv0=number(v.div(size)),tv1=number(v1.div(size));
        CombatStageStrip strip{cmd.slot,0xffffffff,number(key),{},int(pc[4])&0x200?0u:1u};
        strip.vertices={{xa,number(topA.add(spanA.mul(c))),tu0,tv0},{xa,number(topA.add(spanA.mul(d))),tu0,tv1},
                        {xb,number(topB.add(spanB.mul(c))),tu1,tv0},{xb,number(topB.add(spanB.mul(d))),tu1,tv1}};
        r.strips.push_back(std::move(strip));
    }
}
// 1ad0f0: a world mesh drawn column by column. Every strip carries the key
// 114e40(z) = 10000000 - 100 z without the order counter; 114e68 then takes
// one order number for the whole mesh.
void mesh(Projector& r,const StageCommand& cmd) {
    if(cmd.kind!=13)throw std::logic_error("Stage 5 expects a world mesh");
    const size_t n=size_t(cmd.parameters[1]);
    if(n<4||cmd.pieces.empty()||cmd.pieces.size()%n)throw std::logic_error("Invalid stage 5 mesh");
    const float key=number(scalar(10000000).sub(scalar(cmd.parameters[0]).mul(scalar(100))));
    for(size_t at=0;at<cmd.pieces.size();at+=n) {
        CombatStageStrip strip{cmd.slot,r.color,key,{},1};
        for(size_t i=0;i<n;++i) {
            const auto& v=cmd.pieces[at+i];
            const auto xy=r.projection.point(scalar(v[0]),scalar(v[1]),r.projection.scale(v[2]));
            strip.vertices.push_back({number(xy[0]),number(xy[1]),v[3],v[4]});
        }
        r.strips.push_back(std::move(strip));
    }
    ++r.counter;
}
}

void drawCombatStage05(Projector& r,const StageCommandGroups& groups,const CombatStage05State& state,const AngleTrig&) {
    // 1ac3ac..1ac3b4: the task replaces the shadow color 50e048 for its own
    // duration and restores the saved value at 1acd6c. 510ce8 is 0.2 here.
    r.shadowColor=0x90000000;
    r.shadowSkewX=0;
    r.shadowSkewY=.2f;
    r.color=0xffffffff;
    r.mode=0;
    {
        // 1ac3c4: backdrop rectangle 543df0, anchored at two world points.
        const F wide=r.projection.scale(3000).div(scalar(0.11764705181121826f)).mul(scalar(1.5f));
        const F x=r.projection.point(scalar(-1588),scalar(0),r.projection.scale(3000))[0];
        const F y=r.projection.point(scalar(0),scalar(-5),r.projection.scale(2000))[1];
        const F height=scalar(480).mul(r.projection.scale(2000).div(scalar(0.1666666567325592f)));
        r.rectangle(5,30000,x,y.sub(height),scalar(600).mul(wide),height,scalar(0),scalar(544),scalar(600),scalar(480));
    }
    r.run(groups[0].front());
    const auto row=[&](unsigned n){r.run(groups[1+n].at(state.pictures[n]));};
    row(0);
    row(1);
    r.mode=1;
    const std::span<const StageCommand> mid=groups.at(middleGroup).front();
    if(mid.size()!=19)throw std::logic_error("Unexpected stage 5 command list");
    Wall w=wall(r,mid.subspan(0,2));
    flatten(r,w,1200);
    pieces(r,mid[2],w);
    w=wall(r,mid.subspan(3,2));
    flatten(r,w,1300);
    pieces(r,mid[5],w);
    w=wall(r,mid.subspan(6,2));
    flatten(r,w,1200);
    submit(r,5,w);
    w=wall(r,mid.subspan(8,2));
    flatten(r,w,1300);
    submit(r,5,w);
    mesh(r,mid[10]);
    mesh(r,mid[11]);
    // The last two walls keep the per-edge keys.
    pieces(r,mid[14],wall(r,mid.subspan(12,2)));
    pieces(r,mid[17],wall(r,mid.subspan(15,2)));
    {
        // 1acc58: sprite 544300 at X = drift + 320.
        StageCommand drift=mid[18];
        if(drift.kind!=1)throw std::logic_error("Unexpected stage 5 drifting sprite");
        drift.parameters[0]=number(F{state.driftX}.add(scalar(320)));
        r.sprites(drift);
    }
    for(unsigned n=firstAnimatedRow;n<CombatStage05State::rowCount;++n)row(n);
    r.run(groups.at(tailGroup).at(state.tailVariant));
}
}
