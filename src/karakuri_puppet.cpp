#include "karakuri_puppet.hpp"
#include "state_entry.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
int32_t& mode128(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x128/4]);}
int32_t& mode12c(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x12c/4]);}
bool clipDone(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& b){o[0x38/4]=(o[0x38/4]&~mirror)|(b[0x38/4]&mirror);} //11dbb8
// 202000: the owner is held in one of these opponents' capture rows (594840: (char, k) pairs).
bool captured(const StateEntryActor& owner,unsigned opponentCharacter) {
    if(owner.stateTable()!=2)return false;
    const int k=owner.stateIndex()-0x50;
    if(k<0)return false;
    static constexpr unsigned pairs[3][2]{{0x19,1},{0x20,1},{0x20,2}};
    for(const auto& p:pairs)if(p[0]==opponentCharacter&&int(p[1])==k)return true;
    return false;
}
}
uint32_t spawnKarakuriPuppet(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                             unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x201b40);
    if(!handle)throw std::runtime_error("Missing puppet object slot");
    auto& o=pools.objects.at(handle-1);
    const auto t=o[0x104/4];o[0x40/4]=0;o[0x44/4]=0;o[0x104/4]=t|2;
    objects.request(o,0x22c,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000; // 1a3220's shared tail
    return handle;
}
void updateKarakuriPuppet(AuxiliaryObjects& objects,AuxiliaryObject& o,const AuxiliaryObject& ob,
                          const StateEntryActor& owner,unsigned opponentCharacter) {
    if(captured(owner,opponentCharacter)) {
        o[0x104/4]|=2;objects.request(o,0x22c,false,false);o[0x128/4]=0;o[0x12c/4]=0;
        return;
    }
    const auto R=[&](unsigned act){objects.request(o,act,false,false);};
    // 201d40: mode entry.
    bool entered=false;
    {
        const int m=mode128(o);
        if(m!=mode12c(o)) {
            AuxiliaryObjects::stop(o);o[0x104/4]&=~2u;
            if(unsigned(m)<9)switch(m) {
            case 0:o[0x104/4]|=2;R(0x22c);break;
            case 1:o[0x40/4]=ob[0x40/4];copyFacing(o,ob);R(0x22f);break;
            case 2:copyFacing(o,ob);R(0x230);break;
            case 3:R(0x231);break;case 4:R(0x232);break;case 5:R(0x233);break;
            case 6:R(0x234);break;case 7:R(0x242);break;case 8:R(0x215);break;
            }
            mode12c(o)=m;entered=true;
        }
    }
    if(!entered) {
        // 201bf0: follow the owner at 9 (ahead) or 4 (behind) per visit.
        const F ox{o[0x40/4]},bx{ob[0x40/4]};
        const int d=bx.sub(ox).truncate();
        bool hold=mode12c(o)==1;
        if(owner.stateTable()!=0)hold=false;
        else if(owner.stateIndex()==0x18)hold=false;
        else if(owner.stateIndex()==0x25)hold=false;
        const bool mir=o[0x38/4]&mirror;
        if(!hold) {
            if(d>0) {
                const F nx=ox.add(F::integer(mir?4:9));o[0x40/4]=nx.bits;
                if(bx.less(nx))o[0x40/4]=bx.bits;
            } else if(d<0) {
                const F nx=ox.sub(F::integer(mir?9:4));o[0x40/4]=nx.bits;
                if(nx.less(bx))o[0x40/4]=bx.bits;
            }
        }
        const int dd=mir?-d:d;
        // 201e90: mode update.
        const int m=mode128(o);bool s1=false;
        o[0x104/4]&=~0x100u;
        bool run=true;
        if(!(owner.flags23c&0x10)) {
            if(m==0)run=false;
            else if(m!=2){mode128(o)=2;run=false;}
        }
        if(run) {
            switch(m) {
            case 0:mode128(o)=1;break;
            case 1:case 6:case 7:if(clipDone(o))s1=true;break;
            case 2:if(clipDone(o))mode128(o)=0;break;
            case 3:case 4:case 5:s1=true;break;
            case 8:if(owner.stateTable()==2)s1=true;else if(clipDone(o))s1=true;break;
            default:break;
            }
            if(s1)mode128(o)=dd>0?3:dd<0?4:5;
        }
    }
    // 1a3ba8(o, 0.0)
    o[0xec/4]=0;o[0xf0/4]=0;o[0xb4/4]=0;
}
}
