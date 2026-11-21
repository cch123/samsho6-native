#pragma once
#include <array>
#include <cstdint>
#include <vector>

namespace ss6 {
// One port of the software controller as a menu task sees it through
// 118128: +4 pressed edges, +8 edges plus directional auto-repeat.
// Bits: 10 up, 20 down, 40 left, 80 right, 20a confirm, 404 cancel,
// 8 START, 1 SELECT, 100000/400000 page previous/next.
struct MenuPad {
    uint32_t pressed=0,repeat=0;
};
// 117fd8: each direction repeats after 20 held visits, then every 2.
class MenuPadRepeat {
public:
    std::array<MenuPad,2> sample(std::array<uint32_t,2> held,std::array<uint32_t,2> pressed);
private:
    std::array<std::array<int,4>,2> delay_{};
};

// 1252f0 modes 1 (white) and 2 (black) with speed 0: the level rises by 25
// per visit to 256, holds three visits, runs the old scene destructor and
// the next scene entry on the third, then falls back to 0.
class SceneFade {
public:
    void begin(bool white=true) {phase_=1;white_=white;hold_=0;}
    // Returns true on the visit that replaces the scene.
    bool tick();
    bool active() const {return phase_!=0;}
    int level() const {return shown_;}
    bool white() const {return white_;}
private:
    int phase_=0,level_=0,shown_=0,hold_=0;
    bool white_=true;
};

// Counters of the shared option/gallery page frame (1ce478, 1ce660).
struct MenuChrome {
    int band=0;      // 582b34: 0..15 slide-in of the three bands
    int content=0;   // 582b38: 0..15 content fade
    int legend=0;    // 582b3c: 0..5 button legend fade
    int variant=1;   // 582b44: background animation 1 or 2
    std::array<int,2> helpX{0x10,0};
    int helpDelay=0;
    // 1ce478 makes 1802 C library draws per page entry: 1800 in 1e1620, this
    // variant draw, then one in 1e2358/1e23a0. Pass the 1801st result.
    void enter(int libraryRandom);
    void advance();                       // tail of 1ce660
    bool inputReady() const {return content>=15&&legend>=5;}   // 1cf750
    int contentAlpha() const {return content*17;}              // 1cf738
    void restartLegend() {legend=0;}                           // 1cf7c8
    void setHelp(int byteLength);                              // 1cebb0
    int helpPosition(bool scroll,int byteLength,unsigned copy);// 1ceb10
};
}
