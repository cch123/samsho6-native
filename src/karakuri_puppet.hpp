#pragma once
#include <array>
#include <cstdint>
#include <span>
#include "auxiliary_objects.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
// Character 32's kind-3 puppet: 201ac0 (1a3220 at 1a32fc), task 201b40 with the capture
// predicate 202000, the mode entry 201d40 (6642e0), follow 201bf0 and update 201e90 (664320).
uint32_t spawnKarakuriPuppet(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                             unsigned player,uint32_t flags,const AuxiliaryObject& body);
void updateKarakuriPuppet(AuxiliaryObjects&,AuxiliaryObject&,const AuxiliaryObject& ownerBody,
                          const StateEntryActor& owner,unsigned opponentCharacter);
}
