#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
struct ConsoleTitleFrame {
    bool modeMenu=false;
    unsigned firstRow=5,scrollDirection=0,scrollTick=0,titleTick=0,idleTick=0;
    unsigned unlock=0;
};

// Canonical rows of jump table 656828 behind 1ccfd0.
enum class ConsoleMode : int {
    None=-1,Arcade=0,Versus=1,Practice=2,Survival=3,SpiritsEdit=4,ColorEdit=5,Gallery=6,Network=7,Option=8
};
// 1ccfd0/1cd818 pick one of four row lists. Bit 0 mirrors system byte 43d0d6
// (survival and spirits edit), bit 1 the 1e3f70 result (gallery).
struct ConsoleModeRows {
    std::array<ConsoleMode,9> items{};
    unsigned count=0;
};
inline ConsoleModeRows consoleModeRows(unsigned unlock) {
    using M=ConsoleMode;
    switch(unlock&3) {
    case 0:return {{M::Arcade,M::Versus,M::Practice,M::ColorEdit,M::Network,M::Option},6};
    case 1:return {{M::Arcade,M::Versus,M::Practice,M::Survival,M::SpiritsEdit,M::ColorEdit,M::Network,M::Option},8};
    case 2:return {{M::Arcade,M::Versus,M::Practice,M::Survival,M::ColorEdit,M::Gallery,M::Network,M::Option},8};
    default:return {{M::Arcade,M::Versus,M::Practice,M::Survival,M::SpiritsEdit,M::ColorEdit,M::Gallery,M::Network,M::Option},9};
    }
}

// Japanese factory system data, with both local input ports present.
class ConsoleTitle {
public:
    // returnRow restores the raw cursor 582af8, which survives a mode's scenes.
    explicit ConsoleTitle(bool returningFromVersus,unsigned unlock=0,int returnRow=-1);
    unsigned firstRow() const {return firstRow_;}
    void tick(const std::array<uint32_t,2>& menuCommands,bool startPressed);
    ConsoleTitleFrame draw;
    std::array<int,2> tones{-1,-1};
    bool announce=false,unavailableMode=false;
    int confirmingSeat=-1;
    ConsoleMode confirmedMode=ConsoleMode::None;
    // Rows whose scene exists natively; other rows only report unavailableMode.
    uint32_t supportedModes=1u<<unsigned(ConsoleMode::Versus)|1u<<unsigned(ConsoleMode::Option)|
                           1u<<unsigned(ConsoleMode::SpiritsEdit);
    int transitionTick=0;
private:
    unsigned firstRow_,direction_=0,scroll_=0,inputAge_=0,titleTick_=0,idleTick_=0;
    bool joined_;
    ConsoleModeRows rows_;
    unsigned unlock_;
};
}
