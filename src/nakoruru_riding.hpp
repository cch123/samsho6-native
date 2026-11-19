#pragma once
#include "ground_state.hpp"

namespace ss6 {
void beginNakoruruDismount(StateEntryActor&);
bool isNakoruruRidingCallback(const StateEntryActor&);
bool updateNakoruruRiding(PlayerObject&,StateEntryActor&,const ActorCommandInput&,
                          StateEntryContext&,const GroundStateFrame&);
}
