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

// Stage 10 (constructor 1b2350, task 1b24e0). The task owns one free-running
// counter for fourteen blinking far rectangles, eight picture clocks drawn
// before the object rows (four of them as perspective quads) and three
// animated rows with skewed shadows. It reads no game state besides delta
// and the hide flag and draws no random numbers.
struct CombatStage10State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=19;
    // 57294c: 8.8 counter, advanced by delta on every visit. No constructor
    // or other routine writes it, so it runs for the life of the process.
    int32_t scroll=0;
    // Descriptors 132b5bc + d4 * k, bound through the pairs at 5723a0.
    std::array<StageClock,8> clocks{};
    // Descriptors 132b340 / 132b414 / 132b4e8 of rows 16, 17 and 18.
    std::array<StageClock,3> rowClocks{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage10State& previous);
};
void drawCombatStage10(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage10State&,const AngleTrig&);
}
