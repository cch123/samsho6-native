#pragma once
#include "stage_camera.hpp"
#include <array>
#include <cstdint>

namespace ss6 {
struct GameRandom;

struct CombatStageLayer {
    int32_t elapsed=0;
    unsigned picture=0,step=0;
};

struct CombatStageLayer01 {
    int32_t elapsed=0;
    unsigned picture=0,flags=0;
};

struct CombatStageState {
    unsigned stage=0;
    static constexpr unsigned stageCount=2;
    static constexpr bool supports(unsigned id) { return id<stageCount; }
    uint32_t handler() const { return stage==1 ? 0x1a8098 : 0x1a7810; }
    unsigned pictureForRow(unsigned row) const;
    // In descriptor order. Multiple objects may use the same sequence while
    // each keeps its own EE timer and current picture.
    static constexpr std::array<unsigned,7> rows{1,2,15,16,18,21,22};
    std::array<CombatStageLayer,7> layers{};
    static constexpr std::array<unsigned,10> rows01{3,4,5,20,21,22,23,24,25,26};
    // 1a7e70 marks only the first three layer clocks as continuous.
    std::array<CombatStageLayer01,10> layers01{{{0,0,1},{0,0,1},{0,0,1}}};
    StageCamera camera;
    bool visible=false;
    bool suppressGeometry=false;
    void visit(const StageCamera& published,uint32_t delta46a908,bool backdropPreviouslyDrawn=false,
               GameRandom* random=nullptr); // priority 10
    void inheritRematch(const CombatStageState& previous);
};
}
