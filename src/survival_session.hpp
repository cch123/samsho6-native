#pragma once
#include "survival_run.hpp"
#include <string>

namespace ss6 {
// One SURVIVAL MODE run as the battle scene 139660 owns it: the controller
// 12d4cb8.., the per-seat configuration 456890 and the setup block 4d3d04.
// The original keeps one battle scene for the whole run; natively every
// opponent is a new NativeMatch, so everything that survives 13a6c0 lives here.
struct SurvivalSession {
    explicit SurvivalSession(const std::filesystem::path& path):assets(path),run(assets) {}
    SurvivalAssets assets;
    SurvivalRun run;
    int modeWord=0xb;                         // g+0
    std::array<SurvivalSeatConfig,2> config{};
    SurvivalSetup setup{};
    SurvivalSessionFlags flags{};             // 13430b0..13430cc
    bool pauseRequested=false;                // 123a0c4, written by 1392e8
    bool reload=false;                        // 13a6c0 ran on this frame
    bool ended=false;                         // 145628 requested scene 138340
    SurvivalMatchEnd end{};
    // Native admission: a candidate's arena, spirit or fighter without a port.
    std::string notice;
    int humanSeat() const {return modeWord==0xb?0:1;}
};
}
