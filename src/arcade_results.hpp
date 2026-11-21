#pragma once
#include "arcade_run.hpp"
#include "menu_canvas.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <vector>

namespace ss6 {
// Result scenes of the arcade run: win quote 135e30, VS result 136a60, the
// kind-4 challenger banner of 1252f0, the name entry overlay drawing 1c9ec8,
// the unlock notice 1e5d88 and the unlock predicates 584f78 / 584fb8.
//
// Record conventions of this module (as src/arcade_art.hpp):
//  - Quad records of slot 0xc (font_otherscene2_16, 4-bit) carry the CLUT bank
//    in `glyph`; quad texel spans are clamped to size-1 (108118).
//  - Rotated records emitted for 114118 hold the four caller-supplied corners.

struct ArcadeResultRecord { int32_t u=0,v=0,w=0,h=0,flags=0,slot=0; };

// arcade_results.bin, written by work/ss6/extract_arcade_results.py.
struct ArcadeResultsTables {
    std::array<float,7> backgroundFloats{};                 // 5e1024..5e1038, 5e106c
    std::array<std::array<ArcadeResultRecord,10>,11> rows{}; // 4c96f0.. in drawing order
    ArcadeResultRecord picture{};                           // 4ca140
    std::array<float,23> quoteFloats{};                     // 5e1188..5e11e0
    std::array<float,7> resultEntry{};                      // 5e1230..5e1248
    std::array<float,6> resultFloats{};                     // 5e14b0..5e14c4
    std::array<std::array<int32_t,2>,8> resultShake{};      // 5e14c8
    std::array<float,5> faceFloats{};                       // 5e1508..5e1518
    std::array<ArcadeResultRecord,10> resultDigits{};       // 4c3c10
    ArcadeResultRecord resultDigitBefore{};                 // 4c3bf8: digit -1
    ArcadeResultRecord resultLabel{},resultMark{};          // 4c3d18, 4c3d30
    std::array<std::array<int16_t,3>,52> faces{};           // 5e1360: slot, column, row
    std::array<ArcadeResultRecord,2> banner{};              // 4c5188, 4c51a0
    std::array<float,3> bannerFloats{};                     // 5dfc18
    std::array<ArcadeResultRecord,10> entryDigits{};        // 4c40d8
    ArcadeResultRecord entryBack{},entryEnd{};              // 4c5350, 4c5368
    std::array<float,4> entryFloats{};                      // 655770..65577c
    std::array<float,3> unlockFloats{};                     // 65ca90, 65ca94, 654d84
    std::array<std::string,16> unlockTexts;                 // 584f20, Shift-JIS with 0x0a
    using Quote=std::vector<std::string>;                   // up to three Shift-JIS lines
    // [table][character][index]: table 0 is 50d550, table 1 is 50d618 (system
    // byte 43d052 != 0; characters 0..42 only).
    std::array<std::array<std::array<Quote,16>,49>,2> quotes;
    explicit ArcadeResultsTables(const std::filesystem::path& assets);
    // 1a3070(character, 2, index). Null for character 43, >= 49 and unused records.
    const Quote* quote(const SystemData& system,int character,int index) const;
};

// --- unlock predicates ------------------------------------------------
// Words 13430b0..13430cc (session flags set by 1e3fd0 after a survival win).
using UnlockSessionFlags=std::array<int32_t,8>;
int unlockEndingCount(const SystemData& system);   // 1e3f70 over g_GameOption+47..77
int unlockSpiritCount(const SystemData& system);   // 1e3fa0 over g_GameOption+81..89
// 584f78[index](endings, spirits, force). force == 1 evaluates the condition
// even when the item is already unlocked (1e3640).
bool unlockPredicate(unsigned index,const SystemData& system,const UnlockSessionFlags& session,int endings,int spirits,int force);
void unlockSetter(unsigned index,SystemData& system,int value); // 584fb8[index](value)
void unlockRecompute(SystemData& system,const UnlockSessionFlags& session); // 1e3640
bool unlockPending(const SystemData& system,const UnlockSessionFlags& session); // 1e6180
// 1e62b8: applies setter(1) for every pending item and returns their indices.
std::vector<int> unlockCollect(SystemData& system,const UnlockSessionFlags& session);

// --- shared scene plumbing -------------------------------------------
struct ArcadeResultEvents {
    int music=-1;                 // 1e7c00(id, 0)
    bool sound=false;             // 1e7b70(soundA, soundB)
    int soundA=0,soundB=0;
    bool voice=false;             // 1e7d60(voiceA, voiceB)
    int voiceA=0,voiceB=0;
    bool exit=false;              // the scene called 1252f0; see ArcadeRun::transition
    bool autosave=false;          // 10f158
    bool objectAction=false;      // 11d908(object, action, 1, 0) on this visit
    int action=0;
};
// Scrolling board 135438 (variant 0) and still picture 135de0 (variant 1).
void drawResultBackground(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,int variant,int frame);

// --- win quote 135e30 ---------------------------------------------------
struct ArcadeWinQuoteDraw {
    int32_t frame=0,backgroundFrame=0; // arguments of 136400
    int32_t revealLimit=0;             // 3d3aa0 as 1a2870 reads it
    int32_t winner=0;                  // g+8: side of the portrait entrance
    int32_t character=0;               // sheet win_NN of slot 8
    const ArcadeResultsTables::Quote* quote=nullptr;
};
// Task_VS_Next: entry 135e30, handler 136000 (priority 14, tag bbf), destructor 136288.
class ArcadeWinQuote {
public:
    static constexpr int music=0x19;
    int32_t frame=0,backgroundFrame=0,messageFrame=0,endFrame=0; // 4ca1b4, 4ca1b8, 4ca1bc, 4ca1c0
    int32_t messageDone=0,latch=0;                               // 4ca1b0, 4ca1c4
    int32_t revealLimit=0;                                       // 3d3aa0
    ArcadeWinQuoteDraw draw;
    ArcadeResultEvents enter(ArcadeRun& run,const ArcadeResultsTables& tables);
    // `pressed` holds both seats' edge words; `held` is the argument of
    // ArcadeRun::winQuoteExit. One 136000 visit including its draw state.
    ArcadeResultEvents tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t held);
    static void leave(ArcadeRun& run) {if(run.game.mode!=3)run.game.versusInterrupted=0;} // 136288
    // 1a2870's result for a reveal limit: glyph positions shown < limit.
    static int glyphCount(const ArcadeResultsTables::Quote& quote);
};
void drawArcadeWinQuote(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,const ArcadeWinQuoteDraw& draw);

