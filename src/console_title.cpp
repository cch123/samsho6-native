#include "console_title.hpp"

namespace ss6 {
ConsoleTitle::ConsoleTitle(bool returningFromVersus)
    :firstRow_(returningFromVersus?0:5),joined_(returningFromVersus) {
    draw={joined_,firstRow_};
}

void ConsoleTitle::tick(const std::array<uint32_t,2>& commands,bool startPressed) {
    tones={-1,-1};
    announce=titleTick_==30;
    draw={joined_,firstRow_,direction_,scroll_,titleTick_,idleTick_};
    if(!joined_) {
        if(startPressed){joined_=true;tones[0]=1;}
        ++titleTick_;
    } else {
        // 127c18 visits both ports before drawing. The initial 30-count
        // input lock is shared, so two connected seats consume it in 15 ticks.
        bool cancel=false;
        for(unsigned side=0;side<2;++side) {
            if(confirmingSeat>=0 || direction_)continue;
            if(inputAge_<30){++inputAge_;continue;}
            const auto command=commands[side];
            if(command&3) {
                direction_=(command&1)?1:2;
                const unsigned step=direction_==1?5:1;
                firstRow_=(firstRow_+step)%6;
                // An unconfigured network row stays visible during scrolling
                // but the retail cursor skips it in both directions.
                if(firstRow_==3)firstRow_=(firstRow_+step)%6;
                tones[side]=32;unavailableMode=false;
            } else if(command&32) {
                cancel=true;tones[side]=37;unavailableMode=false;
            } else if(command&16) {
                tones[side]=1;
                if(firstRow_==0)confirmingSeat=int(side);
                else unavailableMode=true;
            }
        }
        draw.firstRow=firstRow_;draw.scrollDirection=direction_;draw.scrollTick=scroll_;
        if(direction_ && ++scroll_==15){direction_=scroll_=0;}
        if(cancel) {
            joined_=false;firstRow_=5;direction_=scroll_=inputAge_=idleTick_=0;
        }
    }
    if(!joined_)++idleTick_;
    if(confirmingSeat>=0)++transitionTick;
}
}
