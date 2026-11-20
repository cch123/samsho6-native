#pragma once
#include <functional>
#include "collision.hpp"
#include "ground_state.hpp"

namespace ss6 {
// 154e10. The source of the contact is the incoming blade, and the target
// is the defender's active parry box. Failed attempts do not consume it.
// 1561e8: counter stances on route 2/3. Returns true when the contact is
// consumed; a capture requests 2/(0x50+n) on the attacker. catchSound is
// 1e7b70(-1, 0x16), played by Jubei's catches only.
bool resolveCounterStance(StateEntryActor& attacker,uint32_t attackerFlags108,StateEntryActor& defender,
                          uint8_t& defenderConsumed,const std::function<void()>& catchSound);
// 154e10 after the counter check: true when the deflection consumes the contact.
bool deflectionApplies(StateEntryActor& defender);
bool resolveWeaponDeflection(const ContactEvent&,PlayerObject& attackerBody,StateEntryActor& attacker,
                             PlayerObject& defenderBody,StateEntryActor& defender);
void beginWeaponDeflection(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
void beginDeflectedWeapon(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
void updateDeflectedWeapon(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
}
