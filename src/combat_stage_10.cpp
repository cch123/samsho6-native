#include "combat_stage_10.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations as left in RAM by 1a7350(572360, 1), which multiplies the
// tick counts of the nine timelines by 256 once (inside once-guarded 1b2170).
// Picture 256 (bit 0x100) draws nothing.
constexpr R rowTimeline[]{{0,1536},{1,1536},{0,1536},{1,1536},{0,15360}};                               // 5720a8
constexpr R early[]{{0,1536},{1,1536},{2,1536},{256,73728},{0,1536},{1,1536},{2,1536},{256,16896}};      // 5720d8, 572170
constexpr R late[]{{256,19968},{0,1536},{1,1536},{2,1536},{256,55296},{0,1536},{1,1536},{2,1536},{256,15360}}; // 572120, 5721b8
constexpr R slow[]{{256,30720},{0,3072},{1,3072},{2,3072},{256,32256},{0,3072},{1,3072},{2,3072},
                   {256,18432},{0,3072},{1,3072},{2,3072}};                                             // 572208
constexpr R pair[]{{0,3072},{1,1536},{256,15360},{0,3072},{1,1536},{256,53760},{0,4608},{1,1536},{256,15360}}; // 572270, 5722c0, 572310
constexpr std::span<const R> timelines[8]{early,late,early,late,slow,pair,pair,pair};
constexpr unsigned firstAnimatedRow=16;

struct Rect { int u,v,w,h; };
// 571498: fourteen 0xdc-byte records {pieces, -, -, x, y, z = 1999, ..., +d8 count} on texture
// slot 6. The piece index is (57294c / 0x600) % count and index zero is not
// drawn. Four records have count zero in the executable and never appear.
struct Blinker { float x,y; int count; Rect pieces[4]; };
constexpr Blinker blinkers[14]{
    {-11,722,2,{{},{1,350,134,7}}},
    {57,708,0,{}},
    {104,729,0,{}},
    {129,833,3,{{},{157,342,155,70},{157,413,155,70}}},
    {-105,849,2,{{},{313,346,14,1}}},
    {156,712,0,{}},
    {-120,790,0,{}},
    {-133,735,2,{{},{398,348,51,2}}},
    {-135,584,4,{{},{398,366,49,14},{398,381,49,14},{398,396,49,14}}},
    {-90,641,2,{{},{398,416,69,4}}},
    {-70,670,2,{{},{412,441,71,14}}},
    {-29,659,2,{{},{412,469,54,12}}},
    {4,667,2,{{},{450,346,40,1}}},
    {85,845,2,{{},{448,356,51,4}}}};

// Perspective quads of clocks 0..3 (1b2764.., 1b28c0.., 1b2a1c.., 1b2b78..):
// a far edge at Z 2000 six half-pieces wide and high, and a near edge whose
// width uses its own factor.
struct Panel { unsigned slot; float farX,farY,nearZ,nearScale,nearX,nearY; Rect pieces[3]; };
constexpr Panel panels[4]{
    {7,-163,227,1001,3.50249981880188f,-22,547,{{1,1,128,318},{130,1,128,318},{259,1,128,318}}},          // 571030
    {4,349,196,1001,3.50249981880188f,341,538,{{1,648,192,329},{194,648,192,329},{387,648,192,329}}},     // 570a00
    {5,535,68,1001,3.50249981880188f,631,562,{{1,666,232,356},{235,666,232,356},{470,666,232,356}}},      // 570b50
    {5,-670,476,1201,4.002499580383301f,-483,396,{{860,345,163,132},{860,478,163,132},{860,611,163,132}}}}; // 570b98
constexpr Rect clock4[3]{{1,541,94,83},{96,541,94,83},{191,541,94,83}};  // 5709b8
constexpr Rect clock5[2]{{1,320,189,106},{191,320,189,106}};             // 571078
constexpr Rect clock6[6]{{763,433,260,242},{763,676,260,242},{649,610,111,21},{649,853,111,21},
                         {378,989,645,3},{378,1000,645,3}};              // 570a48
constexpr Rect clock7[2]{{463,508,146,157},{610,508,146,157}};           // 570bf8

