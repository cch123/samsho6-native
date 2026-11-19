#include "stage_item_contact.hpp"
#include "battle_round.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include "sound_selection.hpp"
#include "thrown_stage_item.hpp"

namespace ss6 {
namespace {
void queueItemAction(StateEntryActor& actor,int armedAction,uint32_t handler,unsigned table) {
    actor.queuedActionA3c=armedAction+!(actor.flags23c&0x1000);
    actor.flags248&=~0x800u;
    actor.callbacks260[0]=handler;
    actor.callbacks260[1]=table;
    actor.callbacks260[2]=0xffffffffu;
}

int takeItem(BattleRoundState& battle,TaggedTaskPools& pools) {
    int id=battle.stageItems.itemIndex();
    if(id==-1) {
        // 141200 only inspects the first shared kind-5 object. A second
        // bomb cannot bypass an ineligible first one in the same registry.
        for(auto task:battle.objectTasks) {
            if(!task)continue;
            const auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            if(o[0xcc/4]!=5)continue;
            if(o[0x24/4]==76||o[0x24/4]==133)id=8;
            break;
        }
    }
    if(id!=-1)battle.stageItems.clear();
    return id;
}
}

void beginStageItemPickup(PlayerObject&,StateEntryActor& actor) {
    queueItemAction(actor,152,0x16bb88,0);
}

bool updateStageItemPickup(PlayerObject& body,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    auto& battle=*frame.battle;
    const bool ended=actionEnded(body,actor.queuedActionA3c);
    if(actor.callbacks260[0]==0x16bb88) {
        if(!ended)return false;
        // The permission check used the object's position at button press.
        // 141200 reads its identity again after the pickup animation; the
        // other player may already have taken it on this very update.
        const int id=takeItem(battle,context.tasks);
        actor.pickedItemA40=id;
        if(id>=0&&id<=3) {
            constexpr int base[]={-16,-4,-12,-32};
            battle.queueLifeChange(actor,frame.weaponLock->opponent.flags23c,base[id]);
        } else if(id>=4&&id<=6) {
            // 14e838 awards no points in local VS. 14d97c still plays SE 66.
            if(frame.sound)frame.sound->sample(-1,66);
        } else if(id>=7&&id<=18) {
            actor.bodyState128=id;
            queueItemAction(actor,154,0x16c2b0,1);
            return false;
        }
        return true;
    }

    const auto c=body.timeline.clock();
    body.setFlags(c.flags104&~0x100u,c.flags108); // 1699f8 consumes the separate hold marker.
    if(!(c.flags104&0x8000)&&!ended)return false;
    auto& world=*frame.weaponLock;
    throwStageItem(world.objects,context.tasks,world.objectTasks,battle.objectTasks,context.player,
                   actor.bodyState128,actor.flags23c,body);
    actor.callbacks260[0]=0x169a50;
    actor.callbacks260[1]=0;
    actor.callbacks260[2]=0xffffffffu;
    actor.callbacks260[5]=0;
    return false;
}
}
