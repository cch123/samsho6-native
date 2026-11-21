#pragma once
#include "color_edit.hpp"
#include "menu_canvas.hpp"
#include "spirits_edit.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace ss6 {
// Drawing of SPIRITS EDIT (task 13ada0) and COLOR EDIT (task 13b1c8): the
// 17cxxx/17dxxx box renderers, the 17e228/17e428 text layer, the screen
// frame 1822a0 and the list, panel, swatch and slider widgets. Everything is
// appended to a MenuDrawList in original submission order.

// 17c260: the 0x30-byte box descriptor shared by the box renderers.
struct EditBox {
    int style=0;                 // +0: 0 single border, 1 triple, 2 quintuple
    int value=0;                 // +4: filled length of the 17d370 bar
    float w=1,h=1,x=0,y=0;       // +c, +10, +14, +18
    uint32_t outer=0xff000000;   // +1c
    uint32_t inner=0xffffffff;   // +20
    uint32_t fill=0x80ffffff;    // +24
    uint32_t bar=0xffffffff;     // +28
    uint32_t track=0xff808080;   // +2c
};

// Globals of the text layer that persist between calls and frames.
struct EditPen {
    uint32_t colour=0xffffffff;  // 4ee548, set by 17db28/17db38
    bool front=false;            // 4ee85c (17e1f0): text layer 1000
    bool middle=false;           // 4ee860 (17e200): text layer 520
};

// edit_art.bin (extract_edit_art.py) and texture slot 5.
class EditArtAssets {
public:
    explicit EditArtAssets(const std::filesystem::path& assets);
    struct Icon {int u=0,v=0,w=0,h=0,slot=0;};
    enum Text {KeysDefault,KeysRestore,KeysReset,KeysCancel,KeysCopy,KeysSelect,KeysSelectConfirm,Space,Exit,Cost,Refund,
               OneDigit,TwoDigits,DialogDefault,Yes,No,ResetQuestion,ColourRow,CopyRow=ColourRow+5,TextCount=CopyRow+2};
    float f(uint32_t address) const;                 // float constant stored at that ELF address
    std::array<double,2> slant{};                    // 5f1f80, 5f1f88
    std::vector<Icon> icons;                         // 4ee6b8
    std::array<MenuSheetRect,17> titles{};           // 4c7660
    Icon summaryPlate;                               // 4c9120
    std::array<uint8_t,6> shade{};                   // 4ee868
    uint32_t initialTextColour=0;                    // 4ee548
    std::array<int,5> colourButtons{};               // 59cd58
    std::vector<std::string> strings;
    const std::string& text(Text t) const {return strings.at(size_t(t));}
    std::vector<uint8_t> gauge;                      // ps2_gage_1_2_3_all.tex, 1024x1024 indices
    std::array<std::array<uint8_t,4>,256> gaugeSource{};  // .pal as 116478 stores it at bank 0x300
private:
    std::vector<std::pair<uint32_t,float>> floats_;
};

// 1822a0..182828: backdrop, title bar, message bar and two key-hint bars of
// the edit scenes. The logic modules report its requests; this struct holds
// the state the draw routine 182600 reads.
struct EditFrame {
    struct Bar {
        int shown=0,open=0,configured=0,layout=-1;   // +0, +4, +8, +40
        EditSlide slide;                             // +c
    };
    struct Keys:Bar {
        int w=0,h=0,dx=0,dy=0;                       // +48..+54
        bool hasText=false;std::string text;         // +58
    };
    int initialised=0,layout=-1;                     // +0, +4
    int backdrop=-1;                                 // +8: -1 none, 0 picture 1ce628, 1 animated 1ce570, 2 flat blue
    Bar title;int titleRect=0;                       // +10; +58 index into 4c7660
    bool hasTitleText=false;std::string titleText;   // +5c (181e68)
    Bar message;bool hasMessage=false;std::string messageText; // +60; +a8
    Keys keys,extra;                                 // +ac, +108
    // 181c30 skips a key bar of layout 0 while the mode word 4c3808 is 0x11.
    // Neither edit scene uses layout 0; the owner of such a scene sets this.
    bool mode11=false;

    // seat is 178f90(): several key-hint layouts slide in from that seat's side.
    EditFrame(const EditArtAssets& art,const EditWidgetAssets& widgets,unsigned seat=0);
    void setLayout(int value);                       // 182318
    void tick();                                     // 1825b8, once per task visit before any request
    void open();                                     // 182648
    void close();                                    // 1826b0
    void setMessage(int id,int sub);                 // 1827c0
    void setExtraLayout(int value) {setKeys(extra,value);} // 1827d8
    void openExtra();                                // 1827f0
    void closeExtra();                               // 182828
    void setKeyText(const std::string& text) {keys.text=text;keys.hasText=true;} // 181c10 on +ac
    void hideTitle() {title.slide.slideOut();title.open=0;}  // 17f4b0(frame+1c); frame+14 = 0

