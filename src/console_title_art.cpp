#include "console_title_art.hpp"

#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <string_view>

namespace ss6 {
namespace {
constexpr int width=640,height=480;
// Indexed by ConsoleMode; the strings sit at 656860..656910.
constexpr std::array<std::string_view,9> names={
    "ARCADE MODE","VS MODE","PRACTICE MODE","SURVIVAL MODE","SPIRITS EDIT MODE",
    "COLOR EDIT MODE","GALLERY MODE","NETWORK MODE","OPTION MODE"
};

std::vector<uint8_t> load(const std::filesystem::path& file,size_t size) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=static_cast<std::streamoff>(size))
        throw std::runtime_error("Invalid title resource: "+file.string());
    std::vector<uint8_t> bytes(size);
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),size))
        throw std::runtime_error("Truncated title resource: "+file.string());
    return bytes;
}
}

ConsoleTitleArt::ConsoleTitleArt(const std::filesystem::path& assets) {
    const auto indices=load(assets/"bg_title00.tex",1024*1024);
    const auto clut=load(assets/"bg_title00.pal",512);
    for(unsigned i=1;i<256;++i)backgroundPalette_[i]=clut[2*i]|(unsigned(clut[2*i+1])<<8);
    for(int menu=0;menu<2;++menu) {
        auto& pixels=backgrounds_[menu];
        pixels.resize(width*height);
        for(int y=0;y<height;++y) {
            // The lower title picture reaches the texture's final row. The
            // original GS submitter clips its far UV to 1023 before sampling.
            const int v=menu?544+(2*y+1)*479/(2*height):y;
            for(int x=0;x<width;++x) {
                auto index=indices[1024*v+x];
                if(y>=410&&y<432) {
                    const auto copyright=indices[1024*(488+y-410)+x];
                    if(backgroundPalette_[copyright]&0x8000)index=copyright;
                }
                pixels[y*width+x]=index;
            }
        }
    }
    font_=load(assets/"obj0_16.tex",512*512+1024);
    for(unsigned i=0;i<256;++i) {
        // Slot 1 carries an embedded 16x16 CLUT; CSM1 exchanges index bits 3/4.
        const unsigned j=(i&~24u)|((i&8u)<<1)|((i&16u)>>1);
        std::copy_n(font_.data()+512*512+4*j,4,fontColors_[i].begin());
    }
    font_.resize(512*512);

    const auto coin=load(assets/"font_coin.tex",128*128+1024);
    // Slot 40 uses a separate CLUT transfer: 1099f0 writes sixteen 8x2
    // strips to 3189, so the appended colors retain their logical order.
    const auto makePrompt=[&](std::span<const std::array<int,3>> pieces,int w) {
        std::vector<uint8_t> pixels(4*w*12);
        int left=0;
        for(auto [u,v,pieceWidth]:pieces) {
            for(int y=0;y<12;++y)for(int x=0;x<pieceWidth;++x) {
                const unsigned index=coin[(v+y)*128+u+x];
                std::copy_n(coin.data()+128*128+4*index,4,pixels.data()+4*(y*w+left+x));
            }
            left+=pieceWidth;
        }
        return pixels;
    };
    // 1ba228 composes PRESS, START, BUTTON from three cells, while the
    // pending-transition label is a single image centered separately.
    constexpr std::array start{std::array{1,66,64},std::array{60,92,64},std::array{1,79,73}};
    constexpr std::array<std::array<int,3>,1> wait{std::array{1,105,124}};
    prompts_[0]=makePrompt(start,201);
    prompts_[1]=makePrompt(wait,124);
}

void ConsoleTitleArt::label(ConsoleMode item,int y,int intensity,int opacity,std::span<uint8_t> rgba) const {
    int x=240;
    for(char ch:names.at(unsigned(item))) {
        const int cell=ch-32,u=2+17*(cell%30),v=2+17*(cell/30);
        for(int row=0;row<15;++row) {
            auto* dst=rgba.data()+4*((y+row)*width+x);
            const auto* index=font_.data()+512*(v+row)+u;
            for(int col=0;col<15;++col,dst+=4) {
                const auto& texel=fontColors_[index[col]];
                const int alpha=texel[3]*opacity/128;
                for(int c=0;c<3;++c)dst[c]+=((texel[c]*intensity/128-dst[c])*alpha)>>7;
            }
        }
        x+=14;  // The final glyph column overlaps the next cell on the PS2.
    }
}

