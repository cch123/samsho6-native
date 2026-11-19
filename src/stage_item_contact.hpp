#pragma once

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct StateEntryContext;
struct GroundStateFrame;

void beginStageItemPickup(PlayerObject&,StateEntryActor&);
bool updateStageItemPickup(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
}
