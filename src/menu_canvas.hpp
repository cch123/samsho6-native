#pragma once
#include "console_menu.hpp"
#include "game_random.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace ss6 {
// One record per entry of the original 128-byte submission queue 68c3c0.
enum class MenuPrimitive:uint8_t {
    Flat,      // tag ff3, four vertices: 1145c0 through 114c10/105790
    Triangle,  // tag ff3, three vertices: 1143e0
    Quad,      // tag ff2, axis-aligned: 113f98 and 113690 through 1149d0
    Rotated,   // tag ff2 with the rotated corners of 1e2048
    Glyph      // tag ff1: font sprite 1090a8/108c98
};
// Texture selector of a Glyph record; Quad records carry the sheet slot.
enum class MenuFont:uint8_t { None, Half, Goth20, Goth24 };

struct MenuDrawRecord {
    MenuPrimitive kind=MenuPrimitive::Flat;
    MenuFont font=MenuFont::None;
    uint8_t slot=0;        // 1 obj0_16, 4 PS2_menu_bg00_00, 0x2e ps2_common_icon
    uint8_t blend=1;       // 3db8fc as passed to 1149d0
    bool additive=false;   // latch 348b10: queue tag 2ff2, GS ALPHA preset 348bc0 (Cd + Cs)
    uint16_t glyph=0;      // Goth20/Goth24 record number
    uint32_t colour=0;     // final queue colour word (fade, GS halving and BRIGHT applied)
    float z=0;             // queue depth; larger is nearer
    // Flat/Quad/Glyph: screen rectangle and texel rectangle. A negative w is
    // the mirrored submission of 117de8. Glyph u,v address the per-frame
    // cache page (Goth) or the half-width sheet.
    float x=0,y=0,w=0,h=0,u=0,v=0,uw=0,vh=0;
    // Triangle: three points. Rotated: four corners in 113f98 vertex order
    // (u0v0, u0v1, u1v0, u1v1); u,v,uw,vh then give the texel span.
    std::array<float,8> corner{};
};

struct MenuSheetRect { int u=0,v=0,w=0,h=0; };

// The per-frame submission list together with the renderer globals that the
// original routines read and leave modified between calls.
struct MenuDrawList {
    std::vector<MenuDrawRecord> records;
    uint32_t colour=0xffffffff; // 3db900, AARRGGBB
    int blend=1;                // 3db8fc
    bool additive=false;        // 348b10
    int depth=100;              // 3db8f4, tie breaker added by 114d88
    int glyphs=0;               // 345180, cache cursor of 10a710/10a1c0
    int textDepth=0;            // 348a8c
    float asciiDepth=-200.f;    // 3d3aac (initial and 113838 value -200), read by 113690 through 114e40
    float cursor=0;             // 12d3850, depth cursor of 17c228
    float cursorBase=0;         // 4ee54c
    // 114e80 and the per-frame reset of the glyph cache cursor.
    void beginFrame() {records.clear();depth=100;glyphs=0;}
    void resetCursor() {cursor=0;cursorBase=0;} // 17c210
};

class MenuCanvas;

// 1e1620..1e2408: the 200 drifting sprites drawn over the menu background.
class MenuBackdrop {
public:
    MenuBackdrop();
    // The library generator draws of 1ce478 in order: 1e1620 (nine per
    // sprite), the variant draw (returned for MenuChrome::enter), and the
    // population target of 1e2358/1e23a0. Also 1e2408.
    int enter(GameRandom& random);
    // 1ce570 after the picture: updates and submits. override is 582b40.
    void draw(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random,int variant,int overrideVariant=0);
    struct Sprite {
        float x=0,y=0,x0=0,y0=0,x1=0,y1=0,w=0,h=0;
        int tick=0,duration=0,frame=0,frameTick=0,framePeriod=0,angle=0,spin=0;
    };
    std::array<Sprite,200> sprites{};
    std::array<int,204> previous{},next{};   // 200..203: sentinels of the two lists
    int target=0,shown=0,clock=0;            // 584d60, 584d64, 584d68
private:
    void link(int node,int before);
    void unlink(int node);
    void respawnFalling(const MenuCanvas& canvas,Sprite& s,GameRandom& random) const;  // 1e17e8
    void respawnDrifting(const MenuCanvas& canvas,Sprite& s,GameRandom& random) const; // 1e18e0
    void submit(const MenuCanvas& canvas,MenuDrawList& list,Sprite& s,float z,float scale) const;
    void animate(Sprite& s) const;
    void intro(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random);      // 1e1a20
    void stream(const MenuCanvas& canvas,MenuDrawList& list,GameRandom& random,int variant); // 1e1c40, 1e1e18
};

class MenuCanvas {
public:
    explicit MenuCanvas(const std::filesystem::path& assets);

    // 3ebf18 bit 1, 3ec734 (0..256) and the colour word 3ec730 (AARRGGBB).
    // Colour arguments are AARRGGBB; MenuDrawRecord::colour is the queue's AABBGGRR.
    void setFade(bool enabled,int level,uint32_t colour);
    void setBrightness(int value) {brightness_=value;}  // 43d064, 0x38..0x100

