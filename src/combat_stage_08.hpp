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

// Stage 8 (constructor 1b05b8, task 1b0738): 19 object rows at 56ef10 drawn
// by 1b10a0 in two calls (rows 0..2, rows 3..18) around seven moving
// backdrop objects whose descriptors live at 131fee8 + d4 * n.
struct CombatStage08State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=19;
    // 1b0490 (guarded by 56f468): clocks of rows 5, 6, 13..18 in row order.
    std::array<StageClock,8> clocks{};
    // Object 0 (131fee8): horizontal sway about a fixed X, stepwise rise in Y.
    int32_t swayClock=0;            // +0, 24-bit
    bool swayRolled=false;          // +30
    uint32_t swayAmplitude=0;       // 131aff0, float bits
    uint32_t riseY=0,riseStep=0;    // +c, +18, float bits
    int32_t visits=0;               // 56f470, never reset
    // Objects 1 and 2 (131ffbc, 1320090): 1:2 Lissajous figures.
    struct Orbit {
        bool rolled=false;              // +30
        uint32_t amplitude=0x41200000;  // 56f478 / 56f484, float bits (10 in the data segment)
        int32_t angle=0;                // 56f47c / 56f488, never reset
    };
    std::array<Orbit,2> orbits{};
    // Objects 3 and 4 (1320164, 1320238): X bounces between two limits.
    std::array<uint32_t,2> bounceX{0x43480000,0x43160000};      // +8: 200, 150
    std::array<uint32_t,2> bounceStep{0xbd23d70a,0xbd23d70a};   // +14: -0.04
    // Objects 5 and 6 (132030c, 13203e0): X drifts left and wraps.
    std::array<uint32_t,2> driftX{0x43a00000,0x43f00000};       // +8: 320, 480
    // Outputs of the latest visit. The trigonometric terms are evaluated by
    // the draw function from the angles sampled before this visit's advance.
    int32_t swayAngle=0;
    std::array<int32_t,2> orbitAngles{};
    std::array<uint8_t,rowCount> pictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    // Validation fixture only: index 0 presets object 6's X (13203e8).
    void poke(unsigned index,uint32_t bits) {driftX.at(1+index)=bits;}
    void reload(const CombatStage08State& previous);
};
void drawCombatStage08(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage08State&,const AngleTrig&);
}
