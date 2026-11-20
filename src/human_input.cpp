#include "human_input.hpp"

namespace ss6 {
ActorInputRoute HumanInputPipeline::requests(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,
        InputSampler& sampler,const ActorInputSampling& frame,const std::array<NormalizedPadSample,2>& pads,
        const std::array<InputMapping,2>& maps,const InputSystemConfig& config,PermissionContext& permissions,const SelectionThreat& threat,SystemCancelContext& cancel,
        const std::function<CpuCommand()>& decideCpu) const {
    const auto route=sampleActorInput(a,opponent,input,sampler,commands_,frame,pads,maps);
    if(route==ActorInputRoute::AiRequired) {
        if(!decideCpu)return route;
        // 1498b0 rejoins at 149740. Hitstop, permissions, and state requests
        // see the CPU's published words on the very same actor visit.
        const auto command=decideCpu();
        publishCpuCommand(command,(a.bodyFlags38&0x80000)!=0,input);
    }
    //Suppressed sampling is not a suppressed request visit: the original
    //dispatch can observe previously published features in this case.
    if(inputRequestsLocked(a))requestLockedInput(a,opponent,input,sampler,frame.player,frame.battleState,config,actions_,threat);
    else {
        cancel.pad=pads.at(frame.player);cancel.mapping=maps.at(frame.player);
        processRecognizedInput(a,opponent,input,config,bindings_,permissions_,actions_,permissions,threat,cancel);
    }
    return route==ActorInputRoute::AiRequired?ActorInputRoute::AiVisited:route;
}
}
