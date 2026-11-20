#include "karuta.hpp"
#include "actor_state.hpp"
#include "state_entry.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& b){o[0x38/4]=(o[0x38/4]&~mirror)|(b[0x38/4]&mirror);} //11dbb8
F beside(const AuxiliaryObject& b){const F x{b[0x40/4]};return (b[0x38/4]&mirror)?x.add(F::integer(40)):x.sub(F::integer(40));}
bool isZero(uint32_t bits){return !(bits&0x7fffffffu);} // c.eq.s with 0.0 accepts -0.0
bool retired(const AuxiliaryObject& o){return o[0xc0/4]&&(o[0x104/4]&5)==4;}
}
uint32_t spawnKaruta(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                     unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x203920);
    if(!handle)throw std::runtime_error("Missing karuta object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=0;o[0x44/4]=0;o[0x104/4]|=2;
    objects.request(o,0x300,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000; // 1a3220's shared tail
    return handle;
}
void updateKaruta(AuxiliaryObjects& objects,AuxiliaryObject& o,const AuxiliaryObject& ob,
                  StateEntryActor& owner,const StageCamera& camera) {
    const int32_t m=int32_t(o[0x128/4]);
    if(m!=int32_t(o[0x12c/4])) { // 2039a8
        AuxiliaryObjects::stop(o);o[0x104/4]&=~2u;
        const bool alt=o[0x130/4]!=0;
        switch(m) {
        case 0:o[0x104/4]|=2;objects.request(o,0x300,false,false);break;
        case 1:
            copyFacing(o,ob);o[0x40/4]=beside(ob).bits;o[0x44/4]=F::integer(camera.top).bits;
            objects.request(o,alt?0x238:0x235,false,false);break;
        case 2:objects.request(o,alt?0x239:0x236,false,false);break;
        case 3:objects.request(o,alt?0x23a:0x237,false,false);break;
        default:break;
        }
        o[0x12c/4]=uint32_t(m);
    } else switch(m) { // 203b20
    case 1:
        if(!F{0}.less(F{o[0x44/4]})){o[0x44/4]=0;AuxiliaryObjects::stop(o);o[0x128/4]=2;}
        break;
    case 2: {
        if(retired(o)){o[0x128/4]=0;break;}
        if(!isZero(o[0x44/4]))break;
        const F px=beside(ob),x{o[0x40/4]};
        if(!isZero(ob[0x44/4]))break;
        if(px.less(x.sub(F::integer(24))))break;
        if(x.add(F::integer(24)).less(px))break;
        if(!(owner.flags23c&0x1000))break;
        if(owner.stateTable()==2)break;
        o[0x128/4]=3;
        break;
    }
    case 3:
        if(o[0x104/4]&0x100) {
            if((owner.flags23c&0x1000)&&owner.stateTable()!=2) {
                owner.flags244|=0x200000;
                ActorTimers t{owner.timerDelta,owner.timers};t.set(21,0x168);owner.timers=t.values;
            }
            o[0x104/4]&=~0x100u;
        }
        if(retired(o))o[0x128/4]=0;
        break;
    default:break;
    }
    // 1a3ba8(o, -6.0)
    o[0xec/4]=0;o[0xf0/4]=std::bit_cast<uint32_t>(-6.0f);o[0xb4/4]=std::bit_cast<uint32_t>(-5.0f);
}
}
