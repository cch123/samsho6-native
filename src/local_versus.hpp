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
    // The save image shared by every scene of this session; restart() keeps it.
    SystemData& system() {return *system_;}
    // Set when the scheduled stage or fighter has no native port yet.
    const std::string& arcadeNotice() const {return arcadeNotice_;}
    unsigned matchNumber() const {return matchNumber_;}
    void tick(const std::array<NormalizedPadSample,2>&);
    void restart();
    using TickObserver=std::function<void(const NativeMatch&)>;
    void onTick(TickObserver observer) {observer_=std::move(observer);}
private:
    std::filesystem::path assets_;
    int roundTime_;
    VersusMode mode_;
    std::array<unsigned,2> spirits_;
    VersusEntry entry_;
    std::array<bool,2> cpuSeats_{};
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
    void startArcade(unsigned seat,int character,int colour,int spirit);
    void startArcadeFight();
    void tickArcade(const std::array<NormalizedPadSample,2>&);
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