    // COLOR EDIT: apply the requests of one ColorEdit::tick in order.
    void apply(const ColorEditEvent& event);
    // SPIRITS EDIT: mirror the 182648/1826b0/1827c0/182268 calls of the visit
    // that just ran (call after SpiritsEdit::tick).
    void follow(const SpiritsEdit& scene);
private:
    void setTitle(int value);                        // 181d70
    void setMessageLayout(int value);                // 182010
    void setKeys(Keys& bar,int value);               // 181910
    const EditArtAssets* art_;
    const EditWidgetAssets* widgets_;
    unsigned seat_=0;
    bool spiritsOpen_=false;
};

// A text list as 20ef38 reads it (list widget 20e570).
struct EditListView {
    int width=0,height=0,visibleRows=1,scroll=0,visible=0,active=0,x=0,y=0,count=1,cursor=0;
    uint32_t flags=0;                                // selector flags: bit 16 large rows, bit 15 medium rows
    std::vector<std::string_view> rows;              // rows[i].data() == nullptr is the original NULL item
};

class EditArt {
public:
    EditArt(const std::filesystem::path& assets,const MenuCanvas& canvas);
    // Mirror every MenuCanvas::setFade call: 116588 fades the CLUT of slot 5 too.
    void setFade(bool enabled,int level,uint32_t colour);

    // Per-frame drawing context. seat is 178f90() (the operating seat tints
    // the borders). option7e is option byte 7e (43d0d6): while it is zero,
    // icon 2d is not drawn and an "MS" token ends a markup line.
    struct Context {
        MenuDrawList& list;
        EditPen& pen;
        unsigned seat=0;
        bool option7e=true;
    };
    // --- depth cursor and boxes ----------------------------------------
    float layer(Context& c,uint32_t constant) const;                               // 17c228(4ee54c - K)
    void focus(Context& c,EditBox& box,bool focused) const;                        // 17c2d0
    void cursorColours(Context& c,EditBox& box,bool focused) const;                // 17c370
    void border(Context& c,uint32_t colour,float x,float y,float w,float h,float t) const;        // 17c3d8
    void diamondBorder(Context& c,uint32_t colour,float x,float y,float w,float h,float t) const; // 17c560
    void window(Context& c,const EditBox& box,int gutter) const;                   // 17c718
    void diamond(Context& c,const EditBox& box) const;                             // 17cb50
    void tab(Context& c,const EditBox& box) const;                                 // 17ce58
    void slider(Context& c,const EditBox& box) const;                              // 17d370
    void brackets(Context& c,const EditBox& box) const;                            // 17d790
    void arrow(Context& c,const EditBox& box,bool left) const;                     // 17dd88
    void shade(Context& c,float x,float y,float z,float w,float h) const;          // 17eed8
    void scrollBar(Context& c,const EditBox& box,int count,int visible,int top,int scale) const; // 17f090
    // 1147d8: flat quadrilateral through four float points (two triangle
    // records sharing one queue depth; see docs/mode-edit-art.txt).
    void quad(Context& c,uint32_t colour,float x0,float y0,float x1,float y1,float x2,float y2,
              float x3,float y3,float z) const;
    // --- text and icons -------------------------------------------------
    static uint32_t rowColour(bool active,bool selected);                          // 17db38
    void text(Context& c,std::string_view sjis,int x,int y,int mode) const;        // 17e228: 0 ascii, 1 20-dot, 2 24-dot
    // 17e428. Returns the offset behind a "CR" token, or npos at the end.
    size_t markup(Context& c,std::string_view sjis,int mode,bool plain,float x,float y) const;
    int sheet(Context& c,const EditArtAssets::Icon& rect,float x,float y,float z) const; // 17df90
    int icon(Context& c,int index,float x,float y,float z) const;                  // 17e038
    // --- widgets --------------------------------------------------------
    // 182600. Backdrop kind 1 needs the animated page background.
    void frame(Context& c,const EditFrame& frame,MenuBackdrop* backdrop=nullptr,GameRandom* random=nullptr,
               const MenuChrome* chrome=nullptr) const;
    void listMenu(Context& c,const EditListView& view) const;                      // 20ef38
    void buttonListMenu(Context& c,const EditListView& view) const;                // 20f360
    void spiritPanel(Context& c,const SpiritPanel& panel,bool raised) const;       // 20d2e8
    void spiritEditor(Context& c,const SpiritEditor& editor) const;                // 20d9f8
    void spiritSummary(Context& c,int x,int y,std::span<const SpiritIcon> icons) const; // 17eac8
    void partSelector(Context& c,const ColorEdit& scene) const;                    // 20c038
    void swatches(Context& c,const ColorEdit& scene) const;                        // 20f680
    void sliders(Context& c,const ColorEdit& scene) const;                         // 20fb58
    void dialog(Context& c,const ColorEdit::Panel& panel,std::string_view message) const; // 2129d0

    // Resolves a list like MenuCanvas::rasterise, adding texture slot 5.
    void rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const;

