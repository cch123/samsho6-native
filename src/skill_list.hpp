#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>
#include "menu_widgets.hpp"
#include "system_data.hpp"

namespace ss6 {
// skill_list.bin: the two static command-list tables behind 13cf88/13cfc0
// and the literals of their renderer. The list is authored text; nothing in
// it is derived from the input-template tables.
class SkillListData {
public:
    enum Table {Common=0,Character=1};
    // One 0x14-byte record. id -1 continues the group of the last id >= 0.
    // type: 0 basic, 1 spirit heading, 2 weapon-flipping technique, 3 secret
    // technique, 4 special move, 5 transformation, 6 text-only paragraph.
    // flags: 1 armed, 2 unarmed (heading icons e/f), 4 "SC" icon, 8 tall bar.
    // spirits: bit i shows the icon of spirit i (0x10+i) on the heading.
    struct Record {
        int16_t id;
        uint8_t type,flags;
        uint16_t spirits;
        std::array<uint16_t,3> text;   // name, condition, command (indices into texts)
    };
    struct Rect {int32_t u,v,w,h;};
    explicit SkillListData(const std::filesystem::path& assets);
    std::array<std::vector<Record>,2> tables;   // 4caab0, 4cb190 without the -2 terminator
    std::vector<std::string> texts;
    std::vector<std::string> categories;        // 4ceef8
    std::vector<std::string> commonRows;        // 4cef08
    std::array<std::array<uint8_t,3>,7> nameColour{};    // 4cef38
    std::array<std::array<uint8_t,3>,2> shadowColour{};  // 4cef50: type 1, other types
    std::array<std::array<uint8_t,6>,6> barColour{};     // 4ee830
    std::array<Rect,0x33> icons{};                       // 4ee6b8, texture slot 2e
    std::string space,exitLabel;                         // 5f2000, 5f2008
    int barX=0,smallGlyphY=0,iconX=0,exitY=0,scrollBarWidth=0,scrollBarHeight=0;
    std::string_view text(const Record& r,unsigned column) const {return texts[r.text[column]];}
    // 13cf88 / 13cfc0: index of the record opening group `id`. The original
    // scan has no end test; an absent id is reported as -1 here.
    int find(int table,int id) const;
    // 13cff8: text lines of the group, counted over all three columns. A
    // type-6 record counts its (never drawn) first column as well.
    int lines(int table,int first,int id) const;
};

// 17e3d8: offset behind the next "CR" at or after `at`; npos when the text
// ends first. The scan is bytewise and does not respect Shift_JIS pairs.
size_t skillNextLine(std::string_view text,size_t at);

// Unlock bytes of g_GameOption read by the list and its renderer.
struct SkillUnlocks {
    bool matsuri=false,ma=false,kemono=false;   // +7e, +7f, +80
    explicit SkillUnlocks(const SystemData& system)
        :matsuri(system.option(0x7e)!=0),ma(system.option(0x7f)!=0),kemono(system.option(0x80)!=0) {}
    SkillUnlocks()=default;
};

// One leaf request of the detail page, in original submission order.
struct SkillDraw {
    enum Kind:uint8_t {
        Bar,     // 17e0b0(id = type, w, h) at (x, y): heading gradient
        Icon,    // 17e038(id) at (x, y); w = pen advance, 0 when nothing is drawn
        Glyph,   // 10a710 (size 1) / 10a1c0 (size 2) with id = Shift_JIS code
        Ascii,   // 17e228(id: 0 " ", 1 "EXIT", x, y, size)
    };
    Kind kind;
    int id,x,y,w,h,size;
    uint32_t colour;   // 17db28 word in force for Glyph and Ascii
};

// 17e428: draws one line starting at `at` and returns the offset of the next
// line (npos at the end of the text). Two-letter ASCII codes select icons
// unless `plain` is set; "MS" hides the rest of the line while the Matsuri
// spirit is locked. Text is consumed in byte pairs.
size_t skillLayoutLine(const SkillListData& data,std::string_view text,size_t at,int x,int y,int size,bool plain,
                       const SkillUnlocks& unlocks,uint32_t colour,std::vector<SkillDraw>& out);
// 17e428 code table: icon index of the pair, -1 when the pair is no code.
// dx/dy receive the placement offset.
int skillIconCode(unsigned char first,unsigned char second,int& dx,int& dy);

// 13d0d0: the page of group `id` from text line `scroll`, at most `lines`
// lines, records separated by `gap` pixels.
void skillPage(const SkillListData& data,int table,int first,int id,int x,int y,int scroll,int lines,int gap,
               const SkillUnlocks& unlocks,std::vector<SkillDraw>& out);

// Row -> spirit index map 1373818 of the common-command sub-list. Entry 9
// lies behind the nine words the original resets.
using CommonRows=std::array<int16_t,10>;
// 20e8c0: "basic operation" plus the available spirits.
void fillCommonRows(ListWidget& list,const SkillListData& data,const SystemData& system,CommonRows& rows,int visibleRows);
// 20ea88: group id of the highlighted row (0 basic operation, 1 + spirit).
int commonSelection(const ListWidget& list,const CommonRows& rows);

// 2100b0..210298: the detail page. Field order follows the 0x78-byte object.
struct SkillDetail {
    static constexpr int pageX=0x38,pageY=0x28,pageLines=0xc,recordGap=8;
    int width=0x80,visible=1,top=0,shown=0,active=0;
    SlidePanel panel;
    MenuSelector selector;
    int category=-1,selection=-1;
    int table=-1,first=-1;   // +0x74 record pointer; (-1,-1) is the null pointer
    const SkillListData* data=nullptr;
    void init(const SkillListData& tables);          // 2100b0
    void open(int categoryRow,int id);               // 210138
    int update(const WidgetPad& pad,std::vector<int>& tones);   // 210210
    bool drawn() const {return first>=0&&shown;}     // 210298 gate
    bool scrollBar() const {return visible<selector.max;}
    // 17f090 arguments of the scroll bar: total rows, page rows and top.
    int scrollTotal() const {return selector.max+0xb;}
    void draw(const SkillUnlocks& unlocks,std::vector<SkillDraw>& out) const;   // 210298 -> 13d0d0
};

// 13d680: the SKILL LIST task of the battle pause menu (tag 151b). It is
// created suspended by 1d9cd8 and woken by the pause item; closing it calls
// 1da7e8, which suspends it again in place, so the next visit after a wake
// re-enters state 0 with every widget kept.
class SkillListWindow {
public:
    enum Event {None,ReturnToPause,LeaveScene};
    struct Result {
        std::vector<int> tones;   // 1e7b70(-1, id) in order
        Event event=None;         // 1da7e8(1), or 1252f0(1,0,13d640,1cfa10) in a menu mode
    };
    struct Draw {
        int dim=0;                // 1145c0(0,0,640,448, dim<<24) when positive
        std::vector<SkillDraw> page;
        bool scrollBar=false;
        int scrollX=0,scrollY=0,scrollTotal=0,scrollTop=0;
    };
    // Read when the character sub-list is built (entry of state 1) and when
    // the window closes.
    unsigned gameMode=1;   // 4c3808, tested by 17ea48
    int listId=0;          // actor+0xa14 of the operating seat, +0x32 when actor+0x23c & 0x100000

    SkillListWindow(const SkillListData& data,const MenuWidgetData& widgets,const SystemData& system);
    void enter(unsigned operatingSeat);   // 13d680 prologue; seat = 178f90()
    Result tick(const WidgetPad& pad);    // one loop body up to 112a28
    Draw draw() const;                    // 210298 and the overlay of the last visit

    int state=0,last=-1,dim=0;
    unsigned seat=0;
    GuideWindow guide;
    ListWidget list,sub;
    SkillDetail detail;
    CharacterRows characterRows{};
    CommonRows commonRows{};
private:
    const SkillListData& data_;
    const MenuWidgetData& widgets_;
    const SystemData& system_;
};
}
