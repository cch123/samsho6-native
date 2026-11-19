#pragma once
#include "state_callbacks.hpp"
#include "player_object.hpp"

namespace ss6 {
// Ten's 連斬 is a character callback. Its follow-ups use sampled face-button
// edges and the current ACT's flags, independently of the generic chain table.
void beginTenChain(PlayerObject&,StateEntryActor&,float opponentX);
bool updateTenChain(const PlayerObject&,StateEntryActor&,const ActorCommandInput&,
                    const InputSystemConfig&,const StateCallbacks&);
}
