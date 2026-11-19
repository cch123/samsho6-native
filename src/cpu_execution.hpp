#pragma once
#include "cpu_tactics.hpp"
#include "state_entry.hpp"
#include "cpu_decision.hpp"

namespace ss6 {
struct CpuExecutionFrame {
    const InputSystemConfig& config;
    const InputBindings& bindings;
    const CpuTactics& tactics;
    GameRandom& random;
    uint8_t characterFlags;
    int level;
    uint32_t condition178;
    const StateEntryActor* opponent=nullptr;
    int battleDistance=0;
    bool opponentThreat=false; // 151478, including opponent's registered objects
    int roundIndex=0; // 1418f8 also controls scripted technique timing.
    int bodyDelta30=256;
};

// 15f638. The four-byte sequence and its cursor belong to the tactical
// dispatcher. It can replace them between consecutive visits of this runner.
void finishCpuInstruction(StateEntryActor&); //15f6f0
void executeCpuInstruction(StateEntryActor&,const CpuExecutionFrame&);
uint32_t cpuTimerDown(StateEntryActor&,unsigned index); // 15de18
uint32_t cpuTimerUp(StateEntryActor&,unsigned index); // 15de40
void resetCpuSequence(StateEntryActor&); // 158d98
void advanceCpuSequence(StateEntryActor&,const InputSystemConfig&,const CpuDecisionFrame&,
                        const CpuTactics&,GameRandom&);
}
