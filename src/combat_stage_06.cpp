#include "combat_stage_06.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations as they stand in memory after 1a7350 multiplied the tick
// counts of the seventeen timelines listed at 5509f0 by 256 (once, in 1ad748).
constexpr R sway[]{{0,3072},{1,3072},{2,3072},{1,3072},{0,3072},{0,3072},{1,3072},{2,3072},{1,3072},{0,9216}}; // 5504e0 5505b8 5506b0 550740
constexpr R cycle3[]{{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,3072},{1,3072},{2,3072},{0,9216}}; // 550538
constexpr R four[]{{0,3072},{1,3072},{2,3072},{3,3072}}; // 550590
constexpr R rest3[]{{0,9216},{1,3072},{2,3072},{1,3072},{0,6144},{0,3072},{1,3072},{2,3072},{1,3072}}; // 550610 550890 5508e0 550930
constexpr R blink[]{{0,3072},{1,3072},{0,3072},{1,3072},{0,6144},{1,3072},{0,6144},{1,3072},{0,3072}}; // 550660 550840 550980
constexpr R nod[]{{0,6144},{1,3072},{0,3072},{1,3072},{0,6144},{1,3072}}; // 550708
constexpr R flapA[]{{0,3072},{1,3072},{0,3072},{1,3072},{0,3072},{1,3072},{0,3072},{1,3072},{0,9216}}; // 550798
constexpr R flapB[]{{0,3072},{1,3072},{0,3072},{1,3072},{0,3072},{1,3072},{0,3072},{1,3072},{0,3072},{1,9216}}; // 5507e8
constexpr R banner3[]{{0,3072},{1,3072},{2,3072}}; // 5509d0
struct Binding { unsigned row; std::span<const R> timeline; };
// Rows with flag 0x100, each with its own descriptor.
const Binding bindings[]{
    {0,sway},{1,flapB},{2,cycle3},{4,four},{5,four},{6,four},{7,four},{8,four},{9,four},{10,four},
    {11,sway},{12,rest3},{13,blink},{14,sway},{15,nod},{17,sway},{18,flapA},{19,blink},
    {22,rest3},{23,rest3},{24,rest3},{25,blink}};

// Positions inside group 0 of the exported command file.
constexpr unsigned floorFirst=0,floorCount=8,spriteFirst=8,spriteCount=7,bannerFirst=15,bannerCount=4,ropeFirst=27,ropeCount=5;

struct Edge { F x,top,bottom; float key; };
// 1aedb8 (key from the fixed Z 980) and 1aeef8 (key from the edge's own Z):
// one vertical edge of a banner, anchored like an ordinary scenery sprite.
// 114dc8 reads the order counter without advancing it.
Edge edge(const Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const float z=p[2];
    const F x=scalar(z).add(scalar(400)).mul(scalar(.0025f)).mul(scalar(p[0]).sub(scalar(320))).add(scalar(320));
    const auto point=r.projection.point(x,scalar(p[1]),r.projection.scale(z));
    const F height=scalar(p[3]).mul(r.projection.artworkScale(z));
    return {point[0],point[1].sub(height),point[1],r.depth(cmd.kind==12?980.f:z)};
}
// 1af1f8: every piece of an atlas picture is mapped into the quadrilateral
// spanned by two edges. X comes from the top side only, Y is interpolated
// along both sides, and each piece is flat at the depth key of its left
// border. Direct 1149d0 submissions: no screen cull, no order number.
void banner(Projector& r,std::span<const StageCommand> cmds) {
    const Edge a=edge(r,cmds[0]),b=edge(r,cmds[1]);
    const auto& cmd=cmds[2];
    const auto& box=cmd.pieces.front();
    const F size=F::integer(cmd.slot==4||cmd.slot==5?1024:512); // 6535a0[slot]
    const F ax=b.x.sub(a.x),ay=b.top.sub(a.top),by=b.bottom.sub(a.bottom),az=scalar(b.key).sub(scalar(a.key));
    const F bx=scalar(box[0]),boxY=scalar(box[1]),bw=scalar(box[2]),bh=scalar(box[3]);
    for(size_t i=1;i<cmd.pieces.size();++i) {
        const auto& pc=cmd.pieces[i];
        const F u=scalar(pc[0]),v=scalar(pc[1]);
        const F s0=u.sub(bx).div(bw);
        const F u1=u.add(scalar(pc[2]));
        const F s1=u1.sub(bx).div(bw);
        const F t0=v.sub(boxY).div(bh);
        const F v1=v.add(scalar(pc[3]));
        const F t1=v1.sub(boxY).div(bh);
        const F leftTop=a.top.add(ay.mul(s0)),rightTop=a.top.add(ay.mul(s1));
        const F leftSpan=a.bottom.add(by.mul(s0)).sub(leftTop),rightSpan=a.bottom.add(by.mul(s1)).sub(rightTop);
        const float key=number(scalar(a.key).add(az.mul(s0)));
        const F left=a.x.add(ax.mul(s0)),right=a.x.add(ax.mul(s1));
        const float tu0=number(u.div(size)),tv0=number(v.div(size)),tu1=number(u1.div(size)),tv1=number(v1.div(size));
        CombatStageStrip strip{cmd.slot,0xffffffff,key,{},int(pc[4])&0x200?0u:1u};
        strip.vertices={{number(left),number(leftTop.add(leftSpan.mul(t0))),tu0,tv0},
                        {number(left),number(leftTop.add(leftSpan.mul(t1))),tu0,tv1},
                        {number(right),number(rightTop.add(rightSpan.mul(t0))),tu1,tv0},
                        {number(right),number(rightTop.add(rightSpan.mul(t1))),tu1,tv1}};
        r.strips.push_back(std::move(strip));
    }
}
// 1af030 -> 1a54e8 x 21: copies of one atlas rectangle, centered on points
// of the line from Q (t = 0) to P (t = 1) that sags by 170 (t - 1/2)^2 - 50.
// The whole line is skipped while its height is above the top of the view.
void rope(Projector& r,const StageCommand& cmd) {
    const auto& p=cmd.parameters;
    const auto& rect=cmd.pieces.front();
    if(scalar(r.projection.camera.projectionY).add(scalar(480)).less(scalar(p[1]).mul(r.projection.scale(0))))return;
    const F step{0x3d4ccccc}; // one unit below 0.05f
    for(int i=0;i<21;++i) {
        const F t=F::integer(i).mul(step),q=scalar(1).sub(t);
        // EE multiply-add pairs (MULA, MADD).
        const F x=scalar(p[0]).mul(t).add(scalar(p[3]).mul(q));
        const F d=t.sub(scalar(.5f));
        const F y=scalar(p[1]).mul(t).add(scalar(p[4]).mul(q)).add(d.mul(d).mul(scalar(170)).sub(scalar(50)));
        const F z=scalar(p[2]).mul(t).add(scalar(p[5]).mul(q));
        const F size=scalar(400).div(z.add(scalar(400))).mul(scalar(2.2f));
        // 1a54e8
        const float depth=number(z);
        const F scale=r.projection.scale(depth);
        const auto center=r.projection.point(x,y,scale);
        const F s=size.mul(scale);
        const F height=scalar(rect[3]).mul(s),width=scalar(rect[2]).mul(s);
        r.rectangle(cmd.slot,depth,center[0].sub(width.mul(scalar(.5f))),center[1].sub(height.mul(scalar(.5f))),width,height,
                    scalar(rect[0]),scalar(rect[1]),scalar(rect[2]),scalar(rect[3]));
    }
}
}

