#include "cpu_technique.hpp"
#include "cpu_technique_script.hpp"
#include <algorithm>
#include <bit>

namespace ss6 {
namespace {
constexpr uint32_t waitForTechnique=0x162ce0,recoverTechnique=0x162d70;

unsigned selectCollectedTechnique(unsigned slot,uint8_t collected,GameRandom& random) {
    // 162df0. The board's last two bits are visited in slot order, with
    // bit 6 before bit 5. The order determines the result of the RNG draw.
    constexpr std::array<unsigned,7> bits{1,2,4,8,16,64,32};
    constexpr std::array<unsigned,7> moves{3,4,5,7,8,9,10};
    if(slot>=29) {
        std::array<unsigned,7> choices;
        unsigned count=0;
        for(unsigned i=0;i<bits.size();++i)if(!(collected&bits[i]))choices[count++]=moves[i];
        slot=count?choices[random.bounded(count)]:12;
    }
    if((collected&127)==127) {
        if(slot==11 || slot==19)++slot;
    } else if(slot==12 || slot==20)--slot;
    return slot;
}
}

void beginCpuTechnique(StateEntryActor& a,const CpuExecutionFrame& f,unsigned slot) {
    bool permitted=f.bindings.allowsTechniqueCategory(a.character,slot,f.config);
    if(a.character==9 && slot==13 && !a.characterBytesF14[4]) {
        const int elapsed=std::bit_cast<int32_t>(a.controlTimers0c[9])/256;
        const int choices=int(elapsed>=180)+int(elapsed>=300)+int(elapsed>=480);
        if(choices) {
            a.characterBytesF14[4]=uint8_t(1+f.random.bounded(choices));
            a.controlTimers0c[9]=0;
        } else permitted=false;
    }
    if(a.character==48)slot=selectCollectedTechnique(slot,a.characterBytesF14[13],f.random);
    if(!permitted){finishCpuInstruction(a);return;}
    a.controlFlagsB4|=0x1000;
    const int script=f.tactics.techniqueScript(f.config.character,slot);
    if(script!=-1) {
        beginCpuTechniqueScript(a,f,script);
        return;
    }
    if(a.character==9 && slot==13)
        a.characterBytesF14[4]=std::clamp<uint8_t>(a.characterBytesF14[4],1,5);
    a.controlMotion60[3]=slot;
    a.control8c=slot+31;
    a.controlTimers0c[0]=4*256;
    a.controlMotion38[9]=waitForTechnique;
}

void chooseCpuTechniqueSlot(StateEntryActor& a,const CpuExecutionFrame& f,unsigned opcode) {
    unsigned column;
    if(opcode==216) {
        bool alternate=(a.character==11 && (a.flags23c&0x400000)) ||
                       (a.character==31 && (a.flags23c&0x10)) ||
                       (a.character==48 && (a.characterBytesF14[13]&127)==127);
        column=alternate?4:3;
    } else {
        column=opcode==218;
        switch(a.character) {
        case 11:column=bool(a.flags23c&0x400000);break;
        case 19:column=bool(a.flags23c&0x800000);break;
        case 17:case 25:
            if(a.character==25 && opcode==218)column=2;
            else {
                if(!f.opponent)throw std::logic_error("CPU category selection requires opponent height");
                column=a.character==17?f.opponent->y>=48.f:f.opponent->y<48.f;
            }
            break;
        }
    }
    const int slot=f.bindings.techniqueCategorySlot(a.character,column);
    if(slot<0)finishCpuInstruction(a);
    else beginCpuTechnique(a,f,unsigned(slot));
}

bool visitCpuTechnique(StateEntryActor& a,const CpuExecutionFrame& f) {
    const auto callback=a.controlMotion38[9];
    if(callback!=waitForTechnique && callback!=recoverTechnique)return visitCpuTechniqueScript(a,f);
    // Both callbacks compare the raw main state at 194/196, even for an
    // actor whose selector currently exposes an alternate state table.
    const auto slot=a.controlMotion60[3];
    const bool started=a.state194==(((slot+64)<<16)|1u);
    if(callback==waitForTechnique) {
        if(started) {
            a.control88=0;a.control8c=UINT32_MAX;
            a.controlMotion38[9]=recoverTechnique;
        } else if(!cpuTimerDown(a,0))finishCpuInstruction(a);
    } else if(!started || (a.character==2 && (a.bodyAction24==597 || a.bodyAction24==598))) {
        finishCpuInstruction(a);
    }
    return true;
}
}

