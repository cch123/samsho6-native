#pragma once
#include "native_match.hpp"
#include "arcade_session.hpp"
#include <memory>
#include <string>
#include <functional>
#include <iosfwd>
#include <string_view>

namespace ss6 {
std::array<bool,2> versusCpuSeats(std::string_view name);
unsigned versusSpirit(std::string_view name);
bool readVersusReplaySegment(std::istream&,unsigned& ticks,std::array<uint32_t,2>& held);
enum class VersusEntry {Fight,CharacterSelect,Title,Arcade};
class LocalVersus {
public:
    LocalVersus(const std::filesystem::path& assets,int roundTime=-1,VersusMode mode=VersusMode::Console,std::array<unsigned,2> spirits={},bool startAtSelect=false);
    LocalVersus(const std::filesystem::path& assets,int roundTime,VersusMode mode,std::array<unsigned,2> spirits,VersusEntry entry,std::array<bool,2> cpuSeats={});
    const NativeMatch& match() const {return *match_;}
    // The running ARCADE MODE session, or null. While its scene is not the
    // fight, match() still holds the last fight for display only.
    const ArcadeSession* arcade() const {return arcade_.get();}
    const PracticeState* practice() const {return practice_.get();}
    // The running SURVIVAL MODE run, or null (its Game Over scene is arcade()).
    const SurvivalSession* survival() const {return survival_.get();}
    // The save image shared by every scene of this session; restart() keeps it.
    SystemData& system() {return *system_;}
    // Set when the scheduled stage or fighter has no native port yet.
    const std::string& arcadeNotice() const {return arcadeNotice_;}
    unsigned matchNumber() const {return matchNumber_;}
    // Validation fixture: the running arcade fight ends now with `winner` (seat, or -1 for
    // a draw) as though 145628 had been reached, without playing it out.
    void forceArcadeResult(int winner) {forcedWinner_=winner;forced_=true;}
    // Every arcade scene entered in this process (validation trace).
    std::vector<ArcadeSceneEntry> arcadeLog() const;
    void tick(const std::array<NormalizedPadSample,2>&);
    void restart();
    // Pin the stage of a directly started fight (0..11). Stages 10 and 11
    // are not offered by the VS selector.
    void fixedStage(int stage) {stage_=stage;restart();}
    void stageItems(bool enabled) {items_=enabled;restart();}
    using TickObserver=std::function<void(const NativeMatch&)>;
    void onTick(TickObserver observer) {observer_=std::move(observer);}
    // Sound requests of the ARCADE presentation scenes on this tick.
    using SceneSoundObserver=std::function<void(const std::vector<ArcadeSceneSound>&)>;
    void onSceneSounds(SceneSoundObserver observer) {sceneSounds_=std::move(observer);}
private:
    std::filesystem::path assets_;
    int roundTime_;
    VersusMode mode_;
    std::array<unsigned,2> spirits_;
    VersusEntry entry_;
    std::array<bool,2> cpuSeats_{};
    int stage_=0;
    bool items_=false;
    void configureControllers(NativeMatch&) const;
    MatchRules versusRules() const;
    std::unique_ptr<ArcadeSession> arcade_;
    std::shared_ptr<SystemData> system_;
    std::string arcadeNotice_;
    bool arcadeSelecting_=false; // CONTINUE reopened the character select
    // PRACTICE MODE: settings 13738a0.. live from the mode-menu confirm (210368) to RETURN TO TITLE.
    std::shared_ptr<PracticeState> practice_;
    int practiceRow_=-1; // mode-menu cursor 582af8 at the confirm
    bool tickPracticeSession();
    // SURVIVAL MODE. The charaTable 12d3668 keeps its history rows and the last
    // confirmed candidate between runs (17ac98 only clears the win count).
    std::shared_ptr<SurvivalSession> survival_;
    SurvivalTable survivalTable_;
    bool survivalOver_=false; // the Game Over scene on screen ends a survival run
    int survivalReload_=0; // frames since 13a6c0: 1 arena load (1a4a98), 2 fighters (13f9f0(1))
    void startSurvival(unsigned seat,int character,int colour,int spirit);
    bool startSurvivalFight(const GameRandom& random,bool confirmed);
    void tickSurvival(const std::array<NormalizedPadSample,2>&);
    void endSurvival();
    void startArcade(unsigned seat,int character,int colour,int spirit);
    void startArcadeFight();
    void tickArcade(const std::array<NormalizedPadSample,2>&);
    bool arcadeSceneFlow();      // opens the select / starts the fight the session entered
    void deliverSceneSounds();
    SceneSoundObserver sceneSounds_;
    std::vector<ArcadeSceneEntry> arcadeLog_; // scenes of the finished runs
    bool forced_=false,fightMissing_=false;int forcedWinner_=-1;
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
