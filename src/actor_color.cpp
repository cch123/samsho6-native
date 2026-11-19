#include "actor_color.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
int32_t word(uint32_t value) {return std::bit_cast<int32_t>(value);}
int alphaMode(int32_t action) {
    //14deb0 uses the displayed body, before149918 commits a queued action.
    if(action<164||uint32_t(action)-278<42||uint32_t(action)-716<2)return 2;
    if(uint32_t(action)-185<73)return 1;
    return action>=529?1:0;
}
}
void updateActorColor(StateEntryActor& a,const InputSystemConfig& config) {
    //Characters11/33 also mutate registered objects/visibility. Do not
    //silently omit those branches when admitting another playable actor.
    if(!playableFighter(a.character)||a.character!=config.character||config.system>5)
        throw std::runtime_error("Invalid fighter or spirit for actor color");
    ActorTimers timers{a.timerDelta,a.timers};
    a.bodyFlags38&=~0x40810000u;
    uint32_t rgb=0x808080;
    constexpr uint32_t damageColors[]{0x808080,0xc06020,0x1848b0,0x3070a0,
        0xa868a0,0x1848b0,0x6030b0,0,0x9a66b0};
    if(a.fieldA2c>0&&a.fieldA2c<9) {
        rgb=damageColors[a.fieldA2c];a.bodyFlags38|=0x40000000;
        //An explicit damage color bypasses BOTH rage and flash updates,
        //including timer16's usual clearing on the inactive branch.
    } else {
        // 14f748 suppresses the full-rage pulse on a Ken fighter.
        if((config.system!=5 && a.rageState120==1)||a.rageState120==2||a.state194==0x2e0000) {
            const int period=a.rageState120==2?24:40,half=period/2;
            const int phase=(timers.increase(16)/256)%period;
            const int ramp=phase<half?phase:period-phase;
            const int amplitude=word(uint32_t(ramp)<<6)/half;
            rgb=0x800000+((128u-uint32_t(amplitude))<<8)-uint32_t(amplitude)+128;
            a.bodyFlags38|=0x40010000;
            //Pulse color uses the OLD value, but wrap checks the new one.
            if(timers.values[16]>=0x7800)timers.clear(16);
        } else timers.clear(16);

        int32_t flash=0,denominator=1;
        if(a.state194==0x80000) {
            flash=word(uint32_t(timers.values[9])-0x400);denominator=0x400;
        } else if(timers.values[33]>0) {flash=timers.values[33];denominator=0xa00;}
        if(flash>0) {
            const uint32_t channel=uint32_t(word(uint32_t(flash)<<6)/denominator);
            const uint32_t red=uint32_t(word(uint32_t(flash)*96)/denominator);
            rgb=0x808080+(channel<<16)+(channel<<8)+red;
            a.bodyFlags38|=0x40000000;
        }
    }
    int targetAlpha=255;
    if(timers.values[17]>0) {
        const int mode=alphaMode(a.bodyAction24);
        if(mode==2)targetAlpha=0;
        else if(mode==1)targetAlpha=120;
    }
    const int alpha=std::clamp(256-timers.values[18]/16,0,255);
    //The published alpha precedes this visit's timer adjustment. Using the
    //new timer here would shift every fade edge by one actor update.
    if(targetAlpha<alpha)timers.increase(18);
    else if(alpha<targetAlpha)timers.decrease(18);
    if(alpha<255)a.bodyFlags38|=0x40000000;
    a.bodyColor8c=(uint32_t(alpha)<<24)+rgb;
    a.bodyField20=a.fieldA28;
    a.timers=timers.values;
}
}
