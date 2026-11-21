#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
#include "console_menu.hpp"
#include "game_random.hpp"
#include "menu_widgets.hpp"
#include "system_data.hpp"

namespace ss6 {
// Scene entry addresses as passed to 1252f0(1, 0, destructor, entry).
enum class GalleryScene : uint32_t {
    Title=0x127940,TopMenu=0x1d22f8,Ending=0x182968,SoundTest=0x13e090,Illustrations=0x13ed98
};
// Requests a gallery scene makes of the rest of the program, in call order.
struct GalleryEvent {
    enum Kind : int {
        Tone=1,           // 1e7b70(a, b): a = -1 is the common bank
        BankTone=2,       // 1e7ba0(a, b)
        LoadBank=3,       // 1e79c8(a, b): sample bank b into group a
        BattleSound=4,    // 1e8298(a, b, c): command b of character c (SoundSelection::act, mode 13/14)
        Voice=5,          // 1e7d60(a, b); c = narration language byte 43d055 in force
        Music=6,          // 214060(a, b); c = BGM variant byte 43d056 in force
        MusicStop=7,      // 1e7ad0
        EffectsStop=8,    // 1e7b40
        NarrationCheck=9, // 213238; c = language byte in force
        NarrationLoad=10, // 213180; c = language byte in force
        Scene=11,         // 1252f0(1, 0, a, b)
        GameDataReset=12, // 124d50: the whole g_GameData block, including the mode word
        EndingChosen=13   // 182a98(a): play the ending of character a
    };
    int kind=0,a=0,b=0,c=0;
};

// Tables of the four gallery scenes (console_gallery.bin).
class GalleryData {
public:
    struct SoundRecord {int16_t key;uint8_t type;uint16_t id;};
    struct LyricGlyph {uint16_t code;int32_t time;};
    struct LyricLine {int32_t base;std::vector<LyricGlyph> glyphs;};
    explicit GalleryData(const std::filesystem::path& assets);
    std::vector<std::string> topLabels,topHelp,extraIllustrations,categories,bgmVersions,languages;
    std::vector<uint8_t> topHelpScroll;
    std::string common,endingHelp,lyricKeys;
    std::vector<std::string> bgmLabels,voiceLabels,effectLabels,narrationLabels;
    std::vector<SoundRecord> commonSounds,bgm,narration,characterSounds;
    std::array<std::vector<LyricLine>,2> lyrics;
};

// The sub-scenes keep the original stack layout: their lists point at the
// row map stored beside them, so a live scene object must not be copied.
struct GalleryPinned {
    GalleryPinned()=default;
    GalleryPinned(const GalleryPinned&)=delete;
    GalleryPinned& operator=(const GalleryPinned&)=delete;
};

// 1d22f8 / 1d2380: the four-row gallery menu. `row` survives the sub-scenes;
// only the mode menu clears it (reset).
struct GalleryTopMenu {
    int row=0;            // 582d88
    int leaving=0;        // 582d8c: set by any scene request, stops pad sampling
    int operatingSeat=0;  // 12d35c4: the seat that confirmed; polled alone by the sub-scenes
    int alpha=0;          // 1cf738 after the frame advance
    std::array<int,2> helpX{0x10,0};
    std::vector<GalleryEvent> events;
    void reset() {row=0;}                                                // 1d2610
    void enter(const GalleryData& data,MenuChrome& chrome,GameRandom& random);
    void tick(const GalleryData& data,MenuChrome& chrome,const std::array<MenuPad,2>& pads);
private:
    void leave();                                                        // 1d2508
};

// 13ed98 / 13edf0: character list plus six fixed pictures; gl_NN image id
// = character id, or 49..54 for the fixed rows.
struct IllustrationViewer : GalleryPinned {
    GuideWindow guide;
    ListWidget list;
    CharacterRows rows{};
    unsigned seat=0;
    int state=0,previous=-1;   // 0 list, 1 full view, -1 leaving, -2 scene requested
    int hideUi=0,centreX=0x140,centreY=0xe0,size=0x1b8;
    int characterRows=0;       // list rows that map to characters
    std::vector<GalleryEvent> events;
    void enter(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
               const GalleryData& data,MenuChrome& chrome,GameRandom& random);
    void tick(const WidgetPad& pad);
    // Draw state. The picture is the whole 1024x1024 texture scaled to
    // size x size at (imageX, imageY) over a (size+6)^2 backing at -3,-3.
    bool imageVisible() const {return previous==1;}
    int imageId() const;
    int imageX() const {return centreX-size/2;}
    int imageY() const {return centreY-size/2;}
    bool uiVisible() const {return !(hideUi&&previous==1);}   // otherwise backdrop only
};

// 13e090 / 13e0e8: category, second level, track list, lyrics overlay.
struct SoundTest : GalleryPinned {
    struct LyricDraw {uint16_t code;int x,y;uint8_t r,g,b;};
    GuideWindow guide;
    std::array<ListWidget,3> lists;  // category, second level, tracks
    CharacterRows rows{};
    unsigned seat=0;
    int state=0,previous=-1;         // 0..3 as above, -1 leaving, -2 scene requested
    int lyricAlpha=0,lyricCounter=0,lyricSet=-1;
    int lyricDrawCounter=0;          // the counter value 13dc98 drew this visit
    std::array<int16_t,ListWidget::capacity> ids{};   // 128a1c0: request id per track row
    std::vector<GalleryEvent> events;
    void enter(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
               const GalleryData& data,MenuChrome& chrome,GameRandom& random);
    // streamPlaying is 213d70(): the driver's "BGM stream running" word.
    void tick(const WidgetPad& pad,bool streamPlaying);
    // 13dc98 glyph pass of this visit; empty unless the overlay
    // is visible. The dim rectangle uses alpha/8, the key bar sits at
    // y = 0x188 + (0xff - lyricAlpha).
    std::vector<LyricDraw> lyricGlyphs() const;
private:
    const SystemData* system_=nullptr;
    const GalleryData* data_=nullptr;
    bool musicRequested_=false;
    void fillSecond(int category);
    void fillTracks(int category,int character,bool commonRow);
    void play(int category,int second,int character,bool commonRow);
    bool lyricWrap() const;
};

// 182968 gallery branch, 182ce0 and the selection UI 13f4a8. The ending
// script engine (182a98) is outside this class: tick() reports the chosen
// character and stops; after playback the owner calls beginSelection again.
struct EndingViewer : GalleryPinned {
    GuideWindow guide;
    ListWidget list;
    CharacterRows rows{};
    unsigned seat=0;
    int state=0,previous=-1;   // 0 list, -1 leaving, -2 scene requested
    int countdown=0x10;
    int character=0;           // 182ce0 s0: the last ending played, preselected
    bool chosen=false;         // the selection returned; playback owns the scene
    bool fromGallery=true;
    std::vector<GalleryEvent> events;
    void enterScene(const GalleryData& data,MenuChrome& chrome,GameRandom& random);
    void beginSelection(unsigned operatingSeat,const SystemData& system,const MenuWidgetData& widgets,
                        MenuChrome& chrome,GameRandom& random);
    void tick(const WidgetPad& pad);
};
}
