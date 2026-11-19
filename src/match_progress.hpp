#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
// Per-player record at battle+254+108*player, shared by attacks and round scoring.
struct PlayerMatchStats {
    uint32_t hitCount0c=0;
    int32_t previousLife10=0,previousPosture14=0,field18=0;
    int32_t outcome1c=-1,outcome20=-1,previous24=-1;
    int32_t wins=0,requiredWins=2,rating=0,score=0,bonus=0;
    int32_t weaponLockPresses30=0;
    std::array<uint8_t,5> history{255,255,255,255,255};
    void initialize(int32_t selectedPlayer,int32_t ratingSource);
    void resetRound();
    void record(int32_t result,bool perfect,bool otherFlag,bool draw);
    bool complete() const { return wins>=requiredWins; }
};
struct RoundResult {
    int winner=-1,result=-1,ui=-1;
    bool draw=false;
};
struct RoundTransition { int state=0,delay=30; };
struct MatchProgress {
    // Two wins is an explicit inspection-fixture setting, not an inferred
    // default from the PS2 option screen, whose loading path is unported.
    std::array<PlayerMatchStats,2> players;
    int32_t roundIndex=0;
    RoundResult result;
    bool complete() const { return players[0].complete()||players[1].complete(); }
    unsigned openingLabel() const;
    // Ordinary mode of143ce0..144020: the special1393a0 time-limit
    // winner override is excluded. KO and ordinary time-limit results work.
    void recordRound(const std::array<int32_t,2>& life,const std::array<int32_t,2>& maximum);
    RoundTransition transition(int mode,int submode) const;
};

// Battle+104 has seven independent timers, distinct from actor+1ac.
// Delta is already resolved by the outer clock; this type does not pretend
// to implement the global11f450 pause/slow-motion policy.
struct BattleTimers {
    int32_t flags=0,lock=0,rawDelta=256,delta=256;
    std::array<int32_t,7> values{};
    void set(unsigned index,int32_t ticks,int32_t divisor=1);
    void clear(unsigned index);
    int32_t decrease(unsigned index);
    int32_t increase(unsigned index);
    void decreaseLock();
    bool locked() const { return lock>0; }
};
}
