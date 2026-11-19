#include "console_versus_session.hpp"
#include <array>

namespace ss6 {
int selectConsoleVersusStage(GameRandom& random,int selectedStage) {
    // 1040a0 seeds 90 effect objects, including two position coordinates.
    // Inside 103b30 one velocity branch consumes an extra draw. The libc
    // generator is used directly even when the battle uses the game RNG.
    for(unsigned i=0;i<90;++i) {
        random.nextLibrary();
        random.nextLibrary();
        const bool twoVelocityDraws=(random.nextLibrary()&0x4000)!=0;
        if(twoVelocityDraws)random.nextLibrary();
        for(unsigned property=0;property<6;++property)random.nextLibrary();
    }

    // 180510 builds three candidate records even in a human mirror match.
    // Character duplicates use a linear search; sword-system duplicates
    // roll again. Only the latter changes when the stage draw is reached.
    for(unsigned i=0;i<3;++i)random.bounded(36);
    std::array<bool,7> used{};
    for(unsigned i=0;i<3;++i) {
        int system;
        do {system=random.bounded(7);} while(used[system]);
        used[system]=true;
    }
    random.bounded(2);
    for(unsigned i=0;i<3;++i) {
        random.bounded(11);
        random.bounded(5);
        // 17b2bc selects from a variable-length list. Its bound affects
        // the discarded candidate field but never the state of either RNG.
        random.bounded(1);
    }
    random.bounded(3);

    // 139be8 consumes this draw before asking whether a stage was pinned.
    const int randomStage=random.bounded(10);
    return selectedStage==10?randomStage:selectedStage;
}
}
