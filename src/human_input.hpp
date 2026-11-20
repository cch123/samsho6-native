#pragma once
#include "input_lifecycle.hpp"
#include "input_routes.hpp"
#include "cpu_input.hpp"
#include <functional>

namespace ss6 {
//Persistent pad -> original recognition -> permission -> request pipeline.
//It leaves animation and entry consumption to the actor dispatcher. Shared
//sampler state belongs to the battle, not to a newly constructed per-frame view.
class HumanInputPipeline {
public:
    explicit HumanInputPipeline(const std::filesystem::path& assets):commands_(assets),bindings_(assets),permissions_(assets),actions_(assets) {}
    bool opponentThreat(const SelectionActor& self,const SelectionActor& enemy,const SelectionThreat& context) const {
        return actions_.opponentThreat(self,enemy,context);
    }
    const InputPermissions& permissions() const {return permissions_;}
    uint8_t characterFlags(unsigned id) const {return actions_.characterFlags(id);}
    const InputBindings& bindings() const {return bindings_;}
    void initialize(ActorCommandInput& input,const InputSystemConfig& config) const {bindings_.initialize(input,&config);}
    ActorInputRoute requests(PermissionActor&,const PermissionActor&,ActorCommandInput&,InputSampler&,const ActorInputSampling&,
        const std::array<NormalizedPadSample,2>&,const std::array<InputMapping,2>&,const InputSystemConfig&,PermissionContext&,const SelectionThreat&,SystemCancelContext&,
        const std::function<CpuCommand()>& decideCpu={}) const;
private:
    CommandInput commands_;
    InputBindings bindings_;
    InputPermissions permissions_;
    ActionSelection actions_;
};
}