// --- VS result 136a60 ---------------------------------------------------
struct ArcadeVersusResultDraw {
    int32_t frame=0;
    int32_t streak=0;                  // g+38
    std::array<int32_t,20> defeated{}; // g+3c
};
// The winner's fighter object (tag bc2): 11d570(object, seat, x, 0, flags),
// object+20 = colour, 11d908(object, 0, 1, 0); action 1fb from frame 64.
struct ArcadeResultFighter {
    int32_t seat=0,character=0,colour=0,x=0,flags=0,action=0;
};
// Task_VS_Result: entry 136a60, handler 136c58 (priority 19, tag bc2), destructor 136f88.
class ArcadeVersusResult {
public:
    static constexpr int music=0x19;
    int32_t frame=0,endFrame=0,latch=0; // 4ca1e4, 4ca1e8, 4ca1f0
    ArcadeVersusResultDraw draw;
    ArcadeResultFighter fighter;
    ArcadeResultEvents enter(const ArcadeRun& run,const ArcadeResultsTables& tables);
    // `poseHeld` is the object's word +c0 while its action +24 is 1fb (the
    // fighter pipeline owns the object); zero while another action runs.
    ArcadeResultEvents tick(ArcadeRun& run,std::array<uint32_t,2> pressed,uint32_t held,int32_t poseHeld);
};
void drawArcadeVersusResult(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,
                            const ArcadeVersusResultDraw& draw);

