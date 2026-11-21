#pragma once
#include "practice_mode.hpp"
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {
// The practice objects of one battle scene: the window controller 17f790 with
// its settings tables, the damage counters 123a0f0.., the command history
// 123a100.. and the one-frame requests the battle thread 138f48 consumes.
struct PracticeBattle {
    explicit PracticeBattle(const std::filesystem::path& assets):tables(assets) {}
    PracticeTables tables;
    PracticeWindow window;
    PracticeDamage damage;
    PracticeKeyHistory keys;
    bool pauseRequested=false;   // 123a0c4 (1392e8): the next battle frame is skipped
    bool resetRequested=false;   // 123a0cc (1392d0): 13f9f0(0) before the next battle frame
    bool keyConfigOpen=false,skillListOpen=false;
    int exit=0;                  // pending 1252f0(2,0,139778,x): 1 character select, 2 title
    int exitDone=0;              // the same value once the fade reached the scene switch
    unsigned resets=0;           // soft restarts performed (inspection only)
    std::vector<PracticeHelp> help;
};
}
