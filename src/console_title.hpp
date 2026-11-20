#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
struct ConsoleTitleFrame {
    bool modeMenu=false;
    unsigned firstRow=5,scrollDirection=0,scrollTick=0,titleTick=0,idleTick=0;
};

// Japanese factory system data, with both local input ports present.
class ConsoleTitle {
public:
    explicit ConsoleTitle(bool returningFromVersus);
    void tick(const std::array<uint32_t,2>& menuCommands,bool startPressed);
    ConsoleTitleFrame draw;
    std::array<int,2> tones{-1,-1};
    bool announce=false,unavailableMode=false;
    int confirmingSeat=-1;
    int transitionTick=0;
private:
    unsigned firstRow_,direction_=0,scroll_=0,inputAge_=0,titleTick_=0,idleTick_=0;
    bool joined_;
};
}
