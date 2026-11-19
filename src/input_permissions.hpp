#pragma once
#include "action_selection.hpp"
#include "scalar_float.hpp"
#include "actor_state.hpp"
#include <span>

namespace ss6 {
struct PermissionActor : SelectionActor,ActorContactHistory {
    uint8_t stateFlags19a=0,aliasFlags1aa=0;
    uint32_t bodyFlags108=0,bodyState128=0,bodyLatch12c=0,auxiliaryAction24=0,auxiliaryState12c=0;
    uint32_t sampledButton9=0; //Actor+2e8, feature9 at input owner+24.
    std::array<int32_t,35> timers{};
    int32_t timerDelta=256;
    std::array<uint8_t,14> characterBytesF14{};
    int32_t rageState120=0,rageAmount124=0,systemState13c=0,systemMeter158=0,fieldA30=0;
    float y=0;
    int32_t velocityX50=0,velocityY5c=0;
    int32_t offsetX4c=0,accelerationX54=0,offsetY58=0,accelerationY60=0;
    uint32_t controlFlagsB4=0,aliasRequest19c=0;
    int16_t aliasPendingTable=-1,aliasPendingIndex=-1;
    uint32_t auxiliaryFlags104=0;
    uint32_t auxiliaryTimer130=0,auxiliaryFrameC0=0;
    int32_t auxiliaryPendingC4=-1;
    float auxiliaryX=0,auxiliaryY=0;
    uint8_t effectiveFlags() const {return flags23c&0x200000?aliasFlags1aa:stateFlags19a;}
};
struct PermissionObject {
    int32_t kind=0,subtype=0,action=0;
    uint32_t flags108=0;
    float x=0;
};
struct PermissionContext {
    //Keep registration order and holes: several conditions inspect only the
    //first matching object, not any matching object with a suitable action.
    std::array<std::optional<PermissionObject>,48> ownObjects{};
    std::array<std::optional<PermissionObject>,64> battleObjects{};
    int32_t mode4c3808=0,stageObjectIndex=-1;
    float stageObjectX=0;
    //Original condition74 prints a diagnostic before saving bodyState128.
    //Expose that event without introducing PS2 libc into the native runtime.
    unsigned condition74Diagnostics=0;
};
class InputPermissions {
public:
    explicit InputPermissions(const std::filesystem::path& assets);
    bool condition(unsigned id,PermissionActor&,const PermissionActor& opponent,const InputSystemConfig&,PermissionContext&) const;
    int characterFrontRange(unsigned character) const {return targetRanges_.at(character)[2];} // 168cb8(1)
    static bool objectAvailable(unsigned key,const PermissionContext&);
    static bool actorAllowed(const PermissionActor&); //179e38
    bool category(unsigned id,const PermissionActor&) const; //179e68
    bool requirement(unsigned id,PermissionActor&) const; //17a150
    bool cancelAllowed(unsigned record,PermissionActor&,int specialStart,const InputBindings&) const; //179968
    //Whole14a1b8: snapshot gates, filter normal then special commands, then
    //publish cancel permissions. This does not consume any command buffer.
    void apply(PermissionActor&,const PermissionActor&,const InputSystemConfig&,PermissionContext&,ActorCommandInput&,const InputBindings&) const;
    //14af48's caller supplies13 category words and9 requirements. Filtering
    //clears only recognized results; partial motions/buffers stay intact.
    void filter(PermissionActor&,const PermissionActor&,const InputSystemConfig&,PermissionContext&,
                std::span<CommandSlot>,std::span<const InputBindingRecord>,
                const std::array<uint32_t,13>& categories,const std::array<uint32_t,9>& requirements) const;
private:
    std::array<std::array<int16_t,4>,51> airRectangles_,targetRanges_;
    std::array<std::array<int16_t,18>,51> attackRanges_;
    std::array<std::array<uint32_t,10>,9> systems_;
    std::array<uint32_t,5> limits_;
    std::array<uint32_t,13> gateLimits_;
    std::array<uint32_t,96> cancelConditions_;
    bool auxiliaryReady(PermissionActor&) const;
};
}
