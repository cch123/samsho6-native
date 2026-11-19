#pragma once
#include "input_permissions.hpp"
#include "input_features.hpp"

namespace ss6 {
struct ActorInputSampling {
    unsigned player=0; //Actor+a24; pad swapping does not rewrite this owner.
    bool expectedFacing=false; //Actor+a08, distinct from body+38 bit19.
    int32_t replayIndex=-1; //Actor+2c0.
    int32_t gameMode=0,battleState=0,battleField18=0;
    //1405f0's result is a supplied scheduler boundary until its producer
    //and the AI dispatcher are integrated. It is not a guessed pause flag.
    bool opponentSamplingAllowed=true;
};
enum class ActorInputRoute {HumanVisited,HumanSuppressed,AiSuppressed,AiRequired};
void updateCharacterCharge(PermissionActor&,const ActorCommandInput&,int32_t battleState,int32_t battleField18); //14bcc8
//1495e8..149740 sampling branch, including dynamic bindings and whole179530.
//AiRequired explicitly hands control back to the unported158990/158aa8 path.
ActorInputRoute sampleActorInput(PermissionActor&,const PermissionActor&,ActorCommandInput&,InputSampler&,
    const CommandInput&,const ActorInputSampling&,const std::array<NormalizedPadSample,2>&,const std::array<InputMapping,2>&);
bool inputRequestsLocked(const PermissionActor&); //149740..149768/1497fc
void toggleLockedCharacterMode(PermissionActor&,ActorCommandInput&,InputSampler&,unsigned player); //14bba8
void clearSystemCancelWindow(PermissionActor&,const NormalizedPadSample&,const InputMapping&); //14bdf0
//149790..1497f8 tail, after callbacks. Recording wraps at720 even though
//the sampler stores only600 entries; preserve the original neutral gap.
void finishActorInput(PermissionActor&,ActorInputSampling&,const std::array<NormalizedPadSample,2>&,const std::array<InputMapping,2>&);
}
