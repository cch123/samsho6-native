#pragma once
#include "game_random.hpp"

namespace ss6 {
// Match entry at 139760, for the supported local two-human Haohmaru matchup.
// Both a new match and CONTINUE start from the current process RNG state.
// Stage selection 10 is RANDOM, as returned by the console stage selector.
constexpr int pinnedStageBase=100;
int selectConsoleVersusStage(GameRandom& random,int selectedStage);
}
