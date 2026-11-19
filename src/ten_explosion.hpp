#pragma once
#include "ground_state.hpp"

namespace ss6 {
void beginSpiritBurst(PlayerObject&,StateEntryActor&,const InputSystemConfig&,const GroundStateFrame&);
void beginIssenVictim(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
bool updateTenExplosion(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
}
