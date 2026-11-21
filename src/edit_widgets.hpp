#pragma once
#include "console_menu.hpp"
#include "system_data.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {
// Widgets shared by the SPIRITS EDIT (13ada0) and COLOR EDIT (13b1c8) tasks.
// Strings are the original Shift-JIS bytes: panel widths derive from strlen.

// 17f308..17f508: linear slide between a retracted and an extended position.
struct EditSlide {
    int x=0,y=0,remaining=0,duration=1,startX=0,startY=0,targetX=0,targetY=0;
    int retracted=1,outX=0,outY=0,inX=0,inY=0;
    void configure(int outX,int outY,int inX,int inY,int frames); // 17f428
    void reset() {configure(0,0,0,0,1);}                           // 17f308
    void snap(int px,int py);                                      // 17f3a0
    void slideIn();                                                // 17f468
    void slideOut();                                               // 17f4b0
    // 17f330: 2 while moving, 1 settled extended, 0 settled retracted.
    int update();
    bool settled() const {return remaining<1;}                     // 17f400
};
int editPageScroll(int event,int cursor,int visible,int scroll,int rows); // 17f528
int editFollowScroll(int cursor,int visible,int scroll,int rows);         // 17f560

enum EditEvent : int {EditNone=0,EditMoved=1,EditPageBack=2,EditPageForward=3,EditConfirm=4,EditCancel=5,EditRejected=6};
// Requests issued as 1e7b70(-1, id).
enum EditSound : int {EditSoundConfirm=0,EditSoundMove=0x20,EditSoundCancel=0x24};

// 20dff8..20e528. Flag bits (1 << n): 0 vertical keys, 1 horizontal keys,
// 2 wrap, 3 inverted, 4 confirm rejected, 5 cancel rejected, 7 silent move,
// 8/9 silent confirm, 8/10 silent cancel, 11 bitmap attached, 12/13/15/16
// owner layout, 17 START ignored, 18 movement locked.
struct EditListCursor {
    uint32_t flags=5;
    int min=0,max=1,step=1,cursor=0,page=0;
    std::array<uint32_t,16> disabled{};   // 20e480 attaches the owner's bitmap
    void init();                                             // 20dff8
    void setRange(int lo,int hi,int stride,int pageRows);    // 20e028
    void setFlag(unsigned bit,bool on) {flags=on?flags|1u<<bit:flags&~(1u<<bit);} // 20e0a0
    bool flag(unsigned bit) const {return flags>>bit&1;}     // 20e088
    // 20e0d0. With the wrap flag the delay-slot store leaves the requested
    // value unclamped; only a non-wrapping list clamps to [min, max).
    void setCursor(int value);
    void attachBitmap() {flags|=0x800;}                      // 20e480
    void disableRow(int row);                                // 20e4e0
    void enableRow(int row);                                 // 20e528
    bool rowDisabled(int row) const;                         // 20e498
    // 20e128: one update from the controlling seat's pad record.
    int update(const MenuPad& pad,std::vector<int>& sounds);
};

struct EditWidgetAssets {
    explicit EditWidgetAssets(const std::filesystem::path& assets); // edit_widgets.bin
    // 1821f8: text of row (first row whose id matches) + sub.
    const std::string& help(int id,int sub) const;
    std::vector<uint8_t> helpIds;
    std::vector<std::string> helpTexts;
    std::array<uint8_t,0x35> characterOrder{};   // 59cd20: 49 ids, then the four EX ids
    std::array<std::string,49> characterNames;   // 4d4bb0
    std::string menuTitle,undefinedRow,helpFallback;
    std::array<std::string,5> exNames;           // default, 73, 72, 75, 74
};

// 20e570: titled list of up to 0x200 text rows with a slide and a scroll window.
struct EditListMenu {
    int width=0x80,height=0;
    std::string title;
    int visibleRows=1,scroll=0,visible=0,active=0;
    EditSlide slide;
    EditListCursor list;
    std::vector<std::string> rows;
    std::array<int16_t,0x37> characterIds{};     // 1373830, valid with list flag 13
    explicit EditListMenu(const EditWidgetAssets& assets);
    void setRows(int count,int visibleCount);                              // 20e5d8 (-1: all visible)
    void setStrings(const std::vector<std::string>& strings,int visibleCount); // 20e738
    void setRow(unsigned row,const std::string& text);                     // 20e7f8
    int update(const MenuPad& pad,std::vector<int>& sounds);               // 20ee70
    // 20eae0. Locked fighters are option bytes 16+id, seen endings 47+id,
    // the EX group is option byte 94.
    void buildCharacterList(const SystemData& data,int visibleCount,int firstRow,bool includeEx,
                            bool includeKuroko,bool useEndingTable);
    int selected() const;                                                  // 20ee20
    void select(int id);                                                   // 20ed70
private:
    const EditWidgetAssets* assets_;
};
}
