#pragma once
#include <cstdint>
#include <span>
#include <array>
#include "auxiliary_objects.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
struct StageCamera;
struct ActorCommandInput;
// Galford's (character 4) kind-3 companion Poppy. Original task 1efe78 with the
// state entry table 1f0138 (663994) and the update table 1f07b8 (663a78).
struct PoppyWorld {
    const AuxiliaryObject& body;          // owner body words
    const StateEntryActor& owner;
    const ActorCommandInput* ownerInput;  // state 10 reads the owner's held buttons 0x5b..0x60
    const AuxiliaryObject& opponentBody;  // 1efc98: 1400a8(o.10) lands beside the owner's opponent
    const StageCamera& camera;            // 140040
    std::span<uint32_t> ownerRegistry;    // 16c408(owner) for the 0x317 effect
    unsigned ownerSeat=0;
    bool ownerWon=false,opponentWon=false; // 14ab80 / 14abb0
};
uint32_t spawnPoppy(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                    unsigned player,uint32_t flags,const AuxiliaryObject& body); // 1efdc0 + 1a3220 tail
void updatePoppy(AuxiliaryObjects&,TaggedTaskPools&,AuxiliaryObject&,const PoppyWorld&); // 1efe78
// 1efc98: drop an object from y 300 beside the opponent (Galford's dives and Poppy 31/38).
void dropBesideOpponent(AuxiliaryObject& o,const AuxiliaryObject& opponentBody,int variant);
// Presentation commands written by 1a3340/1a3400/1a34c0/1a3580/1a3640 (0x2e..0x32).
inline void commandPoppy(AuxiliaryObject& o,uint32_t state){o[0x108/4]&=~0x100000u;o[0x128/4]=state;}
}
