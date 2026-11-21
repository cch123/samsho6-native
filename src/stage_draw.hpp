#pragma once
#include "combat_stage_state.hpp"
#include "scalar_float.hpp"
#include "stage_raster.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>

// Shared projection and strip builders of the battle scenery tasks. Stage
// specific callbacks combine these in their original submission order.
namespace ss6 {
using CombatStageVertex=StageVertex;
struct CombatStageStrip {
    unsigned slot;
    uint32_t color;
    float z;
    std::vector<CombatStageVertex> vertices;
    // 1149d0 argument 3: 1 keeps the vertex alpha, otherwise alpha is 0x80.
    unsigned mode=1;
    // Empty for a strip that is flat in depth, else one sort key per vertex.
    std::vector<float> depths{};
};
struct StageCommand {
    unsigned kind,slot;
    std::array<float,7> parameters{};
    std::vector<std::array<float,5>> pieces;
};
// [group][picture] -> commands, as exported by the stage extractors.
using StageCommandGroups=std::vector<std::vector<std::vector<StageCommand>>>;
// pieceFlags: rectangle pieces carry a fifth value, the original piece flag
// word, or -1 where the helper keeps the caller's alpha mode.
StageCommandGroups readStageCommands(std::span<const uint8_t> bytes,size_t groups,bool pieceFlags);
namespace stage_draw {
using F=ScalarFloat;
inline F scalar(float x) { return {std::bit_cast<uint32_t>(x)}; }
inline float number(F x) { return std::bit_cast<float>(x.bits); }
inline F neg(F x) {return {x.bits^0x80000000u};}

struct Projection {
    // A copy: some stage tasks draw part of their scenery under a
    // temporarily shifted projection (1a5ad0/1a5ba0/1a5b38).
    StageCamera camera;
    F scale(float z) const {
        const F depth=scalar(camera.depth);
        return scalar(camera.depthOffset).sub(depth).div(scalar(z).sub(depth));
    }
    std::array<F,2> point(F x,F y,F scale) const {
        // 123020 writes already doubled, Y-inverted graphics coordinates.
        x=x.sub(scalar(camera.projectionX)).mul(scale).sub(scalar(-160));
        y=y.sub(scalar(camera.projectionY)).mul(scale).sub(scalar(camera.verticalOffset)).add(scale.mul(scalar(12)));
        return {x.add(x),scalar(448).sub(y.add(y))};
    }
    F artworkScale(float z)const {
        // Art was authored at camera depth -400. World mesh vertices already
        // contain that transformation; the atlas-sized scenery pieces do not.
        return scale(z).div(scalar(400).div(scalar(z).add(scalar(400))));
    }
};

struct Projector {
    Projection projection;
    unsigned counter=100;
    std::vector<CombatStageStrip> strips;
    unsigned mode=1;            // 3db8fc
    uint32_t color=0xffffffff;  // 3db900 after 117288
    uint32_t shadowColor=0x60000000; // 50e048
    float shadowSkewX=0,shadowSkewY=.1f; // 510ce4, 510ce8

