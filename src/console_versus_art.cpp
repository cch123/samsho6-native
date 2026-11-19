#include "console_versus_art.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
void mix(uint8_t* dest,int r,int g,int b,int alpha) {
    dest[0]+=((r-dest[0])*alpha)>>7;
    dest[1]+=((g-dest[1])*alpha)>>7;
    dest[2]+=((b-dest[2])*alpha)>>7;
}
void rect(std::span<uint8_t> rgba,int x,int y,int w,int h,int r,int g,int b,int alpha) {
    if(!alpha)return;
    for(int row=0;row<h;++row) {
        auto* pixel=rgba.data()+4*((row+y)*640+x);
        for(int col=0;col<w;++col,pixel+=4)mix(pixel,r,g,b,alpha);
    }
}
int gsAlpha(int raw){return (raw+1)/2;}
}

ConsoleVersusArt::ConsoleVersusArt(const std::filesystem::path& assets) {
    std::ifstream in(assets/"console_versus_art.bin",std::ios::binary);
    if(!in)throw std::runtime_error("Cannot load original console versus menu art");
    auto half=[&]() -> uint16_t {
        const int lo=in.get(),hi=in.get();
        if(lo<0||hi<0)throw std::runtime_error("Truncated console versus menu art");
        return uint16_t(lo|(hi<<8));
    };
    std::array<char,4> header{};in.read(header.data(),4);
    const unsigned count=half(),groups=half();
    if(header!=std::array{'C','V','M','1'}||count==0||count>512||groups!=groups_.size())
        throw std::runtime_error("Invalid console versus menu art header");
    for(auto& row:borders_)in.read(reinterpret_cast<char*>(row.data()),4);
    for(unsigned i=0;i<count;++i) {
        const int w=half(),h=half();
        if(w<=0||w>24||h<=0||h>24)throw std::runtime_error("Invalid console menu glyph dimensions");
        auto& sprite=sprites_.emplace_back(Sprite{w,h,std::vector<uint8_t>(w*h*4)});
        in.read(reinterpret_cast<char*>(sprite.pixels.data()),sprite.pixels.size());
    }
    for(auto& list:groups_) {
        const unsigned n=half();
        if(n>80)throw std::runtime_error("Invalid console menu placement count");
        for(unsigned i=0;i<n;++i) {
            const unsigned ref=half();
            const int x=std::bit_cast<int16_t>(half()),y=std::bit_cast<int16_t>(half());
            const auto& sprite=sprites_.at(ref);
            if(x<0||y<0||x+sprite.width>640||y+sprite.height>448)throw std::runtime_error("Console menu glyph outside viewport");
            list.push_back({ref,x,y});
        }
    }
    if(!in||in.peek()!=EOF)throw std::runtime_error("Invalid console menu art length");
}

void ConsoleVersusArt::group(unsigned index,int alpha,std::span<uint8_t> rgba) const {
    if(!alpha)return;
    for(auto at:groups_.at(index)) {
        const auto& sprite=sprites_[at.sprite];
        for(int y=0;y<sprite.height;++y) {
            auto* dst=rgba.data()+4*((at.y+y)*640+at.x);
            const auto* texel=sprite.pixels.data()+4*y*sprite.width;
            for(int x=0;x<sprite.width;++x,texel+=4,dst+=4) {
                const int a=texel[3]*alpha/128;
                if(a)mix(dst,texel[0],texel[1],texel[2],a);
            }
        }
    }
}

void ConsoleVersusArt::paint(const ConsoleVersusMenuDraw& d,std::span<uint8_t> rgba) const {
    if(rgba.size()!=640*448*4)throw std::invalid_argument("Expected the 640x448 console VS battle surface");
    if(!d.visible)return;
    if(d.selection<0||d.selection>2||d.choice<0||d.choice>1)throw std::invalid_argument("Invalid console VS selection");
    rect(rgba,0,0,640,448,0,0,0,gsAlpha(d.backgroundAlpha));
    const int panel=gsAlpha(d.panelAlpha);
    const auto& border=borders_[d.borderFrame%borders_.size()];
    // 1c1528 advances the same oscillator for each of the four edges, so
    // adjacent edges differ in color and its phase survives a Continue.
    rect(rgba,176,156,288,4,0,border[0],0,panel);
    rect(rgba,176,260,288,4,0,border[1],0,panel);
    rect(rgba,176,160,4,100,0,border[2],0,panel);
    rect(rgba,460,160,4,100,0,border[3],0,panel);
    rect(rgba,180,160,280,100,255,255,255,panel);
    const int text=gsAlpha(d.textAlpha);
    group(2*d.selection,text,rgba);
    // 1db708 halves the help background's alpha before GS conversion.
    rect(rgba,0,372,640,36,0,0,0,gsAlpha(d.textAlpha/2));
    group(2*d.selection+1,text,rgba);
    rect(rgba,332,410,308,28,0,0,0,panel);
    group(6,gsAlpha(d.phase2b3c*51),rgba);
    if(d.dialog==3||d.dialog==4) {
        rect(rgba,0,100,640,240,0,0,0,96);
        group((d.dialog==3?7:9)+d.choice,128,rgba);
    }
}
}
