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

// Stage 7 (constructor 1af840, task 1afa48): two backdrop pictures, a floor
// mesh, 17 object rows drawn by 1afef0 and two hopping objects that the task
// animates and draws itself after the rows.
struct CombatStage07State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=17;
    // 1a7290 descriptors of rows 7, 8, 10, 12, 13, 14, 16 (131a7a8 + d4 n).
    // They are created under the once flag 56ac38 and survive a reload.
    std::array<StageClock,7> clocks{};
    // One hopping object: record 130b920 (A) / 130b9f4 (B), wait timer
    // 130bad0 / 130bad4 and height 130bac8 / 130bacc. The constructor seeds
    // them on every load.
    struct Hopper {
        int32_t clock;      // +0, 8.8 ticks since take-off
        int32_t timer;      // 8.8 ticks on the ground; flight begins at 0x1400
        uint32_t height=0;  // float bits
        unsigned picture=0; // output of the latest visit
    };
    Hopper a{0,0xa00},b{0xf00,0x1400};
    std::array<uint8_t,rowCount> pictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage07State& previous);
};
void drawCombatStage07(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage07State&,const AngleTrig&);
}
