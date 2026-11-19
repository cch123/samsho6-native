#pragma once
#include <array>
#include <stdexcept>

namespace ss6 {
// Japanese battle resource IDs admitted to versus play. The IDs also index
// the selection grid and the per-character tables, so the set is sparse.
inline constexpr std::array<unsigned,5> playableFighterIds{0,1,2,3,24};
constexpr bool playableFighter(unsigned character) {
    for(auto id:playableFighterIds)if(id==character)return true;
    return false;
}
inline const char* versusFighterName(unsigned character) {
    switch(character) {
    case 0:return "HAOHMARU";
    case 1:return "NAKORURU";
    case 2:return "RIMURURU";
    case 3:return "HANZO";
    case 24:return "MINA";
    }
    throw std::out_of_range("Unsupported versus fighter");
}
}
