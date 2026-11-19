#include "ending_playback.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
void queueBody(PlayerObject& object,unsigned action,bool force,int32_t* actorAction) {
    if(actorAction) {
        *actorAction=int32_t(action);
        //1493c0's forced path marks the old body immediately, before the
        //actor queue reaches149918. Round history observes this boundary.
        if(force)object.markActorActionPending();
    }
    else object.request(action,force);
}
}
void EndingPlayback::beginIntroduction(PlayerObject& object,uint32_t& gates,unsigned player,int32_t* actorAction,bool sameCharacter) {
    // 14dfdc mutes the second copy of the same introduction. The
    // original voice-collision check returns zero delay for 00 versus 01.
    queueBody(object,492,true,actorAction);gates&=~uint32_t(0x40000000);phase=EndingPhase::Playing;
    if(player==1&&sameCharacter){const auto c=object.timeline.clock();object.setFlags(c.flags104|0x200,c.flags108);}
}
void EndingPlayback::deferIntroduction(PlayerObject& object,ActorTimers& timers,int ticks) {
    if(ticks<=0)return;
    const auto c=object.timeline.clock();object.setFlags(c.flags104|0x300,c.flags108);
    object.pendingFlags|=6;timers.set(34,ticks); //14be28
}
void EndingPlayback::releaseIntroduction(PlayerObject& object,ActorTimers& timers) {
    //Release the intro's gates without stopping motion or requesting idle.
    //The caller decides whether this is a timed replay or a round transition.
    const auto c=object.timeline.clock();object.setFlags(c.flags104&~uint32_t(0x330),c.flags108);
    object.pendingFlags&=~uint16_t(6);timers.clear(34);
}
void EndingPlayback::beginLoser(PlayerObject& object,uint32_t posture,uint32_t& gates,int32_t* actorAction) {
    // 14e178 force-restarts the corpse clip. Its terminal ACT jump is later
    // suppressed by the callback prefix, so it cannot animate into get-up.
    gates&=~uint32_t(0x40000000);
    object.pendingFlags|=1;
    queueBody(object,((gates&0x8000) ? 50 : 48)+!(posture&0x1000),false,actorAction);
    phase=EndingPhase::Playing;
}
void EndingPlayback::beginWinner(PlayerObject& object,uint32_t posture,uint32_t& gates,int life,bool final,int32_t* actorAction) {
    // 14e000 ->14ab70 uses inclusive life100, not the usual low-life idle
    // threshold49.14ab80 selects the separate match-winning pair.
    queueBody(object,(life>=100 ? 495 : 497)+(final?4:0)+!(posture&0x1000),false,actorAction);
    gates&=~uint32_t(0x40000000);
    phase=EndingPhase::Playing;
}
void EndingPlayback::update(PlayerObject& object,uint32_t& gates,ActorTimers* timers,unsigned player,int32_t* actorAction,bool companionReady) {
    if(phase==EndingPhase::Inactive)return;
    const auto c=object.timeline.clock();
    uint32_t flags=c.flags104|0x2000; //168a68 type0 prefix;168aa0 has the same operation.
    if(timers&&timers->values[34]>0) {
        if(player>1)throw std::runtime_error("Introduction player outside0/1");
        timers->decrease(34);
        if(timers->values[34]>0)object.setFlags(flags|0x130,c.flags108);
        else {
            //14e320 tests the NEW timer value, unlike the round timer gate.
            //14bea0 releases animation/motion holds before restarting492.
            object.setFlags(flags,c.flags108);releaseIntroduction(object,*timers);
            object.timeline.setPosition(player?400:240,0);queueBody(object,492,true,actorAction);
        }
        return;
    }
    //1699f8 clears100 even when the action is not yet complete.492 has
    // a zero-duration record that must resume on the next animation pass.
    flags&=~uint32_t(0x100);
    if(actionEnded(object,actorAction?*actorAction:-1)&&companionReady) {
        if(phase==EndingPhase::Playing) {
            // 14e320 waits for both the ending pose and the owner's companion.
            // The latter signals completion independently on its task visit.
            gates|=0x40000000;
            flags&=~uint32_t(0x200);
            phase=EndingPhase::Holding;
        }
        // Subsequent169a50 case4 keeps normal41 while alive, and damage15
        // while KO: its KO restart is restricted to current table0/1.
    }
    object.setFlags(flags,c.flags108);
}
}
