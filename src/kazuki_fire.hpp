#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>
#include "auxiliary_objects.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
// angle_trig.bin: the original 10b4b8 (cosine) and 10b4f8 (sine) for every 16-bit unit.
class AngleTrig {
public:
    explicit AngleTrig(const std::filesystem::path& assets);
    uint32_t cosine(uint32_t unit) const {return table_.at(2*(unit&0xffff));}
    uint32_t sine(uint32_t unit) const {return table_.at(2*(unit&0xffff)+1);}
private:
    std::vector<uint32_t> table_;
};
// Kazuki's (character 16) fire: created by 1f7258, task 1f7318 (1f76a0 once launched).
struct KazukiFireWorld {
    const AuxiliaryObject& body;            // owner body words
    StateEntryActor& owner;                 // f15 (fire level) is cleared when a launch ends
    const AuxiliaryObject& opponentBody;
    bool opponentHoldsOwner=false;          // 14ac90: opponent is 33 with body ACT 0x240/0x241
    bool opponentConcentrating=false;       // 142120(owner seat)
    const AngleTrig& trig;
};
uint32_t spawnKazukiFire(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                         uint32_t flags,const AuxiliaryObject& body,unsigned level);
void updateKazukiFire(AuxiliaryObjects&,AuxiliaryObject&,const KazukiFireWorld&);
}
