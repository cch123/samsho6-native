#pragma once
#include "ground_state.hpp"

namespace ss6 {
// The ordinary B+C attempt and the successful throw have separate states.
// Only route 4 in the contact resolver can advance 26 into 31.
void beginGroundThrow(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
bool isGroundThrowCallback(const StateEntryActor&);
bool updateGroundThrow(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
}
