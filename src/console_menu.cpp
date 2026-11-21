#include "console_menu.hpp"
#include <algorithm>

namespace ss6 {
std::array<MenuPad,2> MenuPadRepeat::sample(std::array<uint32_t,2> held,std::array<uint32_t,2> pressed) {
    std::array<MenuPad,2> pads;
    for(unsigned side=0;side<2;++side) {
        pads[side].pressed=pads[side].repeat=pressed[side];
        for(unsigned n=0;n<4;++n) {
            const uint32_t bit=0x10u<<n;
            auto& delay=delay_[side][n];
            if(!(held[side]&bit))delay=0;
            else if(delay==0){delay=20;pads[side].repeat|=bit;}
            else if(--delay==0){delay=2;pads[side].repeat|=bit;}
        }
    }
    return pads;
}
bool SceneFade::tick() {
    bool replace=false;
    shown_=level_;
    switch(phase_) {
    case 1:
        if(level_<256)level_=std::min(256,level_+25);
        else {phase_=2;hold_=0;}
        break;
    case 2:
        if(++hold_==3){phase_=3;replace=true;}
        break;
    case 3:
        if(level_>0)level_=std::max(0,level_-25);
        else phase_=0;
        break;
    }
    return replace;
}
void MenuChrome::enter(int libraryRandom) {
    band=content=legend=0;
    variant=((libraryRandom&0x7fff)>>14)+1;
}
void MenuChrome::advance() {
    if(band<15){++band;return;}
    if(content<15)++content;
    if(legend<5)++legend;
}
void MenuChrome::setHelp(int length) {
    helpX={0x10,(length>>1)*0x14};
    helpDelay=0x78;
}
int MenuChrome::helpPosition(bool scroll,int length,unsigned copy) {
    if(scroll && --helpDelay<=0) {
        const int half=length/2;
        helpX[copy]-=2;
        if(helpX[copy]<-20*half)helpX[copy]=20*half;
        helpDelay=0;
    }
    return helpX[copy];
}
}
