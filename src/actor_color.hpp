#pragma once
#include "state_entry.hpp"

namespace ss6 {
//14b190 for resource00 Rage or Shin. Writes the original object presentation
//words and advances only the timers owned by this callback. Rendering must
//interpret these words separately; RGBA bytes are not host sRGB tint values.
// kind4: the actor's first own kind-4 object (140d78(seat, 0, 4)), read by character 11.
void updateActorColor(StateEntryActor&,const InputSystemConfig&,uint32_t* kind4Flags38=nullptr);
}