// 1a4e80 / 1a4ee0: parallax correction of X, then 1a4cb8 / 1a4d98.
void plain(Projector& r,bool mirrored,unsigned slot,F x,float y,float z,F u,F v,F w,F h) {
    const F px=scalar(z).add(scalar(400)).mul(scalar(.0025f)).mul(x.sub(scalar(320))).add(scalar(320));
    StageCommand cmd{mirrored?8u:7u,slot,{number(px),y,z},{{number(u),number(v),number(w),number(h),-1}}};
    r.plain(cmd);
}
void plain(Projector& r,bool mirrored,unsigned slot,F x,float y,float z,const Rect& p) {
    plain(r,mirrored,slot,x,y,z,F::integer(p.u),F::integer(p.v),F::integer(p.w),F::integer(p.h));
}
// 1b3398: four projected world points with the corners of one atlas piece.
// It takes an order number without the screen cull and always submits with
// vertex alpha.
void panel(Projector& r,const Panel& q,const Rect& p) {
    const F half=scalar(.5f),six=scalar(6);
    const F w=F::integer(p.w).mul(half),h=F::integer(p.h).mul(half);
    const F farRight=w.mul(six).add(scalar(q.farX)),farTop=h.mul(six).add(scalar(q.farY));
    const F nearRight=w.mul(scalar(q.nearScale)).add(scalar(q.nearX));
    const float key=r.depth(q.nearZ);
    ++r.counter;
    // 653a98: texture size per slot.
    const F size=F::integer(q.slot==4||q.slot==5?1024:512);
    const F v0=F::integer(p.v).div(size),u0=F::integer(p.u).div(size);
    const F u1=F::integer(p.u+p.w).div(size),v1=F::integer(p.v+p.h).div(size);
    const F farScale=r.projection.scale(2000),nearScale=r.projection.scale(q.nearZ);
    const auto a=r.projection.point(scalar(q.farX),farTop,farScale),b=r.projection.point(farRight,farTop,farScale);
    const auto c=r.projection.point(scalar(q.nearX),scalar(q.nearY),nearScale);
    const auto d=r.projection.point(nearRight,scalar(q.nearY),nearScale);
    CombatStageStrip strip{q.slot,0xffffffff,key,{},1};
    strip.vertices={{number(a[0]),number(a[1]),number(u0),number(v0)},{number(b[0]),number(b[1]),number(u1),number(v0)},
                    {number(c[0]),number(c[1]),number(u0),number(v1)},{number(d[0]),number(d[1]),number(u1),number(v1)}};
    r.strips.push_back(std::move(strip));
}
// 1a5078 (via 1a5488, row prologue 4): 1a4f40 with the vertex pairs
// exchanged, so the shadow texture is upside down and the cull of 114f20
// sees the corners in that other order.
void flippedShadow(Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const auto origin=r.projection.point(scalar(p[0]),scalar(p[1]),r.projection.scale(p[2]));
    const F s=r.projection.artworkScale(p[2]),w=scalar(p[5]).mul(s),h=scalar(p[6]).mul(s);
    const F x=origin[0],y=origin[1];
    const F left=x.sub(h.mul(scalar(r.shadowSkewX))),bottom=y.add(h.mul(scalar(r.shadowSkewY)));
    r.quad(cmd.slot,r.shadowColor,p[2],{x,left,x.add(w),left.add(w)},{y,bottom,y,bottom},
           scalar(p[3]),scalar(p[4]),scalar(p[5]),scalar(p[6]),true);
}
}

void CombatStage10State::reload(const CombatStage10State& previous) {
    // 5720a0 guards 1b2170 (descriptors and timeline scaling); the constructor
    // resets no clock. 1b2290 only rebuilds the shared floor mesh at 50e110.
    *this=previous;
}

void CombatStage10State::visit(uint32_t delta,GameRandom&) {
    scroll=std::bit_cast<int32_t>(uint32_t(scroll)+delta);
    for(unsigned k=0;k<clocks.size();++k)advanceStageClock(clocks[k],timelines[k],delta);
    for(auto& clock:rowClocks)advanceStageClock(clock,rowTimeline,delta);
}

