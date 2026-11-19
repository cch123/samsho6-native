#pragma once
#include "state_entry.hpp"
#include <map>

namespace ss6 {
struct CallbackObject {
    int32_t kindCC=0;
    uint32_t fieldD4=0;
    uint32_t flags108=0;
};
struct CallbackContext {
    //140d78/1473b8 choose the first matching object in registration order.
    //Keep holes and duplicate identities; two registrations can reference
    //the same live object. Mutating a copied snapshot would lose that alias.
    std::array<uint32_t,48> ownObjects{};
    std::map<uint32_t,CallbackObject> objects;
    //A live actor resolves registry TASK handles into the shared pool on
    //every access. The map remains the explicit standalone-test boundary.
    void bindTasks(TaggedTaskPools&,std::span<const uint32_t>);
    void releaseAttackGates(); //140de0, after timer4's OLD value becomes zero
    void setFirstAttackCommand(uint32_t);
private:
    TaggedTaskPools* pools_=nullptr;
    std::span<const uint32_t> taskRegistry_;
};
struct CallbackSystemEffects {
    std::array<uint32_t,2> flags46a918{},phases46a910{};
    uint32_t scale1239d84=256;
    std::array<uint16_t,1024> flags3ebf30{};
};
class StateCallbacks {
public:
    explicit StateCallbacks(const std::filesystem::path& assets);
    static uint32_t registerNormal(StateEntryActor&); //172d68
    static void registerAlias(StateEntryActor&); //14cc10
    uint32_t registerAttack(StateEntryActor&,const InputSystemConfig&,CallbackContext&) const; //172eb0
    //173108 resource00/system0 common damage. Weapon-drop and active
    //system termination for other characters/systems have separate owners.
    static uint32_t registerOrdinaryDamage(StateEntryActor&,const InputSystemConfig&);
    void addRage(StateEntryActor&,const InputSystemConfig&,int32_t amount) const; //14efb8
    void addTenChainRage(StateEntryActor&,const InputSystemConfig&) const;
    static bool damageDropsWeapon(const StateEntryActor&,unsigned sourceCharacter,int32_t damageIndex); //1732b0
    static bool hasSystemEffect(const InputSystemConfig&); //14eb78
    static void endSystemEffect(StateEntryActor&,const InputSystemConfig&,CallbackSystemEffects&,unsigned player); //11e548
private:
    StateEntryRules entries_;
    InputBindings bindings_;
    std::array<uint32_t,51> attackHandlers_;
    std::array<std::array<uint8_t,128>,51> specialParameters_;
    std::array<std::array<int32_t,7>,51> characters_;
    std::array<std::array<int32_t,10>,9> systems_;
    std::array<ScalarFloat,2> rageConstants_;
};
}