    const EditArtAssets& assets() const {return assets_;}
    const MenuCanvas& canvas() const {return *canvas_;}
private:
    float f(uint32_t address) const {return assets_.f(address);}
    void tabRow(Context& c,int x,int y,int index,int part,int character,int active,bool selected) const; // 20c1a0
    void listBody(Context& c,const EditListView& view,bool large) const;           // 20f1c8
    void rebuildGauge();
    EditArtAssets assets_;
    const MenuCanvas* canvas_;
    std::array<std::array<uint8_t,4>,256> gaugeColours_{};
    bool fadeEnabled_=false;int fadeLevel_=0;uint32_t fadeColour_=0;
};

// List views of the two scenes (20e5d8/20e7f8 sizes; rows of 20eae0).
EditListView editListView(const EditListMenu& menu);
EditListView colorEditCharacterList(const ColorEdit& scene,const EditWidgetAssets& widgets);
EditListView colorEditColourList(const ColorEdit& scene,const EditArtAssets& art);
EditListView colorEditCopyList(const ColorEdit& scene,const EditArtAssets& art);

// Whole pages in the draw order of the two tasks. The caller owns
// MenuDrawList::beginFrame; both functions start with 17c210.
void drawSpiritsEdit(const EditArt& art,MenuDrawList& list,EditPen& pen,const SpiritsEdit& scene,
                     const EditFrame& frame,unsigned seat,bool option7e=true);

// ---------------------------------------------------------------------
// COLOR EDIT preview: the three objects of 13bf00 / 13bfd0 / 13c4f8.
struct EditPreviewObject {
    enum Kind {Portrait,Sprite,CheckPose};
    Kind kind=Portrait;
    bool hidden=true;          // object flag 2 (+104)
    bool flip=false;           // bit 31 of +38
    int character=0;           // resource slot 1 fighter (Sprite/CheckPose) or 11d668 portrait id
    int action=-1,record=0;    // 11d908 action, zero-based start record (+28)
    float x=0,y=0;             // +40, +44
    float depth=0;             // 11dff8 argument: 17c228(4ee54c - 900)
    uint32_t paletteKey=0;     // +20: stock key for the portrait, key | 10000 for the sprites
};
// The three per-visit object updates in task order (portrait, sprite, check
// pose). Each drawn object takes one 17c228 step from the depth cursor, which
// shifts every later widget depth of the visit.
std::array<EditPreviewObject,3> colorEditPreview(const ColorEditTables& tables,const ColorEdit& scene,
                                                 const EditArt& art,MenuDrawList& list);
// The whole page in task order: 17c210, the preview updates above, then the
// widget draws. The returned objects are a separate submission to the
// fighter renderer; they are not part of the MenuDrawList.
std::array<EditPreviewObject,3> drawColorEdit(const EditArt& art,MenuDrawList& list,EditPen& pen,const ColorEdit& scene,
                                              const ColorEditTables& tables,const EditFrame& frame,
                                              const EditWidgetAssets& widgets,unsigned seat,bool option7e=true);

// 115d40 for every palette key, including the owner bits 10000 / 20000 that
// select an edited table, over the 24-entry cache 439a48 / 439aa8 / 439b08
// and the CLUT store 43ab70. It can own that state or be bound to the fighter
// renderer's (EffectPalettes and CharacterPaletteBank::raw16 / format), so
// that the rows COLOR EDIT pokes are the rows the preview sprite samples.
class EditPaletteBank final:public EditPaletteCache {
public:
    using Words=std::array<std::array<uint32_t,24>,3>;   // identity, reference, busy (= EffectPalettes)
    // palAll is the resident pal_all.bin arena; 115f08 clears the first
    // colour of a group in its SOURCE table, so every table is mutable.
    EditPaletteBank(const ColorEditTables& tables,SystemData& data,std::span<uint8_t> palAll);
    EditPaletteBank(const ColorEditTables& tables,SystemData& data,std::span<uint8_t> palAll,Words& words,
                    std::span<uint16_t,1024> raw16,std::span<uint32_t,1024> format);
    void setRuntime(unsigned side,std::span<uint8_t> table) {runtime_[side&1]=table;}  // 3ec740 / 3f28c0, 6180 bytes
    void setNetwork(unsigned side,std::span<uint8_t> banks) {network_[side&1]=banks;}  // 1232c80 / 1232ce0, 60 bytes
    void reset() override;                                         // 1159d0
    void beginFrame() {words_->at(1).fill(0);}                     // 113aa8: reference words age every frame
    int resolve(uint32_t key,int bank) override;                   // 115d40: CLUT row 5dd5c8[entry], or -1
    void poke(int row,unsigned entry,uint16_t colour) override;    // 43ab70[row*16 + entry]
    std::span<const uint16_t,16> colours(int row) const;           // A1B5G5R5 as uploaded by 116478
    const Words& words() const {return *words_;}
    std::span<const uint16_t,1024> store() const {return raw16_;}
private:
    const ColorEditTables& tables_;
    SystemData& data_;
    std::span<uint8_t> palAll_;
    Words ownWords_{};
    std::array<uint16_t,1024> ownRaw16_{};
    std::array<uint32_t,1024> ownFormat_{};
    Words* words_;
    std::span<uint16_t,1024> raw16_;
    std::span<uint32_t,1024> format_;
    std::array<std::span<uint8_t>,2> runtime_{},network_{};
};
}
