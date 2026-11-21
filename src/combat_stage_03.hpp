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

// Stage 3 (constructor 1aa250, task 1aa3e8). 29 object rows at 51cfa0 drawn
// by 1aad60 in three ranges, with one plain rectangle, four wall strips and
// six 17-link chains between them. The only state is eighteen independent picture clocks.
struct CombatStage03State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=29;
    // One clock per animated row (flag 0x100), in row order: 1a9f30 creates
    // them once per process (flag 51c920).
    std::array<StageClock,18> clocks{};
    // Output of the latest visit.
    std::array<uint8_t,rowCount> pictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage03State& previous);
};
void drawCombatStage03(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage03State&,const AngleTrig&);
}
