#include "cpu_reactions.hpp"
#include <bit>

namespace ss6 {
namespace {
bool custom(const InputSystemConfig& config,unsigned column,int first,int last) {
    if(config.system!=6)return false;
    const int value=config.descriptor.value().at(column);
    return value>=first&&value<=last;
}
bool issue(StateEntryActor& a,int slot=-1,uint32_t mask=0) {
    a.control88=mask;a.control8c=uint32_t(slot);resetCpuSequence(a);return true;
}
bool incoming(const StateEntryActor& a,const CpuReactionFrame& r) {
    const ScalarFloat x{std::bit_cast<uint32_t>(a.x)};
    const auto range=ScalarFloat::integer(r.permissions.characterFrontRange(a.character));
    for(const auto& p:r.projectiles) {
        if(p.owner==r.seat||p.id<109||p.id>120||p.id==110)continue;
        auto distance=x.sub({std::bit_cast<uint32_t>(p.x)});
        // The projectile's travel direction determines which side can react.
        if(p.flags38&0x80000)distance.bits^=0x80000000;
        if(distance.less({0}))continue;
        distance=distance.sub(range);
        const int near=p.id==109?24:p.id==113?40:p.id==118?64:32;
        if(!distance.less(ScalarFloat::integer(near))&&!ScalarFloat::integer(near+16).less(distance))return true;
    }
    return false;
}
bool damageLock(StateEntryActor& a) {
    if(!(a.flags23c&4)) {
        if(a.controlFlagsB4&1)a.flagsB8|=0x20;
        a.controlFlagsB4&=~1u;return false;
    }
    if(a.stateTable()==2) {
        if(a.conditions15c[2]&8) {
            if(!a.timers[2]) {issue(a);a.flagsB8|=0x20;return false;}
        } else if(a.conditions15c[1]&(1u<<30)) {a.controlFlagsB4|=1;return false;}
    }
    issue(a);a.controlFlagsB4&=~0x3007u;return true;
}
void delayAirRecovery(StateEntryActor& a,const CpuDecisionFrame& d,const CpuExecutionFrame& f) {
    if(f.config.system!=8&&!custom(f.config,11,38,38))return;
    int frames=0;
    if(d.kind2)frames=32+f.random.bounded(32);
    else {
        const int base=f.random.bounded(2)?32:8;
        frames=base+f.random.bounded(20);
        if(a.cpuPrevious174>=2&&f.random.bounded(3))frames=0;
        else if(!f.random.bounded(4))frames=0;
    }
    a.controlTimer34=uint32_t(frames)<<8;
}
bool hitEscape(StateEntryActor& a,const CpuDecisionFrame& d,const CpuExecutionFrame& f) {
    const int level=f.level;
    if(!(a.flags23c&0x100)) {
        if((a.character==3||a.character==4)&&!(a.controlFlagsB4&0x40)&&a.stateTable()==2&&(a.effectiveFlags()&8)) {
            a.controlFlagsB4|=0x40;
            if(f.random.bounded(100)<(level+4)/2)return issue(a,(a.character==3?53:47)+f.random.bounded(2));
        }
        if((a.character==16||a.character==19)&&!(a.controlFlagsB4&0x20)&&a.state194==0x00100002) {
            a.controlFlagsB4|=0x20;
            if(f.random.bounded(100)<level+4)return issue(a,a.character==16?46:-1);
        }
    }
    if((a.controlFlagsB4&0x10)||!(a.flags23c&0x10)||a.stateTable()!=2)return false;
    a.controlFlagsB4|=0x10;a.controlTimer34=0;
    if(f.random.bounded(100)>=(level<6?10*level+10:70)) {delayAirRecovery(a,d,f);return false;}
    uint32_t mask=0x2000;
    if(!f.random.bounded(2))mask|=0x20;
    if(a.character==19&&!f.random.bounded(5))mask|=0xa00;
    return issue(a,-1,mask);
}
}

bool updateCpuReaction(StateEntryActor& a,const StateEntryActor& enemy,const CpuDecisionFrame& d,
                       const CpuExecutionFrame& f,const CpuReactionFrame& r) {
    const auto& cfg=f.config;
    auto allowed=[&](unsigned n){return r.permissions.condition(n,a,enemy,cfg,r.objects);};
    auto roll=[&](int chance){return f.random.bounded(100)<chance;};
    const bool armed=a.flags23c&0x1000,grounded=!(a.flags23c&0x10);
    const int level=f.level,hp=a.fieldA30,table=a.stateTable();
    if((cfg.system==3||cfg.system==4||custom(cfg,6,27,28))&&armed&&!cpuTimerDown(a,6)&&
       !(a.controlFlagsB4&0x100)&&grounded&&table!=1&&allowed(5)&&r.opponentWins+1>=r.opponentRequiredWins) {
        a.controlTimers0c[6]=180<<8;a.controlFlagsB4|=0x100;
        const int time=d.clockValue,multiplier=time==-1?2:time<11?4:time<31?2:1;
        if(roll(multiplier*(hp<50?level+8:hp<100?level/2+2:0)))return issue(a,20);
    }
    if(hitEscape(a,d,f)||damageLock(a))return true;
    const bool canPickUp=grounded&&!(a.flags23c&0x800000)&&!(a.controlFlagsBC&0xc0);
    if(!(a.controlFlagsB4&0x80)&&canPickUp&&armed&&incoming(a,r)) {
        a.controlFlagsB4|=0x80;
        if(roll((a.flags244&2)?0:2*level+8))return issue(a,9);
    }
    if(a.controlD8!=UINT32_MAX) {
        // Queued special takes over the slot without restarting the current sequence.
        a.control8c=a.controlD8+31;a.controlD8=UINT32_MAX;return true;
    }
    a.controlFlagsB4&=~2u;
    if(canPickUp&&!armed&&!(a.flags244&2)&&allowed(1)) {a.controlFlagsB4|=2;return issue(a,11);}
    if(canPickUp&&allowed(0)&&roll((a.flags244&2)&&!(a.bodyFlags108&0x40)?0:40)) {
        a.controlFlagsB4|=2;return issue(a,4);
    }
    if((cfg.system==4||custom(cfg,5,24,25))&&armed&&!cpuTimerDown(a,7)&&!(a.controlFlagsB4&0x200)&&
       grounded&&table==0&&allowed(4)) {
        a.controlFlagsB4|=0x200;a.controlTimers0c[7]=120<<8;
        if(roll(hp<50?4*level+40:hp<100?2*level+20:level+10))return issue(a,22);
    }
    if(!armed||cpuTimerDown(a,8)||(a.controlFlagsB4&0x400)||!grounded||(enemy.flags23c&0x10)||table!=0||!allowed(7))return false;
    // The cooldown is already committed when the opponent's state below
    // disqualifies an Issen. Preserve that ordering and its RNG effects.
    a.controlFlagsB4|=0x400;a.controlTimers0c[8]=24<<8;
    const int et=enemy.stateTable(),ei=enemy.stateIndex();
    int chance;
    if(et==2) {
        if(ei<32||ei>=58)return false;
        chance=6*level+30;
    } else {
        if(et==0&&(ei==54||ei==55||ei==45||ei==35))return false;
        chance=et?level+12:ei>=48&&ei<=50?99:level/2+6;
        if(!a.concentrationUsed11c)chance/=2;
    }
    return roll(chance)&&issue(a,21);
}
}
