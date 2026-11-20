#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <vector>

namespace ss6 {
// Per-character tables read from the pinned ELF by extract_script_tables.py.
class FighterTables {
public:
    explicit FighterTables(const std::filesystem::path& assets);
    // The original attack (4e8fe8) / damage-source (4e97a8) handler when it
    // is the common stub AND the roster ports the fighter through the shared
    // engines (FighterPort::ScriptStubs); 0 otherwise.
    uint32_t scriptAttack(unsigned character) const;
    uint32_t scriptVictim(unsigned character) const;
    // Damage form 2: the stub sends k == 4 without a row to a character
    // routine instead of 169810 (Gaira's 1f3be0 -> 1f3cc8).
    // Attack form 2: the stub runs character code for selectors without a
    // script (ported per character in script_fighter.cpp).
    bool attackCharacterBranch(unsigned character) const {return character<51&&stubs_[character].attackForm==2;}
    bool victimK4Routine(unsigned character) const {return character<51&&stubs_[character].damageForm==2;}
    // Raw 4e97a8 entry, whichever form it has.
    uint32_t damageSource(unsigned character) const {return stubs_.at(character).damage;}
    bool noFacing(unsigned character,unsigned k) const;   //168f48, pairs at 4e8098
    bool weaponHold(unsigned character,unsigned k) const; //169218, pairs at 4e8328
    struct DepthRule {unsigned fighter,act,mode;};
    // 148900 scans these rows in order (4d3d18).
    const std::vector<DepthRule>& depthRules() const {return depth_;}
    // 14d788 (inside every 1493c0 queue): the ACT a form substitutes, or -1
    // (no row / no form). companion receives 14e6d8's companion ACT (0x800000).
    int formAction(unsigned character,uint32_t flags23c,int act,int* companion=nullptr) const;
private:
    struct Stub {uint32_t attack=0,damage=0;uint8_t attackForm=0,damageForm=0;};
    std::array<Stub,51> stubs_{};
    std::vector<std::array<uint8_t,2>> facing_,hold_;
    std::vector<DepthRule> depth_;
    std::array<std::vector<std::array<int16_t,3>>,6> forms_{};
};
}
