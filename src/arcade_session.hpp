#pragma once
#include "arcade_run.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <filesystem>
#include <memory>

namespace ss6 {
// Drives one ARCADE MODE run across scenes. The interactive scenes are the
// character select, the fight, CONTINUE and GAME OVER. The presentation
// scenes (opening 1c60c8, map 1c1b20, walk-in 1c4428, stage dialogue 1c5290,
// pre-final 1c6cc0, win quote 135e30, ending 182968) have no native picture
// yet: follow() applies the state changes their tasks make and moves on.
class ArcadeSession {
    SystemData& system_;
    std::unique_ptr<ArcadeTables> tables_; // must precede run
public:
    ArcadeSession(const std::filesystem::path& assets,SystemData& system);
    GameRandom random;            // process RNG; copied from and to the fight
    ArcadeRun run;
    ArcadeCountdown countdown;
    ArcadeContinue continueScene;
    ArcadeGameOver gameOver;
    ArcadeScene scene=ArcadeScene::None;
    bool leftToTitle=false;

    void start(unsigned seat);                                   // mode menu item 0
    // The human seat finished 128008 / 12eee8.
    void selected(int character,int colour,int spirit,uint32_t held);
    ArcadeBattleSetup enterBattle();                             // 1398c0
    // 145118 result (winner seat or -1) and battle+2c, read at state 10.
    void matchEnded(int winner,int stage,int endingChoice,int bonus,uint32_t held);
    // CONTINUE and GAME OVER: one visit. Returns sound ids to request.
    int tickContinue(std::array<uint32_t,2> pressed);
    void tickGameOver(std::array<uint32_t,2> pressed);
private:
    void follow(uint32_t held);
    void enter(ArcadeScene next);
};
}
