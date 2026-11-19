#pragma once
#include "player_object.hpp"
#include "state_entry.hpp"

namespace ss6 {
void beginWeaponPickup(PlayerObject& body, StateEntryActor& actor, TaggedTaskPools& pools,
                       std::span<const uint32_t> ownTasks, float opponentX);
}
