#pragma once
#include "combat_stage_02.hpp"
#include "combat_stage_03.hpp"
#include "combat_stage_04.hpp"
#include "combat_stage_05.hpp"
#include "combat_stage_06.hpp"
#include "combat_stage_07.hpp"
#include "combat_stage_08.hpp"
#include "combat_stage_09.hpp"
#include "combat_stage_10.hpp"
#include "combat_stage_11.hpp"
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
    // The constructor table at 50e080 has twelve entries.
    static constexpr unsigned stageCount=12;
    static constexpr std::array<uint32_t,stageCount> handlers{0x1a7810,0x1a8098,0x1a8cf0,0x1aa3e8,0x1ab518,0x1ac360,
                                                              0x1ae1b8,0x1afa48,0x1b0738,0x1b1730,0x1b24e0,0x1b3bb8};
    static constexpr bool supports(unsigned id) {
        constexpr bool ported[stageCount]{true,true,CombatStage02State::ported,CombatStage03State::ported,
            CombatStage04State::ported,CombatStage05State::ported,CombatStage06State::ported,CombatStage07State::ported,
            CombatStage08State::ported,CombatStage09State::ported,CombatStage10State::ported,CombatStage11State::ported};
        return id<stageCount&&ported[id];
    }
    uint32_t handler() const { return handlers.at(stage); }
    unsigned pictureForRow(unsigned row) const;
    // In descriptor order. Multiple objects may use the same sequence while
    // each keeps its own EE timer and current picture.
    static constexpr std::array<unsigned,7> rows{1,2,15,16,18,21,22};
    std::array<CombatStageLayer,7> layers{};
    static constexpr std::array<unsigned,10> rows01{3,4,5,20,21,22,23,24,25,26};
    // 1a7e70 marks only the first three layer clocks as continuous.
    std::array<CombatStageLayer01,10> layers01{{{0,0,1},{0,0,1},{0,0,1}}};
    // Every stage's descriptors live in process memory and survive a switch
    // to another stage; see inheritRematch.
    CombatStage02State stage02;
    CombatStage03State stage03;
    CombatStage04State stage04;
    CombatStage05State stage05;
    CombatStage06State stage06;
    CombatStage07State stage07;
    CombatStage08State stage08;
    CombatStage09State stage09;
    CombatStage10State stage10;
    CombatStage11State stage11;
    StageCamera camera;
    bool visible=false;
    bool suppressGeometry=false;
    void visit(const StageCamera& published,uint32_t delta46a908,bool backdropPreviouslyDrawn=false,
               GameRandom* random=nullptr); // priority 10
    void inheritRematch(const CombatStageState& previous);
};
}
