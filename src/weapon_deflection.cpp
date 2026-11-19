#include "weapon_deflection.hpp"
#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
void face(PlayerObject& o,StateEntryActor& a,float opponentX,bool force=false) {
    GroundStateRuntime::captureBody(o,a);
    a.opponentX=opponentX;
    a.faceOpponent(force);
    GroundStateRuntime::restoreBody(o,a);
}
void callback(StateEntryActor& a,uint32_t handler,unsigned type) {
    a.callbacks260[0]=handler;a.callbacks260[1]=type;a.callbacks260[2]=0xffffffff;
}
void queueAction(StateEntryActor& a,int action) {
    a.queuedActionA3c=action;
    a.flags248&=~0x800u;
}
void request(StateEntryActor& a,int table,int state) {
    a.pendingTable=int16_t(table);a.pendingIndex=int16_t(state);a.request18c=1;
}
void countParry(StateEntryActor& a) {
    auto& count=a.characterBytesF22[4];
    if(count<99)++count;
}
}

bool resolveWeaponDeflection(const ContactEvent& event,PlayerObject& attackerBody,StateEntryActor& attacker,
                             PlayerObject& defenderBody,StateEntryActor& defender) {
    if(attacker.flags23c&0x20||attackerBody.timeline.clock().flags108&8)return false;
    const int variant=defender.variantA48;
    attacker.variantA48=variant;
    face(attackerBody,attacker,defenderBody.timeline.motion().x,true);
    face(defenderBody,defender,attackerBody.timeline.motion().x,true);
    if(variant==3) {
        countParry(attacker);
        // 14d108 gives the combined slash its own disarming recoil. Other
        // blades select one of three reels from the contact's +0c field.
        const bool combined=attacker.state194==0x150001;
        if(combined)attacker.flags23c|=0x80000;
        else attacker.flags23c&=~0x80000u;
        const int state=combined||event.extra==2?12:event.extra==1?11:10;
        request(attacker,2,state);
    } else if(variant==4) {
        // The barehand catch temporarily overlays the fighters. The weapon
        // is dropped later at a specific ACT hold, not on this contact.
        request(defender,1,29);
        const auto& target=defenderBody.timeline.motion();
        attackerBody.timeline.setPosition(target.x,target.y);
        request(attacker,2,14);
    } else throw std::runtime_error("Unexpected weapon deflection variant");
    return true;
}

void beginWeaponDeflection(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& frame) {
    const int index=a.stateIndex();
    if(index!=29)face(o,a,frame.opponentX);
    stopAtGround(o);
    queueAction(a,index==23?126:index==24?131:132);
    callback(a,0x169a50,1);a.callbacks260[5]=0;
    if(index!=29)a.variantA48=index==23?3:4;
}

void beginDeflectedWeapon(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& frame) {
    const int index=a.stateIndex();
    const auto c=o.timeline.clock();o.setFlags(c.flags104,c.flags108&~0x200u);
    if(index==14) {
        a.timers[2]=60*256;a.flags244&=~0x8000u;
        stopAtGround(o);
        queueAction(a,133);callback(a,0x171208,2);
        return;
    }
    face(o,a,frame.opponentX);stopAtGround(o);
    if(a.flags23c&0x80000) {
        queueAction(a,130);callback(a,0x1713c0,2);
    } else {
        queueAction(a,127+index-10);callback(a,0x169a50,2);a.callbacks260[5]=0;
    }
    countParry(frame.weaponLock->opponent);
}

void updateDeflectedWeapon(PlayerObject& o,StateEntryActor& a,StateEntryContext& entry,const GroundStateFrame& frame) {
    const auto c=o.timeline.clock();
    const bool complete=actionEnded(o,a.queuedActionA3c);
    const bool hold=c.flags104&0x100;
    o.setFlags(c.flags104&~0x100u,c.flags108);
    if(a.callbacks260[0]==0x171268) {
        // 171268 releases the hold but waits for the whole catch animation
        // before queuing the subsequent fall. The two continue separately.
        if(complete) {
            queueAction(a,134);callback(a,0x169a50,2);a.callbacks260[5]=5;
        }
        return;
    }
    if(!(complete||hold))return;
    auto& lock=*frame.weaponLock;
    lock.objects.dropAfterLock(entry.tasks,lock.objectTasks,*frame.random,entry.player,
                               a.character,a.flags23c,o.childParentWords());
    if(a.callbacks260[0]==0x171208)callback(a,0x171268,2);
    else {callback(a,0x169a50,2);a.callbacks260[5]=0;}
}
}
