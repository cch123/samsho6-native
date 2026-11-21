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
    std::string arcadeNotice_;
    bool arcadeSelecting_=false; // CONTINUE reopened the character select
    void startArcade(unsigned seat,int character,int colour,int spirit);
    void startArcadeFight();
    void tickArcade(const std::array<NormalizedPadSample,2>&);
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
