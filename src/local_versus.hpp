#pragma once
#include "native_match.hpp"
#include <memory>
#include <functional>
#include <iosfwd>
#include <string_view>

namespace ss6 {
std::array<bool,2> versusCpuSeats(std::string_view name);
unsigned versusSpirit(std::string_view name);
bool readVersusReplaySegment(std::istream&,unsigned& ticks,std::array<uint32_t,2>& held);
enum class VersusEntry {Fight,CharacterSelect,Title};
class LocalVersus {
public:
    LocalVersus(const std::filesystem::path& assets,int roundTime=-1,VersusMode mode=VersusMode::Console,std::array<unsigned,2> spirits={},bool startAtSelect=false);
    LocalVersus(const std::filesystem::path& assets,int roundTime,VersusMode mode,std::array<unsigned,2> spirits,VersusEntry entry,std::array<bool,2> cpuSeats={});
    const NativeMatch& match() const {return *match_;}
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
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
