#pragma once
#include "actor_history.hpp"
#include "auxiliary_objects.hpp"
#include "kazuki_fire.hpp"

namespace ss6 {
// PakuPaku (47): the four kind-6 objects (d0 == 0xa8, ACT 0x24e -> 0x24f) that script 6 creates
// (16ed60). One visit of the task callback 16ee10 / 16ee80: the phase switch, then 16ee98 orbits
// slot o.128 around the owner's history sample 128 + 1 (updated in 1494f0 before this callback).
void updatePakuOrbit(AuxiliaryObjects&,AuxiliaryObject& o,uint32_t& callback,const ActorHistory&,const AngleTrig&);
}
