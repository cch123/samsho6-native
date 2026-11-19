#pragma once
#include <array>
#include <cstdint>
#include <filesystem>

namespace ss6 {
struct BattleRoundState;
struct RoundPlayerRef;
struct MatchEndState {
    int32_t winner08=-1,stage28=0,result8c=0,submodeA0=0;
    uint32_t continue2c=0,endFlagA4=0,metadataStage04=0;
    uint32_t field18=0,profileBusy4452ac=0;
    uint32_t profileActive123a168=0,profileFlags1239090=0;
    uint8_t characterVersion43d052=0;
};
class MatchEndingRules {
public:
    explicit MatchEndingRules(const std::filesystem::path&);
    //1a3070(character,2,choice): inspect presence only, never execute the
    //source pointer. Unresolved alternate-character rows are rejected.
    bool available(int character,unsigned choice,uint8_t version) const;
    int select(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; //1453a8
    //Ordinary versus145118 with local profile recording explicitly disabled.
    //Profile persistence and single-player score consumers remain separate.
    void recordFinal(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const;
private:
    std::array<std::array<uint32_t,17>,98> choices_{};
};
}
