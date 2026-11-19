#include "hanzo_capture.hpp"
#include "knockout.hpp"
#include <bit>

namespace ss6 {
namespace {
// The three strengths share the victim's ACTs and waits. The attacker ACT,
// impact damage and an optional entry pose vary by the capture row at 4e2a68.
struct Throw {
    uint32_t address;
    int opening,lift,fall,impact,damage;
};
constexpr Throw throws[]={
    {0x4e2a68,623,-1,629,635,16},{0x4e2acc,625,-1,631,635,22},{0x4e2b30,627,-1,633,635,35},
    {0x4e2b94,-1,648,654,660,9},{0x4e2c84,666,668,670,672,45},{0x4e2ce8,-1,-1,-1,-1,0},
    {0x4e2be4,-1,650,656,660,12},{0x4e2c34,-1,652,658,660,20}
};
struct Phase {
    int victim,attacker,victimWait,attackerWait;
    bool followsAttacker;
};
Phase phase(const Throw& data,int slot,unsigned index) {
    if(data.opening>=0) {
        if(!index)return {slot==4?1315:1313,data.opening,int(slot!=4),int(slot==4),slot!=4};
        --index;
    }
    switch(index) {
    case 0:return {1317,data.lift,0,1,true};
    case 1:return {1319,data.fall,0,3,true};
    case 2:return {1321,data.impact,6,0,false};
    default:return {-1,-1,0,0,false};
    }
}
float offset(float x,float dx) {
    return std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(x)}.add({std::bit_cast<uint32_t>(dx)}).bits);
}
void queue(StateEntryActor& actor,int armed) {
    if(armed<0)return;
    actor.queuedActionA3c=armed+!(actor.flags23c&0x1000);
    actor.flags248&=~0x800u;
}
void latchOffset(StateEntryActor& actor,const ActionRecord& record) {
    if(record.motion.kind<5||record.motion.kind>8)return;
    actor.registry28c[4]=uint32_t(record.motion.values[0])<<16;
    actor.registry28c[5]=uint32_t(record.motion.values[1])<<16;
}
void startImpact(PlayerObject& target,StateEntryContext& context,const GroundStateFrame& frame) {
    auto& world=*frame.weaponLock;
    // 16712c requests ACT637 in the attacker's personal object bank, then
    // places it at the victim. The two bodies usually have different Y here.
    auto emitter=target.childParentWords();
    world.objects.spawnActAttachment(context.tasks,frame.opponentObjectTasks,{},1-context.player,world.opponent.flags23c,
                                     world.opponentBody.childParentWords(),emitter,637,false);
}
}

uint32_t hanzoCaptureAddress(int slot) {
    return slot==16?0x4e2cfc:throws[slot].address;
}

void enterHanzoThrowPhase(PlayerObject& target,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    auto& source=frame.weaponLock->opponent;
    auto& body=frame.weaponLock->opponentBody;
    auto& r=actor.registry28c;
    const int slot=actor.stateIndex()-80;
    const auto& data=throws[slot];
    const auto p=phase(data,slot,r[0]);
    r[1]=r[0];r[7]=r[8]=r[9]=0;
    actor.timers[23]=source.timers[23]=0;
    if(p.victim<0) {
        actor.callbacks260={0x169a50,2,0xffffffffu,r[3],0,5,0};
        source.callbacks260={0x169a50,0,0xffffffffu,0,0,0,0};
        return;
    }
    if(p.victim==1321)frame.captureDamage(data.damage);
    // 166c28 rebases both fighters on every phase, even if the next phase
    // retains the attacker's previous animation. Each split is separately rounded.
    const auto m=body.timeline.motion();
    const float split=(body.timeline.clock().objectFlags&0x80000)?.2f:-.2f;
    body.timeline.setPosition(offset(m.x,split),m.y);
    target.timeline.setPosition(offset(m.x,-split),m.y);target.timeline.stopMotion();r[4]=r[5]=0;
    queue(actor,p.victim);queue(source,p.attacker);
    if(p.followsAttacker)latchOffset(actor,target.actionRecord(actor.queuedActionA3c,0));
    if(p.victim==1321)startImpact(target,context,frame);
    actor.callbacks260[0]=0x165cc0;actor.callbacks260[1]=2;actor.callbacks260[2]=0xffffffff;
}

void advanceHanzoThrowPhase(PlayerObject& target,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    auto& other=*frame.weaponLock;auto& source=other.opponent;auto& body=other.opponentBody;
    auto& r=actor.registry28c;const int slot=actor.stateIndex()-80;
    const auto p=phase(throws[slot],slot,r[0]);
    if(p.followsAttacker) {
        latchOffset(actor,target.timeline.record());
        const auto m=body.timeline.motion();
        const int dx=std::bit_cast<int32_t>(r[4])>>16,dy=std::bit_cast<int32_t>(r[5])>>16;
        target.timeline.setPosition(offset(m.x,(target.timeline.clock().objectFlags&0x80000)?-dx:dx),offset(m.y,dy));
        target.timeline.stopMotion();
    }
    for(auto* fighter:{&target,&body}) {
        const auto c=fighter->timeline.clock();fighter->setFlags(c.flags104|0x2000,c.flags108);
    }
    if(!r[7]) {
        if(p.victimWait==6) {
            ActorTimers timers{actor.timerDelta,actor.timers};
            r[7]=timers.increase(23)>=16*256;
            actor.timers=timers.values;
        } else r[7]=!p.victimWait||actionEnded(target,actor.queuedActionA3c);
    }
    if(!r[8]) {
        if(p.attackerWait==3) {
            r[8]=touchedGround(body,source.queuedActionA3c);
            if(r[8])stopAtGround(body);
        } else r[8]=!p.attackerWait||actionEnded(body,source.queuedActionA3c);
    }
    r[9]=1;
    if(r[7]&&r[8]){++r[0];enterHanzoThrowPhase(target,actor,context,frame);}
    GroundStateRuntime::captureBody(body,source);
}
}

