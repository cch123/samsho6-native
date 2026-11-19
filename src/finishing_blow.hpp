#pragma once
#include "object_frame.hpp"

namespace ss6 {
struct StateEntryActor;
struct PlayerMatchStats;
struct ContactEvent;
class InputBindings;

int projectileFinishCategory(const AuxiliaryObject&,const StateEntryActor& owner,const StateEntryActor& opponent,
                             const InputBindings&);

// Sample counter status before changing
// the target's state or increasing the source's per-combo hit counter.
bool isCounterContact(const StateEntryActor& target,const PlayerMatchStats& sourceStats,const ContactEvent&);
void recordContactFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& sourceStats,
                         const ContactEvent&,bool projectile,bool guarded,bool counter,const InputBindings&,int projectileCategory=10);
void recordScriptFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& sourceStats,
                        bool projectile,bool captureDamage,const InputBindings&,int projectileCategory=10);
}
