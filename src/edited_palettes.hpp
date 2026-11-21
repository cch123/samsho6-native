#pragma once
#include "color_edit.hpp"
#include "system_data.hpp"
#include <array>
#include <filesystem>
#include <vector>

namespace ss6 {
// The per-seat runtime palette tables 3ec740 (seat 0) and 3f28c0 (seat 1)
// that 115d40 reads for keys carrying an owner bit together with 40000, and
// the tables of that routine. Layout as the save block: 52 fighters x 5
// colours x 3 stored banks x 16 colours (6180 bytes).
class EditedPalettes {
public:
    static constexpr size_t tableSize=0x6180;
    explicit EditedPalettes(const std::filesystem::path& assets);
    ColorEditTables tables;
    std::array<std::vector<uint8_t>,2> runtime;
    // 115238: one runtime table back to the pal_all defaults (the edit block
    // of the factory image, which 115498 filled from the same source).
    void restoreDefaults(unsigned side);
    // The card task 1b6580 (tag fa4) that 1251d0 starts at every scene switch
    // while the sub-mode word 4c38a8 is 2. Each port's card image + 4 is
    // copied to that seat's table (1b67b0); a port without a readable card
    // takes the defaults (115238); when only port 0 delivered, 1b6418 copies
    // seat 0's table to seat 1 (1b6460).
    // Native storage has one card: `live.file`, or the live image itself when
    // the session has no file. The asynchronous card access is not modelled;
    // the copy completes at the scene switch.
    void loadVersusCards(const SystemData& live);
private:
    std::filesystem::path assets_;
    std::vector<uint8_t> defaults_;
};
}
