#pragma once
#include "combat_stage_state.hpp"
#include "stage_draw.hpp"
#include "stage_raster.hpp"
#include <memory>
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
class AngleTrig;
class CombatStage {
public:
    explicit CombatStage(const std::filesystem::path& assets,unsigned stage=0);
    std::vector<CombatStageStrip> geometry(const CombatStageState&,unsigned* nextDepth=nullptr) const;
    unsigned paint(const CombatStageState&,std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba) const;
private:
    // The first group precedes the scenery object table. Each animated group
    // selects its own frame, including the footprint of its texture shadow.
    unsigned stage_;
    StageCommandGroups groups_;
    StageRaster raster_;
    std::shared_ptr<const AngleTrig> trig_;
};
}
