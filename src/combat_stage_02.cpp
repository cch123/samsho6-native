#include "combat_stage_02.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations at 51ae48..51afb8.
constexpr R sailA[]{{0,3072},{1,1536},{2,1536},{1,6144},{0,3072},{1,1536},{2,7680},{1,6144},{0,15360}};
constexpr R sailB[]{{0,3072},{1,1536},{2,38400},{1,6144},{0,15360}};
constexpr R sailC[]{{0,3072},{1,1536},{3,34816},{2,6144},{1,6144},{0,15360}};
constexpr R four[]{{0,3072},{1,3072},{2,3072},{3,3072}};
constexpr R up[]{{0,1280},{1,1280},{2,1280}};
constexpr R down[]{{2,1280},{1,1280},{0,1280}};
struct Binding { unsigned row; std::span<const R> timeline; unsigned clock; };
// Visit order is row order; clock 3 is advanced by both rows 10 and 11.
const Binding bindings[]{
    {1,sailA,0},{3,sailB,1},{4,sailC,2},{10,four,3},{11,four,3},
    {24,down,4},{25,up,5},{26,up,6},{27,down,7},{28,up,8},{29,down,9},{30,up,10},{31,down,11},{32,up,12},{33,up,13}};
// Bit 0 of the turning rows' first table word (51af28..51af78) reverses them.
constexpr bool reversed[8]{false,true,true,false,false,true,false,true};
constexpr unsigned firstTurningRow=14;

// 1a9ef0
F lerp(int32_t t,int32_t duration,F from,F to) {
    if(t>=duration)return to;
    return from.add(to.sub(from).mul(F::integer(t)).div(F::integer(duration)));
}
int32_t ticks(int32_t timer) {return (timer<0?timer+255:timer)>>8;}
struct Leg { int value,duration; };
constexpr Leg settleHigh[]{{3,6},{-3,10},{2,4},{-1,3},{0,3},{0,-1},{0,-1}}; // 652e68
constexpr Leg settleLow[]{{-3,6},{3,10},{-2,4},{1,3},{0,3},{0,-1},{0,-1}};  // 652eb8
}

void CombatStage02State::reload(const CombatStage02State& previous) {
    // 51ba40 guards 1a8b20; 1a9908 clears the swell on every load.
    clocks=previous.clocks;
    turns=previous.turns;
    pictures=previous.pictures;
    angles=previous.angles;
    swellState=swellTimer=swellStep=0;
    swell=0;
}

void CombatStage02State::visit(uint32_t delta,GameRandom&) {
    const F zero=scalar(0),hundred=scalar(100);
    swellTimer=std::bit_cast<int32_t>(uint32_t(swellTimer)+delta);
    const auto next=[&](int state){swellTimer=0;swellState=state;swellStep=0;};
    F out=zero;
    const auto oscillate=[&](F rest,F peak,bool rising,int after) {
        // Two legs: 0x700 away from rest, 0xa00 back.
        if(swellStep==0) {
            out=lerp(swellTimer,0x700,rest,peak);
            if(rising?!out.less(peak):!peak.less(out)){swellStep=1;swellTimer=0;}
        } else {
            out=lerp(swellTimer,0xa00,peak,rest);
            if(rising?!rest.less(out):!out.less(rest)){swellStep=0;swellState=after;swellTimer=0;}
        }
    };
    const auto settle=[&](std::span<const Leg> legs,F base,int after) {
        const F from=swellStep?F::integer(legs[swellStep-1].value).add(base):base;
        const F to=F::integer(legs[swellStep].value).add(base);
        out=lerp(swellTimer,legs[swellStep].duration<<8,from,to);
        if(number(out)==number(to)) {
            swellTimer=0;
            if(legs[++swellStep].duration<0){swellStep=0;swellState=after;}
        }
    };
    switch(swellState) {
    case 0:if(ticks(swellTimer)>=300)next(1);break;
    case 1:oscillate(zero,scalar(-5),false,2);break;
    case 2:out=lerp(swellTimer,0x1f400,zero,hundred);if(!out.less(hundred))next(3);break;
    case 3:settle(settleHigh,hundred,4);break;
    case 4:out=hundred;if(ticks(swellTimer)>=300)next(5);break;
    case 5:oscillate(hundred,scalar(105),true,6);break;
    case 6:out=lerp(swellTimer,0x1f400,hundred,zero);if(!zero.less(out))next(7);break;
    default:settle(settleLow,zero,0);break;
    }
    swell=out.bits;

    for(const auto& b:bindings) {
        advanceStageClock(clocks[b.clock],b.timeline,delta);
        pictures[b.row]=uint8_t(clocks[b.clock].picture);
    }
    for(unsigned n=0;n<turns.size();++n) {
        // 1a946c: a fixed hundredfold rate, wrapped to 24 bits with C
        // remainder semantics, then reduced to a 16-bit angle.
        int32_t t=std::bit_cast<int32_t>(uint32_t(turns[n])+delta*100u);
        t-=((t<0?t+0xffffff:t)>>24)<<24;
        turns[n]=t;
        angles[n]=reversed[n]?0x10000-(t>>8):t>>8;
    }
}

