#pragma once
#include "arcade_run.hpp"
#include "arcade_talk.hpp"
#include "game_random.hpp"
#include "system_data.hpp"
#include <filesystem>
#include <memory>
#include <string>
#include <vector>

namespace ss6 {
class ArcadePresentation;
// Sound requests of the presentation scenes, in call order.
struct ArcadeSceneSound {
    enum Kind:uint8_t {
        Music,      // 1e7c00(a, b): track a, IOP repeat flag b
        MusicStop,  // 1e7ad0()
        Sound,      // 1e7b70(a, b): group a + 1 (-1 = common bank), tone b
        Voice,      // 1e7d60(a, b)
        ObjectSound,// 1e8298(c, a, b) from an ACT record of an ending object: a = sound command,
                    // b = object+0x14 (character), c = object+0xc; ArcadePresentation also
                    // emits the Sound / Voice it resolves to
        LoadBank,   // 1e79c8(a, b): BVOICE2 bank b into group a + 1
        EffectsStop // 1e7b40()
    } kind{};
    int32_t a=0,b=0,c=0;
};

class ArcadeTransitionTask;
// One arcade scene log entry: the scene entered and how it was reached.
struct ArcadeSceneEntry {
    ArcadeScene scene=ArcadeScene::None;
    int32_t kind=0,speed=0;          // transition kind of the request; -1 = 1c1ac0 hand-off, 0 = first scene
    uint32_t frame=0;                // presentation frame of the entry
    std::vector<uint32_t> state;     // saveArcadeState before the entry (presentation scenes)
};

// Drives one ARCADE MODE run across scenes. The character select and the
// fight belong to NativeMatch (LocalVersus); CONTINUE and GAME OVER run here;
// every presentation scene (opening 1c60c8, map 1c1b20, walk-in 1c4428,
// stage dialogue 1c5290, pre-final 1c6cc0, win quote 135e30, VS result
// 136a60, ending 182968 with the staff roll, unlock notice 1e5d88) runs in
// ArcadePresentation. The scene switches run through the transition task
// (1252f0 kinds 1 / 2 / 4) or the 1c1ac0 hand-off. When the presentation
// assets are missing, or a scene meets an unported branch, that scene is
// skipped by applying its state changes (the static fallback).
class ArcadeSession {
    SystemData& system_;
    std::unique_ptr<ArcadeTables> tables_; // must precede run
public:
    ArcadeSession(const std::filesystem::path& assets,SystemData& system);
    ~ArcadeSession();
    GameRandom random;            // process RNG; copied from and to the fight
    ArcadeRun run;
    ArcadeCountdown countdown;
    ArcadeContinue continueScene;
    ArcadeGameOver gameOver;
    ArcadeScene scene=ArcadeScene::None;
    bool leftToTitle=false;
    // Set when the scene entered is the fight / the character select; the
    // owner of NativeMatch consumes them.
    bool fightRequested=false,selectRequested=false;
    bool battleOver=false;        // the fight ended; its picture holds while the fade-out runs
    bool autosave=false;          // 10f158 on this frame (name entry commit, unlock notice exit)
    std::unique_ptr<ArcadePresentation> presentation;
    std::unique_ptr<ArcadeTransitionTask> transitionTask_;
    ArcadeFade fade;              // 3ebf18.. shared by the scenes and the transition task
    std::string notice;           // why a scene was skipped

    void start(unsigned seat);                                   // mode menu item 0
    // The human seat finished 128008 / 12eee8.
    void selected(int character,int colour,int spirit,uint32_t held);
    // Mode 3 (challenger): the two-seat select finished; both records are set.
    void versusSelected();
    ArcadeBattleSetup enterBattle();                             // 1398c0
    // 145118 result (winner seat or -1) and battle+2c, read at state 10.
    void matchEnded(int winner,int stage,int endingChoice,int bonus,uint32_t held);
    // One frame of a scene that is not the fight or the select: the pad
    // update (118298, 118148), the scene task and the transition task.
    void tickScene(std::array<uint32_t,2> pressed,uint32_t held);
    // One frame of the transition task alone (during and right after a fight).
    void tickTransition();
    bool transitionActive() const;
    // CONTINUE and GAME OVER: one visit (without the transition task).
    int tickContinue(std::array<uint32_t,2> pressed);
    void tickGameOver(std::array<uint32_t,2> pressed);
    // The transition task's view for drawing (kind 4 banner / shutter).
    const ArcadeTransitionTask& transitionTask() const {return *transitionTask_;}
private:
    void arrive(uint32_t held,bool faded);     // the request made by a scene outside the session
    void enterScene(ArcadeScene next,uint32_t held,int kind,int speed);
    void leaveScene();
    void skip(ArcadeScene next,uint32_t held);  // static fallback of one scene
    void follow(uint32_t held);
    void enter(ArcadeScene next);
    void frameEnd();
    uint32_t held_=0;
    // LocalVersus hands presentation->sounds to the mixer after tickScene and
    // after the fight's fade-out visits of tickTransition. Requests made on
    // other visits (a scene entered from the select, a fight's end) wait in
    // the list; only the delivered prefix is dropped on the next visit.
    size_t soundsDelivered_=0;
    void dropDeliveredSounds();
};
}
