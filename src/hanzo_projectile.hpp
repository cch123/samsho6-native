#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
struct StateEntryActor;
uint8_t hanzoProjectileFlags(unsigned descriptor);
void spawnHanzoProjectile(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                          const StateEntryActor&,const AuxiliaryObject& parent);
void updateHanzoProjectile(AuxiliaryObjects&,TaggedTaskPools&,uint32_t task);
}
