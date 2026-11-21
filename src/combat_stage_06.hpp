#pragma once
#include "stage_clock.hpp"
#include <array>
#include <cstdint>
#include <vector>

namespace ss6 {
class AngleTrig;
struct GameRandom;
struct StageCommand;
namespace stage_draw { struct Projector; }

// Stage 6 (constructor 1ae020, task 1ae1b8): 26 object rows at 550af8 behind
// a tinted floor of eight meshes, four perspective banners and five sagging
// lines of lanterns. The only per-visit state is 24 independent frame clocks.
struct CombatStage06State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=26;
    // 1ad748 (guarded by 551248) creates one descriptor per animated row,
    // then the two banner descriptors referenced from 550ae8 and 550af0.
    std::array<StageClock,rowCount> clocks{};
    std::array<StageClock,2> bannerClocks{};
    // Outputs of the latest visit.
    std::array<uint8_t,rowCount> pictures{};
    std::array<uint8_t,2> bannerPictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage06State& previous);
};
void drawCombatStage06(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage06State&,const AngleTrig&);
}
