#pragma once
#include "round_control.hpp"
#include "weapon_lock.hpp"

namespace ss6 {
//All phases borrow the live match's actors, effects and pools. Owning a second
//copy here would lose queued commands and leave captions alive across resets.
struct RoundDispatchServices {
    BattleRoundInitialization& initialize;
    GroundStateRuntime& ground;
    BattleEffects& effects;
    const StageEventRules& events;
    ScheduledOpening& captions;
    const MatchEndingRules& results;
    WeaponLock& weaponLock;
    SoundSelection* sound=nullptr;
};
class RoundDispatcher {
public:
    explicit RoundDispatcher(RoundDispatchServices services):services_(services) {}
    bool enter(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; //143430
    void update(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; //1435d8
    void step(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; //143320
    void interaction(BattleRoundState&,const std::array<RoundPlayerRef,2>&) const; //144950
private:
    RoundDispatchServices services_;
};
}
