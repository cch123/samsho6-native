#pragma once
#include "arcade_run.hpp"
#include "menu_canvas.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string_view>
#include <vector>

namespace ss6 {
// The battle's ending playback (ending_playback.hpp) is also named
// EndingPlayback; this inline namespace keeps the two classes distinct.
inline namespace arcade_scene {
// Per-character ENDING (scene 182968, playback 182a98) and STAFF ROLL (19c1c8).
// The 50 script functions behind 4eefe8 are branch-free call sequences; they
// are data here (arcade_ending.bin, work/ss6/extract_arcade_ending.py).

// Asset opcode order (PRIMITIVES of the extractor).
enum class EndingOp:uint32_t {
    Background,       // 1a4a98(n)
    BackgroundSwitch, // 1a1878(n): 112a70(fa1), 1a4a98(n)
    Camera,           // 122e98(x, y, z)
    CameraOffset,     // 122eb8(x, y, z)
    ObjectStart,      // 120378(object, bank, sub, x, y, flags)
    ObjectAction,     // 120390(object, sub)
    ObjectVelocity,   // 120428(object, vx, vy)
    ObjectColour,     // 120438(object, argb, alpha step, red step, green step, blue step)
    ObjectPalette,    // 1a18a8(k)
    Music,            // 1e7c00(id, flag)
    Sound,            // 1e7b70(a0, id)
    CameraDelta,      // 1a1728(dx, dy)
    Wait,             // 1a1740(n)
    WaitB,            // 1a1780(n): byte-identical copy of 1a1740
    TextColours,      // 112f30(glyph, shadow)
    Portrait,         // 1a18e0(side, id)
    MessageClear,     // 1a1aa8()
    MessageAdd,       // 1a1ad8(text)
    MessageShow,      // 1a1b00(renderer 1..5)
    FadeIn,           // 1a17e8(colour, step)
    FadeOut,          // 1a1830(colour, step)
    Flash,            // 1a17c0(colour, frames)
    RollClear,        // 1a1e98()
    RollAdd,          // 1a1ea8(text)
    RollShow,         // 1a1fe8(hold)
    RollScroll,       // 1a1ed0(extra)
    FadeWrite,        // 117108(colour, level)
    FadeMode,         // 1170c8(mode)
    FadeRange,        // 117180(first, count, tone)
    PaletteBake,      // 1174b8(first, count)
    PaletteSave,      // 117438()
    ObjectStore,      // inline sw: object, field offset, value
    Count
};
struct EndingRecord {
    EndingOp op=EndingOp::Count;
    std::array<uint32_t,6> a{};
};
// A scene object of the block 4ef0d0 (0x138 bytes); the same word layout as
// AuxiliaryObject, so ObjectDrawQueue::submit accepts it.
using EndingObject=std::array<uint32_t,80>;

class EndingData {
public:
    static constexpr unsigned scriptCount=50,staffRoll=43;
    explicit EndingData(const std::filesystem::path& assets);
    std::span<const EndingRecord> script(unsigned index) const;
    uint32_t address(unsigned index) const {return directory_.at(index)[2];}
    std::string_view text(uint32_t offset) const;                       // Shift-JIS, without the terminator
    std::array<float,14> portrait{};                   // 60a050
    std::array<float,6> background{};                  // 652ae8
    std::array<float,3> flash{};                       // 5dd584
    std::array<std::array<int32_t,9>,6> balloons{};    // 4eeef8
    std::array<std::array<int32_t,2>,12> pictures{};   // 50e0b0: {ed_bg number, half}
    std::array<uint32_t,2> glyphColours{};             // 112f30 arguments of 182858
    uint32_t objectScale() const {return objectScale_;} // 5df3ac as float bits (object+0x70)
    // ACT / AID of resource "99a" (120110 binds it to both resource slots).
    unsigned records(unsigned action) const {return aid_.at(0x1000+action);}                // 120bc4
    const uint8_t* record(unsigned action,int step) const;                                  // 1212c0
private:
    std::vector<std::array<uint32_t,3>> directory_;
    std::vector<EndingRecord> records_;
    std::vector<char> strings_;
    std::vector<uint8_t> aid_,act_;
    uint32_t objectScale_=0;
};

// Palette-fade registers shared with the scene transition task.
struct EndingFade {
    int32_t mode=0;                // 3ebf18: bit 1 fades vertex colours and every CLUT entry
    uint32_t colour=0;             // 3ec730, AARRGGBB
    int32_t level=0,step=0;        // 3ec734 (0..0x100), 3ec738
    int32_t ceiling=0x100,floor=0; // 3ebf1c, 3ebf20
    int32_t flash=0;               // 3ebf24: frames the whole screen shows `colour`
    bool blank=false;              // 3ec73c: no sprite, rectangle or glyph is submitted this frame
    std::array<uint16_t,1024> tones{}; // 3ebf30: per CLUT entry flags or-ed with `mode` by 116588
    void beginFrame();             // 113aa8
    // 113b28 and the integration at the end of 116588 (116b9c). Returns true
    // when 113b28 submitted the full-screen quad of `colour`.
    bool endFrame();
    void reset();                  // register block of 182a98 (entry and exit)
};

struct EndingEvent {
    enum Kind:uint32_t {
        Music,            // 1e7c00(a, b)
        MusicStop,        // 1e7ad0()
        Sound,            // 1e7b70(a, b)
        ObjectSound,      // 1e8298(a = object+0xc, b = ACT sound command, c = object+0x14) from 120d10
        BackgroundClear,  // 112a70(fa1): the picture task dies; it has already drawn this frame
        BackgroundStage,  // 1a4a98(a < 0xc): battle stage loader 50e080[a]
        BackgroundPicture,// 1a4a98: ed_bg<a> into slot 4, CLUT 0x200.. ; b = half (task+0x1c)
        Portrait,         // 1a1928 / 1a19e8: demo_<b> into slot 0x22 (a = 0) or 0x23 (a = 1)
        TextColours,      // 112f30(a, b)
        PaletteReset,     // 1159d0 + 112f08(8) of 182858
        PaletteBake,      // 1174b8(a, b) with colour c and level d
        PaletteSave,      // 117438()
        Exit,             // 1252f0(a, b, c, d)
        MenuBackdrop      // gallery playback return: 1ce478() re-enters the menu backdrop; a = 4eefd4 (galleryRow)
    } kind;
    int32_t a=0,b=0;
    uint32_t c=0,d=0;
};

struct EndingTextLine {
    uint32_t text=0;      // EndingData::text offset
    int32_t x=0,y=0;      // 113028 arguments; the colour is always 0xffffffff
};
// Everything one coroutine visit submits, in submission order: the picture
// task 1a4c20 (priority 10, before the coroutine), 1a2118, the page or roll
// text, then 113b28. Objects go to the object queue 479250 instead.
struct EndingFrame {
    bool blank=false;                  // 3ec73c when the coroutine drew (182a98 clears it on entry and exit)
    bool pictureBlank=false;           // 3ec73c when the picture task ran
    bool picture=false;                // task 1a4c20 was alive when the frame began
    int32_t pictureHalf=0;             // task+0x1c & 1
    bool portraits=false;              // 1a2118 ran (false only on a visit that ends inside 182a98's exit)
    std::array<int32_t,2> portrait{-1,-1}; // 4eeef0, 4eeef4
    int32_t balloon=0;                 // renderer 3: 4efa98 (0 = no balloon sprite this frame)
    int32_t reveal=-1,glyphStart=0;    // 3d3aa0 and 3d3ab0 before the first line
    int32_t glyphEnd=0;                // 3d3ab0 behind a page renderer
    std::vector<EndingTextLine> lines;
    bool flash=false;                  // 113b28 quad
    uint32_t flashColour=0;
    std::vector<EndingObject> objects; // 1207e8 copies (kind 0) in submission order
    std::array<float,3> camera{},cameraOffset{}; // 4a2a58.., 4a2a64.. after the visit
    // Fade registers as the picture task's 117288 read them, and as the coroutine's draws and
    // the CLUT pass 116588 of this frame read them (before the level moves by the step).
    int32_t pictureFadeMode=0,pictureFadeLevel=0;
    uint32_t pictureFadeColour=0;
    EndingFade fade;
};

// The script engine: one tick() is one visit of the coroutine, from the
// return of 112a28 to its next call.
class EndingPlayback {
public:
    enum class Mode {Playback,StaffRoll};
    // 1828c0 (scene entry) ends with 182858: the eight objects start hidden.
    explicit EndingPlayback(const EndingData& data):data_(&data) {for(auto& o:objects)o[0x38/4]=0x400000;}
    // Playback: 182a98(script) - register reset, the script unless byte
    // 43d052 is set, fadeOut(0, 4), wait(0x40), register reset.
    // StaffRoll: 19c1c8 as 182d30 calls it (no reset on either side).
    // `colour` is 4ef0c8; `gallery` selects the 0x404 exit of game modes 0xd / 0xe.
    void begin(Mode mode,unsigned script,int colour,bool gallery,bool alternateText);
    // `pressed`: edge word of pad 4ef0c4. `locked`: word 582a68 (name entry).
    // `delta`: 11f450(0x100, 0), i.e. resolveObjectDelta(256, 0, gauges).
    // Returns true on the visit in which the engine returned to its caller;
    // that visit has not yielded and `frame` holds no draw of its own.
    bool tick(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events);
    // The three parts of tick() for an owner that runs more than one engine
    // call in a frame (182d30 enters the staff roll on the visit that ends the
    // playback): 113aa8 and the dispatcher's view of the picture task; the
    // visit; 113b28 with the level integration of 116588.
    void beginFrame();
    bool visit(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events);
    void endFrame();
    // 1a2118 + 1a2158 as 182d30 repeats them after its 1252f0.
    void idle(uint32_t delta,std::vector<EndingEvent>& events);
    bool skipped() const {return skipped_;}
    // 4eefd4 after a gallery playback: the list row to return to.
    int galleryRow() const {return script_==0x30?0x2b:int(script_);}

    EndingFade fade;
    EndingFrame frame;
    std::array<EndingObject,8> objects{};          // 4ef0d0
    std::array<int32_t,2> portrait{-1,-1};         // 4eeef0, 4eeef4
    std::array<int32_t,2> cameraDelta{};           // 4efa90, 4efa94
    std::array<float,3> camera{},cameraOffset{};   // 4a2a58, 4a2a64
    int32_t balloon=0;                             // 4efa98
    std::vector<uint32_t> message,roll;            // 4efaa0 (4 slots), 4efab0
    int32_t reveal=-1,glyphs=0;                    // 3d3aa0, 3d3ab0
    bool picture=false;                            // task 1a4c20 (tag fa1) alive
    int32_t pictureHalf=0;
    uint32_t position() const {return uint32_t(pc_);}
private:
    enum class Block {None,Wait,Message,RollShow,RollScroll};
    void iterate(uint32_t pressed,bool locked,uint32_t delta,std::vector<EndingEvent>& events);
    void execute(const EndingRecord& r,std::vector<EndingEvent>& events);
    void finish(std::vector<EndingEvent>& events);
    void resetObjects(std::vector<EndingEvent>& events);                    // 182858
    void loadBackground(int id,std::vector<EndingEvent>& events);           // 1a4a98
    void portraits();                                                       // 1a2118
    void stepObjects(uint32_t delta,std::vector<EndingEvent>& events);      // 1a2158
    void enterRecord(EndingObject& o,std::vector<EndingEvent>& events);     // 120d10
    void line(uint32_t text,int x,int y);                                   // 113028
    bool page(int renderer);                                                // 1a2468 / 1a2540 / 1a26b0 / 1a2870 / 1a25f0
    void rollLines(int y,bool scrolling);
    const EndingData* data_;
    Mode mode_=Mode::Playback;
    std::vector<EndingRecord> program_;
    size_t pc_=0;
    unsigned script_=0;
    int colour_=0;
    bool gallery_=false,skipped_=false,started_=false;
    Block block_=Block::None;
    int32_t counter_=0,hold_=0,renderer_=0,total_=0,limit_=0,origin_=0;
};

// Coroutine 182d30 of the arcade path: ending flags, name entry, playback,
// staff roll, then 1252f0(1, 1, 182a48, 138340).
class ArcadeEnding {
public:
    enum class Phase {Entry,Playback,StaffRoll,Leaving};
    explicit ArcadeEnding(const EndingData& data):playback(data) {}
    // 182968: g+30 = 1 (the resource loads are the caller's: hukidasi sheets,
    // resource "99a", sound bank 1e79c8(0, 0x31)).
    void enter(ArcadeRun& run,bool alternateText);
    // One frame: the name entry task (priority 0x14, created by the first
    // visit) and one coroutine visit. `pressed` holds both seats' edge words.
    void tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t delta);
    // 182a48.
    static void leave(ArcadeRun& run);
    Phase phase=Phase::Entry;
    unsigned seat=0;                 // 4ef0c4
    ArcadeNameEntry nameEntry;
    bool nameCommitted=false;        // the name entry task ended on this tick
    EndingPlayback playback;
    std::vector<EndingEvent> events; // of the last tick, in call order
private:
    void exit(ArcadeRun& run,uint32_t delta);
    bool alternateText_=false,nameEntryRuns_=false;
    int colour_=0;
};

// 19c1c8 on its own (script 43): for callers that want the roll without the ending.
class StaffRoll {
public:
    explicit StaffRoll(const EndingData& data):playback(data) {}
    void enter() {playback.begin(EndingPlayback::Mode::StaffRoll,EndingData::staffRoll,0,false,false);finished=false;}
    void tick(uint32_t pressed,bool locked,uint32_t delta) {
        events.clear();
        if(!finished)finished=playback.tick(pressed,locked,delta,events);
    }
    bool finished=false;
    EndingPlayback playback;
    std::vector<EndingEvent> events;
};

// Sheets and CLUT entries of the scene (slot 4 ed_bg picture, slots 0x22 /
// 0x23 portraits) and a compose-over rasteriser for them.
class EndingArt {
public:
    explicit EndingArt(std::filesystem::path assets);
    // Texture / palette side of an event; other kinds are ignored.
    void apply(const EndingEvent& event);
    // 116588 inputs. MenuCanvas::setFade(mode & 2, level, colour) owns the vertex half.
    void setFade(const EndingFade& fade);
    // Paints the list over the 640x480 RGBA frame in ascending depth; records of
    // other sheets go to MenuCanvas::rasterise. Balloon sheets 0x1f / 0x20 are not drawn.
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const;
    std::array<uint16_t,1024> source{},saved{};   // 43ab70, 43c370
private:
    void rebuild();
    std::filesystem::path assets_;
    std::vector<uint8_t> picture_;
    std::array<std::vector<uint8_t>,2> portrait_;
    std::array<std::array<uint8_t,4>,1024> colours_{};
    EndingFade fade_;
};

// Submits `frame` in the original order. list.colour / list.blend carry 3db900
// / 3db8fc across frames as the original globals do. The canvas fade is set
// from the frame (MenuCanvas::setFade). `frameEnd` adds 113b28: the depth
// count it always consumes and the full-screen quad of a blank frame.
void drawEnding(MenuCanvas& canvas,MenuDrawList& list,const EndingData& data,const EndingFrame& frame,bool frameEnd=true);
// The five page renderers on their own (talk and pre-final demos share them):
// fills frame.lines / balloon from a message list. Returns the "page complete"
// flag (3d3ab0 < 3d3aa0) for a frame that is not blank.
bool layoutEndingPage(const EndingData& data,int renderer,std::span<const uint32_t> message,int balloon,
                      int leftPortrait,int reveal,bool blank,EndingFrame& frame);
}
}
