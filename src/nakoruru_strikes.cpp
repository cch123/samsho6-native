#include "nakoruru_strikes.hpp"
#include "battle_round.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
// 4df178 and 4df1a0 are arrays of 20-byte phase records. The actor keeps
// their identities in +2b8, along with the last entered phase and strength.
constexpr unsigned lowScript=0x4df178,leapScript=0x4df1a0;

void enter(PlayerObject& body,StateEntryActor& actor,const GroundStateFrame& frame,int action) {
    auto& registry=actor.registry28c;
    if(registry[0]==0) {
        actor.opponentX=frame.opponentX;
        actor.faceOpponent();
        GroundStateRuntime::restoreBody(body,actor);
    }
    actor.flags23c&=~0x02000000u;
    actor.flags248&=~0x800u;
    actor.queuedActionA3c=action;
    registry[1]=registry[0];registry[2]=0xffffffff;
    registry[6]=body.timeline.motion().y>0;
    body.scriptLatch134=0;
}

bool approachingEdge(const PlayerObject& body,const GroundStateFrame& frame) {
    const StageCamera* camera=frame.weaponLock?&frame.weaponLock->camera:frame.battle?&frame.battle->camera:nullptr;
    if(!camera)return false;
    // 14aad8(a,34+2,1,0) tests only the facing edge, with the body's X
    // truncated to an integer. A fighter at her own back wall keeps rushing.
    const int x=int(body.timeline.motion().x);
    return body.timeline.clock().objectFlags&0x80000?x<=camera->left+36:x>=camera->right-36;
}
}

bool updateNakoruruStrike(PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input,
                         const GroundStateFrame& frame) {
    const auto state=actor.stateIndex();
    const bool low=state<=66;
    auto& registry=actor.registry28c;
    const unsigned script=low?lowScript:leapScript;
    if(actor.callbacks260[0]==0x1ec2f0) {
        const unsigned strength=actor.stateFlags19a&4?2u:actor.stateFlags19a&2?1u:0u;
        registry[0]=0;registry[3]=strength;registry[11]=script;
        actor.callbacks260[3]=strength;
        enter(body,actor,frame,(low?529:540)+int(strength));
        actor.callbacks260[0]=0x163610;actor.callbacks260[1]=1;actor.callbacks260[2]=0xffffffff;
        return false;
    }
    if(actor.callbacks260[0]!=0x163610||registry[11]!=script||registry[0]>(low?1u:2u))
        throw std::runtime_error("Unexpected Nakoruru dagger phase");

    const auto clock=body.timeline.clock();
    // 163b40 chooses a guard recovery for the low attack. 163be4 makes
    // either move switch to its own brake at the facing edge. A direct hit
    // keeps the current ACT in both scripts (their +6 override is -1).
    const bool interrupt=registry[0]==0&&((low&&(clock.flags104&0x80000))||approachingEdge(body,frame));
    if(!interrupt&&!actionEnded(body,actor.queuedActionA3c)) {
        body.setFlags(clock.flags104&~0x100u,clock.flags108);
        registry[6]=body.timeline.motion().y>0;
        return false;
    }
    if((low&&!interrupt)||(!low&&registry[0]==2)) {
        if(input.sampledFeatures[0xfc/4])actor.flags23c|=8;
        else actor.flags23c&=~8u;
        registry.fill(0);registry[2]=0xffffffff;
        return true;
    }
    ++registry[0];
    const int base=low?532:registry[0]==1?543:546;
    enter(body,actor,frame,base+int(registry[3]));
    return false;
}
}
