#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
struct StateEntryActor;
struct StageCamera;
uint32_t spawnMamahaha(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                       unsigned player,uint32_t actorFlags,const AuxiliaryObject& body);
// The attack controller writes a command to +128. The stand-alone bird
// task acknowledges it in +12c on its own scheduler visit.
void updateMamahaha(AuxiliaryObjects&,AuxiliaryObject& bird,const AuxiliaryObject& ownerBody,
                    const StateEntryActor&,bool finalWin,const StageCamera&);
}
