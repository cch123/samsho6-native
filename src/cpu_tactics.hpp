#pragma once
#include "game_random.hpp"
#include "scalar_float.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>

namespace ss6 {
struct CpuProfileChoice {
    int tierE4=0,patternE8=0,actionEC=0,variantF0=0;
};
class CpuTactics {
public:
    CpuTactics(const std::filesystem::path& assets,unsigned character);
    std::array<uint8_t,4> sequence(unsigned index) const;
    // The dispatchers index the loaded structure. Its first eight bytes are
    // the loader's cache header and have no entry in the disc file.
    uint8_t characterByte(std::size_t runtimeOffset) const;
    CpuProfileChoice chooseProfile(GameRandom&,int level100,unsigned difficulty,int clockValue,int category) const;
    int normalAttackSituation(unsigned index) const {return attackSituations_.at(index);}
    int techniqueScript(unsigned character,unsigned slot) const;
    int specialPattern(int index,bool projectile) const;
    int airAttackDelay(unsigned character,unsigned attack) const {return airTimings_.at(character*36+attack);}
    bool guardsHigh(unsigned character,unsigned variant,unsigned move) const;
    bool projectileGuardHigh(unsigned kind) const {return projectileFlags_.at(kind)&0x10;}
    int techniqueStart(int script) const;
    std::array<uint8_t,12> techniqueRow(unsigned index) const;
    std::optional<std::array<uint8_t,12>> techniqueDefinition(int character,unsigned ordinal) const;
    int distanceBand(unsigned pattern,ScalarFloat selfX,ScalarFloat otherX) const;
private:
    std::array<uint8_t,556*12> techniqueSteps_;
    std::array<uint8_t,833*12> techniqueDefinitions_;
    std::array<uint8_t,54*36> airTimings_;
    std::array<uint8_t,54*4*12> guardHeights_;
    std::array<uint8_t,190> projectileFlags_;
    std::array<uint8_t,53*32*2> techniqueIds_;
    std::array<uint8_t,64> attackSituations_;
    std::array<uint8_t,0x6a0*4> specials_;
    std::array<uint8_t,0x71a0> common_;
    std::array<uint8_t,0x4c44> character_;
};
}
