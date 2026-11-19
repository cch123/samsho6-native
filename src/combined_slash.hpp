#pragma once
#include "player_object.hpp"
#include "state_entry.hpp"
#include "reaction.hpp"

namespace ss6 {
// In spirit 0 both standing and crouching guards can block this A+B slash.
void beginCombinedSlash(StateEntryActor& actor);
void updateCombinedSlash(const PlayerObject& body, StateEntryActor& actor);
void setCombinedSlashPause(const ReactionTables& reactions, unsigned state, bool guard,
                            ActorTimers& source, ActorTimers& target);
}
