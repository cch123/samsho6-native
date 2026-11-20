#include "andrew_ammo.hpp"
#include "auxiliary_objects.hpp"
#include "player_object.hpp"
#include "state_entry.hpp"
#include "scalar_float.hpp"
#include <bit>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t iconAct=0x23e,iconTask=0x16ec48;
}
void showAndrewAmmo(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                    StateEntryActor& a,const PlayerObject& body) {
    if(a.character!=30)return;
    // 140d78(seat, n, -1): every object of the seat, in registry order.
    for(auto task:registry)if(task) {
        auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        if(o[0x24/4]==iconAct)o[0x108/4]|=0x1000;
    }
    const unsigned stock=a.characterBytesF14[8];
    if(!stock)return;
    const int half=int(stock<8?9*stock:72)>>1;
    const auto m=body.timeline.motion();
    const bool mirrored=body.timeline.clock().objectFlags&0x80000;
    for(unsigned i=0;i<stock;++i) {
        // 16c408(cb, 0x23e, 0, 0) from the owner.
        const auto handle=objects.create(pools,registry,player,a.flags23c,body.childParentWords(),0x1396,6,0);
        if(!handle)throw std::runtime_error("Original 16ea00 writes through a null icon");
        auto& o=pools.objects.at(handle-1);
        objects.request(o,iconAct,false,true);
        o[0x104/4]|=0x1000;o[0x108/4]&=~0x2000u;
        // 11dff8: depth 30 - i, 104 |= 0x20000.
        o[0xb0/4]=F{0x41f00000u}.sub(F::integer(int32_t(i))).bits;o[0x104/4]|=0x20000;
        o[0x130/4]=0x2000;o[0x134/4]=i+1;
        const int row=int(i)/8,column=int(i)%8;
        const F rowShift=F::integer(2*row);
        const F x=mirrored?F{std::bit_cast<uint32_t>(m.x)}.add(rowShift):F{std::bit_cast<uint32_t>(m.x)}.sub(rowShift);
        o[0x40/4]=x.add(F::integer(9*column-half)).bits;
        o[0x44/4]=F::integer(120-12*row).bits;
        pools.tasks.at(o[1]-1)[0]=iconTask;
    }
}
void updateAndrewAmmo(TaggedTaskPools& pools,uint32_t task,const StateEntryActor& owner) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    if(int32_t(owner.characterBytesF14[9])<std::bit_cast<int32_t>(o[0x134/4])){o[0x108/4]|=0x1000;t[0]=0x147540;}
    o[0x130/4]=uint32_t(std::bit_cast<int32_t>(o[0x130/4])-std::bit_cast<int32_t>(o[0x30/4]));
    if(std::bit_cast<int32_t>(o[0x130/4])>0)return;
    if(owner.stateTable()!=1){o[0x108/4]|=0x1000;t[0]=0x147540;}
}
}
