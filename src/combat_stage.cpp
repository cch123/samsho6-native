#include "combat_stage.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ss6 {
namespace {
using F=ScalarFloat;
F scalar(float x) { return {std::bit_cast<uint32_t>(x)}; }
float number(F x) { return std::bit_cast<float>(x.bits); }
F neg(F x) {return {x.bits^0x80000000u};}

struct Projection {
    const StageCamera& camera;
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

    float depth(float z)const {return number(scalar(10000000).sub(scalar(z).mul(scalar(100))).add(F::integer(counter)));}
    void quad(unsigned slot,uint32_t color,float z,std::array<F,4> xs,std::array<F,4> ys,
              F u,F v,F w,F h) {
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
        const bool left=color==0x60000000
            ? number(xs[0])<0&&number(xs[1])<0&&number(xs[2])<0&&number(ys[3])<0
            : std::all_of(xs.begin(),xs.end(),[](F p){return number(p)<0;});
        const bool right=std::all_of(xs.begin(),xs.end(),[](F p){return number(p)>640;});
        if(left||right||outside(ys,480))return;
        const float sort=depth(z);
        ++counter;
        const F ts=scalar(slot<6?1.f/1024.f:1.f/512.f);
        u=u.mul(ts);v=v.mul(ts);
        const F u1=u.add(w.mul(ts)),v1=v.add(h.mul(ts));
        CombatStageStrip strip{slot,color,sort,{}};
        for(unsigned i=0;i<4;++i)
            strip.vertices.push_back({number(xs[i]),number(ys[i]),number(i&2?u1:u),number(i&1?v1:v)});
        strips.push_back(std::move(strip));
    }
    void rectangle(unsigned slot,float z,F x,F y,F w,F h,F u,F v,F uw,F vh) {
        const F x1=x.add(w),y1=y.add(h);
        quad(slot,0xffffffff,z,{x,x,x1,x1},{y,y1,y,y1},u,v,uw,vh);
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
        for(size_t i=cmd.pieces.size()>1?1:0;i<cmd.pieces.size();++i) {
            const auto& pc=cmd.pieces[i];
            const F dx=scalar(pc[0]-header[0]).mul(width).div(w);
            const F dy=scalar(pc[1]-header[1]).mul(height).div(h);
            const F sw=scalar(pc[2]),sh=scalar(pc[3]);
            rectangle(cmd.slot,z,mirror?left.sub(dx):left.add(dx),top.add(dy),
                      mirror?neg(sw.mul(sx)):sw.mul(sx),sh.mul(sy),scalar(pc[0]),scalar(pc[1]),sw,sh);
        }
    }
    void shadow(const auto& cmd) {
        const auto& p=cmd.parameters;
        const auto origin=projection.point(scalar(p[0]),scalar(p[1]),projection.scale(p[2]));
        const F s=projection.artworkScale(p[2]),w=scalar(p[5]).mul(s),h=scalar(p[6]).mul(s);
        const F x=origin[0],y=origin[1],left=x.sub(h.mul(scalar(0))),bottom=y.add(h.mul(scalar(.1f)));
        quad(cmd.slot,0x60000000,p[2],{left,x,left.add(w),x.add(w)},{bottom,y,bottom,y},
             scalar(p[3]),scalar(p[4]),scalar(p[5]),scalar(p[6]));
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
            CombatStageStrip strip{cmd.slot,0xffffffff,z,{}};
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
        const F scale=projection.artworkScale(p[2]),width=scalar(p[3]).mul(scale),height=scalar(p[4]).mul(scale).mul(scalar(.1f));
        const size_t n=size_t(p[5]);
        for(size_t at=0;at<cmd.pieces.size();at+=n) {
            CombatStageStrip strip{cmd.slot,0x60000000,depth(p[2]),{}};
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

CombatStage::CombatStage(const std::filesystem::path& assets,unsigned stage)
    :stage_(stage),groups_(stage==0?24:29),raster_(assets,stage) {
    const auto bytes=readStageFile(assets/(stage==0?"combat_stage.bin":"combat_stage_01.bin"),1024*1024);
    StageReader r{bytes};
    if(r.word()!=(stage==0?0x30475453u:0x31475453u)||r.word()!=1)throw std::runtime_error("Invalid stage geometry header");
    for(auto& group:groups_) {
        const auto variants=r.word();
        if(!variants||variants>20)throw std::runtime_error("Invalid stage picture count");
        group.resize(variants);
        for(auto& commands:group) {
            const auto count=r.word();
            if(!count||count>8)throw std::runtime_error("Invalid stage command count");
            for(unsigned i=0;i<count;++i) {
                Command cmd{r.word(),r.word(),{},{}};
                const auto params=r.word(),pieces=r.word();
                constexpr unsigned expected[]={0,5,5,7,3,6,2};
                if(!cmd.kind||cmd.kind>6||cmd.slot<4||cmd.slot>7||params!=expected[cmd.kind]||pieces>4096)
                    throw std::runtime_error("Invalid stage draw command");
                for(unsigned j=0;j<params;++j)cmd.parameters[j]=r.value();
                const unsigned arity=cmd.kind<3?4:5;
                cmd.pieces.resize(pieces);
                for(auto& piece:cmd.pieces) for(unsigned j=0;j<arity;++j)piece[j]=r.value();
                if(cmd.kind<3&&(!pieces||cmd.pieces[0][2]<=0||cmd.pieces[0][3]<=0))
                    throw std::runtime_error("Invalid stage sprite extents");
                if(cmd.kind>=4) {
                    const float n=cmd.parameters[params-1];
                    if(n<4||n>128||std::floor(n)!=n||!pieces||pieces%unsigned(n))
                        throw std::runtime_error("Invalid stage mesh dimensions");
                }
                commands.push_back(std::move(cmd));
            }
        }
    }
    if(!r.bytes.empty())throw std::runtime_error("Trailing stage geometry data");
}

std::vector<CombatStageStrip> CombatStage::geometry(const CombatStageState& state,unsigned* nextDepth) const {
    if(nextDepth)*nextDepth=100;
    if(!state.visible||state.suppressGeometry)return {};
    Projector renderer{{state.camera},100,{}};
    renderer.strips.reserve(160);
    renderer.sky(stage_);
    for(unsigned group=0;group<groups_.size();++group) {
        unsigned picture=0;
        if(group>0) {
            picture=state.pictureForRow(unsigned(group-1));
        }
        for(const auto& cmd:groups_[group].at(picture)) {
            switch(cmd.kind) {
            case 1:case 2:renderer.sprites(cmd);break;
            case 3:renderer.shadow(cmd);break;
            case 4:renderer.floor(cmd);break;
            case 5:renderer.meshShadow(cmd);break;
            case 6:renderer.floor(cmd,true);break;
            }
        }
    }
    std::stable_sort(renderer.strips.begin(),renderer.strips.end(),[](const auto& a,const auto& b){return a.z<b.z;});
    if(nextDepth)*nextDepth=renderer.counter;
    return std::move(renderer.strips);
}

unsigned CombatStage::paint(const CombatStageState& state,std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba) const {
    StageRaster::clear(rgba);
    const auto palette=raster_.palette(tones);
    unsigned nextDepth=100;
    for(const auto& strip:geometry(state,&nextDepth))
        raster_.paint(rgba,strip.slot,strip.color,strip.vertices,palette);
    return nextDepth;
}
}
