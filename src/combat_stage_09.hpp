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

// Stage 9 (constructor 1b15b0, task 1b1730): a backdrop quad cut at the
// projected horizon, a floor mesh, sixteen object rows drawn by 1b1e58 in two
// runs (0..7, 8..15) and three animated objects with their own clocks.
struct CombatStage09State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=16;
    // Row 2 (flags 0x101), state 132ad70. Created by the once-guarded 1b13b8.
    StageClock row;
    // States 132ae44 / 132afec / 132b194 behind the handles 1320f78 / 80 / 88.
    // 1b1428 clears them on every constructor run.
    std::array<StageClock,3> objects{};
    // Outputs of the latest visit.
    unsigned rowPicture=0;
    std::array<unsigned,3> objectPictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage09State& previous);
};
void drawCombatStage09(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage09State&,const AngleTrig&);
}