void ConsoleTitleArt::paint(bool modeMenu,unsigned firstRow,int direction,unsigned tick,
                           unsigned,unsigned,std::span<uint8_t> rgba,ConsoleTitlePrompt prompt,
                           unsigned fadeLevel,bool fadeWhite,unsigned unlock) const {
    const auto rows=consoleModeRows(unlock);
    if(rgba.size()!=width*height*4)throw std::invalid_argument("Expected 640x480 title surface");
    if(fadeLevel>256)throw std::invalid_argument("Invalid title fade level");
    // 116588 interpolates the title CLUT in 5-bit RGB. The same transition
    // also modulates the vertices in 117288 at 8-bit precision. Combining
    // these after rasterization would brighten the black fade considerably.
    const int level=int(fadeLevel),tone=fadeWhite?255:0;
    const auto vertex=[=](int component) {
        const int faded=(component*(256-level)+tone*level)>>8;
        return (faded+1)/2;
    };
    const int modulation=vertex(255);
    std::array<std::array<uint8_t,4>,256> colors;
    for(unsigned i=0;i<colors.size();++i) {
        const auto v=backgroundPalette_[i];
        for(int c=0;c<3;++c) {
            const int base=(v>>(10-c*5))&31;
            const int channel=(base*(256-level)+(tone>>3)*level)>>8;
            // At level 256, 113b28 replaces the normal background and labels
            // with a full-color quad. The resident prompt has a higher Z.
            colors[i][c]=uint8_t(level==256?tone:(v&0x8000)?(channel*8*modulation)>>7:0);
        }
        colors[i][3]=255;
    }
    const auto& base=backgrounds_[modeMenu];
    for(size_t i=0;i<base.size();++i)std::copy_n(colors[base[i]].data(),4,rgba.data()+4*i);
    if(!modeMenu) {
        if(prompt!=ConsoleTitlePrompt::Hidden) {
            const bool wait=prompt==ConsoleTitlePrompt::Wait;
            const int w=wait?124:201,left=wait?249:224;
            const auto& pixels=prompts_[wait];
            for(int y=0;y<12;++y)for(int x=0;x<w;++x) {
                auto* dst=rgba.data()+4*((320+y)*width+left+x);
                const auto* src=pixels.data()+4*(y*w+x);
                for(int c=0;c<3;++c)dst[c]=uint8_t(std::clamp(dst[c]+(((src[c]-dst[c])*src[3])>>7),0,255));
            }
        }
        return;
    }
    if(firstRow>=rows.count||direction<0||direction>2||(direction&&tick>=15))
        throw std::invalid_argument("Invalid mode menu scroll");
    if(level==256)return;
    if(!direction) {
        for(unsigned row=0;row<3;++row) {
            const auto item=rows.items[(firstRow+row)%rows.count];
            const int shade=item==ConsoleMode::Network?64:row==1?255:128;
            label(item,332+24*row,vertex(shade),128,rgba);
        }
        return;
    }

    // The raw cursor moves on the input frame. In the next fifteen submissions
    // it already identifies the destination; four rows crossfade around it.
    const int offset=int(tick)*24/15,shade=int(tick)*127/15;
    for(unsigned row=0;row<4;++row) {
        const auto item=rows.items[(firstRow+row+(direction==2?rows.count-1:0))%rows.count];
        const unsigned phaseRow=direction==1?row:3-row;
        const int rowShade=item==ConsoleMode::Network?64:phaseRow==1?128+shade:phaseRow==2?255-shade:128;
        const int alpha=phaseRow==0?17*int(tick):phaseRow==3?255-17*int(tick):255;
        const int y=(direction==1?308+offset:332-offset)+24*int(row);
        label(item,y,vertex(rowShade),(alpha+1)/2,rgba);
    }
}
}
