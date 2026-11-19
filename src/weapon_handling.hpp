#pragma once
#include "ground_state.hpp"

namespace ss6 {
void beginWeaponHandling(StateEntryActor&);
void updateWeaponDiscard(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
}
