#pragma once
#include "stage_raster.hpp"
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class VersusDrawStage {
public:
    explicit VersusDrawStage(const std::filesystem::path& assets);
    void paint(unsigned objectTick,std::span<uint8_t> rgba640x480) const;
private:
    struct Strip {unsigned slot;uint32_t color;std::vector<StageVertex> vertices;};
    StageRaster raster_;
    std::vector<Strip> strips_;
    std::vector<std::vector<uint32_t>> frames_;
};
}