void drawCombatStage10(Projector& r,const StageCommandGroups& groups,const CombatStage10State& state,const AngleTrig&) {
    if(groups.size()!=CombatStage10State::rowCount+2||groups[0].front().empty()||groups[0].front().front().kind!=4)
        throw std::runtime_error("Unexpected stage 10 geometry");
    // 50e048; 510ce4 / 510ce8 as the constructor and the end of every visit leave them.
    r.shadowColor=0xa0000000;
    r.shadowSkewX=0;
    r.shadowSkewY=.1f;
    r.color=0xffffffff;
    r.mode=0;
    {
        // 1b2528..1b2608: the sky (piece 570af0), anchored by two separate
        // world points at Z 2001 and stretched 1.2 times horizontally.
        const F far=r.projection.scale(2001);
        const F unit=far.div(scalar(0.16659724712371826f));
        const F x=r.projection.point(scalar(-979),scalar(0),far)[0];
        const F wide=unit.mul(scalar(1.2f));
        const F y=r.projection.point(scalar(0),scalar(306),far)[1];
        const F height=scalar(393).mul(unit);
        r.rectangle(5,30000,x,y.sub(height),scalar(720).mul(wide),height,scalar(0),scalar(114),scalar(720),scalar(393));
    }
    r.mode=1;
    // 1b2614..1b26cc. Both divisions are signed. The counter turns negative
    // only after 2^31 / 256 ticks; the original would then index before
    // the piece tables, which is not modelled.
    const int32_t phase=state.scroll/0x600;
    for(const auto& e:blinkers) {
        if(!e.count)continue;
        const int index=phase%e.count;
        if(index>0)plain(r,false,6,scalar(e.x).add(scalar(320)),e.y,1999,e.pieces[index]);
    }
    r.mode=0;
    r.floor(groups[0].front().front());
    r.mode=1;
    for(unsigned k=0;k<4;++k)
        if(const unsigned picture=state.clocks[k].picture;!(picture&0x100))panel(r,panels[k],panels[k].pieces[picture]);
    if(const unsigned picture=state.clocks[4].picture;!(picture&0x100))plain(r,false,4,scalar(136),900,1199,clock4[picture]);
    if(const unsigned picture=state.clocks[5].picture;!(picture&0x100))
        plain(r,false,7,scalar(522),377.20001220703125f,1201,clock5[picture]);
    if(const unsigned picture=state.clocks[6].picture;!(picture&0x100)) {
        // 1b2e4c..1b2ffc: two mirrored pairs and a strip that loses 140 texels of width.
        const F half=scalar(.5f);
        const Rect& a=clock6[picture];
        plain(r,false,4,scalar(189.5f),353.70001220703125f,551,a);
        plain(r,true,4,scalar(450.5f).sub(F::integer(a.w).mul(half)),353.70001220703125f,551,a);
        const Rect& b=clock6[2+picture];
        plain(r,false,4,scalar(154.1999969482422f),558.5f,1001,b);
        plain(r,true,4,scalar(485.79998779296875f).sub(F::integer(b.w).mul(half)),558.5f,1001,b);
        const Rect& c=clock6[4+picture];
        plain(r,false,4,scalar(193),584.7000122070312f,1001,F::integer(c.u),F::integer(c.v),
              F::integer(c.w).sub(scalar(140)),F::integer(c.h));
    }
    if(const unsigned picture=state.clocks[7].picture;!(picture&0x100))
        plain(r,false,5,scalar(94.10000610351562f),553.5f,1201,clock7[picture]);
    // 1b3588(0, 7), two plain rectangles (exported after row 6), 1b3588(7, 19).
    for(unsigned row=0;row<CombatStage10State::rowCount;++row) {
        const unsigned picture=row>=firstAnimatedRow?state.rowClocks[row-firstAnimatedRow].picture:0;
        for(const auto& cmd:groups[1+row].at(picture)) {
            if(cmd.kind!=3&&cmd.kind!=11) {
                r.run(std::span(&cmd,1));
                continue;
            }
            // Row prologues 2 and 4 multiply both skew globals by the row's
            // factors at +40 / +44 for the duration of the shadow call:
            // row 16 {1, 3}, row 18 {1, 10}. Prologue 1 uses them unchanged.
            const float factor=row==16?3.f:row==18?10.f:1.f;
            const float skewX=r.shadowSkewX,skewY=r.shadowSkewY;
            if(row==16||row==18) {
                r.shadowSkewX=number(scalar(skewX).mul(scalar(1)));
                r.shadowSkewY=number(scalar(skewY).mul(scalar(factor)));
            }
            if(cmd.kind==11)flippedShadow(r,cmd);
            else r.shadow(cmd);
            r.shadowSkewX=skewX;
            r.shadowSkewY=skewY;
        }
    }
}
}
