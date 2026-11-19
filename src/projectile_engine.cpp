#include "projectile_engine.hpp"
#include "script_engine.hpp"
#include "state_entry.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

// Generic descriptor projectiles. Addresses refer to SLPS_255.59; see
// docs/projectile-engine.txt. Only the groups used by admitted characters
// that do not have older hand ports are accepted; others fail explicitly.
namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
F X(const AuxiliaryObject& o){return {o[0x40/4]};}
F Y(const AuxiliaryObject& o){return {o[0x44/4]};}
bool ended(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
void hold(TaggedTaskPools& pools,uint32_t task){pools.tasks.at(task-1)[0]=0x147540;} // 147530
// 146a50(cam,x,inset,towardRight,1): reached the edge it is travelling toward.
bool reachedEdge(const StageCamera& cam,int32_t x,int32_t inset,bool towardRight) {
    return towardRight?!(x<cam.right-inset):!(cam.left+inset<x);
}
}
ProjectileTable::ProjectileTable(const std::filesystem::path& assets) {
    std::ifstream in(assets/"projectile_descriptors.bin",std::ios::binary);
    std::array<uint8_t,190*12> raw{};
    if(!in.read(reinterpret_cast<char*>(raw.data()),raw.size())||in.peek()!=EOF)
        throw std::runtime_error("Invalid projectile_descriptors.bin");
    const auto half=[&](size_t at){return int16_t(uint16_t(raw[at]|raw[at+1]<<8));};
    for(unsigned i=0;i<190;++i) {
        auto& d=descriptors_[i];const size_t at=12*i;
        d.group=raw[at];d.start=half(at+2);d.hit=half(at+4);d.block=half(at+6);d.expire=half(at+8);d.flags=raw[at+10];
    }
}
int ProjectileTable::action(unsigned id,unsigned which,unsigned variant) const {
    const auto& d=at(id);
    const int16_t v=which==0?d.start:which==1?d.hit:which==2?d.block:d.expire;
    if(v==-1)return -1;
    if(which==0&&(d.flags&1))return v+int(variant);
    return v;
}

