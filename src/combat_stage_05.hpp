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

// Stage 5 (constructor 1ac1f8, task 1ac360). The task has no row loop of its
// own: 1ad298 draws rows 0..1 early and rows 2..5 late; receding walls
// (1ace00 + 1af1f8), two world meshes (1ad0f0) and a drifting sprite lie
// between the two calls.
struct CombatStage05State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=6;
    // Rows 2..5 (states 12f1170, 12f1244, 12f1318, 12f13ec; once-guarded by 544618).
    std::array<StageClock,4> clocks{};
    // 12f1594, timeline 5443b0: advanced by the task itself at 1acc6c.
    StageClock tail{};
    // 12f14c8 (float bits): X of the drifting sprite; 1abd80 clears it on every load.
    uint32_t driftX=0;
    // Outputs of the latest visit.
    std::array<uint8_t,rowCount> pictures{};
    unsigned tailVariant=0; // index into the exported group: 0..11, then 12/13 for pictures 0x100/0x101
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage05State& previous);
};
void drawCombatStage05(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage05State&,const AngleTrig&);
}
