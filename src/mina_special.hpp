#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;
class ScriptEngine;
struct StateEntryContext;
struct TaggedTaskPools;
using AuxiliaryObject=std::array<uint32_t,80>;

// Attack callback 1fb7a8 of resource 24 and the scripts it starts.
bool isMinaAttackCallback(uint32_t handler);
// Returns true when the original continues into the ordinary 169918 recovery.
bool updateMinaAttack(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&,
                      StateEntryContext&,const ScriptEngine&);
// 1fb970 for a victim of Mina. Returns true when 169810 recovery follows.
bool updateMinaVictim(PlayerObject&,StateEntryActor& victim,StateEntryContext&,const GroundStateFrame&,const ScriptEngine&);
// Thrown-weapon tasks 1fbfc8 (ACT 613) and 1fc420 (ACT 712, homing return).
void updateMinaWeapon(TaggedTaskPools&,uint32_t task,const AuxiliaryObject& ownerBody,StateEntryActor& owner);
}