    float depth(float z)const {return number(scalar(10000000).sub(scalar(z).mul(scalar(100))).add(F::integer(counter)));}
    void quad(unsigned slot,uint32_t color,float z,std::array<F,4> xs,std::array<F,4> ys,
              F u,F v,F w,F h,bool fourCorners=false) {
        // 114e98/114f20 cull against the full 480-line buffer even if the
        // caller chooses the 448-line output crop. Only surviving quads
        // consume the global 114d88 order offset.
        const auto outside=[](const auto& points,float bound) {
            return std::all_of(points.begin(),points.end(),[](F p){return number(p)<0;})||
                   std::all_of(points.begin(),points.end(),[&](F p){return number(p)>bound;});
        };
        // The four-corner path at 114f5c tests the last Y register for
        // the all-left test. A fully offscreen shadow can therefore still
        // consume an order number and affect the depth of subsequent pieces.
        const bool left=fourCorners
            ? number(xs[0])<0&&number(xs[1])<0&&number(xs[2])<0&&number(ys[3])<0
            : std::all_of(xs.begin(),xs.end(),[](F p){return number(p)<0;});
        const bool right=std::all_of(xs.begin(),xs.end(),[](F p){return number(p)>640;});
        if(left||right||outside(ys,480))return;
        const float sort=depth(z);
        ++counter;
        const F ts=scalar(slot<6?1.f/1024.f:1.f/512.f);
        u=u.mul(ts);v=v.mul(ts);
        const F u1=u.add(w.mul(ts)),v1=v.add(h.mul(ts));
        CombatStageStrip strip{slot,color,sort,{},mode};
        for(unsigned i=0;i<4;++i)
            strip.vertices.push_back({number(xs[i]),number(ys[i]),number(i&2?u1:u),number(i&1?v1:v)});
        strips.push_back(std::move(strip));
    }
    void rectangle(unsigned slot,float z,F x,F y,F w,F h,F u,F v,F uw,F vh) {
        const F x1=x.add(w),y1=y.add(h);
        quad(slot,color,z,{x,x,x1,x1},{y,y1,y,y1},u,v,uw,vh);
    }
    void sky(unsigned stage) {
        // 1a7894..1a79bc: a thin constant-height strip and the scaled
        // remainder have different Z and even different vertical anchors.
        const F scale=projection.scale(1000);
        const F stretch=scale.div(scalar(0.2857142686843872f)).mul(scalar(1.3f));
        if(stage==1) {
            // 1a8098 samples two independent world anchors. The texture loses
            // its last row and uses different horizontal and vertical scales.
            const F x=projection.point(scalar(-547),scalar(0),scale)[0];
            const F y=projection.point(scalar(0),scalar(122),scale)[1];
            const F height=scalar(453).mul(scale.div(scalar(0.2857142686843872f)).mul(scalar(1.4f)));
            rectangle(5,29999,x,y.sub(height),scalar(764).mul(stretch),height,
                      scalar(0),scalar(570),scalar(764),scalar(453));
            return;
        }
        const F x=projection.point(scalar(-514),scalar(0),scale)[0];
        const F y=projection.point(scalar(0),scalar(272),scale)[1];
        rectangle(5,30000,x,y.sub(scalar(1)),scalar(736).mul(stretch),scalar(80),
                  scalar(288),scalar(712),scalar(736),scalar(40));
        const F h=scalar(415).mul(stretch);
        rectangle(5,29999,x,y.sub(h),scalar(736).mul(stretch),h,scalar(288),scalar(336),scalar(736),scalar(415));
    }
    void sprites(const auto& cmd) {
        const auto& p=cmd.parameters;
        const auto& header=cmd.pieces.front();
        const float z=p[2];
        const F x=scalar(z).add(scalar(400)).mul(scalar(.0025f)).mul(scalar(p[0]).sub(scalar(320))).add(scalar(320));
        const auto origin=projection.point(x,scalar(p[1]),projection.scale(z));
        const F s=projection.artworkScale(z);
        const F sx=scalar(p[3]).mul(s),sy=scalar(p[4]).mul(s);
        const F w=scalar(header[2]),h=scalar(header[3]);
        const F width=w.mul(sx),height=h.mul(sy);
        const bool mirror=cmd.kind==2;
        const F left=mirror?origin[0].add(width):origin[0],top=origin[1].sub(height);
        const unsigned callerMode=mode;
        for(size_t i=cmd.pieces.size()>1?1:0;i<cmd.pieces.size();++i) {
            const auto& pc=cmd.pieces[i];
            // 1a6374: piece flag 0x200 drops the vertex alpha for that piece.
            if(pc[4]>=0)mode=int(pc[4])&0x200?0:1;
            const F dx=scalar(pc[0]-header[0]).mul(width).div(w);
            const F dy=scalar(pc[1]-header[1]).mul(height).div(h);
            const F sw=scalar(pc[2]),sh=scalar(pc[3]);
            rectangle(cmd.slot,z,mirror?left.sub(dx):left.add(dx),top.add(dy),
                      mirror?neg(sw.mul(sx)):sw.mul(sx),sh.mul(sy),scalar(pc[0]),scalar(pc[1]),sw,sh);
        }
        mode=callerMode;
    }
    // 1a4cb8 / 1a4d98: one atlas rectangle anchored at its bottom corner.
    // 1a4e80 / 1a4ee0 reach the same code after the parallax correction of
    // sprites(); the exported X already includes it.
    void plain(const auto& cmd) {
        const auto& p=cmd.parameters;
        const auto& rect=cmd.pieces.front();
        const auto origin=projection.point(scalar(p[0]),scalar(p[1]),projection.scale(p[2]));
        const F s=projection.artworkScale(p[2]);
        const F height=scalar(rect[3]).mul(s),width=scalar(rect[2]).mul(s);
        const F top=origin[1].sub(height);
        if(cmd.kind==8)rectangle(cmd.slot,p[2],origin[0].add(width),top,neg(width),height,
                                 scalar(rect[0]),scalar(rect[1]),scalar(rect[2]),scalar(rect[3]));
        else rectangle(cmd.slot,p[2],origin[0],top,width,height,
                       scalar(rect[0]),scalar(rect[1]),scalar(rect[2]),scalar(rect[3]));
    }
    // 1a6f90: a multi-piece sprite turned a quarter, centered on its anchor.
    // Pieces are submitted directly: no screen cull, no new order number.
    // Verified by stage 3 row 1 (six pieces) and stage 8 (single piece).
    void quarter(const auto& cmd) {
        const auto& p=cmd.parameters;
        const auto& header=cmd.pieces.front();
        const F art=projection.artworkScale(p[2]);
        const auto center=projection.point(scalar(p[0]),scalar(p[1]),projection.scale(p[2]));
        const float key=depth(p[2]);
        const F h=scalar(header[3]),w=scalar(header[2]),half=scalar(.5f);
        const F texel=scalar(1).div(scalar(cmd.slot==4||cmd.slot==5?1024.f:512.f));
        const F tall=h.mul(art),wide=w.mul(art).mul(half);
        const F bottom=center[1].add(wide),top=center[1].sub(wide);
        const F right=center[0].add(tall.mul(half)),left=center[0].add(neg(tall).mul(half));
        const F spanY=bottom.sub(top),spanX=right.sub(left);
        const F edgeU=scalar(header[0]).add(w),originV=scalar(header[1]);
        for(size_t i=cmd.pieces.size()>1?1:0;i<cmd.pieces.size();++i) {
            const auto& pc=cmd.pieces[i];
            const F u0=scalar(pc[0]),v0=scalar(pc[1]),u1=scalar(pc[0]+pc[2]),v1=scalar(pc[1]+pc[3]);
            const F ya=top.add(spanY.mul(edgeU.sub(u0)).div(w)),yb=top.add(spanY.mul(edgeU.sub(u1)).div(w));
            const F xa=left.add(spanX.mul(v0.sub(originV)).div(h)),xb=left.add(spanX.mul(v1.sub(originV)).div(h));
            const float tu0=number(u0.mul(texel)),tu1=number(u1.mul(texel)),tv0=number(v0.mul(texel)),tv1=number(v1.mul(texel));
            CombatStageStrip strip{cmd.slot,0xffffffff,key,{},int(pc[4])&0x200?0u:1u};
            strip.vertices={{number(xa),number(yb),tu1,tv0},{number(xa),number(ya),tu0,tv0},
                            {number(xb),number(yb),tu1,tv1},{number(xb),number(ya),tu0,tv1}};
            strips.push_back(std::move(strip));
        }
    }
    // The helper selection common to every stage's object rows.
    void run(const auto& commands) {
        for(const auto& cmd:commands) {
            switch(cmd.kind) {
            case 1:case 2:sprites(cmd);break;
            case 3:shadow(cmd);break;
            case 4:floor(cmd);break;
            case 5:meshShadow(cmd);break;
            case 6:floor(cmd,true);break;
            case 7:case 8:plain(cmd);break;
            case 10:quarter(cmd);break;
            default:throw std::logic_error("Stage command needs its own stage code");
            }
        }
    }
    void shadow(const auto& cmd) {
        // 1a4f40 -> 114118. 50e048 is the stage's shadow color; 510ce4 and
        // 510ce8 skew the far edge and are animated by some stages.
        const auto& p=cmd.parameters;
        const auto origin=projection.point(scalar(p[0]),scalar(p[1]),projection.scale(p[2]));
        const F s=projection.artworkScale(p[2]),w=scalar(p[5]).mul(s),h=scalar(p[6]).mul(s);
        const F x=origin[0],y=origin[1],left=x.sub(h.mul(scalar(shadowSkewX))),bottom=y.add(h.mul(scalar(shadowSkewY)));
        quad(cmd.slot,shadowColor,p[2],{left,x,left.add(w),x.add(w)},{bottom,y,bottom,y},
             scalar(p[3]),scalar(p[4]),scalar(p[5]),scalar(p[6]),true);
    }
    void floor(const auto& cmd,bool fullMesh=false) {
        const auto& p=cmd.parameters;
        const size_t n=size_t(fullMesh?p[1]:p[2]);
        // 1a5890 tests only the first column vertex of the two extreme rows.
        // Even a strip with one point outside each opposite edge is skipped.
        const auto outside=[&](float x){return x < -p[1] || x > 640+p[1];};
        // 1a8768 and 1a88e8 submit every column. Each whole mesh claims a
        // single 114d88 order offset, shared by all of its strips.
        const float z=fullMesh?depth(p[0]):number(scalar(10000000).sub(scalar(p[0]).mul(scalar(100))));
        if(fullMesh)++counter;
        for(size_t at=0;at<cmd.pieces.size();at+=n) {
            CombatStageStrip strip{cmd.slot,color,z,{},mode};
            for(size_t i=0;i<n;++i) {
                const auto& v=cmd.pieces[at+i];
                const auto xy=projection.point(scalar(v[0]),scalar(v[1]),projection.scale(v[2]));
                strip.vertices.push_back({number(xy[0]),number(xy[1]),v[3],v[4]});
            }
            if(fullMesh||!outside(strip.vertices[0].x)||!outside(strip.vertices[n-2].x))strips.push_back(std::move(strip));
        }
    }
    void meshShadow(const auto& cmd) {
        const auto& p=cmd.parameters;
        const auto origin=projection.point(scalar(p[0]),scalar(p[1]),projection.scale(p[2]));
        const F scale=projection.artworkScale(p[2]),width=scalar(p[3]).mul(scale),height=scalar(p[4]).mul(scale).mul(scalar(shadowSkewY)); // 510ce8 (1a5df8, 1a6034)
        const size_t n=size_t(p[5]);
        for(size_t at=0;at<cmd.pieces.size();at+=n) {
            CombatStageStrip strip{cmd.slot,shadowColor,depth(p[2]),{},mode};
            for(size_t i=0;i<n;++i) {
                const auto& v=cmd.pieces[at+i];
                strip.vertices.push_back({number(origin[0].add(width.mul(scalar(v[0])))),
                                          number(origin[1].add(height.mul(scalar(v[1])))),v[3],v[4]});
            }
            strips.push_back(std::move(strip));
        }
    }
};
}
}
