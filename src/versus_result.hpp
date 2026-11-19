#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
struct MatchEndState;

// These are entry addresses of independent scenes selected by 145628 and the
// result tasks. The battle's numbered states have ended at this point.
enum class VersusScene : uint32_t {
    None=0, Winner=0x135e30, Draw=0x138340, AfterWinner=0x1c60c8, AfterDraw=0x1e8850
};
struct VersusResultDraw {
    int frame=0, backgroundFrame=0, glyphLimit=0;
    bool whiteFlash=false;
};
struct VersusResultState {
    int lastWinner=-1, streak=0;
    std::array<unsigned,20> defeatedCharacters{};
    VersusScene scene=VersusScene::None, nextScene=VersusScene::None;
    // The native fixed matchup admits P1 first, then P2. The game-over
    // task reads the pad of the player opposite the last entrant.
    unsigned lastEntrant=1;
    int winner=-1, gameMode=3, quoteIndex=0, quoteGlyphs=0;
    int frame=0, backgroundFrame=0, messageFrame=0, endFrame=0, glyphLimit=0;
    bool messageDone=false, presentationReady=false, pendingDrawFlash=false;
    VersusResultDraw draw;
    // 116588 uses the old alpha to shade this draw, then integrates the
    // signed delta. Both alpha values are in the original 0..256 units.
    int fadePhase=0, fadeCount=0, fadeLevel=0, fadeAlpha=0, fadeDelta=0;
    bool fadeWhite=false;
};
void enterVersusResult(VersusResultState&, const MatchEndState&, std::array<unsigned,2> characters);
void updateVersusResult(VersusResultState&, std::array<uint32_t,2> pressed);
}
