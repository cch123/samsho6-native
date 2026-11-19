#include "vs_curtain.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr int atlasWidth=512, width=640, height=480;
void read(std::istream& stream, void* dst, std::size_t bytes) {
    if(!stream.read(static_cast<char*>(dst), static_cast<std::streamsize>(bytes)))
        throw std::runtime_error("Short read in VS curtain resource");
}
int signed16(std::istream& input) {
    std::array<uint8_t,2> bytes;
    read(input,bytes.data(),bytes.size());
    const int value=bytes[0]|(bytes[1]<<8);
    return value>=32768?value-65536:value;
}
}

VsCurtain::VsCurtain(const std::filesystem::path& assets) {
    std::ifstream layout(assets/"vs_curtain.bin",std::ios::binary);
    std::array<char,4> header;
    read(layout,header.data(),header.size());
    if(header!=std::array<char,4>{'C','V','D','1'})throw std::runtime_error("Invalid VS curtain layout");
    for(auto& panels:frames_) {
        const int count=layout.get();
        if(count<0 || count>9)throw std::runtime_error("Invalid VS curtain panel count");
        for(int i=0;i<count;++i) {
            Panel p{signed16(layout),signed16(layout),signed16(layout),signed16(layout),
                    signed16(layout),signed16(layout),signed16(layout),signed16(layout)};
            if(p.u<0 || p.v<0 || p.endU>atlasWidth || p.endV>atlasWidth ||
               p.endU<=p.u || p.endV<=p.v || std::abs(p.right-p.x)!=p.endU-p.u || p.bottom-p.y!=p.endV-p.v)
                throw std::runtime_error("Invalid VS curtain panel bounds");
            panels.push_back(p);
        }
    }
    if(layout.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected VS curtain layout data");
    std::ifstream texture(assets/"change_base16.tex",std::ios::binary);
    std::vector<uint8_t> indices(atlasWidth*atlasWidth);
    std::array<std::array<uint8_t,4>,256> palette;
    read(texture,indices.data(),indices.size());read(texture,palette.data(),sizeof(palette));
    if(texture.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected VS curtain texture data");
    pixels_.reserve(indices.size());
    for(unsigned i:indices) {
        // Slot 3 selects the embedded 16x16 CSM1 palette in 1149d0,
        // even though the system art initializer also assigns palette bank 7.
        pixels_.push_back(palette[(i&~24u)|((i&8u)<<1)|((i&16u)>>1)]);
    }
}
void VsCurtain::paint(unsigned frame,std::span<uint8_t> rgba) const {
    if(rgba.size()!=width*height*4)throw std::invalid_argument("VS curtain requires a 640x480 RGBA canvas");
    if(frame>=frames_.size())return;
    for(const auto& p:frames_[frame]) {
        const bool mirrored=p.right<p.x;
        const int left=std::max(0,std::min(p.x,p.right));
        const int right=std::min(width,std::max(p.x,p.right));
        if(left>=right)continue;
        for(int y=std::max(p.y,0);y<std::min(p.bottom,height);++y) {
            auto* dst=rgba.data()+(y*width+left)*4;
            for(int x=left;x<right;++x,dst+=4) {
                const int u=p.u+(mirrored?p.x-1-x:x-p.x);
                const auto& c=pixels_[(p.v+y-p.y)*atlasWidth+u];
                for(int i=0;i<3;++i)dst[i]+=((int(c[i])-dst[i])*c[3])>>7;
            }
        }
    }
}
}
