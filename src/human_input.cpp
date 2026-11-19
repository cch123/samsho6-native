#include "human_input.hpp"

namespace ss6 {
ActorInputRoute HumanInputPipeline::requests(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,
        InputSampler& sampler,const ActorInputSampling& frame,const std::array<NormalizedPadSample,2>& pads,
        const std::array<InputMapping,2>& maps,const InputSystemConfig& config,PermissionContext& permissions,const SelectionThreat& threat,SystemCancelContext& cancel) const {
    const auto route=sampleActorInput(a,opponent,input,sampler,commands_,frame,pads,maps);
    if(route==ActorInputRoute::AiRequired)return route;
    //Suppressed sampling is not a suppressed request visit: the original
    //dispatch can observe previously published features in this case.
    if(inputRequestsLocked(a))requestLockedInput(a,opponent,input,sampler,frame.player,frame.battleState,config,actions_,threat);
    else {
        cancel.pad=pads.at(frame.player);cancel.mapping=maps.at(frame.player);
        processRecognizedInput(a,opponent,input,config,bindings_,permissions_,actions_,permissions,threat,cancel);
    }
    return route;
}
}
