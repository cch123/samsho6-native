#pragma once
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <span>
#include <stdexcept>
#include <vector>

namespace ss6::hud {
inline constexpr int screenWidth=640,screenHeight=448,atlasSize=512;
inline std::vector<uint8_t> loadAtlas(const std::filesystem::path& path) {
    std::ifstream stream(path,std::ios::binary|std::ios::ate);
    if(!stream || stream.tellg()!=atlasSize*atlasSize+1024)
        throw std::runtime_error("Missing or invalid HUD texture: "+path.string());
    std::vector<uint8_t> bytes(static_cast<size_t>(stream.tellg()));
    stream.seekg(0);
    if(!stream.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))
        throw std::runtime_error("Truncated HUD texture: "+path.string());
    return bytes;
}

struct Sprite { int u,v,w,h; };
inline void sprite(std::span<uint8_t> dst,const std::vector<uint8_t>& atlas,Sprite s,
            int x,int y,int width,int height,int vertexAlpha=128,bool additive=false,bool flipX=false,bool redOnly=false) {
    for(int dy=std::max(0,y);dy<std::min(screenHeight,y+height);++dy) {
        const auto v=s.v+(2*(dy-y)+1)*s.h/(2*height);
        for(int dx=std::max(0,x);dx<std::min(screenWidth,x+width);++dx) {
            const int texelX=(2*(dx-x)+1)*s.w/(2*width);
            const auto u=s.u+(flipX?s.w-1-texelX:texelX);
            const unsigned index=atlas[v*atlasSize+u];
            // 1162f0 points at the appended 256-entry CLUT. The original
            // uploads a 16x16 PSMCT32 block; the GS CSM1 fetch exchanges
            // logical bits 3 and 4. Its 4-bit palette selector is unused.
            const auto entry=(index&~24u)|((index&8u)<<1)|((index&16u)>>1);
            const auto* texel=atlas.data()+atlasSize*atlasSize+entry*4;
            const int alpha=(texel[3]*vertexAlpha)>>7;
            if(!alpha) continue;
            auto* pixel=dst.data()+(dy*screenWidth+dx)*4;
            for(int c=0;c<3;++c) {
                // The 2ff2 fire packets use GS ALPHA 0x8000000029 (Cs+Cd).
                const int source=redOnly&&c!=0?0:texel[c];
                const int channel=additive?std::min(255,pixel[c]+source):pixel[c]+(((source-pixel[c])*alpha)>>7);
                pixel[c]=uint8_t(channel);
            }
            pixel[3]=255;
        }
    }
}

}
