#pragma once
#include "judgment.hpp"
#include <array>

namespace ss6 {
struct JudgmentFields {
    uint32_t type, group, variant, remainder, bit18, middle11, low7;
};
JudgmentFields decodeJudgment(uint32_t metadata);

// Snapshot of a resource-00 body or projectile. owner is object +0x10, the
// team used for friendly-fire rejection. It is separate from the world slot.
struct CollisionPlayer {
    uint32_t owner=0, objectFlags104=0, objectFlags108=0, actorFlags=0x1000;
    int16_t stateTable=0, stateIndex=0;
    uint8_t stateFlags=0;
    int32_t field1c8=0;
    float x=0, y=0;
    bool mirrorX=false, mirrorY=false;
    uint16_t judgmentFlags=0;
    std::vector<Judgment> judgments;
    uint32_t objectKind=0, judgmentProfile=0;
    int32_t objectTypeD0=-1;
    uint8_t descriptorFlagsA=0; // 0x163430(objectTypeD0)->byte[0xa]
};
class CollisionTables {
public:
    explicit CollisionTables(const std::filesystem::path& assets);
    bool usesAttackDamage(unsigned type,unsigned profile=0) const; // second byte of the JDG class row at 14da48
    uint8_t captureIndex(unsigned type,unsigned profile) const {return classByte(type,profile,1);}
    uint8_t classFor(uint32_t rawType,unsigned profile=0) const;
    uint8_t route(uint8_t a, uint8_t b) const;
private:
    uint8_t classByte(unsigned type,unsigned profile,unsigned offset) const;
    std::array<uint8_t,460> bytes_{};
    std::array<std::array<uint8_t,64>,3> characterClasses_{};
};
struct ContactSide {
    uint16_t judgmentFlags;
    JudgmentFields fields;
    uint8_t category, player;
    uint32_t judgmentIndex;
};
struct ContactEvent {
    uint32_t route;
    int32_t centerX, centerY, extra, auxiliary, width;
    ContactSide a, b;
};
// Collect candidates only. No damage, hitstop, guard, hit sound, or consumed
// bits may be produced here: the original does those in later dispatchers.
void collectContacts(const CollisionTables& tables, const CollisionPlayer& a,
                     const CollisionPlayer& b, uint8_t aSlot, uint8_t bSlot,
                     std::vector<ContactEvent>& queue);
void orderContacts(std::vector<ContactEvent>& queue);
} // namespace ss6
