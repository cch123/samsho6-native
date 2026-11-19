#include "dash_motion.hpp"
#include "actor_state.hpp"
#include "fighter_roster.hpp"
#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
constexpr uint32_t runStart = 0x169f98, runHeld = 0x169ff8, runBrake = 0x16a098;
constexpr uint32_t backstepFlight = 0x16a1e8, recoverOnEnd = 0x169a50;

void registerDashCallback(StateEntryActor& actor,uint32_t routine) {
    // 1522a0 only writes these three words. A phase switch must preserve
    // the callback parameters that its successor reads.
    actor.callbacks260[0]=routine;
    actor.callbacks260[1]=0;
    actor.callbacks260[2]=0xffffffff;
}

int32_t decrease(StateEntryActor& actor,unsigned index) {
    ActorTimers timers{actor.timerDelta,actor.timers};
    const auto previous=timers.decrease(index);
    actor.timers[index]=timers.values[index];
    return previous;
}
}

void beginDash(PlayerObject& body,StateEntryActor& actor) {
    if(!playableFighter(actor.character) || actor.stateTable()!=0)
        throw std::runtime_error("Unexpected fighter or state for dash callback");

    if(actor.stateIndex()==24) {
        stopAtGround(body);
        actor.queuedActionA3c=36+!(actor.flags23c&0x1000);
        registerDashCallback(actor,backstepFlight);
    } else if(actor.stateIndex()==23) {
        // Characters 00–03 have bit 4 clear in the 168bf8 movement table. Their
        // run loops action28 while the callback handles release independently.
        actor.queuedActionA3c=28+!(actor.flags23c&0x1000);
        actor.flags244|=0x10000;
        ActorTimers timers{actor.timerDelta,actor.timers};
        timers.set(8,14);
        timers.set(11,8);
        timers.set(12,8);
        timers.set(27,12);
        actor.timers=timers.values;
        registerDashCallback(actor,runStart);
    } else throw std::runtime_error("Expected forward run or backstep");
}

bool isDashCallback(const StateEntryActor& actor) {
    const auto handler=actor.callbacks260[0];
    return handler==runStart || handler==runHeld || handler==runBrake || handler==backstepFlight ||
        (handler==recoverOnEnd && actor.state194==(24u<<16) && actor.callbacks260[5]==1);
}

bool updateDash(PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input) {
    const auto& features=input.sampledFeatures;
    const bool down=features[0xfc/4]!=0;
    switch(actor.callbacks260[0]) {
    case runStart:
        if(decrease(actor,11)==0) registerDashCallback(actor,runHeld);
        return false;
    case runHeld: {
        const bool mirror=(body.timeline.clock().objectFlags&0x80000)!=0;
        const bool forward=features[(mirror?0x15c:0x14c)/4]!=0;
        const bool back=features[(mirror?0x14c:0x15c)/4]!=0;
        const auto grace=decrease(actor,12);
        // 16a0f0 uses world-direction feature cells after diagonal
        // resolution. Forward takes precedence over back/down or expiry.
        if(!forward && (down || back || grace==0)) {
            actor.flags244&=~0x10000u;
            // 169ff8 clears and rereads this bit before selecting 32/34;
            // the ordinary callback therefore always queues armed action34.
            actor.queuedActionA3c=34+!(actor.flags23c&0x1000);
            registerDashCallback(actor,runBrake);
        }
        return false;
    }
    case runBrake: {
        auto motion=body.timeline.motion();
        if(motion.vx<0) {
            motion.vx=0;
            body.timeline.setMotion(motion);
        }
        if(!actionEnded(body,actor.queuedActionA3c)) return false;
        break;
    }
    case backstepFlight:
        if(landingReady(body,actor.queuedActionA3c)) {
            stopAtGround(body);
            registerDashCallback(actor,recoverOnEnd);
            actor.callbacks260[5]=1;
        }
        return false;
    case recoverOnEnd: {
        // 1699f8 releases an intermediate held record even when the clip
        // has not ended. Only 149488's completed result queues a new state.
        const auto clock=body.timeline.clock();
        body.setFlags(clock.flags104&~0x100u,clock.flags108);
        if(!actionEnded(body,actor.queuedActionA3c)) return false;
        actor.request18c=1;
        break;
    }
    default: throw std::runtime_error("Unexpected dash callback");
    }
    if(down) actor.flags23c|=8;
    else actor.flags23c&=~8u;
    return true;
}
}
