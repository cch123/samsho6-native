#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
#include "menu_widgets.hpp"
#include "system_data.hpp"

namespace ss6 {
// Key masks 4eaac0 (save image +63bc): two players of eight words. Word i is
// the software-pad mask (118128 +0/+4 bit set) that 177310 tests for fighter
// button i; a zero word leaves the button unassigned.
//   slot 0 LIGHT, 1 MIDDLE, 2 STRONG, 3 KICK, 4 SPECIAL, 5 THROW,
//   6 SPIRIT USE, 7 ITEM USE (row labels 59cfb8).
// Pad bits with a button glyph in 212780: 2 circle, 4 cross, 400 square,
// 200 triangle, 100000 L1, 200000 L2, 400000 R1, 800000 R2. Bits 1 and 100
// are capturable but have no glyph. 80000 (legend glyph "SL") leaves the
// window, 8 and the directions are never assignable.
enum class KeySlot : unsigned {Light,Middle,Strong,Kick,Special,Throw,SpiritUse,ItemUse};

// pause_menu.bin sections KEYS and PRES (work/ss6/extract_pause_menu.py).
struct KeyConfigAssets {
    std::array<std::string,10> rows;                 // 59cfb8, Shift_JIS
    std::string legend,unset;                        // 665208, 665220
    std::array<std::array<uint32_t,8>,3> presets{};  // 178e50: 0 is the factory layout
    explicit KeyConfigAssets(const std::filesystem::path& assets);
};

uint32_t keyMask(const SystemData& system,unsigned player,unsigned slot);
// 178d50. A zero mask clears the slot. Otherwise the first slot of the
// player that already holds the mask receives the old content of `slot`
// (the scan stops there), then `slot` takes the mask.
void assignKeyMask(SystemData& system,unsigned player,unsigned slot,uint32_t mask);
// 178e50 (178d38 is preset 0). The original also stores the preset number
// in byte 12d26b0 + player, which is outside the save image.
void applyKeyPreset(SystemData& system,const KeyConfigAssets& assets,unsigned player,unsigned preset);
// 212780: icon number of a mask (table 4ee6b8), -1 when it has no glyph.
int keyGlyph(uint32_t mask);
// 177140: both players hold the factory masks in slots 0..4.
bool keyMasksFactory(const SystemData& system,const KeyConfigAssets& assets);

// Everything 212478 reads. Coordinates are screen pixels before the common
// text helpers 17e228 / 17e038 / 17d790 apply their own offsets.
struct KeyConfigDraw {
    bool visible=false;
    int boxX=0,boxY=0;                        // 17c718: 528 x 286, colour c0000000
    int legendX=0,legendY=0;                  // 17e428(legend, 1, 0)
    int labelX=0;
    std::array<int,10> labelY{};
    std::array<uint32_t,10> labelColour{};    // 17db28 argument per row
    struct Cell {
        int glyph=-1;                         // -1: the text `unset`
        int x=0,y=0;
        bool cursor=false;                    // 17d790 frame of this seat
        int cursorX=0,cursorY=0;              // 48 x 29
        uint32_t cursorColour=0;
    };
    std::array<std::array<Cell,8>,2> cells{};
};

// 212110..212478: the button table shared by OPTION, the pause menu and the
// practice menu. Both pads operate it at once, each with its own cursor over
// rows 0..7 (slots), 8 DEFAULT SETTING and 9 EXIT.
struct KeyConfigWidget {
    enum {DefaultRow=8,ExitRow=9,Leave=4};
    int shown=0,active=0;                     // +0, +4 (written by the owner)
    SlidePanel panel;                         // +c
    std::array<MenuSelector,2> selector{};    // +40, +5c
    GuideWindow* guide=nullptr;               // +78 is the guide's message bar
    std::array<uint8_t,2> presetId{};         // 12d26b0
    void init(GuideWindow* window);           // 212110
    // 2121c8. Returns Leave on the visit a seat presses 80000 or confirms
    // EXIT, otherwise 0. Tones are 1e7b70(-1, id) requests.
    int update(const std::array<WidgetPad,2>& pads,SystemData& system,const KeyConfigAssets& assets,std::vector<int>& tones);
    KeyConfigDraw draw(const SystemData& system) const;   // 212478
};

// Coroutine 13ce08 (task tag 14b6, priority 28): guide window, widget and
// the slide-in panel. One tick is one pass of its loop up to the yield.
struct KeyConfigWindow {
    struct Result {
        bool returnedToPause=false;   // 1da7e8(1): the caller resumes; this task sleeps
        bool optionScene=false;       // 1252f0(1, 0, 13cdc8, 1cfa10)
    };
    GuideWindow guide;
    KeyConfigWidget widget;
    bool closing=false,finished=false;
    // 178f90: the seat whose side the window slides in from.
    static unsigned operatingSeat(unsigned gameMode,unsigned pauseOwner,unsigned editSeat);
    void start(const MenuWidgetData& tables,unsigned seat);
    // `optionScene` is 17ea48() of the current game mode (GuideWindow::menuBackdrop).
    Result tick(const std::array<WidgetPad,2>& pads,SystemData& system,const KeyConfigAssets& assets,bool optionScene,
                std::vector<int>& tones);
};
}
