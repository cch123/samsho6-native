#pragma once
#include "combat_stage_state.hpp"
#include "stage_raster.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
using CombatStageVertex=StageVertex;
struct CombatStageStrip {
    unsigned slot;
    uint32_t color;
    float z;
    std::vector<CombatStageVertex> vertices;
};

class CombatStage {
public:
    explicit CombatStage(const std::filesystem::path& assets,unsigned stage=0);
    std::vector<CombatStageStrip> geometry(const CombatStageState&,unsigned* nextDepth=nullptr) const;
    unsigned paint(const CombatStageState&,std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba) const;
private:
    struct Command {
        unsigned kind,slot;
        std::array<float,7> parameters{};
        std::vector<std::array<float,5>> pieces;
    };
    // The first group precedes the scenery object table. Each animated group
    // selects its own frame, including the footprint of its texture shadow.
    unsigned stage_;
    std::vector<std::vector<std::vector<Command>>> groups_;
    StageRaster raster_;
};
}
