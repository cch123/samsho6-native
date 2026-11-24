#pragma once
#include "asset_files.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <string>
#include <fstream>
#include <span>
#include <stdexcept>
#include <vector>

namespace ss6 {
struct StageVertex {float x,y,u,v;};
inline std::vector<uint8_t> readStageFile(const std::filesystem::path& path,size_t maximum) {
    std::ifstream f(resolveAsset(path),std::ios::binary|std::ios::ate);
    if(!f||f.tellg()<=0||size_t(f.tellg())>maximum) throw std::runtime_error("Invalid combat stage asset: "+path.string());
    std::vector<uint8_t> bytes(size_t(f.tellg()));
    f.seekg(0);
    if(!f.read(reinterpret_cast<char*>(bytes.data()),bytes.size())) throw std::runtime_error("Truncated combat stage asset");
    return bytes;
}
struct StageReader {
    std::span<const uint8_t> bytes;
    uint32_t word() {
        if(bytes.size()<4)throw std::runtime_error("Truncated stage geometry");
        const uint32_t result=bytes[0]|uint32_t(bytes[1])<<8|uint32_t(bytes[2])<<16|uint32_t(bytes[3])<<24;
        bytes=bytes.subspan(4);
        return result;
    }
    float value() {
        const float f=std::bit_cast<float>(word());
        if(!std::isfinite(f)||std::abs(f)>1.e6f)throw std::runtime_error("Invalid stage coordinate");
        return f;
    }
};

// 1149d0 and the 116588 CLUT conversion used by both battle scenery and
// the fixed-camera Game Over page. RGB values retain the original 5-bit
// levels. Index zero is cleared by the loader even for an opaque source.
class StageRaster {
public:
    explicit StageRaster(const std::filesystem::path& assets,unsigned stage=0) {
        if(stage>11)throw std::invalid_argument("Unsupported combat stage textures");
        char stem[16];
        std::snprintf(stem,sizeof stem,"bg%02u_",stage);
        // Texture slots 4.. in constructor order. Stages 3, 9 and 11 load
        // their second CLUT from file 2 and bind every slot after the first
        // to it; the others use file 3 for the slots after the second.
        const bool early=stage==3||stage==9||stage==11;
        for(unsigned id=0;id<textures_.size();++id) {
            const auto path=assets/(stem+std::to_string(id+1)+".tex");
            if(!std::filesystem::exists(path))break;
            textures_[id]=readStageFile(path,1024*1024);
            sizes_[id]=textures_[id].size()==1024*1024?1024:512;
            if(textures_[id].size()!=size_t(sizes_[id])*sizes_[id])throw std::runtime_error("Invalid stage texture");
            banks_[id]=id>=(early?1u:2u);
        }
        if(textures_[0].empty())throw std::runtime_error("Missing stage textures");
        for(unsigned bank=0;bank<2;++bank) {
            const auto bytes=readStageFile(assets/(stem+std::string(bank?(early?"2.pal":"3.pal"):"1.pal")),512);
            if(bytes.size()!=512)throw std::runtime_error("Invalid stage palette");
            for(unsigned i=1;i<256;++i) {
                const unsigned raw=bytes[2*i]|unsigned(bytes[2*i+1])<<8;
                if(!(raw&0x8000))continue;
                const unsigned r=(raw>>10)&31,g=(raw>>5)&31,b=raw&31;
                colors_[0][bank*256+i]=0x80000000u|(r<<3)|(g<<11)|(b<<19);
                colors_[1][bank*256+i]=0x80000000u|(((10*r+16*g+6*b)>>5)<<3)*0x010101u;
            }
        }
    }
    using Palette=std::array<uint32_t,512>;
    Palette palette(std::span<const uint16_t,1024> tones) const {
        Palette result;
        for(unsigned i=0;i<result.size();++i)result[i]=colors_[(tones[512+i]&5)!=0][i];
        return result;
    }
    const Palette& grayPalette() const {return colors_[1];}
    static void clear(std::span<uint8_t> rgba) {
        if(rgba.size()!=640*448*4&&rgba.size()!=640*480*4)
            throw std::invalid_argument("Expected a 640x448 or 640x480 stage");
        for(size_t i=0;i<rgba.size();i+=4){rgba[i]=rgba[i+1]=rgba[i+2]=0;rgba[i+3]=255;}
    }
    void paint(std::span<uint8_t> rgba,unsigned slot,uint32_t color,unsigned mode,
               std::span<const StageVertex> vertices,const Palette& palette) const {
        const unsigned id=slot-4;
        const auto& texture=textures_.at(id);
        if(texture.empty())throw std::out_of_range("Stage texture slot is not loaded");
        // 1149d0 halves each vertex color channel; without its alpha mode
        // the strip is opaque wherever the texel is.
        Modulation m;
        for(unsigned k=0;k<3;++k)m.rgb[k]=int(((color>>(8*k))&255)+1)>>1;
        m.alpha=mode==1?int((color>>24)+1)>>1:128;
        // A shared strip diagonal contributes only once. Double-drawing it
        // is visible on the meshes that project translucent shadows.
        for(size_t i=2;i<vertices.size();++i)
            triangle(rgba,vertices[i-2],vertices[i-1],vertices[i],texture,sizes_[id],
                     palette.data()+(banks_[id]?256:0),m);
    }
private:
    struct Modulation { std::array<int,3> rgb; int alpha; };
    std::array<std::vector<uint8_t>,5> textures_;
    std::array<int,5> sizes_{};
    std::array<bool,5> banks_{};
    std::array<Palette,2> colors_{};
    static double edge(const StageVertex& a,const StageVertex& b,double x,double y) {
        return (double(b.x)-a.x)*(y-a.y)-(double(b.y)-a.y)*(x-a.x);
    }
    static bool topLeft(const StageVertex& a,const StageVertex& b) {
        return b.y<a.y||(b.y==a.y&&b.x>a.x);
    }
    static void triangle(std::span<uint8_t> rgba,const StageVertex& a,const StageVertex& b,const StageVertex& c,
                  const std::vector<uint8_t>& texture,int size,const uint32_t* palette,const Modulation& m) {
        const int height=int(rgba.size()/(640*4));
        const int x0=std::max(0,int(std::ceil(std::min({a.x,b.x,c.x})-.5)));
        const int x1=std::min(640,int(std::ceil(std::max({a.x,b.x,c.x})-.5)));
        const int y0=std::max(0,int(std::ceil(std::min({a.y,b.y,c.y})-.5)));
        const int y1=std::min(height,int(std::ceil(std::max({a.y,b.y,c.y})-.5)));
        const double area=edge(a,b,c.x,c.y);
        if(!area||x0>=x1||y0>=y1)return;
        if(area<0){triangle(rgba,a,c,b,texture,size,palette,m);return;}
        const bool ab=topLeft(a,b),bc=topLeft(b,c),ca=topLeft(c,a);
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x) {
            const double wa=edge(b,c,x+.5,y+.5),wb=edge(c,a,x+.5,y+.5),wc=edge(a,b,x+.5,y+.5);
            if(wa<0||wb<0||wc<0||(!wa&&!bc)||(!wb&&!ca)||(!wc&&!ab))continue;
            const int u=std::clamp(int((wa*a.u+wb*b.u+wc*c.u)*size/area),0,size-1);
            const int v=std::clamp(int((wa*a.v+wb*b.v+wc*c.v)*size/area),0,size-1);
            const uint32_t color=palette[texture[v*size+u]];
            if(!color)continue;
            auto* dst=rgba.data()+(y*640+x)*4;
            // Texel alpha is 0x80 for every visible CLUT entry.
            for(unsigned k=0;k<3;++k) {
                const int source=(int((color>>(k*8))&255)*m.rgb[k])>>7;
                dst[k]=uint8_t(int(dst[k])+(((source-int(dst[k]))*m.alpha)>>7));
            }
        }
    }
};
}
