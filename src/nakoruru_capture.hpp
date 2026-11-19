#pragma once
#include "ground_state.hpp"

namespace ss6 {
// The victim controls both bodies during the on-disc paired throw scripts.
void updateFighterCapture(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
// Kept for existing callers of the original Nakoruru-only comparison driver.
inline void updateNakoruruCapture(PlayerObject& body,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    updateFighterCapture(body,actor,context,frame);
}
bool updateNakoruruThrowLanding(PlayerObject&,StateEntryActor&);
}
