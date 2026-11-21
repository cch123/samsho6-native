#pragma once
#include "object_frame.hpp"

namespace ss6 {
struct StateEntryActor;
struct PlayerMatchStats;
struct ContactEvent;
class InputBindings;

int contactFinishCategory(const StateEntryActor&,const InputBindings&); //14dac8
int projectileFinishCategory(const AuxiliaryObject&,const StateEntryActor& owner,const StateEntryActor& opponent,
                             const InputBindings&);

// Sample counter status before changing
// the target's state or increasing the source's per-combo hit counter.
bool isCounterContact(const StateEntryActor& target,const PlayerMatchStats& sourceStats,const ContactEvent&);
// `concentration`: 14eb78(source) exists and its state word (actor+13c) is 3 at the
// lethal request; 15787c then sets flags248 bit 23 (survival mission b).
void recordContactFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& sourceStats,
                         const ContactEvent&,bool projectile,bool guarded,bool counter,const InputBindings&,int projectileCategory=10,
                         bool concentration=false);
void recordScriptFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& sourceStats,
                        bool projectile,bool captureDamage,const InputBindings&,int projectileCategory=10,
                        bool concentration=false);
}
