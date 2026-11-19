#pragma once
#include "player_object.hpp"
#include "state_entry.hpp"

namespace ss6 {
void updatePursuitVictim(PlayerObject&,StateEntryActor&);
void beginPursuitAttack(StateEntryActor&);
bool updatePursuitAttack(PlayerObject&,StateEntryActor&,float opponentX);
}
