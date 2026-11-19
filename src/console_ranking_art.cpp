#include "console_ranking_art.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
struct Reader {
    std::ifstream input;
    explicit Reader(const std::filesystem::path& path):input(path,std::ios::binary) {
        if(!input)throw std::runtime_error("Missing ranking artwork: "+path.string());
    }
    unsigned take(unsigned size) {
        uint8_t buf[4]{};
        if(!input.read(reinterpret_cast<char*>(buf),size))throw std::runtime_error("Truncated ranking artwork");
        return buf[0]|(unsigned(buf[1])<<8)|(unsigned(buf[2])<<16)|(unsigned(buf[3])<<24);
    }
    int coord(){return std::bit_cast<int16_t>(uint16_t(take(2)));}
};
}

ConsoleRankingArt::ConsoleRankingArt(const std::filesystem::path& assets) {
    Reader file(assets/"console_ranking_art.bin");
    if(file.take(4)!=0x314b4e52)throw std::runtime_error("Invalid ranking artwork header");
    const auto textureCount=file.take(4),rectCount=file.take(4),listCount=file.take(4);
    if(file.take(4)!=phases_.size()||textureCount>255||rectCount>300000||listCount>5000)
        throw std::runtime_error("Invalid ranking artwork dimensions");
    textures_.push_back({});  // GS untextured rectangles carry their own RGB and opacity.
    for(unsigned i=0;i<textureCount;++i) {
        const int w=int(file.take(2)),h=int(file.take(2));
        const auto n=file.take(2);
        if(w<1||h<1||w>1024||h>1024||!n||n>256)throw std::runtime_error("Invalid ranking texture");
        std::array<Color,256> pal{};
        if(!file.input.read(reinterpret_cast<char*>(pal.data()),n*4))throw std::runtime_error("Truncated ranking palette");
        std::vector<uint8_t> indices(w*h);
        if(!file.input.read(reinterpret_cast<char*>(indices.data()),w*h))throw std::runtime_error("Truncated ranking texture");
        auto& t=textures_.emplace_back(Texture{w,h,{}});t.pixels.reserve(indices.size());
        for(auto index:indices) {
            if(index>=n)throw std::runtime_error("Invalid ranking palette index");
            t.pixels.push_back(pal[index]);
        }
    }
    rects_.reserve(rectCount);
    for(unsigned i=0;i<rectCount;++i) {
        Rect r{file.take(1),file.coord(),file.coord(),file.coord(),file.coord(),
               file.coord(),file.coord(),file.coord(),file.coord(),{}};
        const auto col=file.take(4);
        if(r.texture>=textures_.size())throw std::runtime_error("Invalid ranking texture slot");
        for(unsigned c=0;c<4;++c)r.color[c]=uint8_t(col>>(8*c));
        rects_.push_back(r);
    }
    for(unsigned i=0;i<listCount;++i) {
        const auto n=file.take(2);
        if(n>300)throw std::runtime_error("Invalid ranking draw count");
        auto& list=lists_.emplace_back();list.reserve(n);
        for(unsigned j=0;j<n;++j) {
            const auto id=file.take(4);
            if(id>=rects_.size())throw std::runtime_error("Invalid ranking rectangle index");
            list.push_back(id);
        }
    }
    for(auto& frames:phases_) {
        const auto count=file.take(2);
        if(!count||count>2000)throw std::runtime_error("Invalid ranking phase duration");
        frames.reserve(count);
        for(unsigned n=0;n<count;++n) {
            const auto id=file.take(2);
            if(id>=lists_.size())throw std::runtime_error("Invalid ranking draw list");
            frames.push_back(id);
        }
    }
    if(file.input.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Trailing ranking artwork");
}

void ConsoleRankingArt::paint(const RankingFrame& frame,std::span<uint8_t> rgba) const {
    constexpr int width=640,height=480;
    if(rgba.size()!=width*height*4)throw std::invalid_argument("Expected 640x480 ranking framebuffer");
    if(frame.phase>12)throw std::invalid_argument("Invalid ranking phase");
    if(!frame.battleVisible()) {
        // Phase 6 destroys the active battle after its last white quad. The
        // separate score table subsequently draws onto a fresh black target.
        for(size_t i=0;i<rgba.size();i+=4) {
            rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;
        }
    }
    // 1e9740 selects the empty callback 1e9750 while the scene transition
    // is pending. Every display swap still clears its own draw buffer.
    if(frame.phase==12)return;
    const auto& frames=phases_.at(frame.phase);
    if(frame.tick>=frames.size())throw std::invalid_argument("Invalid ranking animation tick");
    // The original lists are already stably depth ordered, including the
    // face quad between its decorative frame and the rank lettering.
    for(const auto id:lists_[frames[frame.tick]]) {
        const auto& r=rects_[id];
        const auto left=std::max(0,r.x),right=std::min(width,r.right);
        const auto top=std::max(0,r.y),bottom=std::min(height,r.bottom);
        const auto alpha=r.color[3];
        if(left>=right||top>=bottom||!alpha)continue;
        const auto& tex=textures_[r.texture];
        std::array<int,width> sourceColumns;
        if(r.texture) {
            for(int x=left;x<right;++x)sourceColumns[x]=std::clamp(
                r.u+((2*(x-r.x)+1)*(r.ur-r.u))/(2*(r.right-r.x)),0,tex.w-1);
        }
        for(int y=top;y<bottom;++y) {
            const int row=r.texture?std::clamp(r.v+((2*(y-r.y)+1)*(r.vb-r.v))/(2*(r.bottom-r.y)),0,tex.h-1)*tex.w:0;
            auto* dst=rgba.data()+(y*width+left)*4;
            for(int x=left;x<right;++x,dst+=4) {
                if(!r.texture) {
                    for(unsigned c=0;c<3;++c)dst[c]+=((r.color[c]-dst[c])*alpha)>>7;
                } else {
                    const auto& pixel=tex.pixels[row+sourceColumns[x]];
                    const int opacity=pixel[3]*alpha/128;
                    if(!opacity)continue;
                    for(unsigned c=0;c<3;++c) {
                        const int src=std::min(255,pixel[c]*r.color[c]/128);
                        dst[c]=uint8_t(std::clamp(int(dst[c])+(((src-dst[c])*opacity)>>7),0,255));
                    }
                }
            }
        }
    }
}
}
