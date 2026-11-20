#pragma once
#include "input_bindings.hpp"
#include <functional>
#include "auxiliary_objects.hpp"
#include "stage_camera.hpp"

namespace ss6 {
struct StateEntryActor;
struct ScriptRow;
// 0x4e4b38 + 12*id (163430). See docs/projectile-engine.txt section 10.
struct ProjectileDescriptor {
    uint8_t group=0,flags=0;
    int16_t start=-1,hit=-1,block=-1,expire=-1;
};
class ProjectileTable {
public:
    explicit ProjectileTable(const std::filesystem::path& assets);
    const ProjectileDescriptor& at(unsigned id) const {return descriptors_.at(id);}
    // 16de88: which 0 start, 1 hit, 2 block, 3 expire. Only the start ACT
    // receives the variant, and only when descriptor flag 1 is set.
    int action(unsigned id,unsigned which,unsigned variant) const;
private:
    std::array<ProjectileDescriptor,190> descriptors_{};
};
// Everything the generic projectile code reads or writes about its owner seat.
struct ProjectileOwner {
    AuxiliaryObjects& objects;
    TaggedTaskPools& pools;
    std::span<uint32_t> registry;      // the owner's 48-slot registry
    unsigned player;
    StateEntryActor& actor;
    const AuxiliaryObject& body;        // childParentWords, +110/+114 = ACT attachment offset
    const AuxiliaryObject& opponentBody;
    const StageCamera& camera;
    GameRandom& random;
    AuxiliaryObject* companion=nullptr; // Mina's Chample (group 17)
    // 1491e0 on the owner inside the object's task (group 8 catch).
    std::function<void()> enterStateNow;
    // The opponent's actor and spirit (142120 for group 15).
    const StateEntryActor* opponentActor=nullptr;
    const InputSystemConfig* opponentConfig=nullptr;
};
// 16d9c8 for a running move script (mode-0 rows; Mina). Returns the object.
uint32_t spawnScriptProjectile(const ProjectileTable&,ProjectileOwner&,const ScriptRow&);
// 16d2b0 + 16d400 tail. Groups 0, 1, 13, 14 and 17 are admitted.
uint32_t spawnDescriptorProjectile(const ProjectileTable&,ProjectileOwner&,unsigned id,unsigned variant);
bool isDescriptorProjectileTask(uint32_t handler);
// 16def0 and the group callbacks 16cac0 (14) and 16c818/16c8d0/16c940 (17).
void updateDescriptorProjectile(const ProjectileTable&,ProjectileOwner&,uint32_t task);
}
