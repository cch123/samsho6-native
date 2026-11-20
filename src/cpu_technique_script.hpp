#pragma once
#include "cpu_execution.hpp"

namespace ss6 {
void beginCpuTechniqueScript(StateEntryActor&,const CpuExecutionFrame&,int script);
bool visitCpuTechniqueScript(StateEntryActor&,const CpuExecutionFrame&);
}
