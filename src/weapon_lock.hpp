#pragma once
#include "battle_round.hpp"
#include "auxiliary_objects.hpp"

namespace ss6 {
//The controller queues normal31 and the common action135; their subsequent
//actor/object animation phases remain separate, as in the original loop.
class WeaponLock {
public:
    explicit WeaponLock(const std::filesystem::path&);
    void enter(BattleRoundState&,const std::array<RoundPlayerRef,2>&,SoundSelection* sound=nullptr); //1449c0
    static void update(BattleRoundState&,const std::array<RoundPlayerRef,2>&,SoundSelection* sound=nullptr); //144b28
    static bool aiPress(StateEntryActor&,GameRandom&); //158ac8
    void task(BattleRoundState&,const std::array<RoundPlayerRef,2>&,uint32_t task) const; //145e30
private:
    AuxiliaryObjects objects_;
    std::array<ScalarFloat,4> constants_;
};
}
