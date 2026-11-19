#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <span>
#include <vector>

namespace ss6 {
class VersusResultText {
public:
    explicit VersusResultText(const std::filesystem::path& assets);
    static int glyphCount(int quoteIndex);
    void paint(int quoteIndex,int visibleGlyphs,std::span<uint8_t> rgba640x480) const;
private:
    using Glyph=std::array<uint8_t,24*12>;
    std::array<std::array<uint8_t,4>,16> palette_{};
    std::map<uint16_t,Glyph> glyphs_;
    std::array<std::vector<std::vector<uint16_t>>,16> quotes_;
};
}