namespace {
// 1a95f0: an atlas rectangle turned about its projected center. It is
// submitted directly, without the screen cull or a new order number.
void turning(Projector& r,const StageCommand& cmd,int32_t angle,const AngleTrig& trig) {
    const auto& p=cmd.parameters;
    const auto& rect=cmd.pieces.front();
    const F texel=scalar(1.f/1024.f),half=scalar(.5f);
    const F u0=scalar(rect[0]).mul(texel),v0=scalar(rect[1]).mul(texel);
    const F art=r.projection.artworkScale(p[2]);
    const auto center=r.projection.point(scalar(p[0]),scalar(p[1]),r.projection.scale(p[2]));
    const F width=scalar(rect[2]).mul(art),height=scalar(rect[3]).mul(art);
    const float key=r.depth(p[2]);
    const F cosine{trig.cosine(uint32_t(angle))},sine{trig.sine(uint32_t(angle))};
    const F v1=v0.add(scalar(rect[3]).mul(texel)),u1=u0.add(scalar(rect[2]).mul(texel));
    const F xs[2]{neg(width).mul(half),width.mul(half)},ys[2]{neg(height).mul(half),height.mul(half)};
    CombatStageStrip strip{cmd.slot,0xffffffff,key,{},1};
    for(unsigned i=0;i<4;++i) {
        const F x=xs[i>>1],y=ys[i&1];
        const F dx=x.mul(cosine).sub(y.mul(sine)),dy=x.mul(sine).add(y.mul(cosine));
        strip.vertices.push_back({number(center[0].add(dx)),number(center[1].add(dy)),number(i&2?u1:u0),number(i&1?v1:v0)});
    }
    r.strips.push_back(std::move(strip));
}
// 1a94d8 x2 + 1149d0: one side wall of the hull, receding from Z 266.67 to 0.
void wall(Projector& r,float farX,float nearX) {
    CombatStageStrip strip{4,0xffffffff,0,{},1};
    const auto edge=[&](float x,float z,float u) {
        const F depth=scalar(r.projection.camera.depth);
        const F s=r.projection.scale(z).div(scalar(0).sub(depth).div(scalar(z).sub(depth)));
        const auto base=r.projection.point(scalar(x),scalar(-.5f),r.projection.scale(z));
        const F height=scalar(128).mul(s);
        const float key=r.depth(z);
        strip.vertices.push_back({number(base[0]),number(base[1].sub(height)),u,0});
        strip.vertices.push_back({number(base[0]),number(base[1]),u,number(scalar(0).add(scalar(128).mul(scalar(1.f/1024.f))))});
        strip.depths.push_back(key);
        strip.depths.push_back(key);
    };
    edge(farX,266.6700134277344f,.0595703125f);
    edge(nearX,0,.5859375f);
    strip.z=strip.depths.front();
    r.strips.push_back(std::move(strip));
}
}

void drawCombatStage02(Projector& r,const StageCommandGroups& groups,const CombatStage02State& state,const AngleTrig& trig) {
    const StageCamera saved=r.projection.camera;
    {
        // 1a5ba0(0, swell): shift the projection, keeping Y of the horizon
        // term clamped at the ordinary 120.
        auto& c=r.projection.camera;
        const F y=scalar(c.projectionY).add(F{state.swell});
        const F ratio=scalar(c.depth).sub(scalar(c.depthOffset)).div(scalar(c.depth));
        c.projectionX=number(scalar(c.projectionX).add(scalar(0)));
        c.projectionY=number(y);
        const F floor=y.less(scalar(120))?scalar(120):y;
        c.verticalOffset=number(neg(y).mul(ratio).add(floor.sub(scalar(120)).mul(ratio)));
    }
    r.mode=0;
    {
        const F scale=r.projection.scale(1000);
        const F stretch=scale.div(scalar(0.2857142686843872f));
        const F x=r.projection.point(scalar(-529.5f),scalar(0),scale)[0];
        const F y=r.projection.point(scalar(0),scalar(-73),scale)[1];
        const F height=scalar(854).mul(stretch);
        r.rectangle(5,29999,x,y.sub(height),scalar(972).mul(stretch),height,scalar(52),scalar(170),scalar(972),scalar(854));
    }
    r.mode=1;
    for(unsigned row=0;row<CombatStage02State::rowCount;++row) {
        const auto& commands=groups[1+row].at(state.pictures[row]);
        if(row>=firstTurningRow&&row<firstTurningRow+8)turning(r,commands.front(),state.angles[row-firstTurningRow],trig);
        else r.run(commands);
    }
    r.projection.camera=saved;
    const auto& tail=groups[1+CombatStage02State::rowCount].front();
    r.mode=0;
    r.run(std::span(tail).first(1));
    r.mode=1;
    r.run(std::span(tail).subspan(1,2));
    wall(r,748.5f,793.5f);
    wall(r,-107,-152);
    r.run(std::span(tail).subspan(3));
}
}
