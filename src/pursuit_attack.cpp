#include "pursuit_attack.hpp"
#include "knockout.hpp"
#include <algorithm>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr unsigned launch=0x16b5b8,descending=0x16b6b8,landing=0x16b7d8,landed=0x16b8c8;
void phase(StateEntryActor& actor,unsigned next) {
    actor.callbacks260[0]=next;
    actor.callbacks260[1]=(next==0x169a50)?0:1;
    actor.callbacks260[2]=0xffffffffu;
    if(next==0x169a50)actor.callbacks260[5]=0;
}
bool releaseHold(PlayerObject& body,int queuedAction) {
    auto clock=body.timeline.clock();
    body.setFlags(clock.flags104&~0x100u,clock.flags108);
    return (clock.flags104&0x100)||actionEnded(body,queuedAction);
}
}
void updatePursuitVictim(PlayerObject& body,StateEntryActor& actor) {
    // 1709d8 renews the three-tick throw protection each visit in the
    // default versus rules (43d05e == 0), including the last hurt frame.
    ActorTimers timers{actor.timerDelta,actor.timers};
    timers.set(6,3);
    actor.timers[6]=timers.values[6];
    if(!actionEnded(body,actor.queuedActionA3c))return;
    const bool knockedOut=actor.flags23c&0x80;
    if(knockedOut)actor.callbacks260[5]=7;
    else {
        actor.queuedActionA3c=((actor.flags244&0x8000)?58:56)+!(actor.flags23c&0x1000);
        actor.flags248&=~0x800u;
    }
    actor.callbacks260[0]=knockedOut?0x169a50:0x170758;
    actor.callbacks260[1]=2;actor.callbacks260[2]=0xffffffffu;
}
void beginPursuitAttack(StateEntryActor& actor) {
    actor.queuedActionA3c=(actor.flags23c&0x1000)?225:226;
    actor.flags248&=~0x800u;
    phase(actor,launch);
}
bool updatePursuitAttack(PlayerObject& body,StateEntryActor& actor,float opponentX) {
    const auto handler=actor.callbacks260[0];
    auto motion=body.timeline.motion();
    if(handler==launch) {
        // 16b5b8 aims 16 units short of the opponent. Only the maximum
        // travel is clamped; an overlapping target can send the hop backward.
        const bool mirrored=body.timeline.clock().objectFlags&0x80000;
        const float target=opponentX+(mirrored?16.0f:-16.0f);
        const float distance=mirrored?motion.x-target:target-motion.x;
        motion.vx=int32_t(std::min(distance,64.0f)*65536.0f*0.03125f);
        motion.ax=0;motion.vy=0x96000;motion.ay=-0x9600;
        body.timeline.setMotion(motion);
        phase(actor,descending);
    } else if(handler==landed) {
        if(releaseHold(body,actor.queuedActionA3c)) {
            stopAtGround(body);
            phase(actor,0x169a50);
        }
    } else {
        if(handler==descending) {
            // ACT225/226 holds the descending pose until the fighter falls
            // below height 64. Landing has a second, independent ACT hold.
            if(motion.vy<0&&motion.y<64.0f&&releaseHold(body,actor.queuedActionA3c)) {
                phase(actor,landing);
                return false;
            }
        } else if(handler==landing) {
            if(landingReady(body,actor.queuedActionA3c)) {
                stopAtGround(body);
                phase(actor,landed);
                return false;
            }
        } else throw std::runtime_error("Unknown pursuit attack callback");
        if(actionEnded(body,actor.queuedActionA3c))return true;
        const bool stopped=motion.vy==0&&motion.ay==0;
        if(handler==descending?(motion.y<=0||stopped):(motion.y>0&&stopped))
            phase(actor,0x169a50);
    }
    return false;
}
}
