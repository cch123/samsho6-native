#include "asset_files.hpp"
#include "action_selection.hpp"
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
template<size_t N>void read(const std::filesystem::path& file,std::array<uint8_t,N>& data) {
    std::ifstream in(resolveAsset(file),std::ios::binary);
    if(!in.read(reinterpret_cast<char*>(data.data()),N)||in.peek()!=EOF)throw std::runtime_error("Invalid action selection table: "+file.string());
}
int lowHalf(uint32_t v){return int16_t(v&0xffff);}
int highHalf(uint32_t v){return int16_t(v>>16);}
}
int SelectionActor::stateTable() const {return lowHalf(flags23c&0x200000?state1a4:state194);}
int SelectionActor::stateIndex() const {
    if(!(flags23c&0x200000))return highHalf(state194);
    //1500d0 delegates transformed state numbers to the character helper.
    //These are logical state aliases, not arbitrary animation substitutions.
    const auto table=lowHalf(state1a4),index=highHalf(state1a4);
    if(table==0)return 19;
    if(character==45||table!=1)return 0; //209a60
    if(index==0||index==2)return 2;
    return index==1?10:0; //1ec808
}
bool SelectionActor::faceOpponent(bool force) {
    if(flags24c&4)return false;
    if(!force&&(flags23c&0x10))return false;
    if(stateTable()==1&&stateIndex()>=64&&(flags248&0x10))return false;
    const bool oldMirror=(bodyFlags38&0x80000)!=0;
    //The original compares float positions directly, and leaves facing
    //unchanged at equal X. Integer distance/facing helpers differ here.
    if(x<opponentX)bodyFlags38&=~0x80000u;
    else if(opponentX<x)bodyFlags38|=0x80000;
    return oldMirror!=bool(bodyFlags38&0x80000);
}
unsigned inputSystemColumn(const InputSystemConfig& c) {
    if(c.system>8)throw std::runtime_error("Invalid input system");
    auto result=c.system;
    if(c.system==6) {
        if(!c.descriptor)throw std::runtime_error("System6 selection needs its descriptor");
        switch((*c.descriptor)[4]) {
        case 17:case 18:result=5;break;
        case 19:result=4;break;
        case 20:result=1;break;
        case 21:result=2;break;
        case 22:result=7;break;
        }
    }
    return result==8?5:result;
}
ActionSelection::ActionSelection(const std::filesystem::path& assets) {
    read(assets/"selection_normal.bin",normal_);read(assets/"selection_attack.bin",attack_);
    read(assets/"selection_chain.bin",chain_);read(assets/"selection_normal_map.bin",normalMap_);
    read(assets/"selection_attack_map.bin",attackMap_);
    read(assets/"selection_normal_descriptors.bin",normalDescriptors_);
    read(assets/"selection_character_flags.bin",characterFlags_);read(assets/"selection_threat_actions.bin",threatActions_);
}
uint8_t ActionSelection::normalTransition(unsigned state,unsigned input,uint32_t flags) const {
    if(state>=64||input>=31)throw std::runtime_error("Normal input transition outside original table");
    const auto next=normal_[state*31+input];
    return next==255||!(flags&0x800000)?next:normalMap_.at(next);
}
uint8_t ActionSelection::attackTransition(unsigned state,unsigned input,uint32_t flags,bool chain) const {
    if(state>=64||input>=17)throw std::runtime_error("Attack input transition outside original table");
    const auto next=(chain?chain_:attack_)[state*17+input];
    return next==255||!(flags&0x800000)?next:attackMap_.at(next*2+((flags&0x1000)?0:1));
}
uint8_t ActionSelection::restrictedState(unsigned state) const {
    if(state>=64)throw std::runtime_error("Restricted state outside original descriptor table");
    return normalDescriptors_[state*5]&2?uint8_t(state):255; //1511e0
}
uint8_t ActionSelection::systemNormal(const SelectionActor& a,const ActorCommandInput& input,unsigned state,const InputSystemConfig& config,bool restricted) const {
    const auto system=inputSystemColumn(config);
    //150410 tries slots30 BEFORE29, irrespective of numeric slot order.
    constexpr unsigned slots[]={24,25,26,27,28,30,29};
    constexpr unsigned columns[]={21,22,23,24,25,27,26};
    for(unsigned i=0;i<7;++i) {
        if(!input.normal[slots[i]].recognized)continue;
        auto next=normalTransition(state,columns[i],restricted?0:a.flags23c);
        if(next==255)continue;
        switch(slots[i]) {
        case 24:case 25:if(system==5)next=56;break;
        case 26:if(system==7)next=57;break;
        case 27:if(system==5)next=60;else if(system==7)next=58;break;
        case 28:if(system==1||system==5)next=60;else if(system==7)next=57;break;
        case 29:if(system==1||system==4)next=60;else if(system==5)next=58;else if(system==7)next=57;break;
        }
        if(!restricted)return next;
        next=restrictedState(next);if(next!=255)return next;
    }
    return 255;
}
unsigned ActionSelection::normal(SelectionActor& a,const ActorCommandInput& input,unsigned state,bool threat,const InputSystemConfig& config) const {
    const auto& f=input.sampledFeatures;
    //These tests inspect the unaliased packed state194, even when200000
    //selects another effective state elsewhere. Preserve this distinction.
    if(a.state194==0x003e0000||a.state194==0x002e0000) {
        const uint32_t flag=a.state194==0x003e0000?0x8000:0x10000;
        return !(a.flags23c&flag)||(f[0x16c/4]&&f[0x170/4])?a.state194>>16:0;
    }
    const auto system=systemNormal(a,input,state,config);
    if(system!=255)return system;
    constexpr unsigned slots[]={19,13,12,0,1},columns[]={12,14,15,19,20};
    for(unsigned i=0;i<5;++i)if(input.normal[slots[i]].recognized) {
        const auto next=normalTransition(state,columns[i],a.flags23c);if(next!=255)return next;
    }
    unsigned direction=0;
    while(direction<8&&!f[49+direction])++direction;
    if((a.flags24c&2)&&!(a.flags244&1)&&!(a.bodyPendingFE&0x100)&&a.faceOpponent())direction=9;
    if(threat) {
        if(f[0xd8/4])direction=10;
        else if(f[0xd4/4])direction=11;
    }
    const auto next=normalTransition(state,direction,a.flags23c);
    //A refused final direction preserves the old state. Earlier refused
    //command candidates merely allow the next candidate to be considered.
    return next==255?state:next;
}
unsigned ActionSelection::restrictedNormal(SelectionActor& a,const ActorCommandInput& input,unsigned state,const InputSystemConfig& config) const {
    const auto system=systemNormal(a,input,state,config,true);if(system!=255)return system;
    constexpr unsigned slots[]={19,13,12,0,1},columns[]={12,14,15,19,20};
    for(unsigned i=0;i<5;++i)if(input.normal[slots[i]].recognized) {
        auto next=normalTransition(state,columns[i],0);
        if(next!=255){next=restrictedState(next);if(next!=255)return next;}
    }
    unsigned direction=0;while(direction<8&&!input.sampledFeatures[49+direction])++direction;
    //150dd8 turns BEFORE inspecting pendingFE. The ordinary1501e8 path
    //checks pendingFE first; sharing that condition would lose a facing write.
    if((a.flags24c&2)&&!(a.flags244&1)&&a.faceOpponent()&&!(a.bodyPendingFE&0x100))direction=9;
    auto next=normalTransition(state,direction,0);
    if(next!=255)next=restrictedState(next);
    return next==255?state:next;
}
int ActionSelection::attack(SelectionActor& a,const ActorCommandInput& input,unsigned state,bool chain) const {
    const auto transition=[&](unsigned column){return attackTransition(state,column,a.flags23c,chain);};
    for(unsigned i=5;i<=6;++i)if(input.normal[i].recognized) {
        const auto next=transition(15);if(next!=255){a.variantA48=int(i-5);return next;}
    }
    if(input.normal[14].recognized){const auto next=transition(10);if(next!=255)return next;}
    if(chain&&input.normal[16].recognized){const auto next=transition(10);if(next!=255)return next;}
    for(auto i:{2u,3u})if(input.normal[i].recognized){const auto next=transition(11);if(next!=255)return next;}
    const auto& f=input.sampledFeatures;
    const bool down=f[0xfc/4]!=0;
    //Raw edges have fixed button priority. Unlike the command candidates,
    //a refused raw button does not fall through to another held edge.
    for(unsigned button=0;button<3;++button)if(f[6+button])return transition(button*2+unsigned(down));
    if(!f[9])return -1;
    if(a.character==32&&(a.flags244&0x400))return -1;
    if(f[0xcc/4])return transition(9);
    if(down)return transition(8);
    return transition(f[0xc8/4]?7:6);
}
int ActionSelection::supplemental(SelectionActor& a,const ActorCommandInput& input,unsigned state,bool systemOnly) const {
    const auto has=[&](unsigned i){return input.normal[i].recognized!=0;};
    const auto allowed=[&]{return a.stateTable()!=0||a.stateIndex()<25||a.stateIndex()>30;}; //150d60
    if(systemOnly) {
        if(has(20)&&a.state194!=0x00240001)return 256+36;
        if((a.flags244&12)!=12&&has(21))return 256+38;
        if(!(a.flags244&4)&&allowed()&&has(22))return 256+37;
        return -1;
    }
    if((a.flags244&10)!=10&&has(23)) {
        const auto next=normalTransition(state,16,0);if(next!=255)return next;
    }
    if(!(a.flags244&8)) {
        if(has(9)){a.variantA48=3;return 256+23;}
        if(has(10)){a.variantA48=4;return 256+24;}
    }
    if((a.flags244&12)!=12&&has(4))return 256+35;
    if(!(a.flags244&4)&&allowed()) {
        if(has(16))return 256+39;
        if(has(8))return 256+33;
    }
    if(!(a.flags244&2)) {
        //Only the first recognized candidate in this group is considered.
        //A refused transition falls to the damage recovery check below.
        constexpr unsigned slots[]={11,17,15,18},columns[]={28,13,17,18};
        for(unsigned i=0;i<4;++i)if(has(slots[i])) {
            const auto next=normalTransition(state,columns[i],0);if(next!=255)return next;
            break;
        }
    }
    return has(17)&&a.stateTable()==2&&unsigned(a.stateIndex())<6?13:-1;
}
bool ActionSelection::requestAttack(SelectionActor& a,const ActorCommandInput& input) const {
    auto state=a.stateIndex();
    if((a.flags244&4)||a.stateTable()==2)return false;
    if(a.flags244&0x2000)state=0;
    const auto next=attack(a,input,state);
    if(next==-1||next==255)return false;
    if(!(a.flags23c&0x800000)||next<17||next>=21)a.faceOpponent();
    a.pendingTable=1;a.pendingIndex=int16_t(next);a.request18c=1;return true;
}
bool ActionSelection::requestChain(SelectionActor& a,const SelectionActor& opponent,const ActorCommandInput& input,const InputSystemConfig& config) const {
    if(config.system>8)throw std::runtime_error("Invalid chain input system");
    bool enabled=config.system==8;
    if(config.system==6) {
        if(!config.descriptor)throw std::runtime_error("System6 chain selection needs its descriptor");
        enabled=(*config.descriptor)[15]==46; //14fcd0
    }
    if(!enabled||(a.flags23c&0x10)||a.stateTable()!=1||(opponent.flags23c&0x10))return false;
    if(opponent.stateTable()==2&&opponent.stateIndex()>=58)return false;
    if(!(a.bodyFlags104&0xc0000))return false;
    const auto state=a.stateIndex();if(state>=64)return false;
    auto next=attack(a,input,state,true);
    if(next==-1||next==255)return false;
    //The input at actor+5b0 is normal slot16, not a persistent actor flag.
    //This variant substitution happens only after chain-table selection.
    if(next==21&&input.normal[16].recognized)next=39;
    if(!(a.flags23c&0x800000)||next<17||next>=21)a.faceOpponent();
    a.pendingTable=1;a.pendingIndex=int16_t(next);a.request18c=1;return true;
}
bool ActionSelection::requestSupplemental(SelectionActor& a,const ActorCommandInput& input,bool systemOnly) const {
    auto state=a.stateIndex();
    if(a.stateTable()==0&&state==22)for(unsigned i=58;i<62;++i)if(input.sampledFeatures[i]){state=0;break;}
    const auto next=supplemental(a,input,state,systemOnly);if(next==-1)return false;
    const auto table=next/256,index=next%256;
    //14c510 compares the raw packed state, not the effective transformed
    //alias. Unlike attack/chain requests it preserves actor+18c.
    if(lowHalf(a.state194)==table&&highHalf(a.state194)==index)return false;
    a.faceOpponent();a.pendingTable=int16_t(table);a.pendingIndex=int16_t(index);return true;
}
bool inputGuardAllowed(const SelectionActor& a,const InputSystemConfig& config) {
    if(config.system>8)throw std::runtime_error("Invalid guard input system");
    if(config.system==6) {
        if(!config.descriptor)throw std::runtime_error("System6 guard selection needs its descriptor");
        if((*config.descriptor)[12]==40)return false;
    }
    return config.system!=8&&!(a.flags244&2)&&!(a.flags23c&0x10);
}
bool auxiliaryThreatActive(const SelectionActor& opponent) {
    //1a3798 dispatches to the character's separate auxiliary object. A
    //body action number cannot substitute for these auxiliary states.
    const auto state=opponent.auxiliaryState128;
    switch(opponent.character) {
    case 1:case 45:if(state==6||state==7)return true;break;
    case 4:if(state==14||state==18||state==24||state==31||state==38||state==41||state==45||state==25||state==26)return true;break;
    case 16:if(opponent.auxiliaryFlag134)return true;break;
    case 19:if(state==13)return true;break;
    case 24:if(state==30)return true;break;
    case 32:if(state==7||state==8)return true;break;
    case 34:if(state==13||state==16||state==17)return true;break;
    }
    return false;
}
bool ActionSelection::opponentThreat(const SelectionActor& a,const SelectionActor& opponent,const SelectionThreat& context) const {
    if(a.flags23c&0x10)return false;
    if(opponent.stateTable()==1&&context.distance<240)return true;
    for(const auto& kind:context.opponentObjectKinds)if(kind&&(*kind==2||*kind==5))return true;
    if(auxiliaryThreatActive(opponent))return true;
    if(opponent.stateTable()!=1)return false;
    for(unsigned offset=0;offset<threatActions_.size();offset+=4) {
        const auto character=threatActions_[offset];
        const auto action=int16_t(unsigned(threatActions_[offset+2])|(unsigned(threatActions_[offset+3])<<8));
        if(character==255||action==-1)break;
        if(character==opponent.character&&action==opponent.bodyAction24)return true;
    }
    return false;
}
int ActionSelection::translateNormalState(const SelectionActor& a,int state) const {
    if((a.controlKindA20!=1||a.controlModeC8==36||(a.flags240&4))&&(a.bodyFlags38&0x80000)) {
        if(state==23)state=24;else if(state==24)state=23;
    }
    if(state==23&&(characterFlags_.at(a.character)&16))state=36;
    if(state==36&&a.character==25&&(a.flags23c&0x100000))state=23;
    return state;
}
bool ActionSelection::requestNormal(SelectionActor& a,const SelectionActor& opponent,const ActorCommandInput& input,const InputSystemConfig& config,const SelectionThreat& context,bool restricted) const {
    if((a.flags244&2)||a.stateTable()==2)return false;
    const auto previous=(a.flags244&0x2000)?0:a.stateIndex();auto state=previous;
    const bool threat=inputGuardAllowed(a,config)&&opponentThreat(a,opponent,context);
    if(state==22)for(unsigned i=58;i<62;++i)if(input.sampledFeatures[i]){state=0;break;}
    const auto next=restricted?restrictedNormal(a,input,state,config):normal(a,input,state,threat,config);
    if(a.character==41&&(a.flags244&0x2000)&&(next==0||next==1||next==9||next==10||next==4||next==5))return false;
    if(next==unsigned(previous)||next==255)return false;
    a.flags248&=~0x02000000u;a.faceOpponent();
    //The comparison above precedes direction/character translation. Do not
    //move deduplication after translation or force actor+18c like attacks.
    a.pendingTable=0;a.pendingIndex=int16_t(translateNormalState(a,int(next)));return true;
}
}