void CombatStage06State::reload(const CombatStage06State& previous) {
    // 551248 guards 1ad748, the only initializer that owns state. 1ad838 and
    // 1ad580 rebuild the constant floor and shadow meshes on every load.
    *this=previous;
}

void CombatStage06State::visit(uint32_t delta,GameRandom&) {
    // 1ae600 and 1ae72c advance the banner clocks before the row loop; all
    // 24 run on hidden visits too.
    for(unsigned n=0;n<bannerClocks.size();++n) {
        advanceStageClock(bannerClocks[n],banner3,delta);
        bannerPictures[n]=uint8_t(bannerClocks[n].picture);
    }
    for(const auto& b:bindings) {
        advanceStageClock(clocks[b.row],b.timeline,delta);
        pictures[b.row]=uint8_t(clocks[b.row].picture);
    }
}

void drawCombatStage06(Projector& r,const StageCommandGroups& groups,const CombatStage06State& state,const AngleTrig&) {
    const auto& prefix=groups.front();
    const std::span base{prefix.front()};
    r.color=0xffffffff;
    r.mode=0;
    {
        // 1ae20c: the sky, one rectangle with independent X and Y anchors.
        const F scale=r.projection.scale(3000);
        const F unit=scale.div(scalar(0.11764705181121826f));
        const F x=r.projection.point(scalar(-1515),scalar(0),scale)[0];
        const F y=r.projection.point(scalar(0),scalar(-471),scale)[1];
        const F width=scalar(720).mul(unit.mul(scalar(1.2f))),height=scalar(398).mul(unit.mul(scalar(1.3f)));
        r.rectangle(4,29999,x,y.sub(height),width,height,scalar(0),scalar(130),scalar(720),scalar(398));
    }
    // Eight 8x4 floor meshes (1ad838), darkened to three quarters.
    r.color=0xffc0c0c0;
    r.run(base.subspan(floorFirst,floorCount));
    r.color=0xffffffff;
    r.mode=1;
    r.run(base.subspan(spriteFirst,spriteCount));
    banner(r,base.subspan(bannerFirst,3));
    for(unsigned n=0;n<2;++n)
        banner(r,std::span{prefix.at(state.bannerPictures[n])}.subspan(bannerFirst+3*(1+n),3));
    banner(r,base.subspan(bannerFirst+3*(bannerCount-1),3));
    for(unsigned n=0;n<ropeCount;++n)rope(r,base[ropeFirst+n]);
    for(unsigned row=0;row<CombatStage06State::rowCount;++row)
        r.run(groups[1+row].at(state.pictures[row]));
}
}
