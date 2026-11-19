#pragma once

#include "player_object.hpp"
#include "state_entry.hpp"

namespace ss6 {
// Haohmaru's normal states 23/24 share the actor's real timers, command
// features and pending action queue with the other 149d08 callbacks.
void beginDash(PlayerObject&,StateEntryActor&);
bool isDashCallback(const StateEntryActor&);
// True delegates to the common 169810 recovery path after reading the
// current down direction, as in 169918. The caller owns the tail transition.
bool updateDash(PlayerObject&,StateEntryActor&,const ActorCommandInput&);
}
