#pragma once
#include <array>

namespace ss6 {
// Indexed by the Japanese battle resource ID, also used by the selection grid.
inline constexpr std::array<const char*,4> versusFighterNames{"HAOHMARU","NAKORURU","RIMURURU","HANZO"};
constexpr bool playableFighter(unsigned character) {return character<versusFighterNames.size();}
}

