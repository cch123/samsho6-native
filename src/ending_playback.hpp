#pragma once
#include "knockout.hpp"
#include "actor_state.hpp"

namespace ss6 {
enum class EndingPhase { Inactive, Playing, Holding };
// Resource00 introduction/victory/corpse callbacks, including armed match wins.
// Armed and unarmed match-winning clips share the same completion callback.
struct EndingPlayback {
    EndingPhase phase=EndingPhase::Inactive;
    //A supplied actor queue defers149918's body request. Its owner must
    //also set actor248:1000 for intro entry and timer34's forced restart.
    void beginIntroduction(PlayerObject& object,uint32_t& gates,unsigned player=0,int32_t* actorAction=nullptr,bool sameCharacter=true);
    void deferIntroduction(PlayerObject& object,ActorTimers& timers,int ticks);
    static void releaseIntroduction(PlayerObject& object,ActorTimers& timers); //14bea0
    void beginLoser(PlayerObject& object,uint32_t posture,uint32_t& gates,int32_t* actorAction=nullptr);
    void beginWinner(PlayerObject& object,uint32_t posture,uint32_t& gates,int life,bool final=false,int32_t* actorAction=nullptr);
    void update(PlayerObject& object,uint32_t& gates,ActorTimers* timers=nullptr,unsigned player=0,int32_t* actorAction=nullptr,bool companionReady=true);
};
}
