#pragma once
#include "auxiliary_objects.hpp"

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct StateEntryContext;
struct GroundStateFrame;
struct ActorCommandInput;

bool nakoruruEagleAttackSupports(int state);
bool updateNakoruruEagleAttack(PlayerObject&,StateEntryActor&,const ActorCommandInput&,StateEntryContext&,const GroundStateFrame&);
// Both the mount and the weapon-breaking attack steer towards the living
// eagle. The two callers stop the fighter only when this reports arrival.
bool approachNakoruruEagle(PlayerObject&,const AuxiliaryObject& eagle);
}
