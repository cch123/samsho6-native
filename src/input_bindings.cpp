#include "input_bindings.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
std::vector<uint8_t> read(const std::filesystem::path& path,size_t count) {
    std::ifstream in(path,std::ios::binary);std::vector<uint8_t> data(count);
    if(!in.read(reinterpret_cast<char*>(data.data()),count)||in.peek()!=EOF)throw std::runtime_error("Invalid original input binding table: "+path.string());
    return data;
}
uint16_t word(const uint8_t* p){return uint16_t(p[0])|(uint16_t(p[1])<<8);}
InputBindingRecord record(const uint8_t* p){return {p[0],p[1],int16_t(word(p+2)),word(p+4),word(p+6),word(p+8),word(p+10)};}
const std::array<uint8_t,16>* descriptor(const InputSystemConfig& c) {
    if(c.system>8)throw std::runtime_error("Invalid original input system");
    if(c.system!=6)return nullptr;
    if(!c.descriptor)throw std::runtime_error("System6 input bindings require the selected descriptor");
    return &*c.descriptor;
}
bool allowsFirstCategory(const InputSystemConfig& c) { // 14fb58
    const auto* d=descriptor(c);
    return (d&&(*d)[1]!=4)||(c.system>=1&&c.system<=5)||c.system==7||c.system==8;
}
bool allowsSecondCategory(const InputSystemConfig& c) { // 14fbd8
    const auto* d=descriptor(c);
    return (d&&(*d)[2]!=7)||c.system==1||c.system==5;
}
bool alternateCommands(const InputSystemConfig& c) { //14fc30
    const auto* d=descriptor(c);return (d&&(*d)[2]==8)||c.system==1;
}
}
InputBindings::InputBindings(const std::filesystem::path& assets) {
    auto data=read(assets/"input_normal.bin",31*12);
    for(unsigned i=0;i<normal_.size();++i)normal_[i]=record(data.data()+i*12);
    data=read(assets/"input_special.bin",972*12);
    for(unsigned i=0;i<972;++i)special_.push_back(record(data.data()+i*12));
    data=read(assets/"input_characters.bin",51*12);
    for(unsigned i=0;i<51;++i)for(unsigned j=0;j<6;++j)characters_[i][j]=int16_t(word(data.data()+i*12+j*2));
    data=read(assets/"input_categories.bin",51*5);
    for(unsigned i=0;i<51;++i)std::copy_n(data.begin()+i*5,5,categories_[i].begin());
}
bool InputBindings::firstCategory(unsigned character,unsigned slot) const {
    const auto& c=categories_.at(character);
    return c[0]==slot||c[1]==slot||c[2]==slot||(character==32&&(slot==20||slot==21))||(character==48&&(slot==16||slot==18));
}
bool InputBindings::secondCategory(unsigned character,unsigned slot) const {
    const auto& c=categories_.at(character);return c[3]==slot||c[4]==slot;
}
bool InputBindings::specialCategory(unsigned character,int stateIndex) const {
    const auto slot=uint32_t(stateIndex)-64;
    return secondCategory(character,slot)||firstCategory(character,slot);
}
bool InputBindings::specialFirstCategory(unsigned character,int stateIndex) const {return firstCategory(character,uint32_t(stateIndex)-64);}
bool InputBindings::specialSecondCategory(unsigned character,int stateIndex) const {return secondCategory(character,uint32_t(stateIndex)-64);}
bool InputBindings::normalAvailable(unsigned index,const InputSystemConfig& c) const {
    auto system=c.system;
    if(const auto* d=descriptor(c)) {
        //Custom system6 substitutes individual system columns, not one
        //effective system for the entire actor. Keep the per-slot rules.
        switch(index) {
        case 14:if((*d)[3]==11)system=0;break;
        case 15:if((*d)[3]==12)system=2;break;
        case 16:if((*d)[3]==13)system=3;break;
        case 17:if((*d)[3]==15)system=5;break;
        case 18:if((*d)[3]==14)system=4;break;
        case 19:if((*d)[10]==36)system=2;break;
        case 20:if((*d)[6]==27||(*d)[6]==28)system=3;break;
        case 21:if((*d)[6]==28)system=3;if((*d)[5]==25)system=4;break;
        case 22:if((*d)[5]==24||(*d)[5]==25)system=4;break;
        case 23:if((*d)[9]==34)system=1;break;
        default:
            if(index>=24&&index<=30) {
                switch((*d)[4]) {
                case 17:case 18:system=5;break;
                case 19:system=4;break;
                case 20:system=1;break;
                case 21:system=2;break;
                case 22:system=7;break;
                }
            }
        }
    }
    return (normal_.at(index).systems>>system)&1;
}
int InputBindings::techniqueCategorySlot(unsigned character,unsigned column) const {
    const auto slot=categories_.at(character).at(column);
    return slot==255?-1:int(slot);
}
bool InputBindings::allowsTechniqueCategory(unsigned character,unsigned slot,const InputSystemConfig& c) const {
    if(firstCategory(character,slot))return allowsFirstCategory(c);
    if(secondCategory(character,slot))return allowsSecondCategory(c);
    return true;
}
bool InputBindings::specialAvailable(unsigned index,unsigned slot,const InputSystemConfig& c) const {
    descriptor(c); // Validate a custom system even for uncategorized slots.
    auto system=c.system;
    if(secondCategory(c.character,slot)) {
        const bool permitted=allowsSecondCategory(c);
        system=permitted?(alternateCommands(c)?1:5):0;
    }
    if(firstCategory(c.character,slot)) {
        const bool permitted=allowsFirstCategory(c);
        system=permitted?5:0;
    }
    return (special_.at(index).systems>>system)&1;
}
void InputBindings::initialize(ActorCommandInput& a,const InputSystemConfig* c) const {
    a.sampledFeatures.fill(0);
    for(auto& s:a.normal){s.definition=-1;s.recognized=0;s.progress={};}
    for(auto& s:a.special){s.definition=-1;s.recognized=s.cancelAllowed=0;s.progress={};}
    a.specialCount=a.specialStart=-1;a.enabled=false;
    //179178 preserves remap flags and priority bytes. In particular a null
    //config disables the owner without destroying those unrelated fields.
    if(!c)return;
    descriptor(*c);
    if(c->character>=characters_.size())throw std::runtime_error("Input character outside original binding table");
    const auto first=std::find_if(special_.begin(),special_.end(),[&](const auto& r){return r.character==c->character;});
    if(first==special_.end())throw std::runtime_error("Character needs unresolved original input alias mapping");
    for(unsigned i=0;i<31;++i) {
        a.normal[i].definition=normal_[i].command;
        a.normal[i].alternateDirections=(normal_[i].flags&0x100)!=0;
    }
    const auto& overrides=characters_[c->character];
    a.normal[23].definition=overrides[3];a.normal[2].definition=overrides[1];
    a.normal[3].definition=overrides[2];a.normal[8].definition=overrides[0];
    for(unsigned i=0;i<31;++i)if(!normalAvailable(i,*c))a.normal[i].definition=-1;
    a.specialStart=int(first-special_.begin());a.specialCount=0;a.enabled=true;
    while(a.specialCount<32) {
        const auto& r=special_.at(a.specialStart+a.specialCount);
        if(r.command==-1)break;
        auto& s=a.special[a.specialCount++];s.definition=r.command;s.alternateDirections=(r.flags&0x100)!=0;
    }
    unsigned replacement=0;
    for(int i=0;i<a.specialCount;++i) {
        if(!specialAvailable(a.specialStart+i,i,*c))a.special[i].definition=-1;
        else if(alternateCommands(*c)&&secondCategory(c->character,i)) {
            if(replacement>=2)throw std::runtime_error("Original alternate command list overflow");
            const auto command=overrides[4+replacement++];
            if(command!=-1)a.special[i].definition=command;
        }
    }
    for(int i=0;i<a.specialCount;++i)a.specialPriority[i]=uint8_t(a.specialCount-1-i);
    //179810 is selection sort with a reversed initial order. A stable sort
    //or filtering disabled commands would change equal-priority winners.
    for(int i=0;i<a.specialCount-1;++i) {
        int best=i;
        for(int j=i+1;j<a.specialCount;++j)
            if(special_[a.specialStart+a.specialPriority[j]].priority>special_[a.specialStart+a.specialPriority[best]].priority)best=j;
        if(best!=i)std::swap(a.specialPriority[i],a.specialPriority[best]);
    }
}
}
