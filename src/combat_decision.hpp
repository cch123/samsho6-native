#pragma once
#include "collision.hpp"
#include <optional>

namespace ss6 {
// Inputs to original 0x155850. Raw names preserve the boundary between a
// proven branch condition and its still-unported input/state producer.
struct DefenseSnapshot {
    uint32_t actorFlags23c=0x1000, actorFlags244=0;
    int16_t stateTable=0, stateIndex=0;
    uint8_t stateFlags=0;
    int32_t fieldA20=0, fieldC8=0, field3C0=0, field39C=0, field398=0;
    int32_t system=0;
    // System 6's descriptor is selected by 0x14f4e0/0x152758. The caller
    // supplies its byte +0xc, including dynamically configured descriptors.
    std::optional<uint8_t> system6DescriptorByteC;
};
uint8_t selectDefense(const CollisionPlayer& source,const DefenseSnapshot& target);

struct ContactMarks {
    uint32_t objectKind=0, flags104=0, flags108=0;
    uint8_t consumed=0;
};
enum class ProjectileContact { None, StrikePlayer, ClashProjectiles, ReflectProjectile, Route1Player, Route4Player };
ProjectileContact projectileContact(const ContactEvent& event,const CollisionPlayer& source,
                                    const CollisionPlayer& target,const ContactMarks& sourceMarks);
// Each ordered contact marks its target. Only the first direction can start
// the two freezes and emit the shared spark/sound, since it pauses both objects.
bool markProjectileClash(ContactMarks& target,uint8_t sourcePause,uint8_t targetPause);

bool contactConsumed(const ContactMarks& object,int index);
void markContactConsumed(ContactMarks& object,int index);

class ContactRegistry {
public:
    // 0x153440 resets only the list. Per-object consumed bits are cleared on
    // first registration, not again if the object is submitted twice.
    void reset() { objects_.clear(); }
    bool add(uint32_t identity,uint32_t character,uint32_t action,ContactMarks& object);
    const std::vector<uint32_t>& objects() const { return objects_; }
private:
    std::vector<uint32_t> objects_;
};

class CombatTables {
public:
    explicit CombatTables(const std::filesystem::path& assets);
    std::array<int,2> consumptionIndices(unsigned route) const;
private:
    std::array<int32_t,24> indices_{};
};
// Reports the next original branch, without committing incomplete damage,
// reaction, gauge, effect or consumption changes to a live actor.
enum class DecisionKind { OtherRoute, AlreadyConsumed, SourceBlocked, HitBranch, GuardBranch };
struct ContactDecision { DecisionKind kind; uint8_t defense=0; };
ContactDecision inspectContactDecision(const CombatTables& tables,const ContactEvent& event,
                                      const CollisionPlayer& source,const DefenseSnapshot& target,
                                      const ContactMarks& sourceMarks,const ContactMarks& targetMarks);
} // namespace ss6
