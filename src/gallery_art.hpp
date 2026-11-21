#pragma once
#include "console_gallery.hpp"
#include "menu_canvas.hpp"
#include "menu_widgets.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string_view>
#include <vector>

namespace ss6 {
// Drawing of the window library 17c210..182600 / 20ef38 and of the four
// GALLERY MODE pages, as MenuDrawList submissions. The logic modules
// (console_gallery, menu_widgets) own every state word read here.
class GalleryArt {
public:
    // Order of FLOATS in extract_gallery_art.py.
    enum Constant:unsigned {
        CursorStep,BorderZ,FrameZ,Five,Two,Ten,Seven,Fourteen,One,Twenty,Twelve,TwentyFour,Thirteen,TwentySix,
        SmallZ,SmallW,SmallVh,SmallH,SmallUw,LabelFront,LabelMiddle,LabelZ,MarkupFront,MarkupMiddle,MarkupZ,
        GlyphDrop,IconInset,ExitDrop,PictureSpan,ScrollZ,ScrollFour,ScrollEight,ScrollTwo,ScrollTwelve,ScrollSix,
        BackdropZ,KeysZ,TitleZ,TitleW,TitleH,TitleSpriteZ,MessageZ,MessageW,MessageH,ScrollW,SmallInset,RowInset,
        TopPlateX,TopPlateY,TopPlateZ,TopRowsZ,TopHelpZ,LyricTextZ,LyricZ,LyricBarX,LyricBarW,LyricBarH,LyricKeysX,
        ViewerBackingZ,ViewerPictureZ,ConstantCount
    };
    // 17c260: the 0x30-byte window frame record.
    struct Frame {
        int style=0;
        float w=1,h=1,x=0,y=0;
        uint32_t border=0xff000000,line=0xffffffff,fill=0x80ffffff;
    };
    static constexpr size_t noBreak=size_t(-1);

    GalleryArt(const MenuCanvas& canvas,const std::filesystem::path& assets);

    // --- globals of the library ---------------------------------------
    unsigned seat=0;                 // 178f90(): frame tint; 12d35c4 in game modes 13/14
    int gameMode=13;                 // 4c3808: 17ea48 and the key bar of layout 0
    bool extraIcons=false;           // byte 43d0d6 (g_GameOption+7e): "MS" text and the "SC" icon
    uint32_t textColour=0xffffffff;  // 4ee548, AARRGGBB (17db28 / 17db38)
    bool frontText=false;            // 4ee85c (17e1f0): text layer 1000
    bool middleText=false;           // 4ee860 (17e200): text layer 520

    // --- primitives ---------------------------------------------------
    float constant(Constant index) const {return floats_[index];}
    // 17c228([4ee54c] - constant): each call sits one step in front of the last.
    float cursor(MenuDrawList& list,Constant layer) const;
    void softBar(MenuDrawList& list,float x,float y,float z,float w,float h) const;                  // 17eed8
    void border(MenuDrawList& list,uint32_t colour,float x,float y,float w,float h,float t) const;   // 17c3d8
    void tint(Frame& frame,bool focused) const;                                                      // 17c2d0
    void frame(MenuDrawList& list,const Frame& frame,int gutter) const;                              // 17c718
    void scrollBar(MenuDrawList& list,const Frame& frame,int count,int visible,int top,int scale=1) const; // 17f090
    void label(MenuDrawList& list,std::string_view text,int x,int y,int mode) const;                 // 17e228
    void smallText(MenuDrawList& list,std::string_view text,int x,int y) const;                      // 17db70("%s")
    // 17e428. Returns the offset behind a "CR" token (the text depth is then
    // left modified, as in the original) or noBreak at the end of the text.
    size_t markup(MenuDrawList& list,std::string_view text,int mode,bool plain,float x,float y) const;
    int sheet(MenuDrawList& list,int slot,const MenuSheetRect& rect,float x,float y,float z) const;  // 17df90
    int icon(MenuDrawList& list,int index,float x,float y,float z) const;                            // 17e038
    std::span<const MenuSheetRect> icons() const {return icons_;}                                    // 4ee6b8

    // --- widgets ------------------------------------------------------
    void drawList(MenuDrawList& list,const ListWidget& widget);                                      // 20ef38
    // 1817f0. kind 0: 1ce628; kind 1: 1ce570; kind 2: the dark blue plane.
    void drawBackdrop(MenuDrawList& list,const GuideWindow& guide,MenuBackdrop& backdrop,GameRandom& random,
                      const MenuChrome& chrome) const;
    void drawGuide(MenuDrawList& list,const GuideWindow& guide,MenuBackdrop& backdrop,GameRandom& random,
                   const MenuChrome& chrome);                                                        // 182600
    // 17eda0: binds picture gl_NN to slot 5 and submits it size x size.
    void picture(MenuDrawList& list,int id,int size,float x,float y,float z);

    // --- pages --------------------------------------------------------
    // 1d2380 draw half. `before` is the MenuChrome as it was before
    // GalleryTopMenu::tick: 1ce660 draws the bands and the legend before it
    // advances the counters that tick() has already advanced.
    void drawGalleryTop(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& before,
                        const GalleryTopMenu& top,const GalleryData& data) const;
    void drawIllustrationViewer(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                                const IllustrationViewer& viewer);                                   // 13edf0
    void drawSoundTest(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                       const SoundTest& sound,const GalleryData& data);                              // 13e0e8
    void drawLyrics(MenuDrawList& list,const SoundTest& sound,const GalleryData& data);              // 13dc98
    // 13f4a8. Nothing is drawn on the visit that returns the selection.
    void drawEndingSelect(MenuDrawList& list,MenuBackdrop& backdrop,GameRandom& random,const MenuChrome& chrome,
                          const EndingViewer& ending);

    // --- presentation -------------------------------------------------
    // Same arguments as MenuCanvas::setFade; 116588 interpolates the picture CLUT too.
    void setFade(bool enabled,int level,uint32_t colour);
    int boundPicture() const {return picture_;}   // 12d3854; -1 after forget()
    void forget() {picture_=-1;}                  // 17ed90
    // MenuCanvas::rasterise extended by the picture sheet of slot 5.
    void rasterise(const MenuDrawList& list,std::span<uint8_t> rgba) const;

private:
    void bind(int id);
    void rebuildPalette();
    float layer(MenuDrawList& list,Constant front,Constant middle,Constant back) const;
    Constant textLayer(Constant front) const;

    const MenuCanvas& canvas_;
    std::filesystem::path assets_;
    std::array<float,ConstantCount> floats_{};
    std::vector<MenuSheetRect> icons_;
    std::array<uint8_t,6> edge_{};
    std::string space_,exit_;
    int picture_=-1;
    std::vector<uint8_t> indices_;
    std::array<uint16_t,256> source_{};
    std::array<std::array<uint8_t,4>,256> colours_{};
    bool fadeEnabled_=false;
    int fadeLevel_=0;
    uint32_t fadeColour_=0;
};

// 1ce478 as the gallery scenes run it. The logic modules draw a single
// library random number for the background variant; the original draws 1802
// (MenuBackdrop::enter). Call with the library seed saved before the logic
// module's enter(): the generator is rewound, the overlay is initialised and
// the variant is taken from the 1801st draw.
void enterGalleryBackdrop(MenuBackdrop& backdrop,MenuChrome& chrome,GameRandom& random,uint64_t seedBeforeEnter);
}
