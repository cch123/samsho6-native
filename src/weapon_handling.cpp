#include "weapon_handling.hpp"
#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
uint32_t AuxiliaryObjects::placeWeapon(TaggedTaskPools& pools,std::span<uint32_t> registry,
        unsigned player,unsigned character,uint32_t& actorFlags,const AuxiliaryObject& parent) {
    if(character>=positions_.size())throw std::runtime_error("Invalid weapon character");
    if(!(actorFlags&0x1000))return 0;
    requireDropCapacity(pools,registry);
    // 16fe20 removes the weapon from the fighter before the child inherits
    // actor flags. Its ACT is queued; the registry commits it later this tick.
    actorFlags&=~0x1000u;
    const auto handle=create(pools,registry,player,actorFlags,parent,0x1390+player,4,0);
    auto& o=pools.objects.at(handle-1);
    request(o,467,false,true);
    const auto dx=ScalarFloat::integer(positions_[character][2]);
    const auto x=ScalarFloat{o[0x40/4]};
    o[0x40/4]=((parent[0x38/4]&0x80000)?x.sub(dx):x.add(dx)).bits;
    o[0x44/4]=ScalarFloat{o[0x44/4]}.add(ScalarFloat::integer(positions_[character][3])).bits;
    o[0x104/4]|=8;
    return handle;
}

void beginWeaponHandling(StateEntryActor& actor) {
    const bool discard=actor.stateIndex()==50;
    actor.queuedActionA3c=discard?135:150+!(actor.flags23c&0x1000);
    actor.flags248&=~0x800u;
    actor.callbacks260[0]=discard?0x16a610:0x169a50;
    actor.callbacks260[1]=0;
    actor.callbacks260[2]=0xffffffffu;
    if(!discard)actor.callbacks260[5]=0;
    // Both actions count as a taunt on entry, including a discard that
    // gets interrupted before its weapon reaches the ground.
    auto& count=actor.characterBytesF22[1];
    if(count<99)++count;
}

void updateWeaponDiscard(PlayerObject& body,StateEntryActor& actor,StateEntryContext& entry,
                         const GroundStateFrame& frame) {
    const auto clock=body.timeline.clock();
    const bool ready=actionEnded(body,actor.queuedActionA3c)||(clock.flags104&0x100);
    body.setFlags(clock.flags104&~0x100u,clock.flags108);
    if(!ready)return;
    if(!frame.weaponLock)throw std::runtime_error("Weapon discard needs the live owner registry");
    frame.weaponLock->objects.placeWeapon(entry.tasks,frame.weaponLock->objectTasks,entry.player,
                                          actor.character,actor.flags23c,body.childParentWords());
    actor.callbacks260[0]=0x169a50;
    actor.callbacks260[1]=0;
    actor.callbacks260[2]=0xffffffffu;
    actor.callbacks260[5]=0;
}
}
