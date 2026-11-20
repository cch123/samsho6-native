#pragma once

#include "player_object.hpp"
#include "state_entry.hpp"

namespace ss6 {
// Normal states 23/36 (169e00) and 24 share the actor's real timers, command
// features and pending action queue with the other 149d08 callbacks.
// movementFlags is the fighter's 168bf8 byte; bit 4 selects the step dash.
void beginDash(PlayerObject&,StateEntryActor&,uint8_t movementFlags);
bool isDashCallback(const StateEntryActor&);
// True delegates to the common 169810 recovery path after reading the
// current down direction, as in 169918. The caller owns the tail transition.
bool updateDash(PlayerObject&,StateEntryActor&,const ActorCommandInput&);
}
