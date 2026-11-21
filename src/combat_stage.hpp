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
    // Strips whose depth key reaches the fighters' plane (Z <= 0, key >=
    // 10000000) must be ordered against the character and effect draws.
    struct Foreground {
        std::vector<CombatStageStrip> strips; // ascending depth key
        StageRaster::Palette palette{};
        size_t next=0;
    };
    // Without a Foreground every strip is painted behind the fighters.
    unsigned paint(const CombatStageState&,std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba,
                   Foreground* foreground=nullptr) const;
    // Paint the pending foreground strips whose key does not exceed depth.
    void paintForeground(Foreground&,float depth,std::span<uint8_t> rgba) const;
private:
    // The first group precedes the scenery object table. Each animated group
    // selects its own frame, including the footprint of its texture shadow.
    unsigned stage_;
    StageCommandGroups groups_;
    StageRaster raster_;
    std::shared_ptr<const AngleTrig> trig_;
};
}
