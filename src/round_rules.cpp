#include "round_rules.hpp"
#include "stage_camera.hpp"
#include <stdexcept>

namespace ss6 {
uint32_t ordinaryStateGates(uint32_t flags,uint32_t posture,int table,int state,
                            uint8_t descriptor,uint32_t objectFlags,int32_t timer5,bool far) {
    // 151b1c/28 and 150158 read the effective table, state and descriptor, including on the eagle.
    flags|=15;
    // Gates are evaluated BEFORE life/KO commit. Once KO was set on an
    // earlier update, the ordinary descriptor must not reopen these gates.
    if (!(posture&0x80)) {
        if (table==0) {
            if (descriptor&4) flags&=~uint32_t(1);
            if (descriptor&8) flags&=~uint32_t(2);
            if (descriptor&16) flags&=~uint32_t(4);
            if (objectFlags&0x40) flags&=~uint32_t(8);
        } else if (table==1) {
            if (descriptor&16) flags&=~uint32_t(6);
            if (state<64&&(objectFlags&0x40)) flags&=~uint32_t(8);
        } else if (table==2&&state==7&&(objectFlags&0x40)) flags&=~uint32_t(8);
    }
    if (flags&0x800) flags|=4;
    if (timer5>0) flags|=1;
    return far ? flags|0x4000 : flags&~uint32_t(0x4000);
}
int knockoutRequest(uint32_t posture,uint32_t gates,int table,int state,int32_t timer15,bool locked) {
    if (!(posture&0x80)) return -1;
    int request=!locked&&!(gates&2) ? ((posture&16) ? 31 : 30) : -1;
    const bool protectedState=table==2&&(state==15||state==30||state==31||state==16||state==61);
    if (timer15>0x257ff&&!protectedState) request=31;
    // 0x14b880 examines the CURRENT table, not the earlier queued request.
    // A completed fatal light reaction first enters normal, then this
    // fallback requests31 on the next dispatch, including on the ground.
    if (table==0||table==1) request=31;
    return request;
}
VictoryRequest victoryRequest(uint32_t posture,uint32_t gates,int table,int state,bool ended,bool condition) {
    if (table==0&&state==52) return ended ? VictoryRequest::Ready : VictoryRequest::Wait;
    if (posture&0x200000) return VictoryRequest::Dismount;
    // 1452e8: riding Rera waits in the air, otherwise requests attack 1/0x46 (and 18c).
    if (posture&0x800000) return (posture&16) ? VictoryRequest::Wait : VictoryRequest::Ride;
    if ((gates&2)||(posture&16)||condition) return VictoryRequest::Wait;
    return VictoryRequest::Queue;
}
uint8_t roundInputFlags(uint8_t flags,int state,int lock) {
    return state==4&&lock==0 ? flags&uint8_t(~1) : flags|1;
}
bool ordinaryMetersActive(int state,bool paused) { return state==4&&!paused; }
void beginVictoryCamera(StageCamera& camera,int winner,bool draw,const std::array<uint32_t,2>& postures) {
    if(winner < -1 || winner > 1)throw std::runtime_error("Invalid round winner");
    camera.commands.clear();
    if(!draw) {
        //1400a8 returns the OPPONENT of the supplied winner. Only a living
        //loser (e.g. time-out) receives the first focus and30-tick hold.
        //Ordinary KO goes straight to the winner, without this extra delay.
        if(winner!=-1&&!(postures[unsigned(1-winner)]&0x80)) {
            camera.appendCommand(2,1-winner);camera.appendCommand(3,30);
        }
        camera.appendCommand(2,winner);
    }
    camera.appendCommand(0,0);
}
void BattlePause::request(int count,int wait) {
    if (count<0||wait<0) throw std::runtime_error("Negative battle pause request");
    remaining=count;delay=wait;
}
bool BattlePause::advance() {
    paused=false;
    // 0x1390d8..139218: the delay expires on a running visit. Only the
    // following visit freezes. A freeze skips140270 entirely; halving actor
    // delta would still run collision, callbacks and timers and is incorrect.
    if (remaining>0) {
        if (delay>0) --delay;
        else {--remaining;paused=true;}
    }
    return paused;
}
}
