#pragma once
#include "kazuki_fire.hpp"
#include "projectile_engine.hpp"
#include "round_dispatcher.hpp"
#include "human_input.hpp"
#include "cpu_tactics.hpp"
#include <memory>
#include "combat_decision.hpp"
#include "sound_selection.hpp"
#include "rage_gauge.hpp"
#include "battle_clock.hpp"
#include "fighter_identity_hud.hpp"
#include "combat_stage_state.hpp"
#include "character_select.hpp"
#include "console_title.hpp"
#include "versus_faceoff.hpp"

namespace ss6 {
// World directions at the normalized software-pad boundary (118128).
enum BattleButton : uint32_t {
    PadUp=0x10,PadDown=0x20,PadLeft=0x40,PadRight=0x80,
    PadLight=0x100,PadMedium=0x200,PadHeavy=0x400,PadKick=0x800,PadSystem=0x1000,PadStart=8,
    PadMediumHeavy=0x2000,PadLightMedium=0x4000,PadLightKick=0x8000
};
enum class VersusMode { FixedMatch, Console };
struct VersusFighterChoice {unsigned character=0,spirit=0,palette=0;};
using VersusLineup=std::array<VersusFighterChoice,2>;
// The mode-dependent part of the setup block 4d3d04 (1398c0) and of 13f9f0.
struct MatchRules {
    int gameMode=3;       // 4c3808: 0 demo, 1/2 arcade P1/P2, 3 two humans, 9/10 practice
    int submode=2;        // 4c38a8: 1 arcade, 2 VS, 3 practice, 4 survival
    int battleKind=0;     // 123a0c0: 0 normal, 1 practice, 2 survival
    std::array<int,2> requiredWins{2,2};   // seat +0x20 (13f9f0 forces 1 in practice/survival)
    int gameTime=0;       // option 43d05d: 0 60, 1 90, 2 infinity
    int damagePercent=100,gameLevel=4;     // options 43d061, 43d05c
    // setup[0]: AI level of each CPU seat, or -1 for a human. Arcade passes
    // the human seat's progress count; 158830 raises it to 8 for 33 and 48.
    std::array<int,2> cpuLevel{-1,-1};
    int stage=-1;         // GameData+4 when the caller already chose the stage
};
struct MatchFighter {
    explicit MatchFighter(ActionBank& bank):body(bank) {}
    PlayerObject body;
    StateEntryActor actor;
    ActorCommandInput input;
    InputSystemConfig config;
    RoundActorStorage storage;
    CallbackContext objects;
    ActorInputSampling sampling;
    unsigned hits=0,guards=0;
};
// Called at the CPU's actual actor visit. The other seat may have already
// advanced this tick, so a single precomputed pair of per-tick inputs would
// lose an observation available to the original player-two decision.
using CpuSeatDecision=std::function<CpuCommand(MatchFighter&,const MatchFighter&,BattleRoundState&)>;
class NativeMatch {
public:
    explicit NativeMatch(const std::filesystem::path& assets,int roundTime=-1,VersusMode mode=VersusMode::FixedMatch,
                         const NativeMatch* rematchFrom=nullptr,std::array<unsigned,2> spirits={},
                         std::optional<VersusLineup> selection={},int selectedStage=0,
                         std::array<CpuSeatDecision,2> cpuSeats={},const MatchRules* rules=nullptr);
    const MatchRules& rules() const {return rules_;}
    NativeMatch(const NativeMatch&)=delete;
    NativeMatch& operator=(const NativeMatch&)=delete;
    void tick(const std::array<NormalizedPadSample,2>& pads);
    // Configure a native decision maker before the first battle tick. Each seat has its own AI level.
    void enableCpu(unsigned seat,int level=4);
    void openTitle(bool returningFromVersus);
    const auto& title() const {return title_;}
    bool titlePromptVisible() const {return promptClock_<60;}
    void openCharacterSelect(bool boot=false);
    void leaveUnportedFight(const UnportedFighterState&);
    const std::string& missingMove() const {return missingMove_;}
    const std::optional<CharacterSelect>& characterSelect() const {return characterSelect_;}
    const std::optional<VersusFaceoff>& faceoff() const {return faceoff_;}
    const VersusLineup& lineup() const {return lineup_;}
    VersusLineup selectedLineup() const;
    int selectWhiteLevel() const;
    int curtainFrame() const;
    int unavailableStage() const {return unavailableStage_;}
    int chosenStage() const {return selectedStage_;}
    bool selectionUnavailable() const {return unavailable_;}
    const MatchFighter& fighter(unsigned i) const {return fighters_.at(i);}
    const BattleRoundState& battle() const {return battle_;}
    std::span<const BattleSoundEvent> soundEvents() const {return sounds_.events();}
    CollisionPlayer collisionPlayer(unsigned i) const;
    const ObjectDrawQueue& objectDraws() const {return objectDraws_;}
    const std::vector<EffectDraw>& effectDraws() const {return draws_;}
    const CombatStageState& combatStage() const {return combatStages_.at(battle_.matchEnd.metadataStage04);}
    bool mikiriWhiteFrame() const { return mikiriWhiteFrame_; }
    uint32_t battleBackdropColor() const {return battleBackdropColor_;}
    const RageGaugeState& rageGauge() const {return rageGauge_;}
    const BattleClockState& hudClock() const {return hudClock_;}
    const FighterIdentityHudState& identityHud() const {return identityHud_;}
    void buildPresentationDraws(ObjectDrawQueue&) const;
    uint64_t updates=0;
    bool finished=false;
private:
    void enterSelectAudio();
    void enterTitleAudio();
    std::optional<ConsoleTitle> title_;
    bool titleAudioPending_=false;
    int titleFadeTick_=0;
    unsigned promptClock_=0;
    std::filesystem::path assets_;
    VersusLineup lineup_;
    std::array<unsigned,3> resourceSlots_;
    std::array<ActionBank,2> banks_;
    std::optional<CharacterSelect> characterSelect_;
    std::optional<VersusFaceoff> faceoff_;
    bool unavailable_=false,selectAudioPending_=false;
    int selectFade_=0,selectedStage_=0,unavailableStage_=-1;
    bool fromFaceoff_=false;
    std::string missingMove_;
    std::array<MatchFighter,2> fighters_;
    std::array<CpuSeatDecision,2> cpuSeats_;
    std::array<std::unique_ptr<CpuTactics>,2> cpuTactics_;
    std::array<int,2> cpuLevels_{-1,-1};
    MatchRules rules_;
    bool explicitRules_=false;
    CpuCommand runCpu(unsigned seat,PermissionContext&,const SelectionThreat&);
    BattleRoundState battle_;
    GroundStateRuntime ground_;
    HumanInputPipeline human_;
    BattleRoundInitialization initialize_;
    BattleGauges gauges_;
    RageGaugeState rageGauge_;
    BattleEffects effects_;
    SoundSelection sounds_;
    ScheduledOpening captions_;
    StageEventRules stage_;
    StageEventPlayback referee_;
    unsigned refereeDrawSlot_=0;
    bool refereeSubmitted_=false;
    unsigned itemDrawSlot_=0,itemDrawCount_=0;
    void visitStageItems(bool retainFighters);
    void visitReferee(bool retainFighters);
    void sampleHud();
    // The PS2 keeps separate animation clocks for each arena across VS scene loads.
    std::array<CombatStageState,CombatStageState::stageCount> combatStages_{};
    CombatStageState& activeStage() {return combatStages_.at(battle_.matchEnd.metadataStage04);}
    uint32_t battleBackdropColor_=0;
    unsigned mikiriFlashLeft_=0;
    bool mikiriWhiteFrame_=false;
    MatchEndingRules ending_;
    WeaponLock lock_;
    AuxiliaryObjects aux_;
    AngleTrig angleTrig_; // angle_trig.bin (Kazuki's fire)
    DamageTables damage_;
    ReactionTables reactions_;
    std::array<JudgmentData,3> judgments_;
    CollisionTables collisions_;
    ProjectileTable projectiles_;
    CombatTables combat_;
    RoundDispatcher rounds_;
    std::array<InputMapping,2> mappings_{};
    std::vector<EffectDraw> draws_;
    ObjectDrawQueue objectDraws_;
    bool sceneAudioEntered_=false;
    uint32_t auxiliaryJumpFlags_=0;
    BattleClockState hudClock_;
    FighterIdentityHudState identityHud_;
    unsigned portraitPosition_=0;
    std::array<uint32_t,2> portraitClocks_{};
    enum class ObjectPhase { Move, Callbacks, Draw };
    void auxiliaryPhase(ObjectPhase);
    int32_t distance_=0;
    std::array<RoundPlayerRef,2> players();
    void resolveContacts();
    void setCaptureObjectGates(bool captured,bool entering);
    void strikeMikiri(const ContactEvent&,const CollisionPlayer& from,const CollisionPlayer& to,
                      const AuxiliaryObject& image,ContactMarks& source,ContactMarks& target);
    enum class DamageOrigin { FighterRecord, ProjectileRecord, CaptureScript };
    void interruptConcentration(unsigned target);
    void updateTakeLoser(unsigned player,uint32_t task);
    void scriptDamage(unsigned target,int base,DamageOrigin,int projectileCategory=10);
    bool resolveStrike(const ContactEvent&,const CollisionPlayer&,const CollisionPlayer&,ContactMarks&,ContactMarks&,uint32_t sourceHandle=0);
    void markOffscreen(); // 142f30
    void minaScriptEvent(unsigned player,uint8_t type); // 164c58 events 33/34
    void scriptProjectileTask(unsigned player,uint32_t task);
    uint32_t spawnScriptProjectileFor(unsigned player,unsigned id,unsigned variant,const ScriptRow* row);
    void updateStage();
    void visitActor(unsigned,const std::array<NormalizedPadSample,2>&);
};
}
