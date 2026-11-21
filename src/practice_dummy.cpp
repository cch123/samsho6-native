#include "practice_dummy.hpp"
#include "round_initialization.hpp"
#include "cpu_execution.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
constexpr uint32_t noSlot=0xffffffffu;
// 161658: the guard height against the opponent's current move. 1588c0 ran
// just before (15ab70), so the projectile and companion observations
// AI+0xdc/+0xe0 are -1: only the attack table and the 1a3798 companion
// branch (move AI+0xe0 + 0x40) can select a low guard.
void guardCommand(StateEntryActor& a,const StateEntryActor& e,const CpuTactics& tactics) {
    const unsigned variant=e.flags23c&0x200000?e.aliasCharacter1a8:e.stateCharacter198; // 150130
    bool high=true;
    if(e.stateTable()==1) {
        const auto character=e.character==19&&(e.flags23c&0x800000)?51:e.character;
        high=tactics.guardsHigh(character,variant,unsigned(e.stateIndex()));
    } else if(a.controlE4!=noSlot)high=tactics.projectileGuardHigh(a.controlE4);
    else if(auxiliaryThreatActive(e))high=tactics.guardsHigh(e.character,variant,a.controlE8+64);
    a.control88=high?0x1000000:0x800000;a.control8c=noSlot;
}
// 15ace8: system 8 (and an edited system whose descriptor byte 0xb is 0x26)
// delays the next recovery attempt through CPU timer 10.
void delayRecovery(StateEntryActor& a,const PracticeDummyFrame& f,GameRandom& random) {
    if(f.system!=8)return;
    int frames;
    if(f.opponentKind2)frames=32+random.bounded(32);
    else {
        frames=(random.bounded(2)?32:8)+random.bounded(20);
        if(a.cpuPrevious174>=2&&random.bounded(3))frames=0;
        else if(!random.bounded(4))frames=0;
    }
    a.controlTimer34=uint32_t(frames)<<8;
}
}
int practiceSupportedBehaviour(int code) {
    if(code>=4&&code<=10)return 0;
    if(code>=15&&code<=19)return 11;
    if(code>=21&&code<=24)return 20;
    if(code>=26&&code<=29)return 25;
    if(code>=31&&code<=34)return 30;
    if(code>=0x26&&code<0x46)return 0;
    return code;
}
void practiceSetBehaviour(StateEntryActor& a,int code,int& level,GameRandom& random) {
    if(int(a.controlModeC8)==code)return;
    if(code!=0x23)level=0x31;
    resetActorControl(a,random);
    a.controlModeC8=uint32_t(code);
}
bool practiceRefreshBehaviour(StateEntryActor& a,int code,int& level,GameRandom& random) {
    practiceSetBehaviour(a,code,level,random);
    const int c=int(a.controlModeC8);
    if(c==1||c==0xc)a.flags240|=1;else a.flags240&=~1u;
    if(c==-1||c==0x23||c==0x24)return false;
    if(c==0x25&&(a.flags240&4))return false;
    const auto within=[c](int base,int count){return unsigned(c-base)<unsigned(count);};
    if(within(4,7)||within(0xf,5)||within(0x15,4)||within(0x1a,4)||within(0x1f,4))return false;
    return !within(0x26,0x20);
}
void practicePosture(StateEntryActor& a,const StateEntryActor& e,const PracticeDummyFrame& f,
                     const CpuTactics& tactics,GameRandom& random) {
    resetActorControl(a,random);
    switch(int(a.controlModeC8)) {
    case 0:case 1:case 0x25:a.control88|=1;break;
    case 2: {
        // GUARD: hold back while threatened, hit or already in a guard state (normal 6, 11, 12).
        const bool guard=f.threat||e.stateTable()==1||a.stateTable()==2||
            a.state194==0x60000||a.state194==0xc0000||a.state194==0xb0000;
        a.control88|=guard?0x20:1;
        break;
    }
    // 1HIT GUARD: timer 28 (actor+0x220) is the 30-count window armed by the last life commit.
    case 3:if(a.timers[28]==0){a.control88=0;a.control88|=1;}else guardCommand(a,e,tactics);break;
    case 11:case 12:a.control88|=8;break;
    case 13:a.control88|=0x10;break;
    case 14:if(a.timers[28]==0){a.control88=0;a.control88|=8;}else guardCommand(a,e,tactics);break;
    case 20:a.control88|=0x80;a.control88|=0x40000000;break;
    case 25:a.control88|=0x100;a.control88|=0x40000000;break;
    case 30:a.control88|=0x40;a.control88|=0x40000000;break;
    default:throw std::runtime_error("AI:_practice"); // 15acc8 assertion
    }
}
bool practiceAirRecovery(StateEntryActor& a,const PracticeDummyFrame& f,int level,GameRandom& random) {
    const int type=f.ukemi;
    if(type==0||(a.controlFlagsB4&0x10)||!(a.flags23c&0x10)||a.stateTable()!=2)return false;
    a.controlFlagsB4|=0x10;a.controlTimer34=0;
    if(type==1||type==2) {
        a.control8c=noSlot;a.control88=type==1?0x2000:0x2020;resetCpuSequence(a);
        return true;
    }
    const int c=int(a.controlModeC8);
    const int chance=c!=-1&&c!=0x23?0x43:level<6?level*10+10:0x46;
    if(random.bounded(100)>=chance){delayRecovery(a,f,random);return false;}
    a.control8c=noSlot;a.control88=0x2000;
    if(!random.bounded(2))a.control88|=0x20;
    resetCpuSequence(a);
    if(a.character==19&&!random.bounded(5))a.control88|=0xa00;
    return true;
}
bool practiceDummyVisit(StateEntryActor& a,const StateEntryActor& e,const PracticeDummyFrame& f,int& level,
                        const CpuTactics& tactics,GameRandom& random) {
    if(!practiceRefreshBehaviour(a,f.code,level,random))return false;
    if(a.conditions15c[1]&(1u<<30))practiceAirRecovery(a,f,level,random);
    else practicePosture(a,e,f,tactics,random);
    // 158fa0: the reaction latches survive only inside the damage table.
    if(a.stateTable()!=2)a.controlFlagsB4&=~0x7f0u;
    return true;
}
}
