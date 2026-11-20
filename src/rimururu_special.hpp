#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;
struct StageCamera;

bool updateRimururuSpecial(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&);
void spawnRimururuIce(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,unsigned slot,
                      const StateEntryActor&,const AuxiliaryObject& parent);
void updateRimururuIce(AuxiliaryObjects&,TaggedTaskPools&,uint32_t task,const StageCamera&,unsigned ownerAction);
}
