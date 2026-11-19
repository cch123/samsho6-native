#pragma once
#include <cstdint>

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;

bool isHanzoSpecialCallback(uint32_t handler);
bool updateHanzoSpecial(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&);
}
