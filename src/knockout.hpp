#pragma once
#include "player_object.hpp"

namespace ss6 {
enum class KnockoutPhase { Inactive, FirstLanding, SecondLanding, Finishing, Complete };

// Resource00 ordinary KO callbacks. Effect29 is emitted as an event; its
// separate task/rendering and the round controller are not implemented here.
class KnockoutPlayback {
public:
    KnockoutPhase phase=KnockoutPhase::Inactive;
    //A supplied actor queue preserves1493c0 ->149918 as separate stages.
    void begin(PlayerObject& object,uint32_t& actorFlags,unsigned variant,int32_t* actorAction=nullptr);
    bool update(PlayerObject& object); // true requests the original dust29
};
bool actionEnded(const PlayerObject& object,int32_t queuedAction=-1); // 0x149488
bool touchedGround(const PlayerObject& object,int32_t queuedAction=-1); // 0x1737d8
bool landingReady(PlayerObject& object,int32_t queuedAction=-1); // 0x173970
void stopAtGround(PlayerObject& object); // 0x1697d0
}
