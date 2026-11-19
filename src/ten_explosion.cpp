#include "ten_explosion.hpp"
#include "battle_round.hpp"
#include "knockout.hpp"

namespace ss6 {
namespace {
void queue(StateEntryActor& a,int action) {
    a.queuedActionA3c=action;
    a.flags248&=~0x800u;
}
void callback(StateEntryActor& a,uint32_t function,unsigned type) {
    a.callbacks260[0]=function;
    a.callbacks260[1]=type;
    a.callbacks260[2]=0xffffffffu;
}
bool releaseHold(PlayerObject& o,const StateEntryActor& a) {
    const auto flags=o.timeline.clock();
    o.setFlags(flags.flags104&~0x100u,flags.flags108);
    return (flags.flags104&0x100)||actionEnded(o,a.queuedActionA3c);
}
void setDownTimer(StateEntryActor& a) {
    a.timers[2]=60*256;
    a.flags244|=0x8000u;
}
}

void beginSpiritBurst(PlayerObject& o,StateEntryActor& a,const InputSystemConfig& config,const GroundStateFrame& f) {
    a.opponentX=f.opponentX;
    a.faceOpponent();
    GroundStateRuntime::restoreBody(o,a);
    if(a.stateIndex()==36) {
        // 16b920 freezes the global gauge clock. The separate world-effect
        // task (descriptor 4) releases it even when the attack misses.
        stopAtGround(o);
        queue(a,238);
        callback(a,0x16b9a8,1);
        f.battle->gauges.scale1239d84=0;
        f.battle->gauges.words910.at(o.ownerCC)=3;
        a.flags248|=4;
        a.concentrationUsed11c=0;
    } else if(a.stateIndex()==37) {
        stopAtGround(o);
        queue(a,148+!(a.flags23c&0x1000));
        callback(a,0x169a50,1);
        a.callbacks260[5]=0;
        // 16baf8 cancels pending super slowdowns before starting the
        // concentration freeze. The ACT's world effect later releases it.
        f.battle->timers.set(5,0);f.battle->timers.set(6,0);
        BattleGauges::beginConcentration(*f.battle,o.ownerCC);
        a.flags248|=8;
        a.concentrationUsed11c=1;
    } else {
        if(StateCallbacks::hasSystemEffect(config)&&a.systemState13c==3)
            BattleGauges::endConcentration(*f.battle,a,o.ownerCC);
        // The spent-explosion transition belongs to the NEXT state entry.
        // In particular the first strike still sees the live explosion meter.
        a.flags244|=0x80000000u;
        queue(a,227);
        callback(a,0x16bf00,1);
    }
}

void beginIssenVictim(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& f) {
    setDownTimer(a);
    if(f.weaponLock->opponent.state194!=0x260001) {
        a.pendingTable=2;a.pendingIndex=74;a.request18c=1;
        return;
    }
    stopAtGround(o);
    queue(a,430+!(a.flags23c&0x1000));
    callback(a,0x172a18,2);
    f.issenMusic(false);
}

bool updateTenExplosion(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& f) {
    const auto flags=o.timeline.clock().flags104;
    switch(a.callbacks260[0]) {
    case 0x16b9a8:
        if(releaseHold(o,a))callback(a,0x16ba08,1);
        return false;
    case 0x16ba08:
        if(!actionEnded(o,a.queuedActionA3c))return false;
        if(a.rageState120>=2)return true;
        if(f.weaponLock->opponent.flags23c&0x80) {
            f.startExplosion();
            return true;
        }
        return false;
    case 0x16bf00:
        if(flags&0x40000u)callback(a,0x16bfc0,1);
        else if(flags&0x80000u) {
            queue(a,228);
            callback(a,0x169a50,0);
            a.callbacks260[5]=0;
        } else return actionEnded(o,a.queuedActionA3c);
        return false;
    case 0x16bfc0: {
        // 16a830 compares world X to the character-00 stage limits, then
        // the defender's current position. Preserve the original facing.
        const float x=o.timeline.motion().x;
        const bool left=(o.timeline.clock().objectFlags&0x80000u)!=0;
        if(left?(x<=34 || x<=f.opponentX+24):(x>=606 || x>=f.opponentX-24)) {
            queue(a,229);
            callback(a,0x16c028,1);
        }
        return false;
    }
    case 0x16c028:
        if(f.weaponLock->opponent.state194!=0x3a0002) {
            callback(a,0x169a50,1);
            a.callbacks260[5]=0;
        }
        return false;
    case 0x172a18:
        if(releaseHold(o,a))callback(a,0x172a90,2);
        break;
    case 0x172a90:
        if(actionEnded(o,a.queuedActionA3c)) {
            setDownTimer(a);
            a.pendingTable=2;a.pendingIndex=16;a.request18c=1;
            if(!f.opponentStats->complete())f.issenMusic(true);
            if(f.weaponLock->opponent.state194==0x260001)f.weaponLock->opponent.fieldA2c=0;
            return false;
        }
        break;
    default:return false;
    }
    if(f.weaponLock->opponent.state194==0x260001)f.battle->flags138|=0x10;
    else a.fieldA2c=0;
    return false;
}
}
