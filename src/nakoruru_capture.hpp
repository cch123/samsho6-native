#pragma once
#include "ground_state.hpp"

namespace ss6 {
// The victim controls both bodies during the on-disc paired throw scripts.
// Returns true when the source character has no row for this state and the
// caller must run the ordinary 169810 recovery.
bool updateFighterCapture(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
// Kept for existing callers of the original Nakoruru-only comparison driver.
inline void updateNakoruruCapture(PlayerObject& body,StateEntryActor& actor,StateEntryContext& context,const GroundStateFrame& frame) {
    updateFighterCapture(body,actor,context,frame);
}
bool updateNakoruruThrowLanding(PlayerObject&,StateEntryActor&);
// Helpers shared by the hand-ported rows and victim_script.cpp.
namespace capture {
void callback(StateEntryActor&,uint32_t pc,unsigned table,unsigned mode); //1522a0 + 274
void queue(StateEntryActor&,int act);                                     //1493c0
void oppositeFacing(PlayerObject& target,PlayerObject& source);
bool weaponLossShakes(unsigned attacker);                                  //1687bc list
float shifted(float x,float offset);
void splitAnchor(PlayerObject& target,PlayerObject& source);               //166c28
void constrain(PlayerObject&);
void loseWeapon(PlayerObject& body,StateEntryActor& victim,StateEntryContext&,const GroundStateFrame&); //168750
bool sourceInvalid(StateEntryActor& victim,StateEntryContext&,const GroundStateFrame&);              //168220
}
}
