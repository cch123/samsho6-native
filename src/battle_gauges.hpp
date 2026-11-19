#pragma once
#include "damage.hpp"

namespace ss6 {
struct BattleRoundState;
struct RoundPlayerRef;
class SoundSelection;
struct GaugeState {
    uint32_t paused46a940=0,scale1239d84=256,scale1239d88=256,delta46a908=256;
    int32_t focus46a948=-2;
    //46a910..93c includes46a924/934, which11e600 deliberately preserves.
    std::array<uint32_t,12> words910{};
    std::array<uint16_t,1024> paletteTones{}; //3ebf30;117180 changes upper512
    //Ordinary14f310 reads the two configured player bytes,43d069/43d06c.
    std::array<uint8_t,2> bonusLimits{32,32};
};
class BattleGauges {
public:
    explicit BattleGauges(const std::filesystem::path& assets):meters_(assets) {}
    static uint32_t start(BattleRoundState&); //11e520; allocation may return null
    static void stop(BattleRoundState&,const std::array<RoundPlayerRef,2>&); //11e600
    void startExplosion(BattleRoundState&,StateEntryActor&,unsigned player,int system=3) const; // 11f248
    void releaseExplosion(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; // 11f1c8
    static void beginConcentration(BattleRoundState&,unsigned); // 11ef30
    static void endConcentration(BattleRoundState&,StateEntryActor&,unsigned); // 11e548
    void releaseConcentration(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; // 11ef90
    void task(BattleRoundState&,const std::array<RoundPlayerRef,2>&,SoundSelection* sound=nullptr) const; //11e708 +11e760
private:
    DamageTables meters_;
};
}
