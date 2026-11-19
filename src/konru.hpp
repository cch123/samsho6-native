#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
struct StateEntryActor;
uint32_t spawnKonru(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                    unsigned player,uint32_t flags,const AuxiliaryObject& body);
void updateKonru(AuxiliaryObjects&,AuxiliaryObject&,const AuxiliaryObject& body,const StateEntryActor& owner,
                 unsigned opponentCharacter,unsigned opponentAction);
}

