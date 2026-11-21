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

// Stage 2 (constructor 1a8b90, task 1a8cf0): the deck of a ship. The whole
// backdrop except the deck floor is drawn under a vertically shifted camera
// driven by an eight-state swell machine (function table 51ba48).
struct CombatStage02State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=34;
    // Clocks in the order 1a8b20 creates them. Rows 10 and 11 share clock 3.
    std::array<StageClock,14> clocks{};
    // 12e8f.. descriptors of the eight turning rows 14..21: 24-bit 8.8 angle clock.
    std::array<int32_t,8> turns{};
    int32_t swellState=0,swellTimer=0,swellStep=0; // 12e9f30 / 34 / 38
    // Outputs of the latest visit.
    uint32_t swell=0;                   // float bits returned by 1a9928
    std::array<int32_t,8> angles{};     // 16-bit angle units passed to 1a95f0
    std::array<uint8_t,rowCount> pictures{};
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage02State& previous);
};
void drawCombatStage02(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage02State&,const AngleTrig&);
}
