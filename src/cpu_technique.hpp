#pragma once
#include "cpu_execution.hpp"

namespace ss6 {
void beginCpuTechnique(StateEntryActor&,const CpuExecutionFrame&,unsigned slot); // 162ab0
void chooseCpuTechniqueSlot(StateEntryActor&,const CpuExecutionFrame&,unsigned opcode);
bool visitCpuTechnique(StateEntryActor&,const CpuExecutionFrame&);
}

