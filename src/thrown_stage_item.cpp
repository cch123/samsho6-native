#include "thrown_stage_item.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
// 4e4b38, descriptors 109..120. All twelve share contact and expiry
// actions. The bomb's two-sided hitboxes are driven by 1415a8 instead.
struct ItemAction { unsigned flight,ending; };
constexpr std::array<ItemAction,12> actions{{
    {73,74},{78,56},{82,83},{87,88},{92,93},{97,98},{102,103},
    {107,108},{112,113},{117,118},{122,123},{127,128}
}};

void attachAtHand(AuxiliaryObject& o,const PlayerObject& body) {
    // 16fae0 only publishes an anchor on the ACT's attachment record.
    // An animation ending before that record still spawns an ordinary item
    // at its inherited position and leaves an existing bomb where it was.
    if(!(body.timeline.clock().flags104&0x8000))return;
    auto parent=body.childParentWords();
    const auto& attachment=body.timeline.attachedEffect();
    parent[0x110/4]=uint32_t(attachment[1]);
    parent[0x114/4]=uint32_t(attachment[2]);
    o[0x40/4]=parent[0x40/4];
    o[0x44/4]=parent[0x44/4];
    AuxiliaryObjects::applyAttachmentOffset(o,parent);
}

void updateBomb(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task,AuxiliaryObject& o) {
    const auto delta=o[0x30/4];
    auto& flash=o[0x12c/4];
    auto& pulse=o[0x130/4];
    auto& age=o[0x134/4];
    pulse+=delta;
    const bool fast=int32_t(age)>=0x7800;
    if(int32_t(pulse)>=(fast?0x400:0x1e00)) {
        pulse=0;
        flash=fast?0x200:0x400;
    }
    auto& flags=o[0x38/4];
    flags&=~0x40000000u;
    o[0x8c/4]=0xff808080;
    if(int32_t(flash)>0) {
        flags|=0x40000000;
        o[0x8c/4]=0xffb0b0b0;
        flash-=delta;
    }
    age+=delta;
    const ScalarFloat y{o[0x44/4]},zero{0};
    if(int32_t(age)>=0xb400) {
        flags&=~0x40000000u;
        o[0x8c/4]=0xff808080;
        AuxiliaryObjects::stop(o);
        pools.tasks.at(task-1)[0]=0x147540;
        o[0x108/4]|=0x2000;
        objects.request(o,zero.less(y)?56:55,false,false);
    } else if(o[0x24/4]==133) {
        if(o[0xc0/4]&&!(o[0x104/4]&1)) {
            AuxiliaryObjects::stop(o);
            objects.request(o,76,false,false);
        }
    } else if(y.less(zero)) {
        o[0x44/4]=0;
        AuxiliaryObjects::stop(o);
        objects.request(o,133,false,false);
    }
}
}

void spawnStageBomb(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,float x) {
    // Two logical explosives share one visible sprite. Each attacks in a
    // different player's collision pass, including after either throws it.
    if(std::count(registry.begin(),registry.end(),0u)<2||pools.freeObjectCount<2||
       !pools.freeTaskHead||!pools.tasks.at(pools.freeTaskHead-1)[3])
        throw std::runtime_error("Ground bomb requires two available object tasks");
    for(unsigned seat=0;seat<2;++seat) {
        const auto handle=objects.createCommonObject(pools,registry,nullptr,0x1396,5,0x1415a8);
        auto& o=pools.objects.at(handle-1);
        o[0x10/4]=seat;
        o[0x40/4]=std::bit_cast<uint32_t>(x);
        o[0xd0/4]=110;
        o[0xb0/4]=std::bit_cast<uint32_t>(-150.f);
        o[0x104/4]|=0x20008;
        objects.request(o,76,false,false);
        if(seat==0)o[0x104/4]&=~2u;
        else o[0x104/4]|=0x202;
    }
}

void throwStageItem(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> ownTasks,
                    std::span<const uint32_t> battleTasks,unsigned seat,unsigned item,
                    uint32_t actorFlags,const PlayerObject& body) {
    const auto parent=body.childParentWords();
    if(item==8) {
        // 16c2b0 transfers both floor-bomb records without resetting their
        // fuse or assigning them to the thrower's registry.
        for(auto task:battleTasks)if(task) {
            auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            if(o[0xcc/4]!=5||(o[0x24/4]!=76&&o[0x24/4]!=133))continue;
            o[0x38/4]=(o[0x38/4]&~0x80000u)|(parent[0x38/4]&0x80000);
            objects.request(o,78,false,false);
            attachAtHand(o,body);
        }
        return;
    }
    const auto action=actions.at(item-7);
    const auto handle=objects.create(pools,ownTasks,seat,actorFlags,parent,0x138e + seat,5,0x16def0);
    if(!handle)throw std::runtime_error("Thrown item requires a free fighter object task");
    auto& o=pools.objects.at(handle-1);
    objects.request(o,action.flight,false,true);
    o[0xd0/4]=item+102;
    o[0x11c/4]=0;
    attachAtHand(o,body);
}

void updateThrownStageItem(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task) {
    auto& t=pools.tasks.at(task-1);
    auto& o=pools.objects.at(t[7]-1);
    if(t[0]==0x1415a8) {
        updateBomb(objects,pools,task,o);
        return;
    }
    const auto& action=actions.at(o[0xd0/4]-109);
    const auto flags=o[0x104/4];
    // Every item descriptor has flag C0 and category zero. The land
    // condition is inclusive. It is bypassed when expiry bit 4 is set.
    const ScalarFloat y{o[0x44/4]};
    if(!(flags&4)&&!ScalarFloat{0}.less(y))o[0x44/4]=0;
    else if(!(flags&(4|0x2c0000))&&!(o[0x100/4]&2))return;
    AuxiliaryObjects::stop(o);
    t[0]=0x147540;
    objects.request(o,action.ending,false,true);
    o[0x108/4]|=0x2000;
}
}
