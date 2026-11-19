#pragma once
#include "collision.hpp"
#include "ground_state.hpp"

namespace ss6 {
// 154e10. The source of the contact is the incoming blade, and the target
// is the defender's active parry box. Failed attempts do not consume it.
bool resolveWeaponDeflection(const ContactEvent&,PlayerObject& attackerBody,StateEntryActor& attacker,
                             PlayerObject& defenderBody,StateEntryActor& defender);
void beginWeaponDeflection(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
void beginDeflectedWeapon(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
void updateDeflectedWeapon(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
}
