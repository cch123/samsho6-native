#include "ground_throw.hpp"
#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
void registerCallback(StateEntryActor& actor,uint32_t address,unsigned mode) {
    actor.callbacks260[0]=address;
    actor.callbacks260[1]=mode;
    actor.callbacks260[2]=0xffffffff;
}
}
void beginGroundThrow(PlayerObject& body,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    const bool unarmed=!(actor.flags23c&0x1000);
    if(actor.stateTable()==0&&actor.stateIndex()==37) {
        // Simultaneous grab boxes recoil both fighters. 1746fc preserves
        // motion until the first record of ACT236/237 installs the hop.
        actor.queuedActionA3c=236+unarmed;
        actor.flags248&=~0x800u;
        registerCallback(actor,0x174158,0);
        actor.callbacks260[5]=1;
        return;
    }
    stopAtGround(body);
    GroundStateRuntime::captureBody(body,actor);
    if(actor.stateIndex()==26) {
        // 174e60 requests the same startup for both variants. 150620 has
        // already latched the direction in A48, including for a missed grab.
        actor.opponentX=frame.opponentX;
        actor.faceOpponent();
        GroundStateRuntime::restoreBody(body,actor);
        actor.queuedActionA3c=230+unarmed;
        registerCallback(actor,0x169a50,0);
        actor.callbacks260[5]=0;
    } else {
        // 16b3b8 marks the opposing actor on entry. The direction latched at
        // startup still controls playback if the attacker's pad has changed.
        context.opponentFlagsB8|=2;
        if(actor.flags244&0x00800000)actor.queuedActionA3c=599+unarmed;
        else if(actor.variantA48==0||actor.variantA48==1)
            actor.queuedActionA3c=232+2*actor.variantA48+unarmed;
        else throw std::runtime_error("Invalid ordinary throw variant");
        registerCallback(actor,0x16b488,0);
    }
    actor.flags248&=~0x800u;
}
bool isGroundThrowCallback(const StateEntryActor& actor) {
    const auto callback=actor.callbacks260[0];
    return callback==0x16b488||callback==0x16b4d8||callback==0x16b528||
        (callback==0x174158&&actor.stateTable()==0&&actor.stateIndex()==37);
}
bool updateGroundThrow(PlayerObject& body,StateEntryActor& actor,const GroundStateFrame& frame) {
    switch(actor.callbacks260[0]) {
    case 0x174158:
        if(!landingReady(body,actor.queuedActionA3c))return false;
        if(actionEnded(body,actor.queuedActionA3c))return true;
        registerCallback(actor,0x169a50,actor.callbacks260[1]);
        actor.callbacks260[5]=0;
        return false;
    case 0x16b488: {
        const auto c=body.timeline.clock();
        if(actionEnded(body,actor.queuedActionA3c)||(c.flags104&0x100)) {
            // 1699f8 releases the attack's zero-duration ACT hold. Pose
            // changes occur in the *next* callback, after another actor visit.
            body.setFlags(c.flags104&~0x100u,c.flags108);
            registerCallback(actor,0x16b4d8,1);
        }
        return false;
    }
    case 0x16b4d8: {
        if(!frame.weaponLock)throw std::runtime_error("Throw requires a live opponent");
        auto& other=frame.weaponLock->opponent;
        auto& otherBody=frame.weaponLock->opponentBody;
        GroundStateRuntime::captureBody(body,actor);
        StateEntryRules::pose(actor,3);
        GroundStateRuntime::restoreBody(body,actor);
        GroundStateRuntime::captureBody(otherBody,other);
        StateEntryRules::pose(other,18);
        GroundStateRuntime::restoreBody(otherBody,other);
        registerCallback(actor,0x16b528,0);
        return false;
    }
    case 0x16b528:return actionEnded(body,actor.queuedActionA3c);
    default:throw std::runtime_error("Unknown ordinary throw callback");
    }
}
}
