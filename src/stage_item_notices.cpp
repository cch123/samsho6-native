#include "stage_item_notices.hpp"
#include "scalar_float.hpp"
#include "stage_raster.hpp"
#include <algorithm>
#include <bit>
#include <cmath>

namespace ss6 {
namespace {
using F=ScalarFloat;
F number(float x){return {std::bit_cast<uint32_t>(x)};}
float value(F f){return std::bit_cast<float>(f.bits);}
}
int StageItemNotices::allocate(int kind,int x,int y) {
    for(unsigned i=0;i<pool_.size();++i)if(pool_[i].kind==-1) {
        pool_[i]={kind,value(F::integer(x)),value(F::integer(y))};return int(i);
    }
    return -1;
}
bool StageItemNotices::heal(int x){return allocate(0,x,80)>=0;}
void StageItemNotices::visit(uint32_t delta,const StageCamera& camera,std::array<int,2> weaponX,
                             std::array<bool,2> cpu,unsigned depthCounter) {
    drawCount_=0;
    for(unsigned side=0;side<2;++side) {
        auto& slot=weaponSlot_[side];
        if(weaponX[side]>=0) {
            if(slot<0)slot=allocate(cpu[side]?3:int(side)+1,weaponX[side],50);
        } else if(slot>=0){pool_[unsigned(slot)]={};slot=-1;}
    }
    for(auto& notice:pool_) {
        if(notice.kind<0)continue;
        notice.elapsed+=delta;
        const bool healing=notice.kind==0;
        int u=317,v=77,w=66,h=24,alpha=255;
        if(healing) {
            const int age=int32_t(notice.elapsed)>>8;
            if(age>=60){notice={};continue;}
            // 1b5fd0 truncates the 8.8 movement product before adding it.
            notice.y=value(number(notice.y).add(F::integer(int32_t((128u*delta)>>8)).mul({0x3b800000})));
            if(age>=30)alpha-=255*(age-30)/30;
        } else {
            notice.animation+=delta;
            int cell=(int32_t(notice.animation)>>8)/4;
            // Even a long update rolls the original animation once, never
            // consuming several cycles in a single priority-20 visit.
            if(cell>=4){notice.animation-=16*256;cell=0;}
            constexpr std::array origin{324,380,439},width{55,58,72};
            u=origin[notice.kind-1];w=width[notice.kind-1];v=152+32*cell;h=31;
        }
        const auto pos=camera.project(notice.x,notice.y,-1);
        const auto scale=number(pos.scale).div({0x3f805220});
        // 1b6128 centers by half the *texture* width, then scales width
        // and height. Centering the scaled width shifts the close camera.
        const auto left=number(pos.x).sub(F::integer(w).mul(number(0.5f)));
        const auto right=left.add(F::integer(w).mul(scale));
        const float bottom=value(number(pos.y).add(F::integer(h).mul(scale)));
        if(value(right)<0||value(left)>640||bottom<0||pos.y>480)continue;
        const float depth=10014100.0f+float(depthCounter++); // 114d88(-141)
        draws_[drawCount_++]={value(left),pos.y,value(right),bottom,depth,u,v,w,h,(alpha+1)/2};
    }
}
StageItemNoticeArt::StageItemNoticeArt(const std::filesystem::path& assets)
    :atlas_(readStageFile(assets/"obj2_16.tex",512*512+1024)) {
    if(atlas_.size()!=512*512+1024)throw std::runtime_error("Invalid stage item notice atlas");
}
void StageItemNoticeArt::paint(const StageItemNoticeQuad& q,std::span<uint8_t> pixels) const {
    if(pixels.size()!=640*448*4&&pixels.size()!=640*480*4)throw std::invalid_argument("Expected battle framebuffer");
    const int height=int(pixels.size()/(640*4));
    const auto lo=[](float edge,int bound){return std::clamp(int(std::ceil(double(edge)-.5)),0,bound);};
    const int firstX=lo(q.left,640),lastX=lo(q.right,640),firstY=lo(q.top,height),lastY=lo(q.bottom,height);
    for(int y=firstY;y<lastY;++y) {
        const int v=q.v+int((double(y)+.5-q.top)*q.height/(q.bottom-q.top));
        for(int x=firstX;x<lastX;++x) {
            const int u=q.u+int((double(x)+.5-q.left)*q.width/(q.right-q.left));
            const unsigned ix=atlas_[v*512+u];
            const unsigned entry=(ix&~24u)|((ix&8u)<<1)|((ix&16u)>>1);
            const auto* texture=&atlas_[512*512+entry*4];
            const int a=texture[3]*q.alpha>>7;
            auto* dst=&pixels[(y*640+x)*4];
            for(int c=0;c<3;++c)dst[c]+=((int(texture[c])-dst[c])*a)>>7;
        }
    }
}
}
