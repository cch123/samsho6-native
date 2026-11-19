#pragma once
#include "cpu_execution.hpp"

namespace ss6 {
struct CpuReactionProjectile {
    unsigned owner;
    int id;
    uint32_t flags38;
    float x;
};
struct CpuReactionFrame {
    const InputPermissions& permissions;
    PermissionContext& objects;
    int opponentWins,opponentRequiredWins;
    unsigned seat;
    // Kind 5 objects registered with either fighter, in seat/registration order.
    std::span<const CpuReactionProjectile> projectiles;
};
// 158b08 for ordinary fight control mode 35. Every visited test can age a
// timer or consume a random number even if a later test publishes the input.
bool updateCpuReaction(StateEntryActor&,const StateEntryActor& opponent,const CpuDecisionFrame&,
                       const CpuExecutionFrame&,const CpuReactionFrame&);
}
