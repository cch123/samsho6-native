#include "special_requests.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
bool queue(PermissionActor& a,unsigned slot) {
    a.pendingTable=1;a.pendingIndex=int16_t(slot+64);a.request18c=1;return true;
}
bool sameRaw(const PermissionActor& a,unsigned slot){return a.state194==((slot+64)<<16|1);}
void checkCount(const ActorCommandInput& input) {
    if(input.specialCount>32)throw std::runtime_error("Special request count outside original slots");
}
}
bool requestDamageSpecial(PermissionActor& a,const ActorCommandInput& input) {
    //14cd78 deliberately ignores the sorted priority and count. These two
    //characters have fixed escape slots even while the effective table is2.
    if(a.character==3) {
        if(input.special[22].recognized)return queue(a,22);
        if(input.special[23].recognized)return queue(a,23);
    } else if(a.character==4) {
        if(input.special[16].recognized)return queue(a,16);
        if(input.special[17].recognized)return queue(a,17);
    }
    return false;
}
bool requestSpecial(PermissionActor& a,const ActorCommandInput& input) {
    if(a.stateTable()==2)return requestDamageSpecial(a,input);
    checkCount(input);
    for(int i=0;i<input.specialCount;++i) {
        const unsigned slot=input.specialPriority[i];const auto& command=input.special.at(slot);
        if(!command.recognized)continue;
        //Only these original character/slot pairs may repeat the same raw
        //special state. Alias state numbers must not replace this comparison.
        if(sameRaw(a,slot)&&!(a.character==15&&(slot==8||slot==10))&&!(a.character==30&&slot>=17&&slot<=19))continue;
        if((a.flags244&8)&&!command.cancelAllowed)continue;
        if(a.character==15&&(slot==8||slot==10))++a.characterBytesF14[0];
        if(a.character==23) {
            auto& used=a.characterBytesF14[6];
            if(slot==17||slot==18)used|=1;
            if(slot==19||slot==20)used|=2;
            if(slot==13||slot==14)used|=4;
            if(slot==15||slot==16)used|=8;
            if(slot==24)used|=16;
            if(slot>=5&&slot<=10)a.flags244|=0x100;
        }
        if(a.character==21&&slot>=4&&slot<=6)a.flags244|=0x80;
        a.flags248&=~0x10u;
        if(a.stateTable()==1&&a.stateIndex()<64)a.flags248|=0x10;
        return queue(a,slot);
    }
    return false;
}
bool requestSpecialCancel(PermissionActor& a,const ActorCommandInput& input,const InputSystemConfig& config,const InputBindings& bindings) {
    if(config.system>8)throw std::runtime_error("Invalid special cancel system");
    if(config.system!=6)return false;
    if(!config.descriptor)throw std::runtime_error("System6 special cancel needs selected descriptor");
    if((*config.descriptor)[14]!=44||!(a.bodyFlags108&0x20)||a.stateTable()!=1)return false;
    const int current=a.stateIndex();
    if(bindings.specialFirstCategory(a.character,current))return false;
    const bool second=bindings.specialSecondCategory(a.character,current);
    if(!second&&current<64&&!(a.character==32&&a.bodyAction24==599))return false;
    checkCount(input);
    for(int i=0;i<input.specialCount;++i) {
        const unsigned slot=input.specialPriority[i];
        if(!input.special.at(slot).recognized||sameRaw(a,slot))continue;
        if(!bindings.specialCategory(a.character,int(slot+64)))continue;
        if(second&&!bindings.specialFirstCategory(a.character,int(slot+64)))continue;
        //This caller neither turns nor writes24810, unlike14c7d0. The
        //request keeps every earlier callback side effect intact.
        return queue(a,slot);
    }
    return false;
}
}
