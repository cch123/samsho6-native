#pragma once
#include "battle_gauges.hpp"
#include <array>
#include <span>

namespace ss6 {
using AuxiliaryObject=std::array<uint32_t,80>;
//11f450 uses a selector, not a resource slot. Common objects use2, which
//aliases the adjacent global words intentionally; do not clamp it toplayer1.
int battleSpeedDelta(int mode);
uint32_t resolveObjectDelta(uint32_t base,unsigned selector,const GaugeState&);
struct ActorHistory;
struct AuxiliaryOwner {
    const AuxiliaryObject* body=nullptr;
    uint32_t flags23c=0,postureA2c=0;
    int32_t effectiveTable=0; //1500a8, including the pending-state override
    const ActorHistory* history=nullptr;
};
struct AuxiliaryFrame {
    const GaugeState& gauges;
    uint32_t& jumpFlags46a99c;
    int32_t speedMode140=0;
    std::array<AuxiliaryOwner,2> owners{};
};
//1207e8 copies78 object words, two clock flags and draw kind. Word140 is
//retained queue storage; beginFrame must only reset count, not erase slots.
struct ObjectDrawQueue {
    using Record=std::array<uint32_t,82>;
    std::array<Record,511> slots{};
    unsigned count=0;
    //122bc0 builds a separate pointer table. Native entries are slot+1;
    //its unused tail persists when a later frame submits fewer objects.
    std::array<uint32_t,512> order{};
    void sort(); //descending separately rounded (48+b0), stable at ties
    std::span<const uint32_t> sorted() const {return {order.data(),count};}
    void beginFrame(){count=0;} //1207d8
    void submit(const AuxiliaryObject&,const GaugeState&,uint32_t kind=0);
    std::span<const Record> active() const {return {slots.data(),count};}
};
}
