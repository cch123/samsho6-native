#pragma once
#include "state_entry.hpp"

namespace ss6 {

struct BattleClockState {
    int seconds=-1;
    bool stopped=false,visible=false;
};

// 141cf8 controls both the counter and its HUD. The hold outlasts the
// startup action when an explosion is active, and ends on leaving state 4.
inline bool roundClockStopped(int currentState,const StateEntryActor& left,const StateEntryActor& right) {
    const auto holds=[](const StateEntryActor& a){return a.rageState120==2||a.state194==0x240001;};
    return currentState==4&&(holds(left)||holds(right));
}

}
