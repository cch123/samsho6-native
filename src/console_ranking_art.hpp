#pragma once
#include "console_attract_ranking.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class ConsoleRankingArt {
public:
    explicit ConsoleRankingArt(const std::filesystem::path& assets);
    void paint(const RankingFrame&,std::span<uint8_t> rgba) const;
private:
    using Color=std::array<uint8_t,4>;
    struct Texture {int w,h;std::vector<Color> pixels;};
    struct Rect {unsigned texture;int x,y,right,bottom,u,v,ur,vb;Color color;};
    std::vector<Texture> textures_;
    std::vector<Rect> rects_;
    std::vector<std::vector<unsigned>> lists_;
    std::array<std::vector<unsigned>,12> phases_;
};
}
