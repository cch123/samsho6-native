#pragma once
#include "battle_round.hpp"

namespace ss6 {
//Actor-facing round stages operate on the same persistent owners used by
//input and ground callbacks. These methods do not stand in for the entire
//143430/143320 dispatcher or its remaining object/input phases.
class RoundControl {
public:
    // 143430 publishes state 1 here. The dispatcher has already submitted
    // the group stops, and the actor/body commit follows later in the update.
    static void enterRound(BattleRoundInitialization&,GroundStateRuntime&,BattleRoundState&,
        const std::array<RoundPlayerRef,2>&,BattleEffects&,const StageEventRules&);
    //143708/1443f0 behavior after the console-only diagnostic call.
    //Validation labels these as tails, not whole original entry functions.
    static void enterIntroduction(BattleRoundState&,const StageEventRules&);
    static void enterVictory(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const StageEventRules&,SoundSelection* sound=nullptr);
    //143430 stage placement/request after13fd80, before entering state1.
    static void resetStage(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const StageEventRules&);
    //143930/143a38. The later task dispatch advances the caption and its voice together.
    static void enterOpening(BattleRoundState&,const std::array<RoundPlayerRef,2>&,
        const StageEventRules&,ScheduledOpening&,SoundSelection* sound=nullptr);
    static void opening(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const StageEventRules&);
    static void startStageMusic(BattleRoundState&,SoundSelection*);
    static void enterCombat(BattleRoundState&,SoundSelection* sound=nullptr);
    // 143b88 handles timeout before the referee and item delivery.
    static void combat(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const StageEventRules&);
    static void combatStageEvent(BattleRoundState&,const std::array<RoundPlayerRef,2>&,const StageEventRules&); //144e10
    //143320 publishes these AFTER interaction update144950, not in143b88.
    static void snapshotPlayers(BattleRoundState&,const std::array<RoundPlayerRef,2>&);
    //Ordinary143c60 behavior after its console diagnostic, both human
    //resource00/system0, local versus with profile recording disabled.
    static void enterEnding(BattleRoundState&,const std::array<RoundPlayerRef,2>&,
        ScheduledOpening&,const MatchEndingRules&,SoundSelection* sound=nullptr);
    //144020: ending caption chains and ordinary actor readiness. It queues
    //normal52 without committing the actor/action in the controller phase.
    static void ending(BattleRoundState&,const std::array<RoundPlayerRef,2>&,ScheduledOpening&);
    static void introduction(BattleRoundState&,const std::array<RoundPlayerRef,2>&); //143798
    // The dispatcher submits the 1438f0 sound group stops before this transition.
    static void skippedIntroduction(BattleRoundState&);
    static void enterVictoryCamera(BattleRoundState&,const std::array<RoundPlayerRef,2>&); //1441e0
    static void victoryCamera(BattleRoundState&,const std::array<RoundPlayerRef,2>&); //144360
    static void victory(BattleRoundState&,const std::array<RoundPlayerRef,2>&,int submode); //144570
    static void advanceBattleClock(BattleRoundState&,const std::array<RoundPlayerRef,2>&);
    static void inputLocks(const BattleRoundState&,const std::array<RoundPlayerRef,2>&); //143390
};
}
