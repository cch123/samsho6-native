#include "asset_files.hpp"
#include "versus_result_text.hpp"
#include <fstream>
#include <stdexcept>

namespace ss6 {
int VersusResultText::glyphCount(int quoteIndex) {
    // 1a2870 counts characters (including full-width spaces). The winner
    // scene can advance its timer before any renderer has been constructed.
    constexpr std::array counts={33,52,42,41,40,37,52,22,40,27,37,7,17,23,25,33};
    return counts.at(quoteIndex);
}

VersusResultText::VersusResultText(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"versus_quotes_00.bin"),std::ios::binary);
    if(!in)throw std::runtime_error("Cannot open original Haohmaru victory text");
    auto byte=[&] {
        const int n=in.get();
        if(n==EOF)throw std::runtime_error("Truncated victory text asset");
        return n;
    };
    auto code=[&] {
        const unsigned lead=byte();
        return uint16_t(lead*256+byte());
    };
    std::array<char,4> header{};
    in.read(header.data(),header.size());
    if(header!=std::array{'S','Q','0','0'})throw std::runtime_error("Invalid victory text header");
    const int low=byte();
    const int size=low+256*byte();
    for(auto& entry:palette_)in.read(reinterpret_cast<char*>(entry.data()),entry.size());
    for(int i=0;i<size;++i) {
        auto [position,inserted]=glyphs_.try_emplace(code());
        if(!inserted)throw std::runtime_error("Duplicate victory glyph");
        auto& glyph=position->second;
        in.read(reinterpret_cast<char*>(glyph.data()),glyph.size());
    }
    for(int q=0;q<int(quotes_.size());++q) {
        int count=0;
        const int rows=byte();
        if(rows<1||rows>3)throw std::runtime_error("Invalid victory quote line count");
        for(int j=0;j<rows;++j) {
            auto& line=quotes_[q].emplace_back();
            const int width=byte();
            if(!width||width*24>640)throw std::runtime_error("Invalid victory line width");
            for(int k=0;k<width;++k) {
                const auto c=code();
                if(!glyphs_.contains(c))throw std::runtime_error("Missing victory glyph");
                line.push_back(c);
            }
            count+=width;
        }
        if(count!=glyphCount(q))throw std::runtime_error("Invalid victory quote length");
    }
    if(in.peek()!=EOF)throw std::runtime_error("Unexpected trailing victory text data");
}

void VersusResultText::paint(int quoteIndex,int visible,std::span<uint8_t> rgba) const {
    if(rgba.size()!=640*480*4)throw std::invalid_argument("Expected a 640x480 victory framebuffer");
    const auto& lines=quotes_.at(quoteIndex);
    int y=366+12*(3-int(lines.size())),shown=0;
    for(const auto& line:lines) {
        // 1a2870 centers the entire SJIS line, even while only its prefix
        // is revealed. Each double-byte cell occupies 24 screen pixels.
        int x=320-12*int(line.size());
        for(const auto code:line) {
            if(visible>=0&&shown>=visible)return;
            ++shown;
            const auto& glyph=glyphs_.at(code);
            for(int row=0;row<24;++row)for(int col=0;col<24;++col) {
                const unsigned packed=glyph[row*12+col/2];
                const auto& texel=palette_[(packed>>(4*(col%2)))&15];
                if(!texel[3])continue;
                auto* dst=rgba.data()+((y+row)*640+x+col)*4;
                for(int c=0;c<3;++c)dst[c]+=((int(texel[c])-dst[c])*texel[3])>>7;
                dst[3]=255;
            }
            x+=24;
        }
        y+=24;
    }
}
}
