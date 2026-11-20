#pragma once
#include "battle_round.hpp"
#include "collision.hpp"

namespace ss6 {
void presentContact(ScheduledOpening&,BattleRoundState&,const ContactEvent&,const CollisionPlayer& target,
                    unsigned defense,bool chip,bool specialHit,uint32_t sourceState,AuxiliaryObjects&);
void spawnElementHurt(AuxiliaryObjects&,BattleRoundState&,unsigned victim,const PlayerObject&,const StateEntryActor&,int state=-1);
void updateElementHurt(AuxiliaryObjects&,BattleRoundState&,uint32_t task,const std::array<RoundPlayerRef,2>&);
void presentWeaponClash(ScheduledOpening&,BattleRoundState&,const ContactEvent&);
}
