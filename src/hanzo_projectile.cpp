#include "hanzo_projectile.hpp"
#include "state_entry.hpp"
#include <algorithm>
#include <bit>

namespace ss6 {
namespace {
struct Projectile {
    unsigned phase,id,group;
    int start,hit,block,expire;
    uint8_t flags;
};
// Script records 4df478..4df4ef select these rows of 4e4b38. The flags
// govern both collision eligibility and the lifetime of this specific object.
constexpr std::array<Projectile,4> projectiles{{
    {0x4df478,11,0,535,538,539,-1,0xa1},
    {0x4df48c,12,0,552,-1,556,555,0xd1},
    {0x4df4a0,13,0,732,-1,-1,-1,0xa8},
    {0x4df4dc,135,1,724,-1,-1,-1,0x30}
}};
const Projectile& projectile(unsigned id) {
    const auto it=std::find_if(projectiles.begin(),projectiles.end(),[&](const auto& d){return d.id==id;});
    if(it==projectiles.end())throw std::runtime_error("Unknown Hanzo projectile descriptor");
    return *it;
}
}
uint8_t hanzoProjectileFlags(unsigned id) {return projectile(id).flags;}
void spawnHanzoProjectile(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                          const StateEntryActor& a,const AuxiliaryObject& parent) {
    if(!a.registry28c[11])return;
    const auto phase=a.registry28c[11]+20*a.registry28c[0];
    const auto it=std::find_if(projectiles.begin(),projectiles.end(),[&](const auto& d){return d.phase==phase;});
    if(it==projectiles.end())return;
    const auto handle=objects.create(pools,registry,player,a.flags23c,parent,0x138e + player,2,0x16def0);
    if(!handle)return;
    auto& o=pools.objects.at(handle-1);
    const auto strength=a.callbacks260[3];
    objects.request(o,unsigned(it->start)+((it->flags&1)?strength:0),false,true);
    o[0xd0/4]=it->id;o[0xd4/4]=a.stateIndex()-64;o[0x11c/4]=strength;
    objects.applyAttachmentOffset(o,parent);
}
void updateHanzoProjectile(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    const auto& d=projectile(o[0xd0/4]);
    const auto flags=o[0x104/4];
    bool expired=((d.flags&0x20)&&o[0xc0/4]&&!(flags&1))||((d.flags&0x80)&&(flags&4));
    if(!expired&&(d.flags&0x40)&&std::bit_cast<float>(o[0x44/4])<=0) {
        objects.stop(o);o[0x44/4]=0;expired=true;
    }
    // In 16def0 incoming clashes precede outgoing contacts; a real hit
    // takes precedence when both the hit and block marks were written.
    int action=-1;
    if(expired)action=d.expire;
    else if(d.group==0&&(o[0x100/4]&2)) {
        action=d.block;
        if(action<0){expired=true;action=d.expire;}
    } else if(flags&0x40000) {
        action=d.hit;
        // 16e188 removes the airborne projectile on hit even though its
        // terminate-on-hit action is -1. Other descriptors continue.
        expired=d.id==12;
    } else if(flags&0x280000)action=d.block;
    if(action<0&&!expired)return;
    t[0]=0x147540;
    if(action<0)o[0x108/4]|=0x1000;
    else {objects.stop(o);objects.request(o,unsigned(action),false,true);o[0x108/4]|=0x2000;}
}
}
