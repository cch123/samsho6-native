#pragma once
#include "ground_state.hpp"

namespace ss6 {
// Row addresses identify the Japanese victim sequence retained in actor+2bc.
uint32_t hanzoCaptureAddress(int slot);
void enterHanzoThrowPhase(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
void advanceHanzoThrowPhase(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
}

