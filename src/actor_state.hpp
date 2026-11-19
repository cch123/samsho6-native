#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
//Actor250..25f is one persistent contact history, shared by contact
//selection and state callbacks. Ordinary entry clears it; consecutive
//hurt entries retain it for alternation and the repeated-heavy decision.
struct ActorContactHistory {
    uint8_t field250=0,field251=0,contactKind252=0,landingCount253=0;
    uint8_t pendingCharacter254=0,previousReaction=255,secondaryReaction=0,field257=0;
    uint32_t heavyReaction=0,extraReaction25c=0;
    void clearContacts() {*this=ActorContactHistory{};} //152220
};
struct ActorTimerInput {
    uint32_t mainState=0;
    int effectiveTable=0;
    bool airborne=false,backD8=false,back100=false;
};
// Actor+0x1ac, initialized by 0x14cf48. Stored values are 8-bit fractional
// timers; callers choose which counters to advance, not a blanket tick-all.
struct ActorTimers {
    int32_t delta=256;
    std::array<int32_t,35> values{};
    void resetRound();
    void set(unsigned index,int32_t ticks);
    void clear(unsigned index);
    int32_t decrease(unsigned index);
    int32_t increase(unsigned index);
    int32_t advanceContactTimers();
    //151eb0. True requests140de0's clear of108:200000 on every registered
    //own object; the caller must apply it to live identities, not snapshots.
    bool advanceActor(const ActorTimerInput&);
};

struct LifeState {
    int32_t life=200, maximum=200, pendingDamage=0, queuedAction=-1;
    uint32_t flags23c=0x1000;
    uint32_t conditions=0; // Actor+0x160, condition bitset's first word.
    float y=0;
};
struct RoundActorFlags {
    uint32_t flags23c=0x1000,flags240=0,flags244=0,flags248=0;
    uint8_t flags24c=0;
    //14fe10 preserves selected cross-round bits, not the whole old posture.
    void resetRound();
};
// 151968 commits the net signed change. The battle presents a food recovery
// before this call when healing exceeds damage received on the same tick.
void commitLife(LifeState& actor,ActorTimers& timers,bool training=false);
} // namespace ss6
