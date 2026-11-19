#include "versus_result.hpp"
#include "match_ending.hpp"
#include "versus_result_text.hpp"
#include <algorithm>
#include <stdexcept>

namespace ss6 {
namespace {
// 1252f0 wakes a pre-existing priority-60 task. A result scene born in its
// midpoint first updates on the next dispatch, since its priority is lower.
void beginFade(VersusResultState& s,bool white) {
    s.fadePhase=1;
    s.fadeCount=0;
    s.fadeLevel=0;
    s.fadeWhite=white;
}
void advanceFade(VersusResultState& s) {
    if(s.fadePhase==0)return;
    const int speed=255/(s.fadeWhite ? 30 : 10);
    switch(s.fadePhase) {
    case 1:
        if(s.fadeLevel<256)s.fadeDelta=speed;
        else {s.fadePhase=2;s.fadeCount=0;}
        break;
    case 2:
        if(s.fadeCount++==2) {
            s.fadePhase=3;
            if(s.nextScene==VersusScene::None)s.presentationReady=true;
            else {s.scene=s.nextScene;s.presentationReady=false;}
        }
        break;
    case 3:
        if(s.fadeLevel>0)s.fadeDelta=-speed;
        else s.fadePhase=0;
        break;
    }
    s.fadeAlpha=s.fadeLevel;
    s.fadeLevel=std::clamp(s.fadeLevel+s.fadeDelta,0,256);
}
void queueSuccessor(VersusResultState& s,VersusScene successor) {
    s.nextScene=successor;
    beginFade(s,true);
}
void updateWinner(VersusResultState& s,uint32_t edge) {
    // Start takes precedence over fast text, even when both edges arrive in
    // one sample. The winner scene keeps running during the outgoing fade.
    if(s.frame>=16 && s.nextScene==VersusScene::None && (edge&8))
        queueSuccessor(s,VersusScene::AfterWinner);
    if(s.frame>=60 && s.endFrame<450 && s.nextScene==VersusScene::None && (edge&0x607)) {
        if(s.messageDone)s.endFrame=450;
        else {s.glyphLimit=256;s.messageFrame=1024;}
    }
    s.draw={s.frame,s.backgroundFrame,s.glyphLimit};
    if(s.frame>=60)s.messageDone=s.glyphLimit>s.quoteGlyphs;
    ++s.frame;
    ++s.backgroundFrame;
    // The final glyph is already visible at equality, but 1a2870 reports
    // completion only after the next increment of the print limit.
    if(s.frame>60)s.glyphLimit=s.messageFrame++/4;
    if(s.messageDone)++s.endFrame;
    if(s.endFrame==480 && s.nextScene==VersusScene::None)
        queueSuccessor(s,VersusScene::AfterWinner);
}
void updateDraw(VersusResultState& s,uint32_t edge) {
    // The default (levelEnding=0) GameOver has one confirm edge. Start
    // does not skip it. Other profiles can trigger a secret-unlock screen.
    const bool flash=s.pendingDrawFlash;
    s.pendingDrawFlash=false;
    if(s.frame>=30 && s.frame<280 && (edge&4)) {
        // 117170 writes a one-draw request after the palette pass has sampled
        // the old flag. The next dispatch renders a full white frame.
        s.pendingDrawFlash=s.frame<200;
        s.frame=280;
    }
    if(s.frame==80)s.pendingDrawFlash=true; // 138e18 marks the regular title reveal.
    // The accelerated GameOver clock does not seek the character animation.
    s.draw={s.frame,s.backgroundFrame++,0,flash};
    if(++s.frame==300)queueSuccessor(s,VersusScene::AfterDraw);
}
}

void enterVersusResult(VersusResultState& s,const MatchEndState& ending,std::array<unsigned,2> characters) {
    if(ending.submodeA0!=0 || ending.field18 || ending.profileActive123a168 ||
       ending.winner08 < -1 || ending.winner08>1 || characters[0]!=0 || characters[1]!=0 ||
       s.lastEntrant>1)
        throw std::runtime_error("Versus result requires the default local resource 00 match");
    s.winner=ending.winner08;
    s.frame=s.backgroundFrame=s.messageFrame=s.endFrame=s.glyphLimit=0;
    s.messageDone=s.presentationReady=s.pendingDrawFlash=false;
    s.nextScene=VersusScene::None;
    s.draw={};
    if(s.winner<0) {
        s.lastWinner=-1;
        s.streak=0;
        s.gameMode=3;
        s.scene=VersusScene::Draw;
        s.quoteIndex=s.quoteGlyphs=0;
    } else {
        if(s.winner!=s.lastWinner)s.streak=0;
        s.defeatedCharacters[unsigned(s.streak)%s.defeatedCharacters.size()]=characters[1-s.winner];
        ++s.streak;
        s.lastWinner=s.winner;
        s.gameMode=s.winner+1;
        s.scene=VersusScene::Winner;
        s.quoteIndex=ending.result8c;
        s.quoteGlyphs=VersusResultText::glyphCount(s.quoteIndex);
    }
    beginFade(s,false);
    // The battle dispatch runs before priority 60, so this very visit can
    // already set the fade velocity. The first displayed alpha stays zero.
    advanceFade(s);
}

void updateVersusResult(VersusResultState& s,std::array<uint32_t,2> pressed) {
    if(s.presentationReady) {
        if(s.scene==VersusScene::Winner)updateWinner(s,pressed[unsigned(s.winner)]);
        else if(s.scene==VersusScene::Draw)updateDraw(s,pressed[s.lastEntrant^1u]);
    }
    advanceFade(s);
}
}
