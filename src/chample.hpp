#pragma once
#include "auxiliary_objects.hpp"
#include "game_random.hpp"

namespace ss6 {
struct StateEntryActor;
class StageItemDelivery;
// Everything 1fc750 reads outside the companion object. Stage-item hooks
// are optional: the states that need an unported stage operation throw.
struct ChampleWorld {
    const AuxiliaryObject& body;          // owner body words (+0x00 of the actor)
    const StateEntryActor& owner;
    const AuxiliaryObject& opponentBody;
    const StateEntryActor& opponent;
    GameRandom& random;
    bool ownerWon=false,opponentWon=false; // 14ab80 / 14abb0
    const StageItemDelivery* delivery=nullptr;
    const AuxiliaryObject* battleBomb=nullptr; // first kind-5 battle object (1473b8)
};
// 1a3220 -> 1fc698, including 1a3220's shared companion tail.
uint32_t spawnChample(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                      unsigned player,uint32_t flags,const AuxiliaryObject& body);
// Task handler 0x1fc750 for Mina's kind-3 companion.
void updateChample(AuxiliaryObjects&,AuxiliaryObject&,ChampleWorld&);
// 1fde18: Chample can take a presentation command (intro/win/lose/draw).
bool champleAvailable(const AuxiliaryObject&);
// Presentation commands written by 1a3340/1a3400/1a34c0/1a3580/1a3640.
void commandChamplePresentation(AuxiliaryObject&,uint32_t state);
}
