#include "throw_victim.hpp"
#include "combat_decision.hpp"
#include "knockout.hpp"
#include "state_entry.hpp"

namespace ss6 {
namespace {
constexpr uint32_t mirrorX=0x80000;

void queueVictimAction(StateEntryActor& actor,int armedAction) {
    actor.queuedActionA3c=armedAction+!(actor.flags23c&0x1000);
    actor.flags248&=~0x800u;
}
void victimCallback(StateEntryActor& actor,uint32_t callback) {
    actor.callbacks260[0]=callback;
    actor.callbacks260[1]=2;
    actor.callbacks260[2]=0xffffffff;
}

float catchPosition(float x,bool mirrored,bool back) {
    // 155330 uses fixed stage edges (14ae18/14ae30 called with character
    // zero). It nudges the old coordinate, rather than snapping to the edge.
    if(back) {
        if(!mirrored) {
            if(x<54)return x+20;
            if(x>566)return x-40;
        } else {
            if(x>586)return x-20;
            if(x<74)return x+40;
        }
    } else {
        if(!mirrored && x>520)return x-20;
        if(mirrored && x<120)return x+20;
    }
    return x;
}
}

void catchGroundThrow(PlayerObject& thrower,StateEntryActor& source,ContactMarks& sourceMarks,
                      PlayerObject& victim,StateEntryActor& target,ContactMarks& targetMarks) {
    const bool back=source.variantA48==1;
    const auto sourceClock=thrower.timeline.clock(),targetClock=victim.timeline.clock();
    const bool mirrored=(sourceClock.objectFlags&mirrorX)!=0;
    source.flags244&=~0x800000u;
    source.pendingTable=1;source.pendingIndex=31;source.request18c=1;
    target.pendingTable=2;target.pendingIndex=13;target.request18c=1;
    target.variantA48=source.variantA48;
    sourceMarks.consumed|=4;
    const auto motion=thrower.timeline.motion();
    const float x=catchPosition(motion.x,mirrored,back);
    thrower.timeline.setPosition(x,motion.y);
    victim.timeline.setPosition(x,motion.y);
    thrower.timeline.stopMotion();victim.timeline.stopMotion();
    sourceMarks.flags104&=~0x140u;targetMarks.flags104&=~0x140u;
    // The victim faces opposite the original thrower first. A back throw
    // flips the thrower afterwards, so both face the same way during capture.
    thrower.timeline.setObjectFlags(sourceClock.objectFlags^(back?mirrorX:0),sourceMarks.flags104,sourceMarks.flags108);
    victim.timeline.setObjectFlags((targetClock.objectFlags&~mirrorX)|(mirrored?0:mirrorX),
                                    targetMarks.flags104,targetMarks.flags108);
}

void breakGroundThrows(StateEntryActor& first,StateEntryActor& second) {
    // 1556a8 queues both normal37s through 14ff80 without forcing 18c.
    // 142580 owns publication after the queue has finished dispatching.
    for(auto* actor:{&first,&second}) {
        actor->pendingTable=0;actor->pendingIndex=37;
        actor->flags248|=0x01000000u;
    }
}

void beginThrowVictim(PlayerObject& victim,StateEntryActor& target,const PlayerObject& thrower) {
    const auto clock=victim.timeline.clock();
    victim.setFlags(clock.flags104,clock.flags108&~0x200u);
    const auto& m=thrower.timeline.motion();
    victim.timeline.setPosition(m.x,m.y);
    stopAtGround(victim);
    if(target.variantA48==0)queueVictimAction(target,404);
    if(target.variantA48==1)queueVictimAction(target,406);
    victimCallback(target,0x171090);
}

void updateThrowVictim(PlayerObject& victim,StateEntryActor& target,PlayerObject& thrower) {
    if(!actionEnded(victim,target.queuedActionA3c))return;
    if(target.variantA48==0)queueVictimAction(target,408);
    if(target.variantA48==1) {
        // 171104 separates the anchors by one unit each only when the first
        // victim clip completes. Applying the offset upon capture shifts the
        // entire grab and permits follow-ups at the wrong distance.
        const float offset=(thrower.timeline.clock().objectFlags&mirrorX)?-1.0f:1.0f;
        const auto v=victim.timeline.motion(),s=thrower.timeline.motion();
        victim.timeline.setPosition(v.x+offset,v.y);
        thrower.timeline.setPosition(s.x-offset,s.y);
        queueVictimAction(target,410);
    }
    victimCallback(target,0x169a50);
    target.callbacks260[5]=0;
}
}
