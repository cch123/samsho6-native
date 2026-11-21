#pragma once
#include "edit_art.hpp"
#include "practice_mode.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <vector>

namespace ss6 {
// Drawing of the PRACTICE MODE overlays of the battle scene: the window
// 17f790 (dim plane, help frame 182600, menu 2109b0 with the gauge sub-window
// 2118a0, confirm dialog 2129d0), the data display 13a280 (command history
// and damage counters) and the REC / PLAY clock 141dd0.
//
// Everything is appended to a MenuDrawList through the window library of
// EditArt (17c228 depth cursor, 17c718, 17dd88, 17e228, 17e428, 17e038,
// 182600). The battle thread 138f48 zeroes the depth cursor once per outer
// frame (17c210 at 138f90) and then draws in this order:
//     141dd0 clock (tail of the battle draw 140120)
//     13a280 data display, only while 2111d8() (DATA DISPLAY = ON)
//     17f790 window
// so one frame is: list.beginFrame(); list.resetCursor();
// drawPracticeDisplays(...); drawPracticeWindow(...); and the list is then
// composed over the finished battle frame with EditArt::rasterise.

// practice_art.bin (work/ss6/extract_practice_art.py).
class PracticeArtTables {
public:
    explicit PracticeArtTables(const std::filesystem::path& assets);
    float f(uint32_t address) const;             // float constant stored at that ELF address
    std::array<uint8_t,15> keyIcons{};           // 4ca210: 17e038 icon per bit of a history word
private:
    std::vector<std::pair<uint32_t,float>> floats_;
};

// The help window 12d3870 is the screen frame 1822a0 (EditFrame). Call
// EditFrame::tick() (1825b8) at the top of the window update, then apply the
// requests PracticeWindow::init / finish returned, in order.
void applyPracticeHelp(EditFrame& frame,const std::vector<PracticeHelp>& requests,const PracticeTables& tables);

// 141dd0. Sets the middle text layer (17e200) around the clock text.
void drawPracticeClock(const EditArt& art,EditArt::Context& c,const PracticeClock& clock,const PracticeTables& tables);
// 13a280: the 24 history columns from x = 600 leftwards, then (battle type 1)
// the damage box. c.seat is 178f90().
void drawPracticeData(const EditArt& art,const PracticeArtTables& tables,EditArt::Context& c,bool practice,
                      const PracticeDamage& damage,const PracticeKeyHistory& keys,const PracticeTables& text);
// 141dd0 followed, while practice.settings.dataDisplay(), by 13a280.
// recordIndex = actor+0x2c0 of actor slots 0 and 1. Sets c.seat.
void drawPracticeDisplays(const EditArt& art,const PracticeArtTables& tables,EditArt::Context& c,const PracticeState& practice,
                          const PracticeDamage& damage,const PracticeKeyHistory& keys,const std::array<int,2>& recordIndex,
                          const PracticeTables& text);

// 2109b0 (with 2118a0) and 2129d0, exposed for the validator and for owners
// that interleave their own windows.
void drawPracticeMenu(const EditArt& art,const PracticeArtTables& tables,EditArt::Context& c,const PracticeMenu& menu,
                      const PracticeSettings& settings,const PracticeTables& text);
void drawPracticeConfirm(const EditArt& art,EditArt::Context& c,const PracticeConfirm& confirm,const PracticeTables& text);

struct PracticeWindowDraw {
    // 1817f0 with a battle scene behind the frame (17ea48() == 0) and a
    // backdrop kind other than -1: 109de8 sets bit 0x10 of the renderer word
    // 3451c8 instead of submitting a backdrop. Only the key-configuration
    // (layout 0) and skill-list (layout 5) pages request it; its effect on
    // the frame is not ported.
    bool battleDim=false;
};
// Draw tail of 17f790 (17f92c..17fa08) for the state PracticeWindow::finish
// left: dim plane 12d3864, then unless the window is hidden (state 2) the
// help frame and the menu, then `subWindows` (212478 key configuration,
// 20ef38 skill list, 20ef38 sub-list, 210298 detail, in that order; they sit
// between the menu and the dialog in the depth-cursor sequence), then the
// confirm dialog. Sets c.seat = practice.localSeat().
PracticeWindowDraw drawPracticeWindow(const EditArt& art,const PracticeArtTables& tables,EditArt::Context& c,
                                      const PracticeWindow& window,const PracticeState& practice,const EditFrame& help,
                                      const PracticeTables& text,const std::function<void()>& subWindows={});
}
