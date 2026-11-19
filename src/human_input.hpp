#pragma once
#include "input_lifecycle.hpp"
#include "input_routes.hpp"

namespace ss6 {
//Persistent pad -> original recognition -> permission -> request pipeline.
//It leaves animation and entry consumption to the actor dispatcher. Shared
//sampler state belongs to the battle, not to a newly constructed per-frame view.
class HumanInputPipeline {
public:
    explicit HumanInputPipeline(const std::filesystem::path& assets):commands_(assets),bindings_(assets),permissions_(assets),actions_(assets) {}
    const InputBindings& bindings() const {return bindings_;}
    void initialize(ActorCommandInput& input,const InputSystemConfig& config) const {bindings_.initialize(input,&config);}
    ActorInputRoute requests(PermissionActor&,const PermissionActor&,ActorCommandInput&,InputSampler&,const ActorInputSampling&,
        const std::array<NormalizedPadSample,2>&,const std::array<InputMapping,2>&,const InputSystemConfig&,PermissionContext&,const SelectionThreat&,SystemCancelContext&) const;
private:
    CommandInput commands_;
    InputBindings bindings_;
    InputPermissions permissions_;
    ActionSelection actions_;
};
}
