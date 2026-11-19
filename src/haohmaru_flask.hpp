#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
uint32_t spawnHaohmaruFlask(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                           unsigned player,uint32_t actorFlags,const AuxiliaryObject& parent);
void reflectHaohmaruProjectile(AuxiliaryObjects&,AuxiliaryObject& target,unsigned newTeam);
void updateHaohmaruFlask(AuxiliaryObjects&,TaggedTaskPools&,uint32_t task);
}