// --- challenger banner: transition kind 4 of 1252f0 -----------------------
struct ArcadeBannerFrame {
    bool banner=false;        // 125c68 submits the two banner sprites
    int curtain=-1;           // VsCurtain::paint frame (0..32) or -1
    bool voice=false;         // 1e7d60(31, 4d)
    bool stopSound=false;     // 1e7b70(-1, f)
    bool swap=false;          // 1253e0, old destructor and new entry run after this visit's draw
    bool finished=false;      // the task ended: g+94 = 0, g+2c = 0
};
// Task 1251d0 (tag bc1) for kind 4: state 1 runs 125c68 for 0x5a + 0xf visits,
// state 2 125848 for three, state 3 1258a8 for fifteen.
class ArcadeChallengerBanner {
public:
    int32_t state=0,age=0;    // 1239da4, 1239da8
    void begin() {state=1;age=0;}
    // `hidden`: sub-mode 5 with word 443140 != 0.
    ArcadeBannerFrame tick(bool hidden);
};
void drawArcadeBanner(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables);

// --- name entry overlay 1c9ec8 + countdown 1ca248 -------------------------
// One 1c9928 visit: drawArcadeNameCountdown with the entry as it stands BEFORE
// ArcadeNameEntry::tick (1ca248 draws the seconds, then steps them), then
// drawArcadeNameEntry with the entry AFTER the tick (1c9ec8; tick() has
// already stepped the blink 1c9d20 into blinkShown).
void drawArcadeNameCountdown(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,
                             const ArcadeNameEntry& entry,int gameMode);
void drawArcadeNameEntry(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,const ArcadeTables& glyphs,
                         const ArcadeNameEntry& entry,int gameMode);

// --- unlock notice 1e5d88 -------------------------------------------------
struct ArcadeEdgePulse { int32_t counter=0,reverse=0; }; // 584ff8, 584ffc (1c1528)
struct ArcadeUnlockDraw {
    int32_t item=-1;       // index into ArcadeResultsTables::unlockTexts, -1: nothing
    int32_t alpha=0;
};
// Task 1e5e90 (priority 14, tag 1797), destructor 1e6130.
class ArcadeUnlockNotice {
public:
    std::vector<int> items;          // 13430d0, filled by 1e62b8
    int32_t index=0,latch=0,frame=0,fading=0; // 584f60, 584f68, 584f6c, 584f70
    ArcadeUnlockDraw draw;
    // 1e5d88: collects the pending items (their setters run here) and sets g+30.
    ArcadeResultEvents enter(ArcadeRun& run,const UnlockSessionFlags& session);
    ArcadeResultEvents tick(ArcadeRun& run,std::array<uint32_t,2> pressed);
    static void leave(ArcadeRun& run); // 1e6130
};
void drawArcadeUnlockNotice(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeResultsTables& tables,
                            const ArcadeUnlockDraw& draw,ArcadeEdgePulse& pulse);

// --- sheets -------------------------------------------------------------
// Slots 4 (menu_bg00_00 or menu_bg01_00), 5 (char_face_1024), 8 (win_NN) and
// 0xc (font_otherscene2_16) plus a compose-over rasteriser; every other
// record goes to MenuCanvas::rasterise.
class ArcadeResultsArt {
public:
    explicit ArcadeResultsArt(const std::filesystem::path& assets);
    void bindBackground(int variant);   // 135300(variant)
    void bindPortrait(int character);   // "win_%02d" of 135e30
    // Same arguments as MenuCanvas::setFade (116588 interpolates the bank CLUTs).
    void setFade(bool enabled,int level,uint32_t colour);
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const;
private:
    struct Bank { std::vector<uint16_t> source; std::vector<std::array<uint8_t,4>> colours; };
    void rebuild(Bank& bank) const;
    std::filesystem::path assets_;
    int background_=-1,portrait_=-1;
    bool portrait32_=false;
    std::vector<uint8_t> board_,picture_,portraitTexels_,faces_,digits_;
    std::array<std::array<uint8_t,4>,256> boardColours_{};
    Bank pictureBank_,portraitBank_,faceBank_,digitBank_;
    bool fadeEnabled_=false;
    int fadeLevel_=0;
    uint32_t fadeColour_=0;
};
}
