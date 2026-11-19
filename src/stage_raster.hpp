#pragma once
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <span>
#include <stdexcept>
#include <vector>

namespace ss6 {
struct StageVertex {float x,y,u,v;};
inline std::vector<uint8_t> readStageFile(const std::filesystem::path& path,size_t maximum) {
    std::ifstream f(path,std::ios::binary|std::ios::ate);
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
        if(stage>1)throw std::invalid_argument("Unsupported combat stage textures");
        const std::string stem=stage==0?"bg00_":"bg01_";
        for(unsigned id=0;id<4;++id) {
            const size_t size=id<2?1024:512;
            textures_[id]=readStageFile(assets/(stem+std::to_string(id+1)+".tex"),size*size);
            if(textures_[id].size()!=size*size)throw std::runtime_error("Invalid stage texture");
        }
        for(unsigned bank=0;bank<2;++bank) {
            const auto bytes=readStageFile(assets/(stem+(bank?"3.pal":"1.pal")),512);
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
    void paint(std::span<uint8_t> rgba,unsigned slot,uint32_t color,
               std::span<const StageVertex> vertices,const Palette& palette) const {
        const unsigned id=slot-4;
        const auto& texture=textures_.at(id);
        // A shared strip diagonal contributes only once. Double-drawing it
        // is visible on the meshes that project translucent shadows.
        for(size_t i=2;i<vertices.size();++i)
            triangle(rgba,vertices[i-2],vertices[i-1],vertices[i],texture,id<2?1024:512,
                     palette.data()+(id<2?0:256),color==0x60000000);
    }
private:
    std::array<std::vector<uint8_t>,4> textures_;
    std::array<Palette,2> colors_{};
    static double edge(const StageVertex& a,const StageVertex& b,double x,double y) {
        return (double(b.x)-a.x)*(y-a.y)-(double(b.y)-a.y)*(x-a.x);
    }
    static bool topLeft(const StageVertex& a,const StageVertex& b) {
        return b.y<a.y||(b.y==a.y&&b.x>a.x);
    }
    static void triangle(std::span<uint8_t> rgba,const StageVertex& a,const StageVertex& b,const StageVertex& c,
                  const std::vector<uint8_t>& texture,int size,const uint32_t* palette,bool shadow) {
        const int height=int(rgba.size()/(640*4));
        const int x0=std::max(0,int(std::ceil(std::min({a.x,b.x,c.x})-.5)));
        const int x1=std::min(640,int(std::ceil(std::max({a.x,b.x,c.x})-.5)));
        const int y0=std::max(0,int(std::ceil(std::min({a.y,b.y,c.y})-.5)));
        const int y1=std::min(height,int(std::ceil(std::max({a.y,b.y,c.y})-.5)));
        const double area=edge(a,b,c.x,c.y);
        if(!area||x0>=x1||y0>=y1)return;
        if(area<0){triangle(rgba,a,c,b,texture,size,palette,shadow);return;}
        const bool ab=topLeft(a,b),bc=topLeft(b,c),ca=topLeft(c,a);
        for(int y=y0;y<y1;++y)for(int x=x0;x<x1;++x) {
            const double wa=edge(b,c,x+.5,y+.5),wb=edge(c,a,x+.5,y+.5),wc=edge(a,b,x+.5,y+.5);
            if(wa<0||wb<0||wc<0||(!wa&&!bc)||(!wb&&!ca)||(!wc&&!ab))continue;
            const int u=std::clamp(int((wa*a.u+wb*b.u+wc*c.u)*size/area),0,size-1);
            const int v=std::clamp(int((wa*a.v+wb*b.v+wc*c.v)*size/area),0,size-1);
            const uint32_t color=palette[texture[v*size+u]];
            if(!color)continue;
            auto* dst=rgba.data()+(y*640+x)*4;
            if(shadow) {
                // 1149d0 halves the 0x60 vertex alpha to the GS value 0x30.
                for(unsigned k=0;k<3;++k)dst[k]+=(-int(dst[k])*48)>>7;
            }else{
                for(unsigned k=0;k<3;++k)dst[k]=uint8_t(color>>(k*8));
            }
        }
    }
};
}
