#include "character_select.hpp"
#include "scalar_float.hpp"
#include <algorithm>

namespace ss6 {
namespace {
constexpr std::array<uint32_t,5> paletteButtons{0x400,0x200,2,4,0x400000};
}
void CharacterSelect::characterTick(unsigned side,const NormalizedPadSample& pad,uint32_t repeat) {
    auto& s=seats[side];
    s.controls=0;
    if(s.phase==2 && !s.committed) {
        const auto button=std::find_if(paletteButtons.begin(),paletteButtons.end(),
            [&](uint32_t bit){return (pad.pressed&bit)!=0;});
        // The five face/auxiliary confirmations encode both the palette and
        // the alternate pose. Character choice takes priority over movement.
        if(button!=paletteButtons.end()) {
            const auto index=unsigned(button-paletteButtons.begin());
            const bool custom=pad.held&0x80000,alternate=pad.held&0x100000;
            const unsigned shift=alternate?(custom?16:11):(custom?6:0);
            s.controls=(0x10u<<index)<<shift;
            s.palette=0x40000+int(index)+(custom?(side?0x20000:0x10000):0);
            s.selected=s.character;
            if(s.selected==53) {
                // 128c78 includes hidden ID 42 at the end of the factory
                // random pool, despite it having no dedicated cell.
                int index=int(((random.nextLibrary()&0x7fff)*41)>>15);
                s.selected=index==40?42:index;
            }
            s.committed=true;s.count=0;s.phase=8;
            if(firstChooser<0)firstChooser=int(side);
            audio.push_back(s.selected<20?SelectVoice{0,s.selected+3}:SelectVoice{1,s.selected-20});
        } else {
            if(repeat&0x30) {
                const bool up=repeat&0x10;
                s.cell=(s.cell/6)*6+(s.cell%6+(up?5:1))%6;
                s.controls=up?1:2;s.count=0;audio.push_back({0,2});
            }
            if(repeat&0xc0) {
                const bool left=repeat&0x40;
                const int step=(left^bool(side))?-6:6;
                s.cell=(s.cell+step+42)%42;
                s.controls|=left?4:8;s.phase=left?3:4;s.count=0;
                audio.push_back({0,2});
            }
            s.character=roster[s.cell];
        }
    }
    s.drawPhase=s.phase;s.drawCount=s.count;s.drawPortrait=s.phase==2;
    if(s.phase==0)return;
    ++s.count;
    switch(s.phase) {
    case 1:
        // 12aa78 cues each of the 42 portrait tiles at its own offset.
        for(int cell=0;cell<42;++cell) {
            static const auto spacing=ScalarFloat::integer(50).div(ScalarFloat::integer(42));
            if(s.drawCount==11+ScalarFloat::integer(cell).mul(spacing).truncate())audio.push_back({-1,24});
        }
        if(s.count==60){s.phase=2;remaining=1739;}
        break;
    case 3:case 4:
        if(s.count==10){s.phase=2;s.count=0;}
        break;
    case 8:
        if(s.count==15){s.phase=10;s.count=0;}
        break;
    case 10:
        if(side==1 && seats[0].phase==10 && sync_++==10) {
            for(auto& seat:seats){seat.phase=11;seat.count=0;}
            spiritRequested=true;
        }
        break;
    case 11:
        if(s.count==15){s.phase=0;s.count=0;}
        break;
    }
}
void CharacterSelect::startSpirits() {
    for(auto& s:spirits) {
        s.phase=1;s.count=0;s.choiceCount=6;
        for(int i=0;i<s.choiceCount;++i)s.choices[i]=i;
    }
}
void CharacterSelect::spiritTick(unsigned side,uint32_t repeat) {
    auto& s=spirits[side];
    auto& other=spirits[side^1];
    const bool owner=int(side)==stageOwner;
    const auto choose=[&](int phase,int sound) {
        s.phase=phase;s.count=0;audio.push_back({0,sound});
    };
    const bool confirm=repeat&0x607,left=repeat&0x40,right=repeat&0x80;
    switch(s.phase) {
    case 2:
        if(confirm)choose(5,1);
        else if(left||right)choose(left?3:4,2);
        break;
    case 13:
        if(confirm)choose(17,1);
        else if(left ? stageOption==1 : (right && stageOption==0)){
            stageOption^=1;s.count=0;audio.push_back({0,2});
        }
        break;
    case 20:
        if(confirm)choose(24,1);
        else if(left||right) {
            stageCursor=(stageCursor+(left?10:1))%11;choose(left?22:23,2);
        }
        break;
    }
    s.drawPhase=s.phase;s.drawCount=s.count;s.drawCursor=s.cursor;s.drawProgress=s.progress;
    ++s.count;
    switch(s.phase) {
    case 1:
        if(s.count==60){s.phase=2;s.count=0;remaining=1200;}
        break;
    case 3:case 4:
        if(s.count==10){s.cursor=(s.cursor+(s.phase==3?5:1))%6;s.phase=2;s.count=0;}
        break;
    case 5:
        if(s.count==6) {
            s.progress=1;seats[side].spirit=s.choices[s.cursor];
            // Only gameData+10's player chooses the last two settings.
            s.phase=(owner && other.phase==14)?13:14;
            if(s.phase==13)remaining=600;
            s.count=0;
        }
        break;
    case 14:
        if(owner && other.phase==14){s.phase=13;remaining=600;}
        break;
    case 17:
        if(s.count==6) {
            s.progress=3;s.phase=20;s.count=0;
            // 1307f8 changes the other seat's phase without clearing its timer.
            other.phase=21;
        }
        break;
    case 22:case 23:
        if(s.count==30){s.phase=20;s.count=0;}
        break;
    case 24:
        if(s.count==6){s.phase=25;s.count=0;stage=stageCursor;complete=true;}
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
    ++visits_;
    // 112838 fixes all priority buckets before dispatch. Each 1129c8 birth
    // therefore costs one visit, even when the new task has a later priority.
    if(spiritRequested) {
        ++spiritAge_;
        if(spiritAge_==1) {
            // 12efd0 restores factory defaults only after the outgoing character
            // page. The previous fight's item setting survives up to this visit.
            remaining=1200;stageOption=0;stageCursor=10;
        }
        if(spiritAge_==2)startSpirits(); // 12f8e8
        if(spiritAge_>=3) {
            spiritTick(1,repeat[1]);spiritTick(0,repeat[0]);
        }
    }
    spiritDirectorVisible=spiritAge_>=2;
    if(spiritDirectorVisible)spiritDrawFrame=frame++;
    characterDirectorVisible=!colorsResolved_;
    if(characterDirectorVisible) {
        if(visits_>=2) {
            for(unsigned side=0;side<2;++side)characterTick(side,pads[side],repeat[side]);
        }
        if(seats[0].phase==0 && seats[1].phase==0) {
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
    drawRemaining=remaining;
}
}
