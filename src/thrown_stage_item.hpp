#pragma once
#include "auxiliary_objects.hpp"
#include "player_object.hpp"

namespace ss6 {
void spawnStageBomb(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> battleTasks,float x);
void throwStageItem(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> ownTasks,
                    std::span<const uint32_t> battleTasks,unsigned seat,unsigned item,
                    uint32_t actorFlags,const PlayerObject& body);
void updateThrownStageItem(AuxiliaryObjects&,TaggedTaskPools&,uint32_t task);
}
