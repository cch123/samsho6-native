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

// Stage 4 (constructor 1ab368, task 1ab518): a shore seen from a rocking
// viewpoint. Everything behind the beach floor (animated sea mesh, sky, rows
// 0..12) is drawn under a projection shifted along a Lissajous path whose
// amplitude is redrawn from the library RNG once per 0x10000-tick period.
struct CombatStage04State {
    static constexpr bool ported=true;
    static constexpr unsigned rowCount=31;
    // Clocks in row order (1ab0e8, guarded by 5331b0); every animated row owns one.
    std::array<StageClock,19> clocks{};
    int32_t swayClock=0;        // 5331bc, 16-bit phase in 8.8 ticks
    int32_t swayIndex=0;        // 5331c8, index into the amplitude table 6531a8
    uint32_t swayFrom=0;        // 12eae28 (float bits)
    uint32_t swayTo=0;          // 12eae2c (float bits)
    int32_t seaClock=0;         // 12eae30, 0..0xb3ff; 0x1e00 per sea mesh
    // Outputs of the latest visit.
    int32_t phase=0;            // 5331bc as sampled by this visit
    uint32_t level=0x41200000;  // 5331cc (float bits)
    unsigned seaFrame=0;        // mesh index handed to 1a5890
    std::array<uint16_t,rowCount> pictures{}; // bit 0x100: the row is not drawn
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage04State& previous);
};
void drawCombatStage04(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage04State&,const AngleTrig&);
}
