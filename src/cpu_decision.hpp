#pragma once
#include "cpu_tactics.hpp"
#include "state_entry.hpp"

namespace ss6 {
struct CpuObservedObject {
    int idD0=0,moveD4=-1,resource14=0;
    float x=0;
};
struct CpuDecisionFrame {
    int level100=0,clockValue=0,roundIndex=0;
    unsigned difficulty=0;
    int battleMode=0;
    int cameraLeft=0,cameraRight=0;
    // 140d78 returns the first object of each kind in the opponent's registry.
    // Kind 3 observations are eligible only when 1a3798 accepts that fighter.
    std::optional<CpuObservedObject> kind2,kind3;
    bool kind3Active=false;
};
// 1403d4 updates these distance categories before the stage camera clamps
// positions. 1403f4 samples both opponents again after collision, before P1 runs.
void observeCpuDistances(StateEntryActor&,const StateEntryActor&,int battleDistance,const CpuTactics&);
void observeCpuSituation(StateEntryActor&,const StateEntryActor&,const CpuTactics&,const StateEntryRules&);
bool beginCpuSequence(StateEntryActor&,const InputSystemConfig&,const CpuDecisionFrame&,
                      const CpuTactics&,GameRandom&,unsigned sequence); //15d5b0
// Ordinary fight AI (control mode 35). Called before advancing 15c550.
// A false return leaves the current sequence running.
bool decideCpuAction(StateEntryActor&,const StateEntryActor& opponent,const InputSystemConfig&,
                     const CpuDecisionFrame&,const CpuTactics&,GameRandom&); //15af80
}
