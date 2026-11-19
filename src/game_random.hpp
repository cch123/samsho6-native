#pragma once
#include <cstdint>

namespace ss6 {
//Both source generators have independent persistent state. The mode chooses
//which one advances; native library rand() is never part of a replay.
struct GameRandom {
    int32_t mode=0; //443150
    uint32_t gameSeed=1; //3d2e80
    uint64_t librarySeed=1; //_impure_ptr+a8
    uint32_t nextGame(); //112290
    uint32_t nextLibrary(); //316b90
    int32_t bounded(int32_t bound); //112300, including signed/wrapped bounds
};
}
