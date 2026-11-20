#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
struct GameRandom;

struct RankingDemoFighter {
    unsigned character=0, color=0, spirit=0;
};
struct RankingDemoMatch {
    // The title demo initializes the same seven-round arcade schedule before
    // drawing its two fighters. Its draws share the battle RNG.
    std::array<int,7> opponents{}, stages{}, roundRolls{};
    std::array<int,49> characterRolls{}, characterOrder{};
    unsigned stage=0;
    std::array<RankingDemoFighter,2> players{};
};
RankingDemoMatch selectRankingDemo(GameRandom& random,uint32_t heldDirection=0);

enum class RankingDestination : uint32_t {
    None=0, Title=0x127940, DemoNG=0x1ca408, DemoSG=0x1ea7f0
};
struct RankingRow {
    unsigned index=0;
    int x=0,y=0,alpha=0,brightness=0,stripAlpha=0;
};
struct RankingRows {
    std::array<RankingRow,6> rows{};
    unsigned count=0;
};
struct RankingFrame {
    unsigned phase=0, tick=0, firstRow=0;
    RankingRows rowLayout() const;
    // Returns -1 on ticks that leave the shared palette fade registers alone.
    int paletteLevelWrite() const;
    bool battleVisible() const {return phase<=6;}
};

class ConsoleAttractRanking {
public:
    // The transition task owns fade timing and the active scene's destructor.
    // Keep ticking through the outgoing fade. START may replace an automatic
    // destination before the transition task calls this scene's destructor.
    RankingDestination tick(bool startPressed,bool& alternateDemo,bool overseas=false);
    RankingFrame draw;
private:
    RankingFrame next_;
    RankingDestination destination_=RankingDestination::None;
};
}
