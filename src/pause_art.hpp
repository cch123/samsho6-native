#pragma once
#include "gallery_art.hpp"
#include "key_config.hpp"
#include "menu_canvas.hpp"
#include "menu_widgets.hpp"
#include "pause_menu.hpp"
#include "skill_list.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>

namespace ss6 {
// Drawing of the in-battle pause menu (task 1d9e10), of the KEY CONFIGURATION
// window (coroutine 13ce08 -> 182600 + 212478) and of the SKILL LIST window
// (coroutine 13d680 -> 182600 + 20ef38 x 2 + 210298), as MenuDrawList
// submissions. The logic modules own every state word read here; the window
// library is GalleryArt.
//
// Record convention added by this module to MenuDrawRecord:
//  - A Flat record with glyph == 1 is the four-colour strip of 17e0b0: `colour`
//    is the queue colour of the two left vertices and corner[0..3] hold the
//    four bytes (R, G, B, A in queue order) of the two right vertices.
//    PauseArt::rasterise interpolates between them along x.

// pause_art.bin (work/ss6/extract_pause_art.py).
struct PauseArtTables {
    // Order of FLOATS in extract_pause_art.py.
    enum Constant:unsigned {
        CursorStep,TitleX,TitleY,TitleZ,RowsZ,HelpTextZ,HelpBarZ,BoxZ,LegendBoxZ,EdgeZ,
        KeyBoxW,KeyBoxH,KeyIconZ,KeyCursorW,KeyCursorH,BracketZ,BracketArm,
        SkillIconZ,SkillBarZ,SkillBarX,SkillDimZ,SkillScrollW,SkillScrollH,ConstantCount
    };
    std::array<float,ConstantCount> value{};
    explicit PauseArtTables(const std::filesystem::path& assets);
    float operator[](Constant index) const {return value[index];}
};

// Words 582f60 (counter) and 582f64 (direction) of the frame edges. 1c1528
// steps them once per EDGE, four times per visit, between 0 and 0x78; no
// routine resets them, so they persist from boot across every pause.
struct PauseEdgePulse {
    int counter=0,reverse=0;
};

// Context of a child window visit.
struct PauseWindowContext {
    unsigned gameMode=1;     // 4c3808: 17ea48 selects the page backdrop instead of the battle scene
    unsigned seat=0;         // 178f90(): tints the frame borders
    // Option bytes 7e..80 (43d0d6..43d0d8). matsuri gates the "MS" text and
    // the "SC" icon of every 17e428 line; ma and kemono gate two spirit
    // icons of the SKILL LIST headings.
    SkillUnlocks unlocks;
};

class PauseArt {
public:
    PauseArt(const MenuCanvas& canvas,GalleryArt& library,const std::filesystem::path& assets);
    const PauseArtTables& tables() const {return tables_;}
    // 43d064 as given to MenuCanvas::setBrightness: 17e0b0 submits through
    // 114c10 directly, so its colours take BRIGHT but not the scene fade.
    void setBrightness(int value) {brightness_=value;}

    // Draw half of one 1d9e10 visit: 1daca8, 1da918, 1da9c0, 1dab38, 1dae00
    // (all skipped with WINDOW OFF) and the 1cf598 dialog. `chrome` is
    // PauseMenu::chrome after the tick (legend counter and marquee);
    // `neoGeoLand` is gameData+0xa0 == 5 (four rows, the NEOGEO LAND prompt).
    void drawPauseMenu(MenuDrawList& list,const PauseMenuAssets& assets,const PauseMenuDraw& draw,const MenuChrome& chrome,
                       bool neoGeoLand,PauseEdgePulse& pulse) const;

    // One 13ce08 visit after KeyConfigWindow::tick: 17c210, 182600, 212478.
    // In a menu mode (17ea48) the guide draws the page backdrop and needs the
    // MenuBackdrop / MenuChrome of the scene (1ce478 done by its owner);
    // otherwise the three arguments are not touched. Returns true when 1817f0
    // requested 109de8: word 3451c8 bit 4, the frame starts with the frame
    // buffer saved in GS memory (blocks 1a40 / 2300) copied back.
    bool drawKeyConfig(MenuDrawList& list,const KeyConfigAssets& assets,const KeyConfigWindow& window,const SystemData& system,
                       const PauseWindowContext& context,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome) const;
    // 212478 alone (the practice menu owns the widget without the window).
    void drawKeyWidget(MenuDrawList& list,const KeyConfigAssets& assets,const KeyConfigDraw& draw) const;

    // One 13d680 visit after SkillListWindow::tick: 17c210, the dim plane,
    // 182600, 20ef38 (categories), 20ef38 (sub-list), 210298. Same return
    // value as drawKeyConfig.
    bool drawSkillList(MenuDrawList& list,const SkillListWindow& window,const PauseWindowContext& context,
                       MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome) const;
    // 13d0d0: the page of group `id` from text line `scroll`.
    void skillPage(MenuDrawList& list,const SkillListData& data,int table,int first,int id,int x,int y,int scroll,int lines,
                   int gap,const SkillUnlocks& unlocks) const;

    // --- primitives private to the original callers --------------------
    // 1c1528: one edge of the pause frame; steps the pulse.
    void edge(MenuDrawList& list,int x,int y,int w,int h,uint32_t first,uint32_t second,PauseEdgePulse& pulse,int period) const;
    // 17d790: four corner brackets, each rectangle on its own cursor step.
    void brackets(MenuDrawList& list,float x,float y,float w,float h,uint32_t outer,uint32_t inner) const;
    // 17e0b0: heading strip, left colour alpha c0, right colour alpha 40.
    void headingBar(MenuDrawList& list,const SkillListData& data,int type,int w,int h,float x,float y,float z) const;
    float cursor(MenuDrawList& list,PauseArtTables::Constant layer) const;   // 17c228(4ee54c - K)

    // Paints the list over the existing 640x480 RGBA frame in ascending
    // depth; everything but the 17e0b0 strips goes through GalleryArt.
    void rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const;

private:
    void apply(const PauseWindowContext& context) const;
    const MenuCanvas& canvas_;
    GalleryArt& library_;
    PauseArtTables tables_;
    int brightness_=256;
};
}
