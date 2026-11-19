#pragma once
#include "player_object.hpp"
#include <array>

namespace ss6 {
struct ActorHistorySample {
    uint32_t flags=0,action=0,step=0;
    float x=0,y=0;
};
// Actor+a60 stores sixty20-byte samples, newest first. The fractional
// clock is a BYTE; even a delta larger than256 shifts the history only once.
struct ActorHistory {
    uint8_t fraction=0;
    std::array<ActorHistorySample,60> samples{};
    static ActorHistorySample capture(const PlayerObject&,float offsetX=0,float offsetY=0);
    void reset(const ActorHistorySample&);
    void update(const ActorHistorySample&,int32_t delta);
};
struct ActorAfterimage {
    ActorHistorySample sample;
    uint32_t color=0,flags104=0x400300;
    unsigned lag=5,alpha=144,depthOffset=1;
    float depth=0;
    bool visible() const { return !(flags104&2); }
    //147b60, resource00. Eligibility is the original169138 table, not a
    // speed threshold; ordinary standing light does not leave a trail.
    void update(const ActorHistory&,int currentTable,float actorDepth=0,unsigned character=0);
};
std::array<ActorAfterimage,3> makeActorAfterimages();
}
