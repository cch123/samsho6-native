#pragma once
#include "round_initialization.hpp"
#include "input_features.hpp"
#include "stage_camera.hpp"
#include "stage_event.hpp"
#include "stage_item_delivery.hpp"
#include "stage_item_notices.hpp"
#include "scheduled_opening.hpp"
#include "battle_gauges.hpp"
#include "match_ending.hpp"
#include "versus_result.hpp"
#include "console_versus_menu.hpp"
#include "round_rules.hpp"
#include <vector>

namespace ss6 {
struct BattleAudioRequest {uint32_t command=0,parameter=0;};
struct BattleAudioState {
    uint32_t streamParameter5a9e78=0,streamStart1553b5c=0,streamWord1553a40=0,musicActive123a174=0;
    bool musicPreloaded123a178=false;
    // Raw 213878 starts retained for round-control validation. The native
    // backend receives the same request through the tick's sound events.
    std::vector<BattleAudioRequest> requests;
};
//Persistent shared state at the ordinary13fd80 boundary. These pools and
//the random/input owners must also be used by both actors between rounds.
struct BattleRoundState {
    StateEntryContext entry;
    GameRandom random;
    InputSampler sampler;
    StageCamera camera;
    BattleTimers timers;
    MatchProgress match;
    StageEventActor stageEvent;
    uint32_t finalSoundPending3d2e78=0;
    uint32_t openingOwner30=0,voiceGate5850e0=0;
    EffectResidency effectResidency;
    GaugeState gauges;
    BattleAudioState audio;
    MatchEndState matchEnd;
    VersusResultState resultScreen;
    ConsoleVersusMenu consoleMenu;
    BattlePause pause;
    int32_t endingParameter2c=0;
    uint32_t stageItemsOption4c3828=0;
    //Three24-word arrays at439a48/439aa8/439b08, reset by1159d0.
    //Keep the raw values until their rendering consumers are integrated.
    std::array<std::array<uint32_t,24>,3> paletteState{};
    std::array<uint32_t,64> objectTasks{};
    int32_t requestedState=0,currentState=0,field08=-1,field0c=-1;
    uint32_t flags138=0,field140=0,phase130=0;
    int32_t gameMode=3,timeOption13c=3;
    // 123a0c0 (139280): 0 normal, 1 practice, 2 survival. Most battle sites
    // test this byte through 139388/1393a0 instead of the mode word.
    int32_t battleKind123a0c0=0;
    // Option byte 43d061 (DAMAGE LEVEL) and 43d05c (GAME LEVEL).
    int32_t damagePercent43d061=100,gameLevel43d05c=4;
    bool practice() const {return battleKind123a0c0==1;}          // 139388
    bool survival() const {return battleKind123a0c0==2;}          // 1393a0
    bool networkSubmode() const {return matchEnd.submodeA0==5||matchEnd.submodeA0==6;} // 139408
    bool fixedRules() const {return survival()||practice()||networkSubmode();}        // 139430
    // 13fd80: the demo, practice and survival skip the character introduction.
    bool skipsIntroduction() const {return gameMode==0||practice()||survival();}
    // The seat whose arcade run this fight belongs to, or -1.
    int arcadeSeat() const {return gameMode==1?0:gameMode==2?1:-1;}
    // In local versus one displayed count spans 90 normal battle updates.
    static constexpr std::array<int,4> roundTimeLimits{60,90,99,0};
    int remainingSeconds() const;
    bool timeExpired() const;
    void queueLifeChange(StateEntryActor& recipient,uint32_t opponentFlags23c,int32_t amount) const;
    int32_t lastItemSecond=0; // 12d2304, zeroed at each round entry.
    StageItemDelivery stageItems;
    StageItemNotices itemNotices;
};
struct RoundPlayerRef {
    PlayerObject& body;
    StateEntryActor& actor;
    ActorCommandInput& input;
    const InputSystemConfig& config;
    RoundActorStorage& storage;
    CallbackContext& objects;
};
class BattleRoundInitialization {
public:
    explicit BattleRoundInitialization(const std::filesystem::path& assets,std::array<unsigned,3> slots={}):actors_(assets,slots) {}
    //Ordinary 13fd80 for resource00 human players and the four versus clock options.
    //Does not dispatch tasks or commit body actions: both occur later in
    //the original loop. Caller-owned sound-selection history is preserved.
    void begin(GroundStateRuntime&,const std::array<RoundPlayerRef,2>&,BattleRoundState&,BattleEffects&);
private:
    RoundInitialization actors_;
};
}
