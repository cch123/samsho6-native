#pragma once
#include "player_object.hpp"
#include "combat_decision.hpp"
#include "damage.hpp"
#include "reaction.hpp"
#include "ordinary_rules.hpp"
#include "stage_camera.hpp"
#include "knockout.hpp"
#include "knockdown.hpp"
#include "state_entry.hpp"
#include "round_rules.hpp"
#include "effect_runtime.hpp"
#include "ending_playback.hpp"
#include "match_progress.hpp"
#include "actor_history.hpp"
#include "action_selection.hpp"
#include "input_features.hpp"
#include <memory>

namespace ss6 {
// Integration fixture for the proven resource-00 ordinary contact paths.
// Movement and guard supply fixture states. Ground slashes use keyboard
// press edges through the original raw attack selector.
enum class TrialCommand { Idle, Forward, Backward, StandGuard, CrouchGuard, LightSlash, HeavySlash, Crouch };
struct TrialActor {
    explicit TrialActor(ActionBank& bank):object(bank) {}
    PlayerObject object;
    ActorTimers timers;
    LifeState life;
    DamageActor damage;
    ReactionTarget reaction;
    int16_t table=0,state=0;
    uint8_t stateFlags=0x9e;
    uint32_t delta=256;
    unsigned hitCount=0,guardCount=0;
    bool expectedMirror=false;
    KnockoutPlayback knockout;
    KnockdownPlayback knockdown;
    DownedState downed;
    bool downEntryQueued=false;
    unsigned landingDustEvents=0;
    bool victoryRequested=false;
    int endingStateRequested=-1;
    EndingPlayback ending;
    TrialCommand command=TrialCommand::Idle;
    uint32_t flags240=0;
    ActorHistory history;
    std::array<ActorAfterimage,3> afterimages=makeActorAfterimages();
    bool roundActionQueued=false;
    int queuedStateFlags=-1; //14b798 metadata waits for the next actor entry visit.
};
class ContactTrial {
public:
    explicit ContactTrial(const std::filesystem::path& assets);
    void reset();
    void command(unsigned player,TrialCommand input);
    void tick();
    void discardAttackPresses() { slashPresses_ = {}; }
    const TrialActor& actor(unsigned player) const { return *actors_.at(player); }
    CollisionPlayer collisionPlayer(unsigned player) const;
    uint64_t updates=0;
    int winner=-1; // Selected at end-state entry, not at life commit.
    int roundState=4,pendingRoundState=4;
    bool roundBodiesReady=false;
    bool roundPresentationReady=false;
    bool roundEndingReady=false; // State8 bodies done; continuation is opt-in for old isolated fixtures.
    bool continueRounds=false,matchFinished=false;
    bool firstRoundIntroduction=false;
    BattleEffects effects;
    BattlePause battlePause;
    MatchProgress match;
    BattleTimers battleTimers;
    std::vector<ContactEvent> contacts;
    StageCamera camera;
    void place(float left,float right); // fixture setup, never a gameplay move
    void setInitialLife(unsigned player,int life); // scripted fixture setup only
    void startOpeningFixture(unsigned label); // state3 setup, not next-round initialization
    void enableRoundContinuation(); // ordinary two-player, no time limit
    void startMatch(); // first-round actor introduction, then automatic rounds
    void setWinRequirement(unsigned wins); // explicit fixture option before start
    void resetActorForRound(unsigned player,bool first=false); //149008 represented resource00 path
    void startKnockoutPreview(unsigned player,unsigned action);
    void startHeavyHurtFixture(unsigned player); //initial reaction34, for a real follow-up contact
    bool knockoutPreview=false; // isolated callback fixture, not a round transition
private:
    ActionBank bank_;
    JudgmentData judgments_;
    CollisionTables collisions_;
    CombatTables combat_;
    DamageTables damage_;
    ReactionTables reactions_;
    OrdinaryRules ordinary_;
    StateEntryRules entries_;
    ActionSelection selection_;
    InputSampler slashSampler_;
    std::array<uint32_t,2> slashPresses_{};
    GameRandom random_;
    std::array<std::unique_ptr<TrialActor>,2> actors_;
    void enter(unsigned player,int table,int state,unsigned action,bool stop,bool deferAction=false);
    void callbacks(unsigned player,uint32_t pressed);
    bool startGroundSlash(unsigned player,uint32_t pressed);
    void downedCallback(unsigned player);
    void faceOpponent(unsigned player);
    void advanceStage();
    void advanceRoundBodies();
    void updateRoundBodies();
    void beginNextRound();
};
}
