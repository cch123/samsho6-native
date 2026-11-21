#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>
#include "system_data.hpp"

namespace ss6 {
// Tagged-section container written by extract_console_gallery.py:
// u32 count, then {char tag[4]; u32 size; payload}. A string table payload
// is u32 count followed by {u16 length; Shift_JIS bytes}.
class AssetSections {
public:
    explicit AssetSections(const std::filesystem::path& file);
    std::span<const uint8_t> section(std::string_view tag) const;
    std::vector<std::string> strings(std::string_view tag) const;
private:
    std::vector<uint8_t> bytes_;
    std::filesystem::path file_;
};

// The 118128 pad block of the operating seat: +0 held, +4 pressed edges,
// +8 edges plus the 117fd8 directional auto-repeat.
struct WidgetPad {
    uint32_t held=0,pressed=0,repeat=0;
};

// Tables read by the list widget and the guide window (menu_widgets.bin).
class MenuWidgetData {
public:
    struct Rect {int32_t u,v,w,h;};
    explicit MenuWidgetData(const std::filesystem::path& assets);
    std::vector<std::string> characterNames;   // 4d4bb0, index = character id 0..48
    std::vector<std::string> exNames;          // ids 0x48..0x4b, then the generic EX label
    std::array<uint8_t,53> order{};            // 59cd20: 49 list rows, then the four EX ids
    std::string undefined;                     // 6647f0, the placeholder of an unset row
    std::vector<uint8_t> messageKeys;          // 4ee870 key bytes (fe continues a key)
    std::vector<std::string> messages;
    std::vector<std::string> keyHelp;          // 5f22c0, 5f22e0, 5f22f8, 5f2318, 5f2328
    std::array<int8_t,11> backdrop{};          // 182318: kind per layout
    std::array<uint8_t,11> titleRect{};        // 181d70: title sprite per layout
    std::array<uint8_t,11> lowMessageBar{};    // 182010: 1 selects the (0,1f6)->(0,156) bar
    std::array<uint8_t,14> keyCase{};          // 181910: jump-table case per layout
    std::array<Rect,17> titleRects{};          // 4c7660, texture slot 2e
    // 1821f8: the record index of (key, sub); -1 when the key is absent.
    int message(int key,int sub) const;
    std::string_view messageText(int record) const;
    std::string_view characterName(int id) const; // 20eae0 row text, including EX ids
};

// 17f308..17f4b0: a rectangle sliding linearly between a closed and an open
// position. Field order is the original 0x34-byte layout.
struct SlidePanel {
    int x=0,y=0,left=0,duration=0,startX=0,startY=0,targetX=0,targetY=0,closing=0;
    int closedX=0,closedY=0,openX=0,openY=0;
    void configure(int cx,int cy,int ox,int oy,int frames);   // 17f410: no snap
    void reset(int cx,int cy,int ox,int oy,int frames);       // 17f428: snap closed
    void snap(int px,int py);                                 // 17f3a0
    void snapClosed() {snap(closedX,closedY);}                // 17f508
    void slide(int px,int py,int frames);                     // 17f3c0
    void open();                                              // 17f468
    void close();                                             // 17f4b0
    bool idle() const {return left<1;}                        // 17f400
    // 17f330: 2 while moving; at rest 1 when open, 0 when closed. The visit
    // on which the countdown reaches zero already reports the rest code.
    int tick();
    std::array<int,13> words() const {return {x,y,left,duration,startX,startY,targetX,targetY,closing,closedX,closedY,openX,openY};}
};

// 20dff8..20e128: cursor over [min,max) driven by the pad.
struct MenuSelector {
    enum Code {Idle=0,Moved=1,PageBack=2,PageForward=3,Confirm=4,Cancel=5,Refused=6};
    // Flag bit numbers as passed to 20e0a0.
    enum Bit {Vertical=0,Horizontal=1,Wrap=2,Negate=3,RefuseConfirm=4,RefuseCancel=5,SilentMove=7,
              Silent=8,SilentConfirm=9,SilentCancel=10,Disabled=11,MenuRows=12,CharacterRows=13,
              MediumText=15,LargeText=16,ConfirmWithoutStart=17,Locked=18};
    uint32_t flags=5;
    const std::vector<uint32_t>* disabled=nullptr;  // 20e480 bitmap, bit i of word i/32
    int min=0,max=1,step=1,current=0,page=0;
    void init();                                      // 20dff8
    void setRange(int lo,int hi,int stride,int pageRows); // 20e028
    void setCursor(int value);                        // 20e0d0
    void setFlag(unsigned bit,bool value) {flags=value?flags|1u<<bit:flags&~(1u<<bit);} // 20e0a0
    bool flag(unsigned bit) const {return flags>>bit&1;}                               // 20e088
    bool itemDisabled(int item) const;                // 20e498
    // 20e128. Tones are 1e7b70(-1, id) requests: 20 move, 0 confirm, 24 cancel/refusal.
    int update(const WidgetPad& pad,std::vector<int>& tones);
};

// Row -> character id map 1373830. It is one global shared by every list
// built with 20eae0, so the scene owns a single instance.
using CharacterRows=std::array<int16_t,55>;

// 20e570..20ee70: a scrolling text list on a slide panel. Rows are drawn at
// (panel.x+14, panel.y+14+21*r) with the large font; the selection is shown
// by the row colour only (rowColour).
struct ListWidget {
    static constexpr unsigned capacity=0x200;
    int width=0x80,height=0,visible=1,top=0,shown=0,active=0;
    SlidePanel panel;
    MenuSelector selector;
    // A default-constructed view is the original null pointer.
    std::array<std::string_view,capacity> items{};
    const MenuWidgetData* data=nullptr;
    CharacterRows* rows=nullptr;
    void init(const MenuWidgetData& tables,CharacterRows& characterRows); // 20e570
    void resize(int count,int visibleRows);                               // 20e5d8
    void setItem(unsigned index,std::string_view text);                   // 20e7f8
    void fill(std::span<const std::string> table,int visibleRows);        // 20e738
    // 20eae0: characters in list order. Kuroko (2b) follows withKuroko;
    // the others are kept by the ending-seen byte or by a clear lock byte.
    void fillCharacters(const SystemData& system,int visibleRows,int first,bool withExtra,bool withKuroko,bool byEnding);
    // The scenes extend a list by writing item[count] and count directly;
    // neither the width nor the page size is recomputed.
    void append(std::string_view text);
    void select(int id);                                                  // 20ed70
    int selected() const;                                                 // 20ee20
    int count() const {return selector.max;}
    int update(const WidgetPad& pad,std::vector<int>& tones);             // 20ee70
    bool scrollBar() const {return visible<count();}
    static uint32_t rowColour(bool active,bool selected);                 // 17db38
    static int pageTop(int code,int visibleRows,int topRow,int count);    // 17f528
    static int followTop(int cursor,int visibleRows,int topRow,int count);// 17f560
};

// 1822a0..182828: backdrop, title bar, message bar and two key-help bars.
struct GuideBar {
    int shown=0,open=0,configured=0,layout=-1;
    SlidePanel panel;
};
struct GuideKeys : GuideBar {
    int width=0,height=0,textX=0,textY=0;
    int text=-1;   // index into MenuWidgetData::keyHelp; -1 is the null pointer
};
struct GuideWindow {
    const MenuWidgetData* data=nullptr;
    int initialised=0,layout=-1,backdrop=-1;
    GuideBar title;       // drawn at panel + (10,c) with titleRects[titleRect]
    int titleRect=0;
    GuideBar message;     // text at panel + (10,c)
    int messageRecord=-1;
    GuideKeys keys,extra; // text at panel + (textX,textY)
    // 1822a0. The original also runs the menu background setup 1ce478 when
    // menuBackdrop(mode) holds; the owning scene performs that call.
    void init(const MenuWidgetData& tables);
    void setLayout(int value,unsigned seat);                  // 182318
    void tick();                                              // 1825b8
    void open();                                              // 182648
    void close();                                             // 1826b0
    void setMessage(int key,int sub) {messageRecord=data->message(key,sub);} // 1827c0
    void setExtraLayout(int value,unsigned seat) {setKeys(extra,value,seat);} // 1827d8
    void openExtra() {extra.panel.open();extra.open=extra.shown=1;}           // 1827f0
    void closeExtra() {extra.panel.close();extra.open=0;}                     // 182828
    std::string_view messageText() const {return data->messageText(messageRecord);}
    static bool menuBackdrop(unsigned gameMode);              // 17ea48
private:
    void setKeys(GuideKeys& bar,int value,unsigned seat);     // 181910
};
}
