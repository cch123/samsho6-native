#include "weapon_pickup.hpp"
#include "ground_state.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
void beginWeaponPickup(PlayerObject& body, StateEntryActor& actor, TaggedTaskPools& pools,
                       std::span<const uint32_t> ownTasks, float opponentX) {
    actor.opponentX = opponentX;
    actor.faceOpponent();
    for (const auto task : ownTasks) {
        if (!task) continue;
        auto& object = pools.objects.at(pools.tasks.at(task-1)[7]-1);
        if (object[0xcc/4] != 4) continue;

        // 140f00 takes the first weapon in this player's registry. Input
        // permission already checked its landed ACT and distance. Marking it
        // here lets the ordinary registry visit reclaim object and task in order.
        actor.flags23c |= 0x1000;
        actor.x = std::bit_cast<float>(object[0x40/4]);
        object[0x108/4] |= 0x1000;
        GroundStateRuntime::restoreBody(body,actor);
        actor.queuedActionA3c = 136;
        actor.flags248 &= ~0x800u;
        actor.callbacks260[0] = 0x169a50;
        actor.callbacks260[1] = 0;
        actor.callbacks260[2] = 0xffffffff;
        actor.callbacks260[5] = 0;
        return;
    }
    throw std::runtime_error("Pickup state requires the player's registered weapon");
}
}
