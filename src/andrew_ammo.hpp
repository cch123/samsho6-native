#pragma once
#include <cstdint>
#include <span>

namespace ss6 {
class AuxiliaryObjects;
struct TaggedTaskPools;
struct StateEntryActor;
class PlayerObject;
// Andrew's (character 30) ammunition counter: actor byte f1c is the stock,
// f1d the count shown; each icon is a kind-6 own object with ACT 0x23e.
// 16ea00 (via 16ec08): delete the old icons, then lay out one per stock.
void showAndrewAmmo(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                    StateEntryActor& owner,const PlayerObject& ownerBody);
// 16ec48: an icon above the shown count disappears; when its own timer runs
// out it also disappears unless the owner is in an attack (table 1).
void updateAndrewAmmo(TaggedTaskPools&,uint32_t task,const StateEntryActor& owner);
}
