#pragma once
#include "actor_state.hpp"
#include "motion.hpp"
#include "player_object.hpp"
#include <array>
#include <filesystem>

namespace ss6 {
struct ReactionDescriptor {
    uint16_t flags;
    int16_t horizontalVelocity,horizontalAcceleration;
    uint16_t firstTimer,secondTimer;
    std::array<uint8_t,4> extra;
};
struct ReactionTarget : ActorContactHistory {
    uint32_t flags23c=0x1000;
    uint32_t flags244=0;
    uint8_t flags24c=0;
    int16_t stateTable=0;
    int16_t pendingTable=-1,pendingState=-1;
    bool forceState=false;
};
struct LightReaction {
    unsigned state,secondary,action;
};
//Type2 prefix168aa0 and170890: retain the damage clip's terminal record,
//release callback-owned holds, then report the ordinary recovery request.
bool updateGroundReaction(PlayerObject& object);
// 156038/156538 select the character's victim script for a body/child hit.
bool applyCapturedHit(ReactionTarget&,unsigned rawType);
class ReactionTables {
public:
    explicit ReactionTables(const std::filesystem::path& assets);
    ReactionDescriptor descriptor(unsigned state) const;
    // Ordinary resource00 light attack (raw type10), grounded target. Caller
    // supplies the special-hit predicate from 0x157fa8; it is not inferred
    // from damage amount. Airborne/downed/heavy/special-object paths reject.
    LightReaction applyLightHit(ReactionTarget& target,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                                unsigned bodyPart,bool special,bool sourceAirborne=false) const;
    LightReaction applyGroundHit(ReactionTarget&,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                                unsigned rawType,unsigned bodyPart,bool special,bool sourceAirborne,
                                unsigned sourceStrength,uint32_t& sourceFlags248,bool sourceSpecialMove=false) const;
    unsigned ordinaryAction(unsigned state,bool armed,bool onBack=false) const;
    // 0x14d5a0: standing, crouching, perfect and airborne guard for ordinary
    // sources. A set no-reaction flag leaves the current guard state alone.
    bool applyGuard(ReactionTarget& target,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                    unsigned defense,unsigned strength,unsigned& action) const;
    // 0x151728 installs retreat in local facing coordinates. The original ORs
    // direction bits; their lifetime is owned by the state-entry reset.
    void startRetreat(unsigned state,MotionState& motion,uint32_t& flags108,int opponentAuxiliary) const;
private:
    std::array<uint8_t,2048> data_{};
};
} // namespace ss6
