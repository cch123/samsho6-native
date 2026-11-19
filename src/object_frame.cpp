#include "object_frame.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t scaled(uint32_t a,uint32_t b) {return uint32_t(std::bit_cast<int32_t>(a*b)>>8);}
}
int battleSpeedDelta(int mode) {
    switch(mode) {
    case 1:return 128;
    case 2:return 85;
    case 3:return 0;
    default:return 256;
    }
}
uint32_t resolveObjectDelta(uint32_t base,unsigned selector,const GaugeState& g) {
    if(selector>2)throw std::runtime_error("Object clock selector must be0,1,2");
    if(g.paused46a940)return 0;
    auto flags=std::array{g.words910[2],g.words910[3]};
    if(selector<2)flags[selector]=0;
    //Selector2 reads paused46a940 here, already known to be zero. When
    //both players borrow, source11f450 falls through instead of recursing.
    if(selector<2&&g.words910[10+selector]&&!g.words910[11-selector])
        return scaled(base,resolveObjectDelta(256,1-selector,g));
    uint32_t factor=256;
    if(!g.words910[6+selector]&&((flags[0]|flags[1])&1)) {
        factor=g.delta46a908;
        if(!factor&&g.words910[selector]==5)factor=64;
    }
    return scaled(base,factor);
}
void ObjectDrawQueue::sort() {
    if(count>slots.size())throw std::runtime_error("Invalid object draw count");
    for(unsigned i=0;i<count;++i)order[i]=i+1;
    //122bc0 swaps only on strict less-than. Stable sorting preserves the
    //submission order for equal rounded depths without moving raw slots.
    std::stable_sort(order.begin(),order.begin()+count,[&](uint32_t a,uint32_t b) {
        const auto& x=slots[a-1];const auto& y=slots[b-1];
        const auto dx=ScalarFloat{x[0x48/4]}.add({x[0xb0/4]});
        const auto dy=ScalarFloat{y[0x48/4]}.add({y[0xb0/4]});
        return dy.less(dx);
    });
}
void ObjectDrawQueue::submit(const AuxiliaryObject& o,const GaugeState& g,uint32_t kind) {
    if(count>=slots.size())return;
    auto& row=slots[count++];std::copy_n(o.begin(),78,row.begin());
    row[78]=g.words910[2];row[79]=g.words910[3];row[81]=kind;
}
}