uint32_t spawnDescriptorProjectile(const ProjectileTable& table,ProjectileOwner& w,unsigned id,unsigned variant) {
    auto& a=w.actor;
    // 16d2b0 remaps before the descriptor is read.
    if(id==0x30&&(a.flags244&0x20000000)&&a.state194==0x00410001){id=0x98;a.flags244&=~0x20000000u;}
    if(id==0x43&&(a.flags248&0x2000)){id=0xbc;a.flags248&=~0x2000u;}
    const auto& d=table.at(id);
    const int start=table.action(id,0,variant);
    uint32_t handler;
    switch(d.group) {
    case 0:case 1:case 13:handler=0x16def0;break;
    case 14:handler=0x16cac0;break;
    case 17:handler=0x16c818;break;
    default:throw std::runtime_error("Projectile group "+std::to_string(d.group)+" is not ported generically");
    }
    // 16c5f8: own kind-2 object, forced start request, no descriptor yet.
    const auto handle=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x138e + w.player,2,handler);
    if(!handle)return 0;
    auto& o=w.pools.objects.at(handle-1);
    w.objects.request(o,unsigned(start),false,true);
    o[0xd0/4]=0xffffffffu;o[0xd4/4]=uint32_t(a.stateIndex()-64);
    if(d.group==13) {
        o[0x44/4]=F::integer(w.camera.top).bits;
        if(id==0x52) {
            // Three library draws in this order: facing, x scatter, y scatter.
            if(w.random.bounded(2)==0)o[0x38/4]&=~mirror;else o[0x38/4]|=mirror;
            if(!(w.body[0x38/4]&mirror)) {
                o[0x40/4]=X(o).add(F::integer(w.random.bounded(0x50))).bits;
                if(o[0x38/4]&mirror)o[0x40/4]=X(o).add(F::integer(20)).bits;
            } else {
                o[0x40/4]=X(o).sub(F::integer(w.random.bounded(0x50))).bits;
                if(!(o[0x38/4]&mirror))o[0x40/4]=X(o).sub(F::integer(20)).bits;
            }
            o[0x44/4]=Y(o).add(F::integer(w.random.bounded(0x80))).bits;
        } else if(id==0x53&&(a.flags23c&0x100000))o[0x40/4]=w.opponentBody[0x40/4];
    } else if(d.group==17) {
        if(!w.companion)throw std::runtime_error("Chample-riding arrow requires Mina's companion");
        (*w.companion)[0x128/4]=19;
    }
    // 16d400 shared tail.
    o[0x11c/4]=variant;o[0xd0/4]=id;
    if(d.flags&4)o[0x104/4]|=0x1000;
    if(d.flags&2)o[0x108/4]|=0x8000;
    if(a.flags23c&0x100000) {
        if(id==0x53)w.objects.request(o,0x2c0,false,true);
        else if(id==0x30)w.objects.request(o,0x296,false,true);
        else if(id==0x98)w.objects.request(o,0x297,false,true);
        else if(id==0x33)w.objects.request(o,0x26a,false,true);
    }
    // 13a858 reads byte 43d05e, zero under the console versus rules ported here.
    switch(id) {
    case 0x1f:o[0xd4/4]=0x20;break; case 0x20:o[0xd4/4]=0x21;break;
    case 0x68:case 0x69:case 0x6a:case 0x6b:case 0x6c:o[0xd4/4]=id-0x68+0x22;break;
    case 0x41:case 0x42:case 0x43:case 0x44:case 0x45:case 0x46:case 0x47:case 0x48:case 0x49:
        o[0xd4/4]=id-0x41+0x27;break;
    case 0xbc:o[0xd4/4]=0x30;break;
    default:break;
    }
    return handle;
}
uint32_t spawnScriptProjectile(const ProjectileTable& table,ProjectileOwner& w,const ScriptRow& row) {
    auto& a=w.actor;
    const unsigned id=uint16_t(row.projectile),mode=row.spawnMode;
    if(mode!=0) {
        if(mode>=5)return 0; // 0xff rows reach 16dcc0's default and spawn nothing.
        throw std::runtime_error("Script spawn mode "+std::to_string(mode)+" is not ported generically");
    }
    auto& f17=a.characterBytesF14[3];
    if(row.type==0x1f){if(!f17)return 0;--f17;}
    // 16dcc0 mode 0: the attachment offset follows group placement.
    const auto spawn=[&](unsigned descriptor,unsigned variant) {
        const auto handle=spawnDescriptorProjectile(table,w,descriptor,variant);
        if(handle)AuxiliaryObjects::applyAttachmentOffset(w.pools.objects.at(handle-1),w.body);
        return handle;
    };
    const auto handle=spawn(id,a.callbacks260[3]);
    if(row.type==0x23) {
        if(!handle)throw std::runtime_error("Original 16d9c8 writes through a null projectile");
        w.pools.objects.at(handle-1)[0x40/4]=w.opponentBody[0x40/4];
    } else if(row.type==0x14)spawn(id+1,0);
    else if(row.type==0x17){spawn(id,1);spawn(id,2);}
    return handle;
}
bool isDescriptorProjectileTask(uint32_t h) {
    return h==0x16def0||h==0x16cac0||h==0x16c818||h==0x16c8d0||h==0x16c940;
}
void updateDescriptorProjectile(const ProjectileTable& table,ProjectileOwner& w,uint32_t task) {
    auto& t=w.pools.tasks.at(task-1);auto& o=w.pools.objects.at(t[7]-1);
    const auto& cam=w.camera;
    switch(t[0]) {
    case 0x16cac0: // group 14: wrap once at 2400 units beyond the view
        if(o[0x104/4]&4) {
            const F x=X(o);
            if(!x.less(F::integer(cam.right).add(F::integer(2400)))) {
                o[0x40/4]=F::integer(cam.right).bits;o[0x38/4]^=mirror;t[0]=0x16def0;
            } else if(!F::integer(cam.left).sub(F::integer(2400)).less(x)) {
                o[0x40/4]=F::integer(cam.left).bits;o[0x38/4]^=mirror;t[0]=0x16def0;
            }
        }
        if(o[0x104/4]&0x2c0000){hold(w.pools,task);o[0x108/4]|=0x1000;}
        return;
    case 0x16c818:
        if(!(o[0x104/4]&0x2c0000)&&!reachedEdge(cam,X(o).truncate(),18,!(o[0x38/4]&mirror)))return;
        o[0x12c/4]=(o[0x104/4]&0x40000)?1:0;
        w.objects.request(o,810,false,false);AuxiliaryObjects::stop(o);t[0]=0x16c8d0;
        return;
    case 0x16c8d0:
        if(ended(o)){w.objects.request(o,811,false,false);o[0x5c/4]=0x20000;o[0x60/4]=uint32_t(-0x3333);t[0]=0x16c940;}
        return;
    case 0x16c940:
        if(Y(o).less(F{0})) {
            AuxiliaryObjects::stop(o);o[0x108/4]|=0x2000;hold(w.pools,task);
            if(!w.companion)throw std::runtime_error("Chample-riding arrow requires Mina's companion");
            auto& c=*w.companion;
            if(c[0x128/4]==19)c[0x128/4]=o[0x12c/4]?11:12;
            c[0x12c/4]=0;c[0x40/4]=o[0x40/4];c[0x44/4]=0;
        }
        return;
    case 0x16def0:break;
    default:throw std::runtime_error("Unknown descriptor projectile callback");
    }
    // 16def0
    const unsigned id=o[0xd0/4],variant=o[0x11c/4];
    const auto& d=table.at(id);
    int sel=-1;
    if((d.flags&0x20)&&ended(o))sel=3;
    else if((d.flags&0x80)&&(o[0x104/4]&4)) {
        if(id==0x51) {
            auto& counter=w.actor.characterBytesF14[3];
            ++counter;
            const bool alternate=w.actor.flags23c&0x100000;
            if(alternate?counter>=4:counter>=6) {
                counter=alternate?3:5;
                spawnDescriptorProjectile(table,w,0x52,0);
            }
        }
        sel=3;
    } else if((d.flags&0x40)&&!F{0}.less(Y(o))){AuxiliaryObjects::stop(o);sel=3;o[0x44/4]=0;}
    if(d.group==2&&reachedEdge(cam,X(o).truncate(),64,!(o[0x38/4]&mirror))){AuxiliaryObjects::stop(o);sel=3;}
    if(d.group==4)throw std::runtime_error("Projectile group 4 recall is not ported generically");
    if(sel==-1) {
        if((o[0x100/4]&2)&&(d.group==0||d.group==4||d.group==16)) {
            sel=2;if(table.action(id,2,variant)==-1)sel=3;
        } else {
            if(o[0x104/4]&0x280000)sel=2;
            if(o[0x104/4]&0x40000)sel=1;
        }
    }
    if(sel==-1)return;
    const int act=table.action(id,unsigned(sel),variant);
    if(act==-1) {
        if(sel==3||(sel==1&&id==0x0c)){hold(w.pools,task);o[0x108/4]|=0x1000;}
        return;
    }
    AuxiliaryObjects::stop(o);hold(w.pools,task);w.objects.request(o,unsigned(act),false,true);o[0x108/4]|=0x2000;
}
}
