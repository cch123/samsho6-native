#pragma once
#include "arcade_run.hpp"
#include "arcade_tally.hpp"
#include "menu_canvas.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <vector>

namespace ss6 {
// Drawing of the ARCADE battle overlays (score digits 1bc098, free-seat legend
// 1ba1b0, state-9 tally 1c8a98 + 113028) and of the Continue (137d20) and
// Game Over (138af0) scenes, as MenuDrawList records.
//
// Record conventions added by this module to MenuDrawRecord:
//  - Quad records of slot 0xc (font_otherscene16, 4-bit indices) carry the CLUT
//    bank selected through 10add8 in `glyph` (0 or 1).
//  - Quad / Rotated texel spans are clamped to size-1 as 108118 does (10849c).
//  - Rotated records emitted for 114118 hold the four caller-supplied corners.

// arcade_art.bin (work/ss6/extract_arcade_art.py).
struct ArcadeArtTables {
    ArcadeSpriteRecord continueTitle{};                // 4c3bc8
    std::array<ArcadeSpriteRecord,10> continueDigits{}; // 4c3ad8
    std::array<float,11> continueFloats{};             // 5e1618..5e1640
    ArcadeSpriteRecord gameOverText{},gameOverTitle{}; // 4c3be0, 4c3bf8
    std::array<float,7> gameOverFloats{};              // 5e18a8..5e18c0
    std::array<std::array<int32_t,2>,8> gameOverShake{}; // 5e18c8
    std::array<float,7> gameOverTail{};                // 5e1908..5e1920
    std::array<ArcadeSpriteRecord,9> scoreNegative{};  // 4c5a10: records indexed by digits -9..-1
    explicit ArcadeArtTables(const std::filesystem::path& assets);
};

// The loser's fighter object of Continue / Game Over is a character sprite of
// the object queue 479250, not a MenuDrawList record. The scene creates it with
// 11d570(object, seat, 0x140, 0, 0) and 11d908(object, action, 1, 0) and runs
// 11d6c8 / 11d868 / 11d730 on it once per frame after the overlay draw.
struct ArcadeFighterRequest {
    bool visible=false;
    int32_t seat=0,character=0;
    bool colourSet=false;        // Continue stores the selected colour at object+0x20
    int32_t colour=0;
    int32_t action=0;            // 0x700 Continue, 0x701 Game Over
    int32_t x=0x140,y=0,z=0;
    int32_t frame=0;             // scene frame counter; the object clock is the caller's
    // Game Over: the first `underRecords` records appended by the call lie
    // behind the object (138b50 backdrop); the rest are in front of it.
    size_t underRecords=0;
};

// Sheets the menu canvas does not hold plus a compose-over rasteriser.
class ArcadeArt {
public:
    explicit ArcadeArt(const std::filesystem::path& assets);
    const ArcadeArtTables& tables() const {return tables_;}
    // 116588 state for the bank CLUTs of slot 0xc. Call MenuCanvas::setFade
    // with the same arguments: it owns the vertex-colour half of the fade.
    void setFade(bool enabled,int level,uint32_t colour);
    // Paints the list over the existing 640x480 RGBA frame in ascending depth.
    // Quads of slots 0x0a, 0x0c and 0x28 are sampled here; every other record
    // is handed to MenuCanvas::rasterise, which also composes over.
    // `first` / `count` restrict the pass to a run of records (in submission order).
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba,
                   size_t first=0,size_t count=size_t(-1)) const;
private:
    void rebuildBanks();
    ArcadeArtTables tables_;
    std::vector<uint8_t> hud_,coin_,scene_;           // obj2_16, font_coin, font_otherscene16
    std::array<std::array<uint8_t,4>,256> hudColours_{},coinColours_{};
    std::array<uint16_t,32> bankSource_{};            // obj0.pal banks 0 and 1, entry 0 cleared (113890)
    std::array<std::array<std::array<uint8_t,4>,16>,2> bankColours_{};
    bool fadeEnabled_=false;
    int fadeLevel_=0;
    uint32_t fadeColour_=0;
};

// 1bab38 gate + 1bc098: the score digits of the arcade seat's HUD.
// `hudMode` is word 58223c (the HUD's copy of gameData+0), `submode` gameData+0xa0.
void drawArcadeScore(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,const ArcadeArtTables& art,
                     int hudMode,int submode,int32_t score);

// 1ba1b0. Advances the blink clock exactly when the original does (inside
// 1ba228 / 1ba448). `enabled` is word 582208, `latched` gameData+0x2c == 1 ||
// gameData+0x30 == 1. Returns true when the legend was submitted.
bool drawFreeSeatPrompt(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,FreeSeatPrompt& clock,
                        int gameMode,int submode,bool enabled,bool latched);

// 1c8a98 followed by the value rows of 1c7f08: panel pieces and every 113028 text.
void drawArcadeTally(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeTallyTables& tally,const ArcadeTallyDraw& draw);

// 137d20: title art and countdown digits. The stage background (1a4a98) and the
// loser object are the caller's; the returned request describes the object.
ArcadeFighterRequest drawArcadeContinue(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeArtTables& art,
                                        const ArcadeContinueDraw& draw);

// 138af0: the black backdrop of 138b50 (gameData+0x34 != 0, behind the loser
// object; see ArcadeFighterRequest::underRecords), then the text, the title and
// the black strip. Frame 0x50 submits no strip: 138e18 requests the fade
// 1170d8(-1) / 117170(1) instead (ArcadeGameOver::fadeRequested).
ArcadeFighterRequest drawArcadeGameOver(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeArtTables& art,
                                        const ArcadeGameOverDraw& draw,bool levelEnding);

// 1382a8 / 138eb0: cubic through four control values, accumulated on the EE
// accumulator and truncated. Exposed for the validator.
int32_t arcadeArtCubic(int32_t step,int32_t total,int32_t p0,int32_t p1,int32_t p2,int32_t p3,float one,float three);
}
