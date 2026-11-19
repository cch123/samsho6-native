#pragma once
#include "round_dispatcher.hpp"
#include "human_input.hpp"
#include "combat_decision.hpp"
#include "sound_selection.hpp"
#include "rage_gauge.hpp"
#include "battle_clock.hpp"
#include "fighter_identity_hud.hpp"
#include "combat_stage_state.hpp"
#include "character_select.hpp"
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
class NativeMatch {
public:
    explicit NativeMatch(const std::filesystem::path& assets,int roundTime=-1,VersusMode mode=VersusMode::FixedMatch,
                         const NativeMatch* rematchFrom=nullptr,std::array<unsigned,2> spirits={},
                         std::optional<VersusLineup> selection={},int selectedStage=0);
    NativeMatch(const NativeMatch&)=delete;
    NativeMatch& operator=(const NativeMatch&)=delete;
    void tick(const std::array<NormalizedPadSample,2>& pads);
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
    DamageTables damage_;
    ReactionTables reactions_;
    std::array<JudgmentData,3> judgments_;
    CollisionTables collisions_;
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
    void scriptDamage(unsigned target,int base,DamageOrigin,int projectileCategory=10);
    bool resolveStrike(const ContactEvent&,const CollisionPlayer&,const CollisionPlayer&,ContactMarks&,ContactMarks&,uint32_t sourceHandle=0);
    void updateStage();
    void visitActor(unsigned,const std::array<NormalizedPadSample,2>&);
};
}
