#pragma once
#include "native_match.hpp"
#include <memory>
#include <functional>
#include <iosfwd>
#include <string_view>

namespace ss6 {
unsigned versusSpirit(std::string_view name);
bool readVersusReplaySegment(std::istream&,unsigned& ticks,std::array<uint32_t,2>& held);
class LocalVersus {
public:
    LocalVersus(const std::filesystem::path& assets,int roundTime=-1,VersusMode mode=VersusMode::Console,std::array<unsigned,2> spirits={},bool startAtSelect=false);
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
    bool startAtSelect_;
    unsigned matchNumber_=1;
    std::unique_ptr<NativeMatch> match_;
    TickObserver observer_;
};
}
