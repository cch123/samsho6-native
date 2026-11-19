#include "cpu_execution.hpp"
#include "cpu_technique.hpp"
#include "cpu_technique_script.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>
#include <string>

namespace ss6 {
uint32_t cpuTimerDown(StateEntryActor& a,unsigned index) {
    auto& timer=index==10?a.controlTimer34:a.controlTimers0c.at(index);
    const auto old=timer;
    timer=uint32_t(std::max(0,std::bit_cast<int32_t>(old-uint32_t(a.cpuTimerDelta08))));
    return old;
}
uint32_t cpuTimerUp(StateEntryActor& a,unsigned index) {
    auto& timer=index==10?a.controlTimer34:a.controlTimers0c.at(index);
    const auto old=timer;
    timer=uint32_t(std::min(0x173400,std::bit_cast<int32_t>(old+uint32_t(a.cpuTimerDelta08))));
    return old;
}
void resetCpuSequence(StateEntryActor& a) {
    a.controlC4=0;a.controlTimers0c[0]=0;
    a.controlMotion38.fill(0);a.controlMotion38[3]=a.controlMotion38[4]=UINT32_MAX;
    a.controlFlagsBC&=~0xc0u;a.controlD8=a.controlE4=a.controlE8=UINT32_MAX;
}
void finishCpuInstruction(StateEntryActor& a) { // 15f6f0
    a.controlMotion38[0]=1;a.controlFlagsBC&=~0x80u;
    a.control88&=0x1ff;a.control8c=UINT32_MAX;
}
namespace {
constexpr uint32_t noSlot=0xffffffff;
enum Handler : uint32_t {
    Begin=0x15c550,TimedDirection=0x15f8e0,
    KeepDistance=0x1607b8,MoveCloser=0x1608b0,MoveFarther=0x160960,
    DashToRange=0x160ad0,StartRangeDash=0x160b40,HoldRangeDash=0x160bd0,
    DashToEdge=0x160c90,StartEdgeDash=0x160cf8,HoldEdgeDash=0x160d88,
    TimedDash=0x160e60,StartTimedDash=0x160e80,HoldTimedDash=0x160f10,
    Backstep=0x160fd0,StartBackstep=0x160ff0,EndBackstep=0x161060,EndDash=0x161140,
    Approach=0x160348,ApproachStop=0x1603a8,ApproachExact=0x160420,ApproachStopExact=0x160480,
    Retreat=0x1605c0,RetreatStop=0x160620,RetreatExact=0x160698,RetreatStopExact=0x1606f8,
    IdleRange=0x15f9c0,IdleUntilImpact=0x15fa98,WaitDamage=0x15fed0,WaitGround=0x15ff58,
    PursueFlying=0x1630b0,CheckProjectileRange=0x163150,BeginProjectileDash=0x1631e8,HoldProjectileDash=0x163270,
    DirectionalGuard=0x161238,GuardActiveFrame=0x161320,GuardUntilHit=0x1614f0,GuardDuringHit=0x161568,GuardUntilSafe=0x161618,
    BeginWalk=0x1604f0,WalkUntilLimit=0x160550,
    BeginBoundCommand=0x15fc38,AwaitBoundCommand=0x15fce0,RecoverBoundCommand=0x15fdb8,
    AllowAttack=0x1622d8,AwaitAttack=0x162440,RecoverAttack=0x1625b8,
    AllowTimedAttack=0x162350,TimedAttack=0x162398,
    BeginJump=0x161848,Airborne=0x161958,Landing=0x161b10,
    BeginVelocityJump=0x161bc0,AwaitVelocity=0x161c80,
    StartAirAttack=0x161f18,WaitForLift=0x161f60,WaitForAirAttack=0x162080,
    BeginSteeredJump=0x161d30,SteerJump=0x161d80,EndSteer=0x161de8
};

bool systemOption(const InputSystemConfig& c,unsigned system,unsigned descriptor,unsigned value) {
    return c.system==system||(c.system==6&&c.descriptor.value().at(descriptor)==value);
}
bool elapse(StateEntryActor& a) {
    // 15de18 returns the value before subtraction. A full zero visit
    // follows the last fractional tick before a timed instruction completes.
    return cpuTimerDown(a,0)!=0;
}
bool actionBusy(const StateEntryActor& a,const InputSystemConfig& config) { // 15f730
    const auto opcode=a.controlMotion38[3];
    if(opcode-6<5||(a.character==2&&uint32_t(a.bodyAction24)-597<2))return false;
    if(a.flags23c&0x580)return true;
    if(systemOption(config,8,15,46)&&a.stateTable()==1&&opcode-131<2)return false;
    return (a.flags244&2)||a.controlCounterC0==3;
}
unsigned nextOpcode(const StateEntryActor& a,const CpuTactics& tactics) { // 15d770
    const auto& m=a.controlMotion38;
    if(m[2]<3)return m[6+m[2]];
    return m[1]==127||m[1]==255?0:tactics.sequence(m[1]+1)[0];
}
bool holdAirDirection(StateEntryActor& a,const CpuExecutionFrame& f) { // 15f800
    if(!(a.conditions15c[1]&0x80))return false;
    if(nextOpcode(a,f.tactics)==105&&!(f.characterFlags&16))a.control88|=16;
    return true;
}
void attackButtons(StateEntryActor& a,unsigned attack) { // 1626f0
    constexpr std::array<uint32_t,10> masks={
        0x200,0x400,0x800,0x1000,0x208,0x408,0x808,0x1008,0x1002,0x1004
    };
    a.control88=attack<masks.size()?masks[attack]:0;a.control8c=noSlot;
}
void boundCommand(StateEntryActor& a,const CpuExecutionFrame& f,unsigned slot,unsigned condition,unsigned timeout=8) {
    if(!f.bindings.normalAvailable(slot,f.config)){finishCpuInstruction(a);return;}
    if(slot==16) {
        const auto draw=f.random.bounded(100);
        beginCpuTechniqueScript(a,f,draw<30?990:draw<60?991:draw<80?992:993);return;
    }
    // motion+28, +38, +3c are the retry time, actual normal slot and
    // condition bit that confirms this action started.
    a.controlMotion60[0]=timeout;a.controlMotion60[4]=slot;a.controlMotion60[5]=condition;
    a.controlMotion38[9]=BeginBoundCommand;
}
void publishBoundCommand(StateEntryActor& a,const CpuExecutionFrame& f) {
    if(holdAirDirection(a,f)||actionBusy(a,f.config))return;
    const auto slot=a.controlMotion60[4];
    a.control8c=slot;
    if(slot==18||slot==15)a.control88|=0x600;
    a.controlTimers0c[0]=a.controlMotion60[0]<<8;a.controlMotion38[9]=AwaitBoundCommand;
}
void ordinaryAttack(StateEntryActor& a,const CpuExecutionFrame& f,unsigned attack,bool timed) {
    if(!timed&&(a.controlModeC8==35||a.controlModeC8==noSlot)) {
        const bool power=systemOption(f.config,0,3,11)&&f.random.bounded(100)<30&&(attack==2||attack==6);
        const bool chain=systemOption(f.config,3,3,13)&&f.random.bounded(100)<50&&attack<3;
        if(power||chain){boundCommand(a,f,power?14:16,power?47:45);return;}
    }
    attackButtons(a,attack);a.controlMotion38[9]=timed?AllowTimedAttack:AllowAttack;
}
bool originalNoOp(unsigned op) {
    return op==0||(op>=16&&op<=19)||(op>=76&&op<=79)||(op>=104&&op<=106)||
           op==110||op==111||(op>=137&&op<=139)||(op>=208&&op<=215)||
           (op>=221&&op<=223)||(op>=239&&op<=254);
}
void guard(StateEntryActor& a,const CpuExecutionFrame& f,unsigned handler) {
    const auto& e=*f.opponent;
    if(!(e.flags23c&1)&&!f.opponentThreat){finishCpuInstruction(a);return;}
    const unsigned variant=e.flags23c&0x200000?e.aliasCharacter1a8:e.stateCharacter198;
    bool high=true;
    if(e.stateTable()==1) {
        const auto character=e.character==19&&(e.flags23c&0x800000)?51:e.character;
        high=f.tactics.guardsHigh(character,variant,e.stateIndex());
    } else if(a.controlE4!=noSlot)high=f.tactics.projectileGuardHigh(a.controlE4);
    else if(auxiliaryThreatActive(e))high=f.tactics.guardsHigh(e.character,variant,a.controlE8+64);
    a.control88=high?0x1000000:0x800000;a.control8c=noSlot;
    a.controlTimers0c[0]=4<<8;a.controlMotion38[9]=handler;
}
bool walkReached(const StateEntryActor& a,const CpuExecutionFrame& f,bool retreat,bool exact) {
    const bool mirrored=a.bodyFlags38&0x80000;
    const bool crossed=mirrored?a.x<=a.opponentX:a.opponentX<=a.x;
    const int target=a.controlMotion60[1],band=a.cpuRange168;
    if(crossed)return true;
    if(retreat) {
        const int inset=a.character==46?8:a.character==47?16:34;
        const bool atRearEdge=mirrored?a.x>=640-inset:a.x<=inset;
        if(a.state194==0x30000&&(atRearEdge||f.battleDistance>=370))return true;
    } else if(a.flags248&0x40)return true;
    // The stricter callbacks wait for the midpoint flag on the exact band.
    // Passing through the target band always ends the movement.
    if(band!=target)return retreat?band>target:band<target;
    return !exact||a.conditionWord17c;
}
void begin(StateEntryActor& a,const CpuExecutionFrame& f) {
    const auto op=a.controlMotion38[3];
    a.control88=0;a.control8c=noSlot;
    // 5eb950 dispatches these durations to the same 15f888 primitive.
    constexpr std::array<unsigned,12> ticks={10,15,30,10,15,5,4,3,2,1,1,2};
    if((op>=1&&op<=12)||op==26||op==34||(op>=224&&op<=228)||op==233) {
        unsigned dir=0,time=10;
        if(op<=12){dir=op==4||op==5?3:op>=11?1:0;time=ticks[op-1];}
        else if(op==26||op==34)dir=op==26?1:5;
        else {constexpr std::array<unsigned,5> dirs={1,8,7,6,5};dir=dirs[op==233?4:op-224];time=30;}
        a.control88|=1u<<dir;a.controlTimers0c[0]=time<<8;
        a.controlMotion38[9]=TimedDirection;return;
    }
    if(op==27){a.controlMotion38[9]=BeginWalk;return;}
    if(op>=80&&op<=103) {
        constexpr std::array<unsigned,3> direction={7,8,6}; // up, up-forward, up-back
        if(op<86) {
            a.control88=1u<<direction[(op-80)/2];
            if(op&1)a.controlFlagsBC&=~8u;else a.controlFlagsBC|=8;
            a.controlMotion38[9]=BeginJump;
        } else if(op>=90&&op<=101) {
            // Velocity is signed 16.16 on the actor, converted to a scalar
            // float by the original compare. This threshold is not height.
            constexpr std::array<float,4> velocity={65470464.f,524288.f,0.f,-393216.f};
            a.controlMotion60[6]=std::bit_cast<uint32_t>(velocity[(op-90)/3]);
            a.control88=1u<<direction[(op-90)%3];a.controlFlagsBC|=8;a.controlMotion38[9]=BeginVelocityJump;
        } else {
            a.controlMotion60[8]=op<90?op-86:2*(op-102);
            a.controlMotion60[9]=op>=102;
            a.control88=a.controlMotion60[8]<2?0x100:0x40;
            a.controlFlagsBC|=8;a.controlMotion38[9]=BeginSteeredJump;
        }
        return;
    }
    if(op>=112&&op<=121){ordinaryAttack(a,f,op-112,false);return;}
    if(op==229||op==230){ordinaryAttack(a,f,op==229?9:11,false);return;}
    if(op>=125&&op<=127){ordinaryAttack(a,f,op==125?0:op==126?4:7,true);return;}
    if(op==13||op==14||op==15||op==122||op==123||op==124||op==219||op==220) {
        if(op==14&&a.character==43){finishCpuInstruction(a);return;}
        const unsigned slot=op==13?13:op==14?12:op==15?23:op==122?((a.flags23c&0x1000)?9:10):
                            op==123?6:op==124?5:21;
        const unsigned condition=op==13?40:op==14?39:op==15?41:op==122?32:op<=124?33:44;
        boundCommand(a,f,slot,condition);return;
    }
    if((op>=20&&op<=25)||(op>=28&&op<=33)) {
        const bool retreat=op>=28,exact=op%2;
        a.controlMotion60[1]=retreat?(op-28)/2+1:(op-20)/2;
        a.controlMotion38[9]=retreat?(exact?RetreatExact:Retreat):(exact?ApproachExact:Approach);
        return;
    }
    if(op==35||op==36) {
        if(!a.cpuRange168){finishCpuInstruction(a);return;}
        a.controlMotion60[2]=op==35?192:256;
        a.controlTimers0c[0]=180<<8;a.controlTimers0c[3]=0;a.controlMotion38[9]=KeepDistance;return;
    }
    if(op>=37&&op<=39){a.controlMotion60[1]=op-37;a.controlMotion38[9]=DashToRange;return;}
    if(op>=40&&op<=42){a.controlTimers0c[0]=(op-39)*5*256;a.controlMotion38[9]=TimedDash;return;}
    if(op==43||op==44){a.controlMotion38[9]=op==43?DashToEdge:Backstep;return;}
    if(op>=45&&op<=53) {
        if(op==51){a.controlMotion38[9]=WaitGround;return;}
        a.controlTimers0c[0]=(180+20*f.random.bounded(4))<<8;
        a.control88=1u<<((op>=48&&op<=50)||op==53?3:0);
        if(op>=52)a.controlMotion38[9]=IdleUntilImpact;
        else {a.controlMotion60[1]=(op-45)%3;a.controlMotion38[9]=IdleRange;}
        return;
    }
    if(op>=55&&op<=63) {
        if(op==57){a.control88=2;a.control8c=0;a.controlMotion60[1]=2;a.controlMotion38[9]=BeginProjectileDash;}
        else {
            a.control88=op<=56?2:1;
            a.controlMotion60[1]=op<=56?op-54:op<=60?op-58:op-61;
            a.controlMotion38[9]=op>=61?PursueFlying:CheckProjectileRange;
        }
        return;
    }
    if(op==64||op==65) {
        if(!f.opponent)throw std::runtime_error("CPU guard requires its opponent");
        if(systemOption(f.config,8,12,40)||(!(f.opponent->flags23c&1)&&!f.opponentThreat)){finishCpuInstruction(a);return;}
        a.control88=1u<<(op-41);a.controlTimers0c[0]=4<<8;a.controlMotion38[9]=DirectionalGuard;return;
    }
    if(op==66||op==67){boundCommand(a,f,op==66?19:17,op==66?53:52);return;}
    if(op==54||op==68||op==69) {
        if(systemOption(f.config,8,12,40)){finishCpuInstruction(a);return;}
        if(!f.opponent)throw std::runtime_error("CPU guard requires its opponent");
        guard(a,f,op==54?GuardActiveFrame:op==68?GuardUntilHit:GuardUntilSafe);return;
    }
    if(op>=140&&op<=175) {
        a.controlMotion60[7]=op-140;a.controlFlagsBC|=8;a.controlMotion38[9]=StartAirAttack;return;
    }
    if(op>=176&&op<=207){beginCpuTechnique(a,f,op-176);return;}
    if(op>=70&&op<=75) {
        // 15cc44 chooses from the system's evasion column, then checks the
        // resulting binding. Entries 71 and 75 share the same physical move.
        constexpr int slots[6][8]={
            {-1,26,29,29,26,26,-1,-1},{-1,24,30,30,24,-1,-1,24},
            {-1,25,29,29,25,29,-1,25},{-1,27,29,29,27,27,-1,-1},
            {-1,-1,29,29,-1,29,-1,-1},{-1,24,30,30,24,-1,-1,24}};
        constexpr unsigned conditions[]={12,13,11,14,0,9,38};
        const int slot=slots[op-70][inputSystemColumn(f.config)];
        if(slot<0)finishCpuInstruction(a);else boundCommand(a,f,slot,conditions[slot-24],10);
        return;
    }
    if(op>=107&&op<=109) {
        if(a.stateTable()!=2){finishCpuInstruction(a);return;}
        if(op!=107)a.control88|=0x2000;
        a.controlMotion38[9]=WaitDamage;return;
    }
    if(op==128) {
        const unsigned slot=(a.flags23c&0x1000)?2:3;
        // The command owner's normal definition at 78c/78e was selected
        // during binding initialization; these two slots both test condition 29.
        boundCommand(a,f,slot,29);return;
    }
    if(op>=129&&op<=136) {
        if(op==129||op==130||op==135||op==136) {
            const int slot=op==129?4:op==130?8:op==135?20:22;
            const int condition=op==129?17:op==130?42:op==135?43:20;
            boundCommand(a,f,slot,condition);return;
        }
        if(op==131||op==132) {
            const bool available=op==131?systemOption(f.config,0,3,11):systemOption(f.config,3,3,13);
            if(available)boundCommand(a,f,op==131?14:16,op==131?47:45);
            else ordinaryAttack(a,f,2,false);
            return;
        }
        const bool hasMeter=f.config.system==4||(f.config.system==6&&
            ((*f.config.descriptor)[3]==14||(*f.config.descriptor)[5]==24||(*f.config.descriptor)[5]==25));
        if(hasMeter&&a.systemState13c!=3&&a.systemState13c!=4&&!a.rageState120&&a.rageAmount124)
            boundCommand(a,f,18,19);
        else if(!a.rageState120)boundCommand(a,f,15,51);
        else finishCpuInstruction(a);
        return;
    }
    if(op>=216&&op<=218){chooseCpuTechniqueSlot(a,f,op);return;}
    if(op==231||op==232){a.controlMotion60[1]=op-231;a.controlMotion38[9]=Approach;return;}
    if(op>=234&&op<=238){beginCpuTechnique(a,f,op<237?6:7+f.random.bounded(6));return;}
    if(op==255)a.controlFlagsBC|=0x40;
    // The source table falls through to 15f6f0 for out-of-range words.
    else if(op<=255&&!originalNoOp(op))throw std::logic_error("Missing CPU instruction "+std::to_string(op));
    finishCpuInstruction(a);
}
void setChainOpportunity(StateEntryActor& a,GameRandom& random) {
    constexpr std::array<int,21> chance={60,60,0,0,60,60,0,0,30,30,0,0,60,0,60,0,0,60,60,60,60};
    const unsigned index=a.stateIndex();
    if(random.bounded(100)<(index<chance.size()?chance[index]:0))a.controlFlagsB4|=0x10000;
    else a.controlFlagsB4&=~0x10000u;
}
void continueChain(StateEntryActor& a,const CpuExecutionFrame& f) { //162920
    constexpr std::array<int,21> first={1,2,-1,-1,5,6,-1,-1,7,-1,-1,-1,3,-1,4,-1,-1,0,0,0,0};
    constexpr std::array<unsigned,8> attacks={0,4,3,7,1,5,2,6};
    const unsigned index=a.stateIndex();
    const bool replace=index==9||(index==8&&!f.random.bounded(2));
    const bool power=systemOption(f.config,0,3,11);
    if(replace&&(power||systemOption(f.config,3,3,13))) {
        a.controlMotion38[3]=power?131:132;
        boundCommand(a,f,power?14:16,power?47:45);
        if(a.controlMotion38[9]==BeginBoundCommand)publishBoundCommand(a,f);
        else visitCpuTechniqueScript(a,f);
    } else if(index<first.size()&&first[index]>=0) {
        const auto lo=first[index];attackButtons(a,attacks[lo+f.random.bounded(8-lo)]);
        // 162920 installs the next attack callback but doesn't visit it yet.
        a.controlMotion38[9]=AllowAttack;
    }
    a.controlFlagsB4&=~0x10000u;
}

}

void advanceCpuSequence(StateEntryActor& a,const InputSystemConfig& config,const CpuDecisionFrame& frame,
                        const CpuTactics& tactics,GameRandom& random) {
    auto& m=a.controlMotion38;
    const unsigned next=nextOpcode(a,tactics);
    const int table=a.stateTable();
    auto markComplete=[&]{m[0]=1;a.control88&=0x1ff;a.control8c=noSlot;};
    // 159018/159108/1591e0 watch following bytes, even when the current
    // callback is still active. These marker bytes can end a move on contact.
    if(next==106&&(a.controlFlagsB4&4)&&!(a.controlFlagsBC&0x80)&&(a.bodyFlags108&0x40)&&
        (table==0||(table==1&&a.timers[3]==0)))markComplete();
    if(next==110) {
        if(config.system==6&&config.descriptor.value()[14]==44) {
            a.controlFlagsBC|=0x40;
            if((a.controlFlagsB4&0x1000)&&(a.bodyFlags108&0x20)&&table==1)markComplete();
        } else if(m[2]<3)m[6+m[2]]=0;
    }
    if(next==111&&(a.controlFlagsB4&0x2000)&&systemOption(config,8,15,46)&&!(a.flags23c&16)&&
        (table==0||(table==1&&(a.bodyFlags104&0xc0000)))) {
        a.controlFlagsB4&=~0x10000u;markComplete();
    }
    if(!m[0])return;
    m[0]=0;
    // 151298 condition set 66 has flags 1 and the single bit 54. It clears
    // both words before setting that bit, without touching the opponent.
    a.conditions15c={66,0,1u<<22};
    for(;;) {
        ++m[2];
        if(m[2]>=4) {
            if(m[1]==127||m[1]==255)break;
            if(a.controlModeC8!=35)throw std::runtime_error("CPU practice sequence paging is pending");
            if(beginCpuSequence(a,config,frame,tactics,random,m[1]+1)) {
                a.control88=0;a.control8c=noSlot;
            }
        }
        const auto word=m[5+m[2]];
        if(!word)break;
        if(word>=104&&word<=106)continue;
        a.controlTimers0c[0]=0;m[4]=noSlot;m[3]=word;
        a.controlFlagsB4&=~0x300cu;a.controlFlagsBC&=~0x80u;
        return;
    }
    a.flagsB8=0;resetCpuSequence(a);a.control8c=noSlot;
    a.controlTimers0c[0]=unsigned(a.controlF8)<<8;
}

void executeCpuInstruction(StateEntryActor& a,const CpuExecutionFrame& f) {
    auto& m=a.controlMotion38;
    if(m[3]!=m[4]) {
        a.control88=0;a.control8c=noSlot;a.controlTimers0c[0]=0;
        m[4]=m[3];m[9]=Begin;
    }
    if(!m[9])return;
    if(m[9]==Begin) {
        begin(a,f);
        if(m[9]==Begin)return;
    }
    if(visitCpuTechnique(a,f))return;
    const auto hasCondition=[&](unsigned index){return a.conditions15c.at(1+index/32)&(1u<<(index%32));};
    const auto slot=a.controlMotion60[4];
    switch(m[9]) {
    case KeepDistance:case MoveCloser:case MoveFarther: {
        // There are two clocks. The 180-frame budget ages even while the
        // shorter clock suppresses a change of direction for 15 frames.
        if(!a.cpuRange168||a.stateTable()!=0||a.stateIndex()>=11||!cpuTimerDown(a,0)){finishCpuInstruction(a);return;}
        if(cpuTimerDown(a,3))return;
        const int target=a.controlMotion60[2],distance=f.battleDistance;
        if(m[9]==KeepDistance) {
            a.control88=0;a.control8c=noSlot;
            if(distance>target+32){a.control88=2;m[9]=MoveCloser;}
            else if(distance<target-32){a.control88=0x20;m[9]=MoveFarther;}
        } else if(m[9]==MoveCloser?distance<target+4:distance>target-4) {
            a.control88=0;a.control8c=noSlot;m[9]=KeepDistance;
        }
        a.controlTimers0c[3]=15<<8;return;
    }
    case DashToRange:case DashToEdge:case TimedDash:case Backstep: {
        const bool edge=(a.flags248&0x40)||f.condition178;
        if((m[9]==DashToRange&&walkReached(a,f,false,false))||(m[9]==DashToEdge&&edge)) {
            a.control88=0;a.control8c=noSlot;finishCpuInstruction(a);return;
        }
        a.control8c=m[9]==Backstep?1:0;
        m[9]=m[9]==DashToRange?StartRangeDash:m[9]==DashToEdge?StartEdgeDash:m[9]==TimedDash?StartTimedDash:StartBackstep;
        return;
    }
    case StartRangeDash:case StartEdgeDash:case StartTimedDash:case StartBackstep: {
        const bool backstep=m[9]==StartBackstep;
        if(backstep?!hasCondition(8):!(a.conditions15c[1]&0x8080))return;
        a.control88=backstep?0:2;a.control8c=noSlot;a.controlFlagsB4|=4;
        m[9]=backstep?EndBackstep:m[9]==StartRangeDash?HoldRangeDash:m[9]==StartEdgeDash?HoldEdgeDash:HoldTimedDash;
        return;
    }
    case EndBackstep:
        if(!hasCondition(8))finishCpuInstruction(a);
        return;
    case HoldRangeDash:case HoldEdgeDash:case HoldTimedDash: {
        if(!(a.conditions15c[1]&0x8080)){a.control88=0;a.control8c=noSlot;finishCpuInstruction(a);return;}
        const bool stop=m[9]==HoldRangeDash?walkReached(a,f,false,false):m[9]==HoldEdgeDash?
            (a.flags248&0x40)||f.condition178:!cpuTimerDown(a,0);
        if(!stop)return;
        a.control88=0;a.control8c=noSlot;
        if(nextOpcode(a,f.tactics)==105&&!(f.characterFlags&16)){a.control88=16;m[9]=EndDash;}
        else finishCpuInstruction(a);
        return;
    }
    case EndDash:
        if(!hasCondition(7)&&!(f.characterFlags&16)){a.control88=0;a.control8c=noSlot;finishCpuInstruction(a);}
        return;
    case IdleRange:
        if(walkReached(a,f,false,false)||!elapse(a))finishCpuInstruction(a);
        return;
    case IdleUntilImpact:
        if((a.flags23c&0x100)||a.controlCounterC0==3)return;
        if(!elapse(a)||(f.opponent&&(f.opponent->bodyFlags104&0x80000000)))finishCpuInstruction(a);
        return;
    case WaitDamage:
        if(!(a.conditions15c[2]&8)&&!(a.conditions15c[1]&(1u<<30)))finishCpuInstruction(a);
        return;
    case WaitGround:
        if(!(a.flags23c&16)&&a.state194!=0x160000&&a.state194!=0x2c0000)finishCpuInstruction(a);
        return;
    case CheckProjectileRange:
        // 1632d8 always reports false in the Japanese build.
        finishCpuInstruction(a);return;
    case PursueFlying:
        if(!f.opponent)throw std::runtime_error("CPU pursuit needs its opponent");
        if(!(f.opponent->flags23c&0x200)||a.cpuRange16a<=int(a.controlMotion60[1])||
           ((a.bodyFlags38&0x80000)?a.x<=a.opponentX:a.opponentX<=a.x))finishCpuInstruction(a);
        return;
    case BeginProjectileDash:case HoldProjectileDash:
        // 1632c8 clears the signed range before the range-mode 3 check.
        a.cpuRange16e=0;finishCpuInstruction(a);return;
    case Approach:case ApproachExact:case Retreat:case RetreatExact: {
        if(holdAirDirection(a,f)||actionBusy(a,f.config))return;
        const bool retreat=m[9]==Retreat||m[9]==RetreatExact;
        a.control88|=retreat?0x20:2;
        m[9]=retreat?(m[9]==RetreatExact?RetreatStopExact:RetreatStop):
                      (m[9]==ApproachExact?ApproachStopExact:ApproachStop);return;
    }
    case ApproachStop:case ApproachStopExact:case RetreatStop:case RetreatStopExact:
        if(walkReached(a,f,m[9]==RetreatStop||m[9]==RetreatStopExact,m[9]==RetreatStopExact||m[9]==ApproachStopExact))finishCpuInstruction(a);
        return;
    case DirectionalGuard:case GuardActiveFrame:case GuardUntilHit:case GuardUntilSafe: {
        if(!f.opponent)throw std::runtime_error("CPU guard callback requires its opponent");
        const bool hold=(a.flags23c&0x100)||a.controlCounterC0==3||(f.opponent->flags23c&1)||elapse(a)||f.opponentThreat;
        if(!hold||(m[9]==GuardActiveFrame&&(f.opponent->bodyFlags104&0x80000000)))finishCpuInstruction(a);
        if(m[9]==GuardUntilHit&&a.stateTable()==2)m[9]=GuardDuringHit;
        return;
    }
    case GuardDuringHit:
        if(a.stateTable()!=2)finishCpuInstruction(a);
        return;
    case StartAirAttack: {
        if(actionBusy(a,f.config))return;
        constexpr std::array<unsigned,3> directions={7,8,6};
        a.control88=1u<<directions[(a.controlMotion60[7]/4)%3];a.control8c=noSlot;
        m[9]=WaitForLift;return;
    }
    case WaitForLift: {
        if(!(a.flags23c&16))return;
        const unsigned move=a.controlMotion60[7];
        const auto character=a.character==19&&(a.flags23c&0x800000)?51:a.character;
        int time=f.tactics.airAttackDelay(character,move);
        if(character==11&&(a.flags23c&0x400000)) {
            // The transformed form advances the first and last attack heights.
            if(move<12)time-=6;
            else if(move>=24&&move<36)time-=10;
        }
        a.controlTimers0c[2]=uint32_t(std::max(0,time))<<8;
        a.control88=0;a.control8c=noSlot;m[9]=WaitForAirAttack;return;
    }
    case WaitForAirAttack:
        if(!(a.flags23c&16)){finishCpuInstruction(a);return;}
        if(!cpuTimerDown(a,2)) {
            a.control88=1u<<(9+a.controlMotion60[7]%4);a.control8c=noSlot;m[9]=BeginJump;
        }
        return;
    case BeginJump:
        if(a.conditions15c[1]&0x70) {
            if(a.stateTable()==0){a.control88=0;a.control8c=noSlot;}
            m[9]=Airborne;
        }
        return;
    case Airborne:
        if(nextOpcode(a,f.tactics)==104&&a.state194==0x160000){finishCpuInstruction(a);return;}
        if((a.flags23c&16)&&a.stateTable()==1){a.control88=0;a.control8c=noSlot;a.controlFlagsB4|=0x1004;}
        if(systemOption(f.config,2,10,36)&&!(a.flags244&2)&&a.velocityY5c<0&&a.y<128&&!(a.controlFlagsB4&8)) {
            if(f.random.bounded(100)<40) {
                a.control88=0;a.control8c=noSlot;boundCommand(a,f,19,53);
                if(m[9]==BeginBoundCommand)executeCpuInstruction(a,f);
                return;
            }
            a.controlFlagsB4|=8;
        }
        if(a.state194==0x160000||a.state194==0x2c0000)m[9]=Landing;
        return;
    case Landing:
        if(a.state194!=0x160000&&a.state194!=0x2c0000)finishCpuInstruction(a);
        return;
    case BeginVelocityJump:
        if(!(a.conditions15c[1]&0x70)||a.stateTable()!=0)return;
        a.control88=0;a.control8c=noSlot;m[9]=AwaitVelocity;
        [[fallthrough]];
    case AwaitVelocity:
        if(!ScalarFloat{a.controlMotion60[6]}.less(ScalarFloat::integer(a.velocityY5c)))finishCpuInstruction(a);
        return;
    case BeginSteeredJump:
        if(!(a.flags23c&16))return;
        a.control88=0;a.control8c=noSlot;m[9]=SteerJump;
        [[fallthrough]];
    case SteerJump:
        if(!(a.flags23c&16)){finishCpuInstruction(a);return;}
        if(!(a.flags244&0x20)) {
            // 161e40 emits absolute directions, independent of actor facing.
            const bool positive=a.x>320;
            const bool left=a.controlMotion60[8]==0||a.controlMotion60[8]==2;
            a.control88=left?(positive?0x100000:0x400000):(positive?0x40000:0x10000);
            a.control8c=noSlot;return;
        }
        a.control88=0;a.control8c=noSlot;m[9]=EndSteer;
        [[fallthrough]];
    case EndSteer:
        if(!(a.flags23c&16)||(a.controlMotion60[9]&&a.velocityY5c<=0))finishCpuInstruction(a);
        return;
    case TimedDirection:
        if(!actionBusy(a,f.config)&&!elapse(a))finishCpuInstruction(a);
        return;
    case BeginWalk:
        if(holdAirDirection(a,f)||actionBusy(a,f.config))return;
        a.control88|=2;m[9]=WalkUntilLimit;return;
    case WalkUntilLimit:
        if((a.flags248&0x40)||f.condition178)finishCpuInstruction(a);
        return;
    case BeginBoundCommand:
        publishBoundCommand(a,f);return;
    case AwaitBoundCommand:
        if(hasCondition(a.controlMotion60[5])) {
            a.control88=(slot==18||slot==15)?0x600:0;a.control8c=noSlot;
            a.controlFlagsB4|=4;m[9]=RecoverBoundCommand;
        } else if(!elapse(a))finishCpuInstruction(a);
        return;
    case RecoverBoundCommand:
        if(!hasCondition(a.controlMotion60[5]))finishCpuInstruction(a);
        return;
    case AllowTimedAttack:
        if(a.flags244&4){a.controlTimers0c[0]=60<<8;m[9]=TimedAttack;}return;
    case TimedAttack:
        if(!elapse(a))finishCpuInstruction(a);
        return;
    case AllowAttack:
        if(!(a.flags244&4))return;
        a.controlTimers0c[0]=8<<8;m[9]=AwaitAttack;
        [[fallthrough]];
    case AwaitAttack:
        if(a.stateTable()!=1){if(!elapse(a))finishCpuInstruction(a);return;}
        if(systemOption(f.config,8,15,46)) {
            if(a.timers[0]){if(!elapse(a))finishCpuInstruction(a);return;}
            setChainOpportunity(a,f.random);
        }
        if(a.character==41) {
            if(f.random.bounded(100)<(a.controlModeC8<38?int(f.level)*5+15:100))a.controlFlagsB4|=0x800;
            else a.controlFlagsB4&=~0x800u;
        }
        a.control88=0;a.control8c=noSlot;a.controlTimers0c[0]=0;
        m[9]=RecoverAttack;a.controlFlagsB4|=0x3004;return;
    case RecoverAttack:
        if(a.stateTable()==0&&unsigned(a.stateIndex())-25<6)return;
        if(a.stateTable()!=1){finishCpuInstruction(a);return;}
        if((a.controlFlagsB4&0x800)&&hasCondition(24)&&(a.bodyFlags104&0x40000)&&!a.timers[0]) {
            beginCpuTechnique(a,f,18);visitCpuTechnique(a,f);
        } else if(!(a.controlFlagsB4&0x800)&&(a.controlFlagsB4&0x10000)&&(a.bodyFlags104&0xc0000)&&!a.timers[0])
            continueChain(a,f);
        return;
    default:throw std::runtime_error("Unported CPU execution callback "+std::to_string(m[9]));
    }
}
}
