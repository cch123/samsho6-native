#include "character_select.hpp"
#include "scalar_float.hpp"
#include <algorithm>

namespace ss6 {
namespace {
constexpr std::array<uint32_t,5> paletteButtons{0x400,0x200,2,4,0x400000};
}
int CharacterSelect::randomCharacter() {
    // 129e2c: randomList[((library & 0x7fff) * randomCount) >> 15].
    return randomPool[size_t(((random.nextLibrary()&0x7fff)*int(randomPool.size()))>>15)];
}
void CharacterSelect::preview(unsigned side,int character,int action) {
    auto& s=seats[side];
    s.previewCharacter=character;s.previewAction=action;s.previewLoaded=s.previewRestarted=true;
}
void CharacterSelect::commit(unsigned side,uint32_t buttons) {
    // 129db0. A countdown expiry calls it with no buttons: the colour word P+4 keeps its value.
    auto& s=seats[side];
    s.selected=roster[s.cell];
    // A Kuroko face selects 48 (no RNG, even on the random cell).
    if(kurokoCell(side,s.cell))s.selected=48;
    else if(s.selected==53){s.selected=randomCharacter();s.randomChosen=true;}
    s.committed=true;s.count=0;s.controls=buttons;
    if(firstChooser<0)firstChooser=int(side);
    if(twoSided())s.phase=8;
    else {
        // 12a010: the single seat leaves through phase 7. SURVIVAL (0xb/0xc) has no spirit
        // page; every other single-seat mode requests 12eee8 here.
        s.previewLoaded=false;s.phase=7;
        if(mode!=11&&mode!=12)spiritRequested=true;
    }
    audio.push_back(s.selected<20?SelectVoice{0,s.selected+3}:SelectVoice{1,s.selected-20});
}
void CharacterSelect::characterTick(unsigned side,const Pads& pads,const Repeats& repeats) {
    auto& s=seats[side];
    const bool single=!twoSided();
    s.controls=0;s.previewRestarted=false;
    if(remaining==0 && s.phase==2 && !s.committed)commit(side,0);
    // 129508: resting on the random tile, the single seat's fighter is redrawn from the
    // library RNG every third count.
    if(single && s.previewLoaded && roster[s.cell]==53 && s.count%3==0 && !kurokoCell(side,s.cell))
        preview(side,randomCharacter(),3);
    // 1295f8: pad input needs 1 <= remaining <= 0x6cb. ARCADE/SURVIVAL count down from
    // 0x708, so the first 61 phase-2 visits ignore the pad.
    bool handled=unsigned(remaining-1)<0x6cb && s.phase==2 && !s.committed;
    unsigned port=side;
    if(handled && (mode==9||mode==10)) {
        // 12dbdc/12ee10: the practising pad drives its own seat, then the other one after
        // the shared ten-visit delay. Movement is still mirrored by seat.
        port=mode==10;
        if(side!=port) {
            if(!seats[port].committed)handled=false;
            else if(--handoverDelay>0)handled=false;
        }
    }
    if(handled) {
        const auto& pad=pads[port];
        const uint32_t repeat=repeats[port];
        // 12db80: PadStart toggles the Kuroko view (Kuroko's unlock byte is 0).
        if(pad.pressed&8)s.kuroko=!s.kuroko;
        bool wiping=false;
        if(s.kuroko) {
            // Each update refills kurokoColumns whole columns from the cursor's column;
            // until all eight show, the divider advances and every other input is ignored.
            s.kurokoFaces=true;
            if(single && !s.kurokoPreview){preview(side,48,3);s.kurokoPreview=true;}
            if(s.kurokoColumns<columns) {
                if(++s.kurokoDivider%3==0)++s.kurokoColumns;
                wiping=true;
            }
        } else if(s.kurokoFaces) { // 12ecb8: restore the faces and reset K = {0, 0, 1, 0}
            s.kurokoFaces=s.kurokoPreview=false;s.kurokoDivider=0;s.kurokoColumns=1;
            if(single)preview(side,roster[s.cell]==53?randomCharacter():roster[s.cell],3);
        }
        const auto button=wiping?paletteButtons.end():std::find_if(paletteButtons.begin(),paletteButtons.end(),
            [&](uint32_t bit){return (pad.pressed&bit)!=0;});
        // The five face/auxiliary confirmations encode both the palette and
        // the alternate pose. Character choice takes priority over movement.
        if(button!=paletteButtons.end()) {
            const auto index=unsigned(button-paletteButtons.begin());
            const bool custom=pad.held&0x80000,alternate=pad.held&0x100000;
            const unsigned shift=alternate?(custom?16:11):(custom?6:0);
            // 12dedc: only the VS menu (submode 2) tags the word with 0x40000 and gives
            // seat 1 the custom base 0x20000.
            s.palette=(submode==2?0x40000:0)+int(index)+(custom?(submode==2&&side?0x20000:0x10000):0);
            // 12e0ac: a single seat's confirmation stops the countdown.
            if(single)countdownPaused=true;
            commit(side,(0x10u<<index)<<shift);
        } else if(!wiping) {
            if(repeat&0x30) {
                const bool up=repeat&0x10;
                s.cell=(s.cell/6)*6+(s.cell%6+(up?5:1))%6;
                s.controls=up?1:2;s.count=0;audio.push_back({0,2});
            }
            if(repeat&0xc0) {
                const bool left=repeat&0x40;
                const int step=(left^bool(side))?-6:6;
                s.cell=(s.cell+step+cells)%cells;
                s.controls|=left?4:8;s.phase=left?3:4;s.count=0;
                audio.push_back({0,2});
            }
            s.character=roster[s.cell];
            if(single) {
                // 12df48: a move drops the fighter; the next idle visit loads the new one.
                if(s.controls)s.previewLoaded=false;
                else if(!s.previewLoaded)
                    preview(side,kurokoCell(side,s.cell)?48:roster[s.cell]==53?randomCharacter():roster[s.cell],3);
            }
        }
        if(kurokoCell(side,s.cell))s.character=48; // 1293d0(seat, 48, 3): the Kuroko preview
    }
    s.drawPhase=s.phase;s.drawCount=s.count;s.drawPortrait=s.phase==2;
    // Both seats of a two-seat page reach phase 0 together and 129110 frees them; SURVIVAL's
    // seat task keeps counting until the scene changes.
    if(s.phase==0 && !single)return;
    ++s.count;
    switch(s.phase) {
    case 1:
        // 12aa78 cues each drawn portrait tile at its own offset (50 / cell count);
        // with 8 columns its drum skips column 0 (12ab90), so cells 0..5 never cue.
        for(int cell=columns==8?6:0;cell<cells;++cell) {
            static const auto spacing=ScalarFloat::integer(50).div(ScalarFloat::integer(cells));
            if(s.drawCount==11+ScalarFloat::integer(cell).mul(spacing).truncate())audio.push_back({-1,24});
        }
        if(s.count==60) {
            s.phase=2;
            // 129b14: submodes 2/3 restart a stopped 0x6cb countdown; the others let the
            // 0x708 one run.
            if(submode==2||submode==3)restart(1739,true);
            else countdownPaused=false;
        }
        break;
    case 3:case 4:
        if(s.count==10){s.phase=2;s.count=0;}
        break;
    case 7:
        if(s.count==6){s.phase=0;s.count=0;}
        break;
    case 8:
        if(s.count==15){s.phase=10;s.count=0;}
        break;
    case 10:
        if(side==1 && seats[0].phase==10) {
            if(sync_++==10) {
                for(auto& seat:seats){seat.phase=11;seat.count=0;}
                spiritRequested=true;
            } else countdownPaused=true; // 129c3c
        }
        break;
    case 11:
        if(s.count==15){s.phase=0;s.count=0;}
        break;
    }
}
void CharacterSelect::startSpirits() {
    // 12f8e8: spirits 0..5 plus, for the companion fighters 44..47, spirit 8 with the cursor
    // on it (option bytes 43d0d6..d8 for spirits 6/7/8 keep their factory 0).
    for(unsigned side=0;side<2;++side) {
        if(!seats[side].present)continue;
        auto& s=spirits[side];
        s.present=s.active=true;
        s.phase=1;s.count=0;s.choiceCount=6;
        for(int i=0;i<s.choiceCount;++i)s.choices[i]=i;
        const int c=seats[side].selected;
        if(c>=44&&c<=47){s.choices[s.choiceCount++]=8;s.cursor=s.choiceCount-1;}
        // 12fb04: a challenger match (mode 3) leaves the other seat's cursor on its
        // current spirit word P+8.
        else if(mode==3 && int(side)!=stageOwner)s.cursor=seats[side].spirit;
    }
}
void CharacterSelect::settings(SpiritSelectSeat& s) {
    // 1301ec/1306fc: the owner continues with the item option; PRACTICE (submode 3) has
    // none and goes to the stage. Only submodes 2/3 stop the 600 countdown.
    s.phase=submode==3?20:13;
    restart(600,submode==2||submode==3);
}
void CharacterSelect::spiritTick(unsigned side,const Repeats& repeats) {
    auto& s=spirits[side];
    auto& other=spirits[side^1];
    const bool owner=int(side)==stageOwner;
    const auto choose=[&](int phase,int sound) {
        s.phase=phase;s.count=0;audio.push_back({0,sound});
    };
    const bool chosen=s.progress==1||s.progress==2;
    if(remaining==0) {
        // 12fc38: an expired countdown confirms the cursor; 134e48 then ignores the pad.
        if(s.phase==2){if(s.progress==0)choose(5,1);}
        else if(s.phase==13 && chosen)choose(17,1);
    } else {
        // 134e48: PRACTICE reads one port for both seats.
        const unsigned port=mode==9?0:mode==10?1:side;
        const uint32_t repeat=repeats[port];
        const bool confirm=repeat&0x607,left=repeat&0x40,right=repeat&0x80;
        if(s.progress==0) {
            // The second PRACTICE cursor waits for the first seat's spirit.
            const bool waiting=(mode==9||mode==10) && side!=port &&
                spirits[port].progress!=1 && spirits[port].progress!=2;
            if(s.phase==2 && !waiting) {
                if(confirm)choose(5,1);
                // The companion fighters 44..47 keep their single spirit-8 cursor; the
                // move sound still plays.
                else if((left||right)&&unsigned(seats[side].selected-44)<4)audio.push_back({0,2});
                else if(left||right)choose(left?3:4,2);
            }
        } else if(chosen && owner && submode!=3) {
            if(s.phase==13) {
                if(confirm)choose(17,1);
                else if(left ? stageOption==1 : (right && stageOption==0)){
                    stageOption^=1;s.count=0;audio.push_back({0,2});
                }
            }
        } else if(s.phase==20) {
            if(confirm)choose(24,1);
            else if(left||right) {
                stageCursor=(stageCursor+(left?10:1))%11;choose(left?22:23,2);
            }
        }
    }
    s.drawPhase=s.phase;s.drawCount=s.count;s.drawCursor=s.cursor;s.drawProgress=s.progress;
    ++s.count;
    switch(s.phase) {
    case 1:
        // 130e1c: the single-seat page slides in 15 counts later.
        if(s.count==(twoSided()?60:75)) {
            s.phase=2;s.count=0;
            if(submode==2||submode==3)restart(1200,true);
            else countdownPaused=false;
        }
        break;
    case 3:case 4:
        if(s.count==10){s.cursor=(s.cursor+(s.phase==3?s.choiceCount-1:1))%s.choiceCount;s.phase=2;s.count=0;}
        break;
    case 5:
        if(s.count==6) {
            s.progress=1;seats[side].spirit=s.choices[s.cursor];
            s.count=0;
            if(!twoSided()){s.phase=11;s.active=false;}
            // Only gameData+10's player chooses the last settings.
            else if(owner) {
                if(other.phase==14)settings(s);
                else s.phase=submode==3?21:14;
            } else {s.active=false;s.phase=submode==3?21:14;}
        }
        break;
    case 14:
        if(owner && other.phase==14 && chosen)settings(s);
        break;
    case 17:
        if(s.count==6) {
            s.progress=3;s.count=0;
            // 1307f8 changes the other seat's phase without clearing its timer. Outside
            // the VS menu there is no stage page (130848).
            if(submode==2){s.phase=20;other.phase=21;}
            else {s.phase=19;s.active=false;}
        }
        countdownPaused=true; // 130840
        break;
    case 21:
        if(owner && other.phase==21 && chosen){s.phase=20;restart(600,true);}
        break;
    case 22:case 23:
        if(s.count==30){s.phase=20;s.count=0;}
        break;
    case 24:
        if(s.count==6){s.phase=25;s.count=0;s.active=false;stage=stageCursor;}
        countdownPaused=true;
        break;
    }
}
void CharacterSelect::tick(const std::array<NormalizedPadSample,2>& pads) {
    audio.clear();
    std::array<uint32_t,2> repeat{};
    for(unsigned side=0;side<2;++side) {
        repeat[side]=pads[side].pressed;
        for(unsigned i=0;i<4;++i) {
            const uint32_t bit=0x10u<<i;
            auto& delay=delays_[side][i];
            if(!(pads[side].held&bit))delay=0;
            else if(!delay){delay=20;repeat[side]|=bit;}
            else if(--delay==0){delay=2;repeat[side]|=bit;}
        }
    }
    if(++visits_==1 && !twoSided()) {
        // 128294: one seat task; 129318 loads its fighter with action 4.
        auto& absent=seats[soleSeat()^1];
        absent.present=false;absent.phase=0;
        preview(soleSeat(),roster[seats[soleSeat()].cell],4);
    }
    // 127f00 (priority 9) runs before every selection task.
    if(!countdownPaused)++elapsed_;
    elapsed_=std::min(elapsed_,limit_);
    remaining=limit_-elapsed_;
    // 112838 fixes all priority buckets before dispatch. Each 1129c8 birth
    // therefore costs one visit, even when the new task has a later priority.
    if(spiritRequested) {
        ++spiritAge_;
        if(spiritAge_==1) {
            // 12efd0 restores factory defaults only after the outgoing character
            // page. The previous fight's item setting survives up to this visit.
            restart(1200,true);stageOption=0;stageCursor=10;
        }
        if(spiritAge_==2)startSpirits(); // 12f8e8
        if(spiritAge_>=3) {
            for(unsigned side:{1u,0u})if(spirits[side].present)spiritTick(side,repeat);
        }
        // 12f100: every seat's 4c8d88 word clear requests the next scene once.
        if(spiritAge_>=2 && !spirits[0].active && !spirits[1].active)complete=true;
    }
    spiritDirectorVisible=spiritAge_>=2;
    if(spiritDirectorVisible)spiritDrawFrame=frame++;
    characterDirectorVisible=!colorsResolved_;
    if(characterDirectorVisible) {
        if(visits_>=2) {
            for(unsigned side=0;side<2;++side)if(seats[side].present)characterTick(side,pads,repeat);
        }
        if(!twoSided()) {
            // 128490/1285f0: ARCADE frees the page (129110); SURVIVAL requests the fight
            // (1252f0 to 139760) and keeps the page until the scene changes.
            if(seats[soleSeat()].phase==0 && visits_>=2) {
                if(mode==11||mode==12)complete=true;
                else colorsResolved_=true;
            }
        } else if(seats[0].phase==0 && seats[1].phase==0) {
            const int first=seats[0].palette,second=seats[1].palette;
            if(seats[0].selected==seats[1].selected && !(first&0x10000) &&
               !(second&0x20000) && (first&0xffff)==(second&0xffff)) {
                auto& losingColor=seats[firstChooser^1].palette;
                losingColor=(losingColor&0xf0000)+((first&0xffff)==0);
            }
            colorsResolved_=true;
        }
        drawFrame=frame++;
    } else {
        for(auto& s:seats){s.drawPhase=0;s.drawCount=0;s.controls=0;s.drawPortrait=false;}
        drawFrame=spiritDrawFrame;
    }
    remaining=limit_-elapsed_;
    drawRemaining=remaining;
}
}
