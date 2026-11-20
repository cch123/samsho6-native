#pragma once
#include <array>
#include <cstdint>
#include <functional>
#include <span>
#include "auxiliary_objects.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
// Chamcham's (character 34) kind-3 companion. Original 203e08 (created by 1a3220 at 1a331c),
// task 203ec0 with the mode entry 2041d0 (66444c) and update 204618 (6644d8).
struct ChamchamPetWorld {
    const AuxiliaryObject& body;           // owner body words
    const StateEntryActor& owner;
    bool ownerWon=false,opponentWon=false;  // 14ab80 / 14abb0
    // 16d2b0(owner cb, id, 0) for modes 16/17 (descriptors 0x7c / 0x7d); returns the object.
    std::function<AuxiliaryObject*(unsigned)> spawnDescriptor;
};
uint32_t spawnChamchamPet(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                          unsigned player,uint32_t flags,const AuxiliaryObject& body);
void updateChamchamPet(AuxiliaryObjects&,AuxiliaryObject&,const ChamchamPetWorld&);
}
