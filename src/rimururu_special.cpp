#include "rimururu_special.hpp"
#include "battle_round.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include <bit>

namespace ss6 {
namespace {
constexpr unsigned firstScript=0x4df348;
struct Cast { int base, projectile; };
constexpr std::array<Cast,12> casts{{
    {529,2},{537,3},{567,4},{571,5},{545,6},{581,7},
    {553,8},{614,-1},{616,-1},{634,9},{623,-1},{595,10}
}};
struct Ice { unsigned group,action; uint8_t flags; int hit,guard,expiry; };
// 4e4b38[2..10]. The same byte selects the collision policy, strength
// variants and the events that can terminate the projectile.
constexpr std::array<Ice,9> ice{{
    {1,531,0x30,-1,-1,-1},{1,539,0x38,-1,-1,-1},{0,573,0xa1,-1,-1,-1},
    {0,575,0xa8,576,576,576},{1,547,0x30,-1,-1,-1},{1,587,0x39,-1,-1,-1},
    {1,559,0x31,-1,-1,-1},{2,636,0x10,-1,-1,637},{3,601,0x10,-1,-1,-1}
}};
unsigned scriptOf(const StateEntryActor& a) {
    return (a.registry28c[11]-firstScript)/20;
}
void enter(PlayerObject& body,StateEntryActor& a,const GroundStateFrame& frame,unsigned script) {
    auto& r=a.registry28c;
    if(script!=11) {
        a.opponentX=frame.opponentX;a.faceOpponent();
        GroundStateRuntime::restoreBody(body,a);
    }
    a.flags23c&=~0x02000000u;
    a.flags248&=~0x800u;
    // Flag 4 stores consecutive armed/unarmed pairs at each strength.
    // The two close-range techniques use flag 2 and index strength directly.
    const int variant=script==7||script==8?int(r[3]):int(2*r[3])+!(a.flags23c&0x1000);
    a.queuedActionA3c=casts.at(script).base+int(2*r[0])+variant;
    const int lock=script==10?64:script==9?16:0;
    if(lock) {
        auto& battle=*frame.battle;
        battle.timers.lock=lock;battle.gauges.focus46a948=int32_t(body.ownerCC);
        for(auto& tone:std::span(battle.gauges.paletteTones).subspan(512))tone|=4;
        a.flags23c|=0x08000000u;frame.weaponLock->opponent.flags23c&=~0x08000000u;
    }
    r[1]=r[0];r[2]=0xffffffff;r[6]=body.timeline.motion().y>0;
    body.scriptLatch134=0;
}
bool platformFinished(PlayerObject& body,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& frame) {
    const auto& pools=frame.battle->entry.tasks;
    for(const auto task:frame.weaponLock->objectTasks)if(task) {
        const auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        if(o[0xcc/4]!=2||o[0xd0/4]!=10)continue;
        const auto flags=o[0x104/4];
        if((o[9]==602&&o[0xc0/4]&&!(flags&1))||(flags&0x2c0000)||(o[0x100/4]&2))return true;
        const bool mirror=body.timeline.clock().objectFlags&0x80000;
        int jump=-1;
        if(input.sampledFeatures[0x168/4])jump=mirror?21:20;
        else if(input.sampledFeatures[0x160/4])jump=mirror?20:21;
        else if(input.sampledFeatures[0xe0/4])jump=19;
        // 14ff80 writes the destination only. Preserving request18c lets the
        // normal state transition, including simultaneous requests, arbitrate it.
        if(jump>=0){a.pendingTable=0;a.pendingIndex=jump;}
        return false;
    }
    return true;
}
}

bool updateRimururuSpecial(PlayerObject& body,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& frame) {
    auto& r=a.registry28c;
    if(a.callbacks260[0]==0x1edf30) {
        const unsigned selector=a.callbacks260[2];
        if(selector>=0x80&&selector<0x80+casts.size()) {
            const unsigned script=selector-0x80;
            r[0]=0;r[1]=r[2]=0xffffffff;r[3]=a.stateFlags19a&4?2u:unsigned(bool(a.stateFlags19a&2));
            r[11]=firstScript+20*script;a.callbacks260[3]=r[3];
            enter(body,a,frame,script);
            a.callbacks260[0]=0x163610;a.callbacks260[1]=1;a.callbacks260[2]=0xffffffff;
            return false;
        }
    } else {
        const unsigned script=scriptOf(a);
        const bool complete=script==11&&r[0]==1?platformFinished(body,a,input,frame):actionEnded(body,a.queuedActionA3c);
        if(!complete) {
            const auto c=body.timeline.clock();body.setFlags(c.flags104&~0x100u,c.flags108);
            r[6]=body.timeline.motion().y>0;return false;
        }
        if(script==11&&r[0]<2) {
            ++r[0];GroundStateRuntime::captureBody(body,a);enter(body,a,frame,script);return false;
        }
    }
    if(input.sampledFeatures[0xfc/4])a.flags23c|=8;else a.flags23c&=~8u;
    r.fill(0);r[2]=0xffffffff;return true;
}

void spawnRimururuIce(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> reg,unsigned slot,
                      const StateEntryActor& a,const AuxiliaryObject& parent) {
    if(!a.registry28c[11]||a.registry28c[0])return;
    const int id=casts.at(scriptOf(a)).projectile;
    if(id<0)return;
    const auto& desc=ice.at(id-2);
    const unsigned strength=a.registry28c[3];
    const uint32_t handler=id==10?0x16c700:0x16def0;
    const auto handle=objects.create(pools,reg,slot,a.flags23c,parent,0x138e +slot,2,handler);
    if(!handle)return;
    auto& o=pools.objects.at(handle-1);
    objects.request(o,desc.action+((desc.flags&1)?strength:0),false,true);
    o[0xd0/4]=unsigned(id);o[0xd4/4]=unsigned(a.stateIndex()-64);o[0x11c/4]=strength;
    objects.applyAttachmentOffset(o,parent);
}
void updateRimururuIce(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task,const StageCamera& camera,unsigned ownerAction) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    const auto& desc=ice.at(o[0xd0/4]-2);
    const unsigned flags=o[0x104/4];
    const bool ended=o[0xc0/4]&&!(flags&1);
    // The platform belongs to the caster's current ACT. It falls on the
    // next task visit after the caster leaves either standing pose.
    if(t[0]==0x16c700) {
        if(ended){objects.request(o,602,false,false);t[0]=0x16c760;}
        return;
    }
    if(t[0]==0x16c760) {
        if(ownerAction!=597&&ownerAction!=598){objects.request(o,603,false,false);t[0]=0x16c7c0;}
        return;
    }
    if(t[0]==0x16c7c0) {
        if(std::bit_cast<float>(o[0x44/4])<=0) {
            o[0x44/4]=0;o[0x104/4]&=~0x100u;o[0x108/4]|=0x2000;t[0]=0x147540;
        }
        return;
    }
    bool expired=((desc.flags&0x20)&&ended)||((desc.flags&0x80)&&(flags&4));
    if(desc.group==2) {
        const int x=int(std::bit_cast<float>(o[0x40/4]));
        if(o[0x38/4]&0x80000 ? x<=camera.left+64 : x>=camera.right-64){objects.stop(o);expired=true;}
    }
    int ending=-1;
    if(expired)ending=desc.expiry;
    else if((o[0x100/4]&2)&&desc.group==0) {
        ending=desc.guard;
        if(ending<0){expired=true;ending=desc.expiry;}
    } else if(flags&0x40000)ending=desc.hit;
    else if(flags&0x280000)ending=desc.guard;
    if(ending<0&&!expired)return;
    t[0]=0x147540;
    if(ending<0)o[0x108/4]|=0x1000;
    else {objects.stop(o);objects.request(o,unsigned(ending),false,true);o[0x108/4]|=0x2000;}
}
}
