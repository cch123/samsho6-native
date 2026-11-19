#pragma once
#include "object_frame.hpp"
#include <filesystem>
#include <vector>

namespace ss6 {
struct BattleRoundState;
struct FighterIdentityHudState {
    std::array<int,2> wins{},required{2,2};
    int submode=2,lastEntrant=1,streak=0;
    bool alternateText=false,visible=false;
    bool portraitsAdvanced=false;
    std::array<uint8_t,2> portraitTime{};
private:
    std::array<uint8_t,2> nextTime_{};
public:
    void sample(const BattleRoundState&,bool reset);
};

class FighterIdentityHud {
public:
    explicit FighterIdentityHud(const std::filesystem::path& assets);
    static void submitPortraits(ObjectDrawQueue&,const GaugeState&,std::array<unsigned,3> resources,
                                const FighterIdentityHudState&);
    void paint(const FighterIdentityHudState&,std::span<uint8_t> rgba) const;
private:
    std::vector<uint8_t> atlas_;
};
}
