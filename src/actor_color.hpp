#pragma once
#include "state_entry.hpp"

namespace ss6 {
//14b190 for resource00 Rage or Shin. Writes the original object presentation
//words and advances only the timers owned by this callback. Rendering must
//interpret these words separately; RGBA bytes are not host sRGB tint values.
void updateActorColor(StateEntryActor&,const InputSystemConfig&);
}
