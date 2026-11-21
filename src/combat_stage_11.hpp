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

// Stage 11 (constructor 1b3aa8, task 1b3bb8): a backdrop rectangle, a floor
// mesh, one static sprite and seven drifting objects (0x9c bytes each at
// 132bc60) that bob vertically, cycle three pictures and fade in and out.
// The referee task 1b4228 that follows the scenery code in the executable is
// created by the battle owner (13972c), not by this constructor.
struct CombatStage11State {
    static constexpr bool ported=true;
    static constexpr unsigned objectCount=7;
    struct Object {
        uint32_t amplitude=0;   // +24, float bits; zero until the first phase wrap
        int32_t pictureClock=0; // +30, 8.8 ticks, three pictures of 0xc00
        int32_t phase=0;        // +34, 16-bit angle of the vertical bob
        int32_t phaseStep=0;    // +38
        int32_t fade=0;         // +3c, angle of the alpha curve
        int32_t fadeStep=0;     // +40
        // Values the latest visit used for drawing (sampled before the steps).
        int32_t picture=0;      // +28; 3..9 are empty table entries
        int32_t drawnPhase=0,drawnFade=0;
        uint32_t drawnAmplitude=0;
    };
    std::array<Object,objectCount> objects{};
    // 1b3e20 runs in the constructor and draws two library random numbers per
    // object. The stage interface has no generator at reload time, so the
    // draws are made by initialize(), at the latest on the first visit.
    bool initialized=false;
    void initialize(GameRandom&);
    void visit(uint32_t delta46a908,GameRandom&);
    void reload(const CombatStage11State& previous);
};
void drawCombatStage11(stage_draw::Projector&,const std::vector<std::vector<std::vector<StageCommand>>>& groups,
                       const CombatStage11State&,const AngleTrig&);
}
