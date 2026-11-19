#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class VersusResultArt {
public:
    explicit VersusResultArt(const std::filesystem::path& assets);
    void paint(unsigned winnerSide,unsigned animationTick,unsigned backgroundTick,
               std::span<uint8_t> rgba) const;
    void paintMenuBackground(unsigned tick,std::span<uint8_t> rgba,bool clearFirst=true) const;
private:
    struct LayerTile { unsigned u,v,w,h,flags,y; };
    struct Vertex { float x,y,u,v; };
    using Quad=std::array<Vertex,4>;
    struct Pose { unsigned count; std::array<Quad,2> slices; };
    std::array<std::array<LayerTile,10>,11> rows_{};
    std::array<std::array<Pose,61>,2> poses_{};
    std::vector<uint32_t> background_,portrait_;
    void drawPortrait(const Pose&,std::span<uint8_t>,int height) const;
    void drawBackground(unsigned tick,std::span<uint8_t>,int height) const;
};
}
