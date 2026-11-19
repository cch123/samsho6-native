#pragma once
#include "ground_state.hpp"
#include "actor_history.hpp"
#include "auxiliary_objects.hpp"
#include "damage.hpp"

namespace ss6 {
struct RoundActorStorage {
    //The original registry holds TASK handles. CallbackContext's object
    //identities must be resolved through these tasks, not copied here.
    std::array<uint32_t,48> objectTasks{};
    std::array<uint32_t,3> afterimageObjects{};
    ActorHistory history;
};
void resetActorControl(StateEntryActor&,GameRandom&); //1588c0
class RoundInitialization {
public:
    explicit RoundInitialization(const std::filesystem::path& assets,std::array<unsigned,3> slots={})
        :meters_(assets),objects_(assets,slots) {}
    //149008, ordinary resource00/system0 with default player options.
    //Uses the caller's persistent actor/input/pools/RNG. Does not initialize
    //the input sampler, clear recording, or commit the queued body action.
    void begin(GroundStateRuntime&,PlayerObject&,StateEntryActor&,ActorCommandInput&,
        const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&,RoundActorStorage&,bool first);
private:
    DamageTables meters_;
    AuxiliaryObjects objects_;
};
}