    // --- primitives ---------------------------------------------------
    float depth(MenuDrawList& list,float z) const;                                   // 114d88
    void rectangle(MenuDrawList& list,int x,int y,int w,int h,uint32_t colour,float z) const; // 1145c0
    void triangle(MenuDrawList& list,float x0,float y0,float x1,float y1,float x2,float y2,
                  float z,uint32_t colour) const;                                    // 1143e0
    // 113f98: colour and blend come from the list globals.
    void sprite(MenuDrawList& list,int slot,float x,float y,float z,float w,float h,
                float u,float v,float uw,float vh) const;
    // 117de8 (flags 100 hides, 200 selects blend 0). Colour 0 keeps 3db900
    // and latches the additive preset for this sprite (1142b8/1142c8).
    void sprite(MenuDrawList& list,const MenuSheetRect& rect,int slot,unsigned flags,uint32_t colour,
                bool mirror,float x,float y,float z,float w,float h) const;
    // 117a00.
    void picture(MenuDrawList& list,const MenuSheetRect& rect,int slot,unsigned flags,uint32_t colour,
                 float x,float y,float z) const;
    // 1e2048.
    void rotated(MenuDrawList& list,int slot,int degrees,float x,float y,float z,float w,float h,
                 float u,float v,float uw,float vh,float scale) const;
    void ascii(MenuDrawList& list,std::string_view text,int x,int y,uint32_t colour) const; // 1135e8
    void text20(MenuDrawList& list,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const; // 10a460
    void text24(MenuDrawList& list,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const; // 109f08
    void marker(MenuDrawList& list,std::string_view text,int x,int y,int frame) const;   // 1cf8f8
    void dialog(MenuDrawList& list,int cursor,int kind,bool neoGeoLand=false) const;     // 1cf598

    // --- chrome -------------------------------------------------------
    void backgroundPicture(MenuDrawList& list,bool withOverlay=true) const;              // 117a00 call of 1ce570 / 1ce628
    void background(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                    int overrideVariant=0) const;                                        // 1ce570
    // Drawing half of 1ce660 (legend=true) or 1ce878; the caller advances the counters.
    void frame(MenuDrawList& list,const MenuChrome& chrome,bool showPage,int page,int pages,bool legend=true) const;
    void legend(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const;          // 1ced08
    void legendConfirm(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const;   // 1cee68
    void legendCancel(MenuDrawList& list,const MenuChrome& chrome,int x,int y) const;    // 1cefc8
    void pageIndicator(MenuDrawList& list,const MenuChrome& chrome,int x,int y,int page,int pages) const; // 1cf2a8
    // Page title plate (1cfdb0 and its per-page copies): banners()[index].
    void banner(MenuDrawList& list,const MenuSheetRect& rect,int alpha,float x=16,float y=28,float z=-350) const;
    // Bottom help line (1cff40 and its per-page copies); advances the marquee.
    void helpText(MenuDrawList& list,MenuChrome& chrome,std::string_view sjis,bool scroll,int alpha,
                  int y=0x198,float z=-350) const;

    std::span<const MenuSheetRect> icons() const {return icons_;}       // 4c7510
    std::span<const MenuSheetRect> banners() const {return banners_;}   // 4c7660
    std::span<const MenuSheetRect> petals() const {return petals_;}     // 4c7960
    const std::string& string(unsigned index) const {return strings_.at(index);}

    // Resolves the list in ascending depth, submission order within a depth.
    void rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const;
    // The 16-entry glyph CLUT. 112f30 rebuilds it per scene (the arcade walk-in uses black ink);
    // without an override the menu default from menu_canvas.bin applies.
    using TextClut=std::array<std::array<uint8_t,4>,16>;
    void setTextClut(const TextClut& clut) {textClut_=clut;}
    void resetTextClut() {textClut_=defaultTextClut_;}

    // Constants of the overlay (65ae58..65ae84) for MenuBackdrop.
    float constant(unsigned index) const {return floats_.at(index);}
    std::array<float,2> trig(int degrees) const {return trig_.at(unsigned(degrees));}

private:
    uint32_t fade(uint32_t colour) const;                       // 117288
    void fade(int& r,int& g,int& b) const;                      // 117318
    uint32_t flatColour(uint32_t colour) const;                 // 114c10 + 105790
    uint32_t quadColour(uint32_t colour,int blend) const;       // 1149d0 + 108118/1085e0
    void quad(MenuDrawList& list,int slot,uint32_t colour,int blend,float z,float x,float y,float w,float h,
              float u,float v,float uw,float vh) const;
    void glyph(MenuDrawList& list,MenuFont font,int record,int x,int y,int w,int h,int u,int v,
               int r,int g,int b,int alpha) const;              // 1090a8
    void text(MenuDrawList& list,bool large,std::string_view sjis,int x,int y,int r,int g,int b,int alpha) const;
    void legendIcons(MenuDrawList& list,const MenuChrome& chrome,unsigned table,unsigned first,unsigned count,
                     int x,int y,bool confirm,bool cancel) const;
    void label(MenuDrawList& list,unsigned text,float z,int x,int y,int alpha) const;   // 1cf178, 1cf210, 1cf500
    void rebuildPalettes();

    std::array<std::array<int,11>,7> bands_{};
    struct Legend { std::array<int,4> x{}; float z=0; };
    std::array<Legend,3> legends_{};
    std::vector<MenuSheetRect> icons_,banners_,petals_;
    std::array<int,6> backgroundRect_{};
    std::array<float,30> floats_{};
    std::vector<std::string> strings_;
    std::array<int,2> dialogX_{};
    std::array<std::array<uint8_t,4>,16> textClut_{},defaultTextClut_{};
    std::array<std::array<float,2>,360> trig_{};
    std::vector<uint8_t> half_,index20_,index24_;
    std::vector<uint16_t> glyphIndex_;
    unsigned glyphCount_=0;
    std::vector<uint8_t> font_,background_,icon_;
    std::array<uint16_t,256> backgroundSource_{};
    std::array<std::array<uint8_t,4>,256> fontColours_{},iconSource_{},backgroundColours_{},iconColours_{};
    bool fadeEnabled_=false;
    int fadeLevel_=0;
    uint32_t fadeColour_=0;
    int brightness_=256;
};
}
