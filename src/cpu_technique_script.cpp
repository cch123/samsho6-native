#include "cpu_technique_script.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr uint32_t firstState=0x15e428,nextState=0x15e508,waitTrigger=0x15e7c8;
struct Step {
    uint8_t move,trigger;
    int parameter;
    uint8_t chance,flags,command;
    explicit Step(std::array<uint8_t,12> row):move(row[2]),trigger(row[3]),
        parameter(std::bit_cast<int16_t>(uint16_t(row[4]|unsigned(row[5])<<8))),
        chance(row[6]),flags(row[7]),command(row[10]) {}
};
Step current(const StateEntryActor& a,const CpuExecutionFrame& f) {
    return Step(f.tactics.techniqueRow(a.cpuTechnique98[5]-1+a.cpuTechnique98[0]));
}
void finish(StateEntryActor& a,bool clearDirections=true) {
    a.controlMotion38[0]=1;a.controlFlagsBC&=~0x80u;
    a.control88=clearDirections?0:a.control88&0x1ff;a.control8c=UINT32_MAX;
}
void clearCommand(StateEntryActor& a) {
    if((a.character==9 && a.state194==0x450001) || (a.character==48 && a.state194==0x4d0001))return;
    a.control88=0;a.control8c=UINT32_MAX;
}
void steer(StateEntryActor& a) {
    constexpr std::array<uint32_t,6> directions={0x100,2,4,0x40,0x20,0x10};
    const unsigned index=a.controlMotion60[3]-(a.character==45?9:7);
    if(index<directions.size())a.control88|=directions[index];
}
uint32_t bit(int n) {return 1u<<(unsigned(n)&31);}
void loadStep(StateEntryActor& a,const CpuExecutionFrame& f) {
    auto& state=a.cpuTechnique98;
    if(state[0]==state[1])return;
    state[1]=state[0];state[3]=0;
    a.controlMotion38[9]=nextState;
    const auto row=current(a,f);
    state[2]=a.controlMotion60[3];
    a.controlMotion60[3]=row.move;
    clearCommand(a);
    if(!row.command){a.control8c=16;return;}
    if(row.flags&4){a.control88|=bit(row.parameter);return;}
    if(row.command==12)steer(a);
    if(row.command==16)a.flags244|=0x4000000;
    if(row.trigger==9)a.control88|=bit(row.parameter+9);
    if(a.character==20 && row.move==10 && a.rageState120!=1 && a.rageState120!=2)a.controlMotion60[3]=3;
    a.control8c=a.controlMotion60[3]+31;
}
bool matches(const StateEntryActor& a,const Step& row,uint32_t move) {
    if(row.command==0)return a.state194==0x270001 || a.state194==0x280001;
    const int index=int16_t(a.state194>>16);
    return uint16_t(a.state194)==1 && index==int32_t(move+((row.flags&4)?0u:64u));
}
void publishStep(StateEntryActor& a,const Step& row) {
    // These are controller masks, including the absolute high-bit directions
    // and combined button chords. They bypass human input recognition.
    constexpr unsigned masks[]={0,2,8,0x20,0x80,0x200,0x400,0x800,0x1000,
        0x202,0x402,0x802,0,0x2000000,0x4000000,0x8000000,0,0,0,0x20000600,0x10000000};
    if(row.command==12)steer(a);
    else if(row.command==18){a.control88=0;a.control8c=UINT32_MAX;}
    else if(row.command<std::size(masks))a.control88|=masks[row.command];
}
ScalarFloat sf(float v){return {std::bit_cast<uint32_t>(v)};}
bool descendingTarget(const StateEntryActor& a,const StateEntryActor& enemy,int kind) {
    if(!a.characterBytesF14[9] || enemy.stateTable()!=2 || enemy.velocityY5c>=0 ||
       (a.state194!=0x500001 && !(a.bodyFlags104&0x40000)))return false;
    const auto dx=sf(a.x).sub(sf(enemy.x));
    const auto threshold=kind==6?ScalarFloat{dx.bits&0x7fffffffu}.div(sf(2.771428346633911f)).add(sf(85)):
                                  sf(kind==7?87:55);
    const int32_t velocity=std::bit_cast<int32_t>((uint32_t(enemy.velocityY5c)+2u*uint32_t(enemy.accelerationY60))<<2);
    const auto height=sf(enemy.y).add(sf(45)).add(ScalarFloat::integer(velocity).mul(sf(1.f/65536)));
    return !threshold.less(height) && !height.less(threshold.sub(sf(32)));
}
bool positionTrigger(const StateEntryActor& a,const StateEntryActor& e,const Step& row) {
    const bool mirror=a.bodyFlags38&0x80000;
    const auto dx=sf(e.x).sub(sf(a.x));
    const int distance=dx.truncate();
    if(row.trigger==2) {
        const int offset=a.character==20 && a.state194==0x440001?std::bit_cast<int32_t>(a.cpuTechnique98[4]):0;
        return e.velocityX50>0 && (mirror?-distance:distance)<=row.parameter+offset;
    }
    if(row.trigger==3)return -row.parameter<=distance && distance<=row.parameter;
    if(row.trigger>=6)return descendingTarget(a,e,row.trigger);
    auto forward=mirror?sf(a.x).sub(sf(e.x)):dx;
    auto height=sf(a.y).sub(sf(e.y));
    if(row.trigger==4) {
        forward=forward.sub(sf(49));
        return !sf(0).less(forward) && !forward.less(sf(-48)) && !height.less(sf(0)) && !sf(28).less(height);
    }
    // 15ed20 projects four fixed-point velocity steps before testing the
    // second rectangular window; the EE additions round separately.
    auto velocity=[](int32_t v){return ScalarFloat::integer(std::bit_cast<int32_t>(uint32_t(v)<<2)).mul(sf(1.f/65536));};
    const auto projected=mirror?sf(a.x).sub(velocity(a.velocityX50)):sf(a.x).add(velocity(a.velocityX50));
    forward=(mirror?projected.sub(sf(e.x)):sf(e.x).sub(projected)).sub(sf(80));
    height=sf(a.y).sub(sf(64)).add(velocity(a.velocityY5c)).sub(sf(e.y));
    return !sf(0).less(forward) && !forward.less(sf(-96)) && !height.less(sf(0)) && !sf(72).less(height);
}
bool triggerMet(StateEntryActor& a,const CpuExecutionFrame& f,const Step& row) {
    if(row.trigger>=13)return row.trigger<=16;
    if(row.trigger>=1 && row.trigger<=5 && !(a.bodyFlags108&0x40))return false;
    if(row.trigger==1)return true;
    if(row.trigger>=2 && row.trigger<=8) {
        if(!f.opponent)throw std::runtime_error("CPU technique predicate requires opponent");
        return positionTrigger(a,*f.opponent,row);
    }
    auto& time=a.cpuTechnique98[3];
    if(row.trigger==9) {
        if(a.bodyAction24!=0x23b)return false;
        if(row.command!=17)return true;
        time+=uint32_t(f.bodyDelta30);
        if(std::bit_cast<int32_t>(time)/256>=12)a.control88|=0x1000;
    } else if(row.trigger==10) {
        time+=uint32_t(f.bodyDelta30);
        return std::bit_cast<int32_t>(time)/256>=row.parameter;
    } else if(row.trigger==11 && a.state194==0x280001) {
        a.controlMotion60[3]=40;return true;
    } else if(row.trigger==12)return (a.bodyFlags104&0x40000) && !(a.bodyFlags108&2);
    return false;
}
}
void beginCpuTechniqueScript(StateEntryActor& a,const CpuExecutionFrame& f,int script) {
    auto& state=a.cpuTechnique98;
    state={};
    const int start=f.tactics.techniqueStart(script);
    if(start<0){finish(a,false);return;}
    state[5]=unsigned(start+1);state[1]=UINT32_MAX;
    if(f.random.bounded(100)>=20+f.roundIndex*10) {
        const int offset=6+f.random.bounded(24);
        state[4]=unsigned(f.random.bounded(2)?-offset:offset);
    }
    a.controlMotion60[3]=UINT32_MAX;
    loadStep(a,f);
    a.controlTimers0c[0]=4<<8;
    a.controlMotion38[9]=firstState;
}
bool visitCpuTechniqueScript(StateEntryActor& a,const CpuExecutionFrame& f) {
    const auto callback=a.controlMotion38[9];
    if(callback!=firstState && callback!=nextState && callback!=waitTrigger)return false;
    const auto row=current(a,f);
    const auto move=a.controlMotion60[3];
    auto& state=a.cpuTechnique98;
    if(callback==firstState) {
        if(!matches(a,row,move)){if(!cpuTimerDown(a,0))finish(a);return true;}
        clearCommand(a);a.controlMotion38[9]=waitTrigger;a.controlFlagsBC|=0x80;
        if(row.trigger==9)a.control88|=bit(row.parameter+9);
    } else if(callback==nextState) {
        if(matches(a,row,move)){clearCommand(a);a.controlMotion38[9]=waitTrigger;publishStep(a,row);}
        else if(!matches(a,row,state[2]))finish(a);
    } else {
        if(!matches(a,row,move)){finish(a);return true;}
        if(!triggerMet(a,f,row))return true;
        // Training always follows the listed branch. Trigger 16 also bypasses
        // the first draw, then uses its own probability to select a row.
        if((row.flags&1) || (a.controlModeC8==35 && row.trigger!=16 && f.random.bounded(100)>=row.chance)) {
            finish(a);return true;
        }
        switch(row.trigger) {
        case 13:state[0]+=1+(row.parameter?f.random.bounded(row.parameter):0);break;
        case 14:state[0]-=row.parameter;break;
        case 15:state[0]+=row.parameter;break;
        case 16:state[0]+=f.random.bounded(100)<row.chance?row.parameter:1;break;
        default:++state[0];break;
        }
        loadStep(a,f);
    }
    return true;
}
}
