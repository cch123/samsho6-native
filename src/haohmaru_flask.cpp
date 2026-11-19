#include "haohmaru_flask.hpp"

namespace ss6 {
uint32_t spawnHaohmaruFlask(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                           unsigned player,uint32_t actorFlags,const AuxiliaryObject& parent) {
    // ACT598 emits one descriptor-1 object at record 4. The body itself
    // carries only push and hurt boxes, so this object owns the hit and guard.
    const auto handle=objects.create(pools,registry,player,actorFlags,parent,0x138eu+player,2,0x16def0);
    if(!handle)return 0;
    auto& o=pools.objects.at(handle-1);
    objects.request(o,600,false,true);
    o[0xd0/4]=1;
    o[0xd4/4]=77-64; // 16c5f8 keeps the originating special slot even after reflection.
    o[0x11c/4]=0;
    objects.applyAttachmentOffset(o,parent);
    return handle;
}

void updateHaohmaruFlask(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task) {
    auto& t=pools.tasks.at(task-1);
    auto& o=pools.objects.at(t[7]-1);
    const auto flags=o[0x104/4];
    // Descriptor 1 has no expiry action. 16def0 sends a natural miss
    // straight to removal. A hit, guard or interception plays ACT601 first.
    if(o[0xc0/4]&&!(flags&1)) {
        t[0]=0x147540;
        o[0x108/4]|=0x1000;
    } else if((o[0x100/4]&2)||(flags&0x2c0000)) {
        objects.stop(o);
        t[0]=0x147540;
        objects.request(o,601,false,true);
        o[0x108/4]|=0x2000;
    }
}
}
