#include "knockout.hpp"
#include <stdexcept>

namespace ss6 {
bool actionEnded(const PlayerObject& object,int32_t queuedAction) {
    const auto& c=object.timeline.clock();
    return c.endReached&&!(c.flags104&1)&&queuedAction==-1;
}
bool touchedGround(const PlayerObject& object,int32_t queuedAction) {
    const auto c=object.timeline.clock();const auto& m=object.timeline.motion();
    const bool ended=actionEnded(object,queuedAction);
    // 0x1737d8 accepts the ground sentinel independently of completion.
    // Y==0 alone is insufficient while vertical motion is still active.
    return (c.endControl&0x100)||m.y<0||
        ((ended||(c.flags104&0x100))&&m.y==0&&m.vy==0&&m.ay==0);
}
bool landingReady(PlayerObject& object,int32_t queuedAction) {
    if(!touchedGround(object,queuedAction))return false;
    const auto c=object.timeline.clock();
    const bool ended=actionEnded(object,queuedAction);
    //173970 calls1699f8 once the ground predicate succeeds. That helper
    //releases100 even on an unfinished hold; its return uses the OLD bit.
    object.setFlags(c.flags104&~uint32_t(0x100),c.flags108);
    return ended||(c.flags104&0x100);
}
void stopAtGround(PlayerObject& object) {
    object.timeline.stopMotion();
    const auto& m=object.timeline.motion();
    if (m.y<0) object.timeline.setPosition(m.x,0);
}
void KnockoutPlayback::begin(PlayerObject& object,uint32_t& actorFlags,unsigned variant,int32_t* actorAction) {
    if (variant>2) throw std::runtime_error("Invalid ordinary KO variant");
    // 0x400000 (Amakusa) and 0x800000 (riding Rera) are remapped by the caller's 14d788 pass (GroundStateRuntime::visit).
    if (actorFlags&0x100000) throw std::runtime_error("Special-character KO action remapping not implemented");
    const bool airborne=actorFlags&0x10;
    if (airborne) variant=2;
    // 0x172b38 uses pose28 on the ground (stop and clamp), pose29 in the
    // air (retain motion/height). Both preserve the armed and KO flags.
    actorFlags=(actorFlags&~uint32_t(1|2|8|0x200|0x400|0x800))|4;
    if (!airborne) {
        object.timeline.stopMotion();
        object.timeline.setPosition(object.timeline.motion().x,0);
    }
    constexpr unsigned actions[]={400,402,382}; // ELF table 0x4e8cf8
    object.pendingFlags|=1;
    const unsigned action=actions[variant]+!(actorFlags&0x1000);
    if(actorAction)*actorAction=int32_t(action);
    else object.request(action);
    phase=KnockoutPhase::FirstLanding;
}
bool KnockoutPlayback::update(PlayerObject& object) {
    if (phase==KnockoutPhase::Inactive) return false;
    const auto c=object.timeline.clock();
    // 0x168aa0 runs before each table2 callback, even during a landing hold.
    object.setFlags(c.flags104|0x2000,c.flags108);
    if (phase==KnockoutPhase::FirstLanding||phase==KnockoutPhase::SecondLanding) {
        if (!landingReady(object)) return false;
        stopAtGround(object);
        const bool dust=phase==KnockoutPhase::FirstLanding;
        phase=dust ? KnockoutPhase::SecondLanding : KnockoutPhase::Finishing;
        return dust;
    }
    if (phase==KnockoutPhase::Finishing&&actionEnded(object)) {
        object.timeline.stopMotion();
        phase=KnockoutPhase::Complete; // 0x172cb0 installs 0x169a50 case7.
    } else if (phase==KnockoutPhase::Complete&&actionEnded(object)) {
        const auto flags=object.timeline.clock();
        object.setFlags(flags.flags104&~uint32_t(0x100),flags.flags108);
    }
    return false;
}
}
