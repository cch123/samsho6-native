#include "jump_motion.hpp"
#include "fighter_roster.hpp"
#include "knockout.hpp"
#include "state_entry.hpp"
#include "stage_camera.hpp"
#include <array>
#include <stdexcept>

namespace ss6 {
namespace {
struct JumpActions {int ascending,descending;};
// Original 4e9878/4e9888 store each armed action; its unarmed pair follows it.
constexpr std::array<JumpActions,4> jumpActions{{{14,16},{18,20},{22,24},{40,20}}};

void setCallback(StateEntryActor& actor,uint32_t handler,uint32_t type=0) {
    // 1522a0 overwrites only these three registration words.
    actor.callbacks260[0]=handler;
    actor.callbacks260[1]=type;
    actor.callbacks260[2]=0xffffffff;
}

void queueAction(StateEntryActor& actor,int action) {
    actor.queuedActionA3c=action;
    actor.flags248&=~0x800u; // 1493c0 clears the previous action's special-sound flag.
}

void requestLanding(StateEntryActor& actor) {
    actor.pendingTable=0;
    actor.pendingIndex=22;
}

}

bool jumpReachedGround(const PlayerObject& object,int pendingAction) {
    // 1737d8 checks the ACT ground sentinel before the animation end. It
    // doesn't release a zero-duration hold as the knockdown helper 173970 does.
    const auto& clock=object.timeline.clock();
    const auto& motion=object.timeline.motion();
    return (clock.endControl&0x100)||motion.y<0||
        ((actionEnded(object,pendingAction)||(clock.flags104&0x100))&&
         motion.y==0&&motion.vy==0&&motion.ay==0);
}

void beginJump(PlayerObject& object,StateEntryActor& actor) {
    if(!playableFighter(actor.character))throw std::runtime_error("Unknown fighter jump movement flags");
    const int state=actor.stateIndex();
    const int unarmed=!(actor.flags23c&0x1000);
    if(state==17) {
        const auto clock=object.timeline.clock();
        object.setFlags(clock.flags104|0x20,clock.flags108);
        queueAction(actor,38+unarmed);
        setCallback(actor,0x173bb8);
        return;
    }
    if(state==18 && actor.jumpDirectionA44==5) {
        queueAction(actor,42+unarmed);
        setCallback(actor,0x173b18);
        return;
    }
    if(state==22) {
        queueAction(actor,26+unarmed);
        setCallback(actor,0x169a50);
        actor.callbacks260[5]=0;
        return;
    }
    actor.jumpDirectionA44=state==18?3:state-19;
    const auto& actions=jumpActions.at(actor.jumpDirectionA44);
    stopAtGround(object);
    queueAction(actor,actions.ascending+unarmed);
    setCallback(actor,0x173a68);
}

void updateJump(PlayerObject& object,StateEntryActor& actor,const ActorCommandInput& input,const StageCamera* camera,uint8_t movementFlags) {
    if(!playableFighter(actor.character))throw std::runtime_error("Unknown fighter jump movement flags");
    if(actor.callbacks260[0]==0x173bb8) {
        if(actionEnded(object,actor.queuedActionA3c)){actor.pendingTable=0;actor.pendingIndex=18;}
        else updateAirLanding(object,actor);
        return;
    }
    if(actor.callbacks260[0]==0x173a68&&object.timeline.motion().vy<=0) {
        // The falling clip retains current velocity. 173a68 sets FE8 before
        // requesting it; the subsequent body commit maps that bit to 104:40.
        object.pendingFlags|=8;
        const auto& actions=jumpActions.at(actor.jumpDirectionA44);
        queueAction(actor,actions.descending+!(actor.flags23c&0x1000));
        setCallback(actor,0x173b18);
        return;
    }
    // 173558 reads the world-direction pad edges while the body is moving
    // near a camera edge. The low two bits of 4e5420 independently allow
    // high and low rebounds; Hanzo has both even though his 3+B stays grounded.
    const unsigned wallFlags=movementFlags&3;
    const auto& m=object.timeline.motion();
    if(wallFlags&&camera&&m.y>=48&&m.vx&&!(actor.flags244&0x20)&&!(actor.flags23c&0x800000)) {
        const auto x=static_cast<int>(m.x);
        if(x<=camera->left+36||x>=camera->right-36) {
            const auto clock=object.timeline.clock();
            const bool mirror=clock.objectFlags&0x80000;
            const bool movingRight=(m.vx>0)!=mirror;
            const auto& pad=input.sampledFeatures;
            const bool high=(wallFlags&1)&&pad[movingRight?0x58:0x5a];
            const bool low=(wallFlags&2)&&pad[movingRight?0x56:0x54];
            const int direction=high?3:low?5:0;
            if(direction) {
                const auto flags=movingRight?clock.objectFlags|0x80000u:clock.objectFlags&~0x80000u;
                object.timeline.setObjectFlags(flags,clock.flags104,clock.flags108);
                actor.jumpDirectionA44=direction;actor.flags244|=0x20;
                actor.pendingTable=0;actor.pendingIndex=17;
                return;
            }
        }
    }
    updateAirLanding(object,actor);
}

bool isJumpAttack(int state) {
    return state==2||state==3||state==6||state==7||state==10||state==11||state==16;
}

void beginAirGuard(PlayerObject& object,StateEntryActor& actor) {
    const int unarmed=!(actor.flags23c&0x1000);
    switch(actor.stateIndex()) {
    case 8:
        // 1733b8 saves the original jump direction on the body. The
        // character's direction remains 6 until landing, even after timeout.
        object.scriptLatch134=uint32_t(actor.jumpDirectionA44);
        actor.jumpDirectionA44=6;
        actor.timers[9]=8*256;
        queueAction(actor,308+unarmed);
        setCallback(actor,0x173438);
        break;
    case 16: {
        constexpr int falling[]={16,20,24,20};
        const auto direction=object.scriptLatch134;
        queueAction(actor,falling[direction<4?direction:0]+unarmed);
        setCallback(actor,0x173b18);
        break;
    }
    case 38: // 173ee8, backward fall after a successful air guard.
        queueAction(actor,24+unarmed);
        setCallback(actor,0x173b18);
        break;
    default:throw std::logic_error("Unknown air guard entry");
    }
}

void updateAirGuard(PlayerObject& object,StateEntryActor& actor) {
    if(actor.callbacks260[0]==0x170b60 && actionEnded(object,actor.queuedActionA3c)) {
        actor.pendingTable=0;actor.pendingIndex=38;
        return;
    }
    if(jumpReachedGround(object,actor.queuedActionA3c)) {
        updateAirLanding(object,actor);
        return;
    }
    if(actor.callbacks260[0]==0x173438) {
        // 14d010 returns the counter before subtraction; its zero visit is
        // the first one on which an unstruck guard can resume its jump.
        ActorTimers timer{actor.timerDelta,actor.timers};
        if(!timer.decrease(9)){actor.pendingTable=0;actor.pendingIndex=16;}
        actor.timers[9]=timer.values[9];
    }
}

void beginAirBlockReaction(PlayerObject& object,StateEntryActor& actor) {
    // 170ac8 replaces both axes on contact, independent of the old jump
    // direction or height. ACT 308 retains this velocity through FE:8.
    actor.jumpDirectionA44=7;
    object.timeline.stopMotion();
    auto motion=object.timeline.motion();
    motion.vx=-0xcccc;motion.vy=0x66666;motion.ay=-0x10000;
    object.timeline.setMotion(motion);
    object.pendingFlags|=8;
    queueAction(actor,308+!(actor.flags23c&0x1000));
    setCallback(actor,0x170b60,2);
    if(actor.characterBytesF22[8]<99)++actor.characterBytesF22[8];
}

void beginAirHurt(PlayerObject&,StateEntryActor& actor) {
    // 1708d8 uses the explosion's second table row for state75. Both rows
    // let the new ACT set the launch even when the target was already falling.
    const bool explosion=actor.stateIndex()==75;
    queueAction(actor,(explosion?412:378)+!(actor.flags23c&0x1000));
    setCallback(actor,0x173880,2);
    actor.callbacks260[3]=0;actor.callbacks260[6]=unsigned(explosion);
}

bool updateAirLanding(PlayerObject& object,StateEntryActor& actor) {
    if(!jumpReachedGround(object,actor.queuedActionA3c))return false;
    actor.pendingTable=0;
    actor.pendingIndex=actor.jumpDirectionA44==6 ? 44 : 22;
    return true;
}

void beginRecoveryRoll(PlayerObject& object,StateEntryActor& actor) {
    const bool back=actor.stateIndex()==55;
    queueAction(actor,(back?76:70)+!(actor.flags23c&0x1000));
    // Both recoveries start on the ground, even if the old airborne ACT
    // still had a positive height when the landing callback queued the roll.
    object.timeline.stopMotion();
    object.timeline.setPosition(object.timeline.motion().x,0);
    actor.timers[6]=back?0:3*256;
    actor.timers[25]=15*256;
    setCallback(actor,0x169a50);
    actor.callbacks260[5]=0;
}

void beginJumpAttack(PlayerObject& object,StateEntryActor& actor) {
    const int state=actor.stateIndex();
    const bool armed=actor.flags23c&0x1000;
    if(!isJumpAttack(state)||!playableFighter(actor.character))
        throw std::runtime_error("Unexpected airborne attack");
    int action=0,landingParameter=0;
    if(state==16) {
        // The air kick (16aec8) refuses an already grounded entry.
        if(object.timeline.motion().y<=0){requestLanding(actor);return;}
        action=armed?217:218;
    } else {
        const int strength=state/4;
        action=armed ? 209+strength+3*(state&1) : (strength?216:215);
        landingParameter=armed ? 1+strength*2 : 0;
    }
    object.pendingFlags|=8;
    queueAction(actor,action);
    actor.callbacks260[4]=landingParameter;
    setCallback(actor,0x16afd8,1);
}

bool updateJumpAttack(PlayerObject& object,StateEntryActor& actor) {
    const bool grounded=object.timeline.motion().y<=0;
    switch(actor.callbacks260[0]) {
    case 0x16afd8:
        actor.flags23c&=~0x4000u;
        if(grounded)requestLanding(actor);
        else setCallback(actor,0x16b050,1);
        break;
    case 0x16b050: {
        // Record zero of each airborne attack is a callback-controlled hold.
        // The first follow-up registers this handler; only its next visit
        // releases 104:100. Early release advances every active hitbox.
        const auto clock=object.timeline.clock();
        object.setFlags(clock.flags104&~0x100u,clock.flags108);
        if(grounded){stopAtGround(object);setCallback(actor,0x16b0c0,1);}
        break;
    }
    case 0x16b0c0:
        if(actor.flags23c&0x4000)return true;
        requestLanding(actor);
        break;
    default:throw std::runtime_error("Unknown airborne attack callback");
    }
    return false;
}
}
