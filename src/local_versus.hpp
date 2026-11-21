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
    // Pin the stage of a directly started fight (0..11). Stages 10 and 11
    // are not offered by the VS selector.
    void fixedStage(int stage) {stage_=stage;restart();}
    void stageItems(bool enabled) {items_=enabled;restart();}
    // Debug only, not an original path: after a selection, field 'character' for 'seat'
    // instead of the selected one. Makai Gaoh (43) is an arcade boss with no grid cell.
    void substituteCharacter(unsigned seat,unsigned character) {substitute_.at(seat)=int(character);}
    using TickObserver=std::function<void(const NativeMatch&)>;
    void onTick(TickObserver observer) {observer_=std::move(observer);}
private:
    std::filesystem::path assets_;
    int roundTime_;
    VersusMode mode_;
    std::array<unsigned,2> spirits_;
    VersusEntry entry_;
    std::array<bool,2> cpuSeats_{};
    int stage_=0;
    bool items_=false;
    std::array<int,2> substitute_{-1,-1};
    void configureControllers(NativeMatch&) const;
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
