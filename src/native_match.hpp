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
#include "system_data.hpp"
#include "console_option.hpp"
#include "spirits_edit.hpp"
#include "arcade_tally.hpp"
#include "menu_canvas.hpp"
#include "pause_menu.hpp"
#include "key_config.hpp"
#include "skill_list.hpp"
#include "practice_battle.hpp"
#include "survival_session.hpp"

namespace ss6 {
// World directions at the normalized software-pad boundary (118128).
enum BattleButton : uint32_t {
    PadUp=0x10,PadDown=0x20,PadLeft=0x40,PadRight=0x80,
    PadLight=0x100,PadMedium=0x200,PadHeavy=0x400,PadKick=0x800,PadSystem=0x1000,PadStart=8,
    PadMediumHeavy=0x2000,PadLightMedium=0x4000,PadLightKick=0x8000,
    PadSelect=0x10000 // physical 80000: opens the pause menu
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
    int32_t score=0;      // GameData+90 carried between arcade fights
    // The process RNG at scene entry when the caller owns it between scenes.
    std::optional<GameRandom> random;
    // Practice settings 13738a0.. and the replay/recording words; they outlive the battle scene.
    std::shared_ptr<PracticeState> practice;
    // SURVIVAL: the run that outlives each opponent's fight (180510 .. 138340).
    std::shared_ptr<SurvivalSession> survival;
};
// 158830: AI+0x100 for an ordinary fight CPU. Sugoroku (33) and Kuroko (48)
// always fight at level 8, except in survival (158850), which keeps 17b890's level.
inline int cpuFightLevel(bool survival,int rawCharacter,int level) {
    return !survival&&(rawCharacter==0x21||rawCharacter==0x30)?8:level;
}
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
    // The save image outlives every scene; rematches and new fights share it.
    SystemData& system() const {return *system_;}
    const std::shared_ptr<SystemData>& systemHandle() const {return system_;}
    // Call before the first tick or scene: replaces the factory image.
    void adoptSystem(std::shared_ptr<SystemData> system) {system_=std::move(system);}
    NativeMatch(const NativeMatch&)=delete;
    NativeMatch& operator=(const NativeMatch&)=delete;
    void tick(const std::array<NormalizedPadSample,2>& pads);
    // Configure a native decision maker before the first battle tick. Each seat has its own AI level.
    void enableCpu(unsigned seat,int level=4);
    void openTitle(bool returningFromVersus);
    const auto& title() const {return title_;}
    // OPTION MODE scenes (1cfa10 and its sub-pages) and their white fade.
    const std::optional<ConsoleOption>& option() const {return option_;}
    const SceneFade& sceneFade() const {return sceneFade_;}
    // The menu page submissions of this tick (1ce570, 1ce660 and the page
    // routines); the viewer rasterises them with menuCanvas().
    const MenuCanvas* menuCanvas() const {return menuCanvas_.get();}
    const MenuDrawList& menuDrawList() const {return menuList_;}
    // SPIRITS EDIT MODE (13ad40); the page is driven by one seat.
    const std::optional<SpiritsEdit>& spiritsEdit() const {return spiritsEdit_;}
    // Arcade: GameData+90 and the state-9 tally task (1c7f08).
    int32_t arcadeScore() const {return arcadeScore_;}
    const ArcadeTally& arcadeTally() const {return tally_;}
    // Set once the single-seat select (mode word 1/2) has left through
    // 12f100: the seat and its character, colour and spirit.
    struct SoloSelection {unsigned seat=0;int character=0,colour=0,spirit=0;};
    const std::optional<SoloSelection>& soloSelection() const {return soloSelection_;}
    // In-battle pause menu (1d9b50) and its child windows.
    const PauseMenu* pauseMenu() const {return pause_.get();}
    const PauseMenuAssets* pauseAssets() const {return pauseAssets_.get();}
    const PauseMenuDraw& pauseDraw() const {return pauseDraw_;}
    bool keyConfigOpen() const {return pause_&&pause_->windowTask[0]==PauseMenu::Woken;}
    bool skillListOpen() const {return pause_&&pause_->windowTask[1]==PauseMenu::Woken;}
    // A pause-menu exit the session must route (arcade runs only).
    PauseScene pauseExit() const {return pauseExitDone_?pauseExit_:PauseScene::None;}
    void openSoloSelect(unsigned seat);
    // PRACTICE MODE: menu confirm 1cd428 (mode word 9/10, sub-mode 3), the
    // battle-side window 17f790 and its exits.
    void openPracticeSelect(unsigned seat);
    // CHARACTER SELECT exit of the practice window: scene 128008 with the process RNG as the battle left it.
    void reopenPracticeSelect(const GameRandom& random);
    // Scene 127940 entered from a mode: the mode menu reopens on the row that started it.
    void openModeMenu(int row);
    int menuRow() const {return menuRow_;}
    const PracticeBattle* practiceBattle() const {return practiceBattle_.get();}
    const std::shared_ptr<PracticeState>& practiceState() const {return practice_;}
    // 1 = CHARACTER SELECT (128008), 2 = RETURN TO TITLE (127940), once the fade has switched scenes.
    int practiceExit() const {return practiceBattle_?practiceBattle_->exitDone:0;}
    int practiceBehaviour() const;                 // 139c88
    std::vector<std::string> practiceOverlay() const; // provisional text view of the window and displays
    // SURVIVAL MODE: menu confirm 1cd494 (mode word b/c, sub-mode 4) and the battle-side controller 180630.
    void openSurvivalSelect(unsigned seat);
    const SurvivalSession* survivalSession() const {return survival_.get();}
    int survivalFade() const;                          // 12d4cc8: alpha of the black rectangle 1806e4
    std::vector<std::string> survivalOverlay() const;  // provisional text view of the windows and the panel 1810f8
    // 13a6c0 frees tag fa1 (the arena task) one frame before 1a4a98 loads the next arena.
    void survivalReleaseStage();
    int cpuLevel(unsigned seat) const {return cpuLevels_.at(seat);}
    const ArcadeTallyTables* arcadeTables() const {return tallyTables_.get();}
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
    std::unique_ptr<ConsoleOptionTables> optionTables_;
    std::optional<ConsoleOption> option_;
    OptionScene pendingOption_=OptionScene::None;
    MenuPadRepeat menuRepeat_;
    SceneFade sceneFade_;
    int menuRow_=-1;
    std::unique_ptr<MenuCanvas> menuCanvas_;
    MenuBackdrop menuBackdrop_;
    MenuDrawList menuList_;
    void drawOption();
    std::unique_ptr<SpiritsEditAssets> spiritsAssets_;
    std::unique_ptr<EditWidgetAssets> editWidgets_;
    std::optional<SpiritsEdit> spiritsEdit_;
    unsigned editSeat_=0;
    std::unique_ptr<ArcadeTallyTables> tallyTables_;
    std::optional<SoloSelection> soloSelection_;
    std::unique_ptr<PauseMenuAssets> pauseAssets_;
    std::unique_ptr<PauseMenu> pause_;
    PauseMenuDraw pauseDraw_;
    ArcadeGameData pauseGame_;
    std::array<ArcadePlayer,2> pausePlayers_{};
    std::unique_ptr<KeyConfigAssets> keyAssets_;
    std::unique_ptr<MenuWidgetData> widgetData_;
    std::unique_ptr<SkillListData> skillData_;
    KeyConfigWindow keyConfig_;
    std::optional<SkillListWindow> skillList_;
    PauseScene pauseExit_=PauseScene::None;
    bool pauseExitDone_=false,pauseHold_=false;
    bool tickPause(const std::array<NormalizedPadSample,2>&);
    std::shared_ptr<PracticeState> practice_;
    std::unique_ptr<PracticeBattle> practiceBattle_;
    void enterPractice();                  // 17f5a0 and the practice part of 1398c0
    void buildPracticeActor(unsigned seat);// practice parts of 148df0/158830 and 13fb64..13fd28
    void practiceRestart();                // 13921c: 11e600, 13f9f0(0)
    void tickPractice(const std::array<NormalizedPadSample,2>&); // one iteration of 138f48 in practice
    // The scheduler dispatch, 140120 and 140270; `held` is the pause request 123a0c4 (140270 is skipped).
    // Returns true on a frame the KO pause 123a0ec counted (s1 of 138f48).
    bool battleFrame(const std::array<NormalizedPadSample,2>&,bool held=false);
    std::shared_ptr<SurvivalSession> survival_;
    bool survivalEndHandled_=false;
    void tickSurvival(const std::array<NormalizedPadSample,2>&); // one iteration of 138f48 in survival
    ArcadeTally tally_;
    int32_t arcadeScore_=0,arcadeFinishBonus_=0;
    std::array<uint32_t,2> menuPressed_{};
    ArcadeTallyWorld tallyWorld() const;
    ArcadeTallyWorld tallyWorld_; // the words the task counts down between visits
    bool editLeaving_=false;
    void tickSpiritsEdit(const std::array<NormalizedPadSample,2>&);
    void returnToModeMenu();
    void enterOption(OptionScene);
    void tickOption(const std::array<NormalizedPadSample,2>&);
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
    std::shared_ptr<SystemData> system_;
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
    // A fight whose opponent the session chose (arcade schedule, survival candidate):
    // 139660 loads both fighters' banks at scene entry, whatever the previous scene bound.
    bool rebindAudio_=false;
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
