#pragma once
#include <cstdint>
#include <span>
#include "auxiliary_objects.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
// Rera's (character 19) wolf Shikuru: 1f95e8 (1a3220 at 1a32dc), task 1f96a0 "_update_skru"
// with the state entry 1f9938 (663d9c), follow distance 1f9808 and update 1f9cf8 (663e1c).
struct ReraWolfWorld {
    const AuxiliaryObject& body;          // owner body words
    const StateEntryActor& owner;
    const AuxiliaryObject& opponentBody;  // 1400a8(owner seat)
    bool ownerWon=false,opponentWon=false; // 14ab80 / 14abb0
};
uint32_t spawnReraWolf(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                       unsigned player,uint32_t flags,const AuxiliaryObject& body);
void updateReraWolf(AuxiliaryObjects&,AuxiliaryObject&,const ReraWolfWorld&);
// 1fa138: the wolf is airborne (or riding) and unavailable; clears 104:100 otherwise.
bool reraWolfBusy(AuxiliaryObject&);
// 1fa1d8: the wolf is idle (< 12), on the ground and within 80 of its follow point.
bool reraWolfNear(AuxiliaryObject&,const AuxiliaryObject& ownerBody);
}
