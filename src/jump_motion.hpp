#pragma once
#include <cstdint>

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct StageCamera;

// Includes the two wall-jump transitions selected by 173558.
// GroundStateRuntime owns state entry, callback prefixes, the input and ACT commits.
void beginJump(PlayerObject&, StateEntryActor&);
void updateJump(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const StageCamera*,uint8_t movementFlags);

// 1737d8 also gates the landing phase of directional weapon attacks.
bool jumpReachedGround(const PlayerObject&,int pendingAction);
bool isJumpAttack(int state);
void beginJumpAttack(PlayerObject&, StateEntryActor&);
// True requests the common 169810 recovery (including turn selection) on contact.
bool updateJumpAttack(PlayerObject&, StateEntryActor&);

void beginAirGuard(PlayerObject&, StateEntryActor&);
void updateAirGuard(PlayerObject&, StateEntryActor&);
void beginAirBlockReaction(PlayerObject&, StateEntryActor&);

void beginAirHurt(PlayerObject&, StateEntryActor&);
bool updateAirLanding(PlayerObject&, StateEntryActor&); // 173880: true once it requested the landing

void beginRecoveryRoll(PlayerObject&, StateEntryActor&);
}
