#include "nakoruru_riding.hpp"
#include "nakoruru_eagle_attack.hpp"
#include "knockout.hpp"
#include <algorithm>
#include <bit>

namespace ss6 {
namespace {
void setHandler(StateEntryActor& actor,uint32_t callback,unsigned active=1) {
    actor.callbacks260[0]=callback;actor.callbacks260[1]=active;
    actor.callbacks260[2]=0xffffffff;
}
void queuePose(StateEntryActor& actor,int action) {
    actor.queuedActionA3c=action;
    actor.flags248&=~0x800u;
}

using F=ScalarFloat;
F constant(float value){return {std::bit_cast<uint32_t>(value)};}

// The horizontal/vertical dead zones are measured using the low word of
// MULT, even when the signed square overflows. EE SQRT works on its magnitude.
bool inDeadZone(int32_t v,F limit) {
    const int32_t square=std::bit_cast<int32_t>(uint32_t(v)*uint32_t(v));
    F magnitude=F::integer(square);magnitude.bits&=0x7fffffff;
    return !limit.less(magnitude.sqrt());
}
void fly(PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input,float opponentX) {
    actor.opponentX=opponentX;
    const bool turned=actor.faceOpponent(true);
    if(turned)GroundStateRuntime::restoreBody(body,actor);
    auto m=body.timeline.motion();
    if(turned){m.vx=-m.vx;m.ax=-m.ax;}
    const auto& keys=input.sampledFeatures;
    const F acceleration=constant(2621.44f);
    if(keys[62])m.ax=F::integer(m.ax).add(acceleration).truncate();
    else if(keys[64])m.ax=F::integer(m.ax).sub(acceleration).truncate();
    else {
        m.ax=0;m.vx=F::integer(m.vx).mul(constant(.9f)).truncate();
        if(inDeadZone(m.vx,acceleration))m.vx=0;
    }
    if(keys[65])m.ay=F::integer(m.ay).add(acceleration).truncate();
    else if(keys[63])m.ay=F::integer(m.ay).sub(acceleration).truncate();
    else {
        m.ay=0;m.vy=F::integer(m.vy).mul(constant(.8f)).truncate();
        if(inDeadZone(m.vy,constant(36864)))m.vy=-36864;
    }
    m.vx=std::clamp(m.vx,-229376,229376);m.vy=std::clamp(m.vy,-229376,229376);
    // 1ec9cc/1ec9ec clear velocity only. A held direction keeps its acceleration.
    if(m.y>512){m.y=512;m.vy=0;}
    if(m.y<32){m.y=32;m.vy=0;}
    body.timeline.setMotion(m);
}
}

namespace {
struct RidePhase {
    int action;
    unsigned end; // Terminal predicate at 5f0d6c, indexed by byte 4 of the source row.
    unsigned flags;
    unsigned command;
};
struct RideScript {uint32_t address;std::array<RidePhase,3> phases;};
constexpr std::array<RideScript,5> scripts{{
    {0x4df268,{{{624,0,0,3},{627,4,0,255},{629,0,1,255}}}},
    {0x4df2a4,{{{625,0,0,3},{628,4,0,255},{630,0,1,255}}}},
    {0x4df2e0,{{{626,4,0,3},{631,0,1,255},{}}}},
    {0x4df204,{{{637,4,5,255},{},{}}}},
    {0x4df218,{{{655,4,2,12},{658,0,3,255},{}}}}
}};
void enterRidePhase(PlayerObject& body,StateEntryActor& actor,AuxiliaryObject& bird,const RidePhase& phase) {
    auto& r=actor.registry28c;
    actor.flags23c&=~0x02000000u;
    if(phase.command==12) {
        // 164d58 sends the eagle itself. A separate strike from this body
        // would lose the eagle's strength, movement and contact ownership.
        bird[0x128/4]=6;bird[0x130/4]=actor.callbacks260[3];
    }
    int action=phase.action;
    if(phase.flags&4)action+=2*int(r[3])+!(actor.flags23c&0x1000);
    if(phase.flags&2)action+=int(r[3]);
    queuePose(actor,action);
    r[1]=r[0];r[2]=0xffffffff;r[6]=body.timeline.motion().y>0;body.scriptLatch134=0;
}
bool mountedSpecial(PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input,AuxiliaryObject& bird) {
    const int state=actor.stateIndex();
    const auto& script=scripts[state<=82?state-80:state<=85?3:4];
    auto& r=actor.registry28c;
    if(actor.callbacks260[0]==0x1ec2f0) {
        r[0]=0;r[1]=r[2]=0xffffffff;r[3]=(actor.stateFlags19a&4)?2u:unsigned(bool(actor.stateFlags19a&2));
        r[11]=script.address;actor.callbacks260[3]=r[3];
        enterRidePhase(body,actor,bird,script.phases[0]);setHandler(actor,0x163610);
        return false;
    }
    const auto& phase=script.phases.at(r[0]);
    if(phase.command==3)body.setFlags(body.timeline.clock().flags104|0x2000u,body.timeline.clock().flags108);
    const bool finished=phase.end==4?touchedGround(body,actor.queuedActionA3c):actionEnded(body,actor.queuedActionA3c);
    if(!finished) {
        const auto c=body.timeline.clock();body.setFlags(c.flags104&~0x100u,c.flags108);
        r[6]=body.timeline.motion().y>0;
        return false;
    }
    if(phase.end==4)stopAtGround(body);
    if(!(phase.flags&1)) {
        ++r[0];enterRidePhase(body,actor,bird,script.phases.at(r[0]));
        return false;
    }
    if(input.sampledFeatures[63])actor.flags23c|=8;else actor.flags23c&=~8u;
    r.fill(0);r[2]=0xffffffff;
    return true;
}
}

void beginNakoruruDismount(StateEntryActor& a) {
    const int direction=a.stateIndex()-32;
    a.jumpDirectionA44=direction;queuePose(a,596+2*direction+!(a.flags23c&0x1000));
    setHandler(a,0x173b18,0);
}

bool isNakoruruRidingCallback(const StateEntryActor& a) {
    if(a.character!=1)return false;
    const auto h=a.callbacks260[0];
    if(h==0x1ec2f0||h==0x163610)return a.stateTable()==1&&a.stateIndex()>=80&&a.stateIndex()<=89;
    return h==0x1ecd20||h==0x1ecd90||h==0x1ec728||h==0x1ec848||h==0x1ecb10;
}

bool updateNakoruruRiding(PlayerObject& body,StateEntryActor& a,const ActorCommandInput& input,
                          StateEntryContext& context,const GroundStateFrame& frame) {
    const int bare=!(a.flags23c&0x1000);
    const auto h=a.callbacks260[0];
    if((h==0x1ec2f0||h==0x163610)&&a.stateIndex()>=80&&a.stateIndex()<=88)
        return mountedSpecial(body,a,input,context.tasks.objects.at(a.auxiliaryObject04-1));
    if(h==0x1ec2f0&&a.stateIndex()==89) {
        a.opponentX=frame.opponentX;a.faceOpponent();GroundStateRuntime::restoreBody(body,a);
        queuePose(a,578);a.flags23c|=0x01000000;setHandler(a,0x1ecd20);
    } else if(h==0x1ecd20) {
        const auto& bird=context.tasks.objects.at(a.auxiliaryObject04-1);
        if(approachNakoruruEagle(body,bird)) {
            stopAtGround(body);queuePose(a,579+bare);setHandler(a,0x1ecd90);
        }
    } else if(h==0x1ecd90) {
        if(actionEnded(body,a.queuedActionA3c)) {
            body.timeline.stopMotion();queuePose(a,581+bare);setHandler(a,0,0);
            // 1ecdf0 resets the main state and metadata. The alias channel
            // commits on the next 149d44 visit, allowing damage to preempt it.
            a.request18c=0;a.pendingTable=a.pendingIndex=-1;a.state194=0xffffffff;
            a.stateCharacter198=0;a.stateFlags19a=0;
            a.flags23c|=0x200000;a.aliasPendingTable=a.aliasPendingIndex=0;a.timers[23]=0;
        }
    } else if(h==0x1ec728) {
        body.timeline.stopMotion();
        if(int16_t(a.state1a4)==0){queuePose(a,581+bare);a.callbacks260[0]=0x1ec848;}
        else {queuePose(a,588+int16_t(a.state1a4>>16));a.callbacks260[0]=0x1ecb10;}
    } else if(h==0x1ec848) {
        fly(body,a,input,frame.opponentX);
    } else if(h==0x1ecb10) {
        if(actionEnded(body,a.queuedActionA3c))a.aliasPendingTable=a.aliasPendingIndex=0;
    } else throw UnportedFighterState(a.character,1,a.stateIndex());
    return false;
}
}
