#include "asset_files.hpp"
#include "versus_draw_art.hpp"
#include "player_object.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
std::vector<uint8_t> load(const std::filesystem::path& path,size_t size) {
    std::ifstream in(resolveAsset(path),std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(size))throw std::runtime_error("Missing or invalid Game Over resource: "+path.string());
    std::vector<uint8_t> bytes(size);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),size))throw std::runtime_error("Truncated Game Over resource: "+path.string());
    return bytes;
}

int titleSize(unsigned tick,int dimension) {
    // 138eb0 accumulates four cubic terms separately, then truncates. The
    // algebraically simplified cubic changes a pixel at some early ticks.
    using F=ScalarFloat;
    const auto t=F::integer(tick).div(F::integer(50)),s=F::integer(1).sub(t);
    const auto threeS=s.mul(F::integer(3)),large=F::integer(5*dimension);
    auto sum=s.mul(s).mul(s).mul(large);
    sum=sum.add(threeS.mul(s).mul(t).mul(large));
    sum=sum.add(threeS.mul(t).mul(t).mul(large));
    return sum.add(t.mul(t).mul(t).mul(F::integer(dimension))).truncate();
}
}

VersusDrawArt::VersusDrawArt(const std::filesystem::path& assets)
    :scene_(assets),atlas_(load(assets/"font_otherscene16.tex",512*512/2)) {
    // 113890 loads the shared obj0 CLUT and clears index zero in each
    // bank. 138888 grays entries 256 onward (the actor and stage banks).
    const auto pal=load(assets/"obj0.pal",512);
    for(unsigned bank=0;bank<2;++bank)for(unsigned i=1;i<16;++i) {
        const auto pos=(bank*16+i)*2;
        const unsigned color=pal[pos]|(unsigned(pal[pos+1])<<8);
        palettes_[bank][i]={uint8_t(((color>>10)&31)*8),uint8_t(((color>>5)&31)*8),
                             uint8_t((color&31)*8),uint8_t(color&0x8000?128:0)};
    }
    std::fill(tones_.begin()+256,tones_.end(),1);
    ActionBank bank(assets,true);
    PlayerObject actor(bank,1793);
    actor.timeline.setPosition(320,0);
    // 1388e0 moves and submits the raw body before advancing its clock.
    // Cache those immutable submissions so a redraw never advances the ACT.
    const auto ticks=actor.timeline.action().cycleTicks();
    for(unsigned i=0;i<=ticks;++i) {
        actor.move(256);
        auto pose=actor.childParentWords();
        pose[0x24/4]=actor.timeline.action().id();
        pose[0x28/4]=actor.timeline.clock().step;
        pose[0x104/4]=actor.timeline.clock().flags104;
        poses_.push_back(pose);
        actor.animate(256);
    }
    if(!actor.timeline.clock().endReached)throw std::runtime_error("Game Over ACT must hold its last pose");
}

void VersusDrawArt::caption(std::span<uint8_t> rgba,unsigned palette,int u,int v,int texWidth,int texHeight,
                            int left,int top,int width,int height,int alpha) const {
    const int right=std::min(left+width,640),bottom=std::min(top+height,480);
    const auto& colors=palettes_[palette];
    for(int y=std::max(0,top);y<bottom;++y) {
        const int sy=v+((2*(y-top)+1)*texHeight)/(2*height);
        for(int x=std::max(0,left);x<right;++x) {
            const int sx=u+((2*(x-left)+1)*texWidth)/(2*width);
            const auto& texel=colors[(atlas_[sy*256+sx/2]>>(4*(sx%2)))&15];
            if(!texel[3])continue;
            auto* dst=rgba.data()+4*(y*640+x);
            for(int c=0;c<3;++c)dst[c]+=((int(texel[c])-dst[c])*alpha)>>7;
        }
    }
}

void VersusDrawArt::paint(unsigned frame,unsigned objectTick,unsigned characterSlot,std::span<uint8_t> rgba) {
    if(rgba.size()!=640*480*4||characterSlot>1)throw std::invalid_argument("Expected a 640x480 Game Over stage and a player slot");
    auto pose=poses_[std::min<size_t>(objectTick,poses_.size()-1)];
    pose[0xc/4]=pose[0x10/4]=pose[0xcc/4]=characterSlot;
    queue_.beginFrame();
    queue_.submit(pose,{});
    queue_.sort();
    // The bottom ACT tiles extend below the battle viewport in this scene.
    const StageCamera camera;
    scene_.paint(queue_,{camera,{},-2,3},{},tones_,rgba,{});
    if(frame<30)return;
    if(frame>80)for(int y=185;y<305;++y)for(int x=0;x<640;++x) {
        auto* pixel=rgba.data()+4*(y*640+x);
        pixel[0]=pixel[1]=pixel[2]=0;
    }
    int x=72,y=154,w=470,h=132;
    if(frame<80) {
        w=titleSize(frame-30,470);
        h=titleSize(frame-30,132);
        x-=(w-470)/2;
        y-=(h-132)/2;
    }else if(frame<136) {
        constexpr std::array<int,8> dx={0,0,-4,9,-6,8,6,-1},dy={-5,7,0,0,-4,2,-5,4};
        x+=dx[(frame-80)%8];
        y+=dy[(frame-80)%8];
    }
    // 108020 clamps the far texture coordinate to 511 before submission.
    // The title reaches the lower atlas edge; the last source span is 131.
    caption(rgba,0,0,380,470,131,x,y,w,h,128);
    if(frame>=136) {
        const int alpha=frame>=196?255:int((frame-136)*17/4);
        caption(rgba,1,211,136,206,58,204,260,206,58,(alpha+1)/2);
    }
}
}
