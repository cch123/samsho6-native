#include "actor_state.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
void ActorTimers::resetRound() {
    //14cf80 saves timer struct+50 around14cf48. Values begin at+4,
    // so the preserved value is index19, not20. Character9 uses this as its
    // charge accumulator; the original preserves it for every character.
    const auto carried=values[19];values.fill(0);values[19]=carried;delta=256;
}
void RoundActorFlags::resetRound() {
    flags23c=(flags23c&0x400000)|0x1000;
    flags240&=0xe;flags244&=0x20000040;flags248=(flags248&0xc)|2;flags24c=0;
}
void ActorTimers::set(unsigned index,int32_t ticks) {
    values.at(index)=std::bit_cast<int32_t>(uint32_t(ticks)<<8);
}
void ActorTimers::clear(unsigned index) { values.at(index)=0; }
int32_t ActorTimers::decrease(unsigned index) {
    int32_t previous=values.at(index);
    int32_t next=std::bit_cast<int32_t>(uint32_t(previous)-uint32_t(delta));
    values[index]=next<0 ? 0 : next;
    // Original returns the PREVIOUS value. The update that reaches zero is
    // still observed as active by callers; returning next loses one tick.
    return previous;
}
int32_t ActorTimers::increase(unsigned index) {
    int32_t previous=values.at(index);
    int32_t next=std::bit_cast<int32_t>(uint32_t(previous)+uint32_t(delta));
    values[index]=next>0x173400 ? 0x173400 : next;
    return previous;
}
int32_t ActorTimers::advanceContactTimers() {
    int32_t first=decrease(0);
    return first>0 ? first : decrease(1); // 0x1520a0 advances these serially.
}
bool ActorTimers::advanceActor(const ActorTimerInput& in) {
    //Hit stop skips the ordinary group, but attack windows3/4 and the
    //serial contact timers still run. All tests below use OLD timer values.
    if(values[0]<=0) {
        if(in.effectiveTable!=2&&in.mainState!=0x360000)decrease(6);
        if(decrease(5)>0&&(in.airborne||in.backD8))clear(5);
        if(in.airborne||in.back100){clear(27);clear(8);}
        if(in.mainState==0x170000)decrease(8);
        else {decrease(27);clear(8);}
        for(unsigned i:{7u,14u,20u,21u,17u,25u})decrease(i);
        increase(24);
        if(decrease(33)==0){decrease(31);decrease(32);}
        if(in.effectiveTable!=2)decrease(28);
    }
    const bool releaseObjects=decrease(4)==0;
    decrease(3);advanceContactTimers();return releaseObjects;
}
void commitLife(LifeState& actor,ActorTimers& timers,bool training) {
    if (actor.maximum<0) throw std::runtime_error("Invalid maximum life");
    if (actor.pendingDamage) {
        actor.life=std::bit_cast<int32_t>(uint32_t(actor.life)-uint32_t(actor.pendingDamage));
        actor.pendingDamage=0;
        timers.set(28,30);
    }
    if (actor.life<=0) {
        actor.life=0;
        if (training) actor.life=1;
        else actor.flags23c|=0x80;
    } else {
        actor.flags23c&=~uint32_t(0x80);
        if (actor.life>actor.maximum) actor.life=actor.maximum;
    }
    if (uint32_t(actor.queuedAction)-0x198<4) actor.flags23c|=0x40;
    else actor.flags23c&=~uint32_t(0x40);
    if (actor.y>0) actor.flags23c|=0x10;
    else actor.flags23c&=~uint32_t(0x10);
    if ((actor.flags23c&0x10) || (actor.conditions&((1u<<4)|(1u<<5)|(1u<<6)|(1u<<18))))
        actor.flags23c|=0x20;
    else actor.flags23c&=~uint32_t(0x20);
}
} // namespace ss6
