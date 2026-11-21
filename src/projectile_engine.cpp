#include "projectile_engine.hpp"
#include "soft_double.hpp"
#include "state_callbacks.hpp"
#include "nakoruru_capture.hpp"
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
    case 0:case 1:case 5:case 6:case 7:case 13:handler=0x16def0;break;
    case 14:handler=0x16cac0;break;
    case 17:handler=0x16c818;break;
    // 16d654/16d690/16d6ac: the fighter throws its own weapon (Wanfu).
    case 4:handler=0x16c9e0;break; // 16d620: after a 16c408 side effect 0x235
    case 8:handler=0x16f088;break; // 16d3ac -> 16c680: the returning weapon
    case 15:handler=0x16f510;break; // 16d8c4: the delayed homing shot
    case 9:handler=0x16ccb8;break;
    case 10:handler=0x16cd60;break;
    case 11:handler=0x16ce50;break;
    case 12:handler=0x16cb88;break; // 16d6c8: no placement
    case 16:handler=0x16f8e8;break; // 16d8f4: PakuPaku's 0xa0 / 0xa1, no placement
    default:throw std::runtime_error("Projectile group "+std::to_string(d.group)+" is not ported generically");
    }
    if(d.group>=8&&d.group<=11)a.flags23c&=~0x1000u;
    if(d.group==4) { // 16c408(cb, 0x235, 0, 0) before the projectile
        const auto side=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x1396,6,0);
        if(!side)throw std::runtime_error("Original 16c408 writes through a null object");
        auto& e=w.pools.objects.at(side-1);w.objects.request(e,0x235,false,true);e[0x108/4]|=0x2000;
    }
    // 16c5f8: own kind-2 object, forced start request, no descriptor yet.
    const auto handle=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x138e + w.player,2,handler);
    if(!handle)return 0;
    auto& o=w.pools.objects.at(handle-1);
    w.objects.request(o,unsigned(start),false,true);
    o[0xd0/4]=0xffffffffu;o[0xd4/4]=uint32_t(a.stateIndex()-64);
    // 16d6dc placement: group 5 at cam.left when the body is mirrored, else
    // cam.right (group 7 the opposite edge), y = 0; group 6 at the opponent's x, y = cam.1c.
    if(d.group==5||d.group==7) {
        const bool m=w.body[0x38/4]&mirror;
        o[0x40/4]=F::integer((m==(d.group==5))?w.camera.left:w.camera.right).bits;o[0x44/4]=0;
    } else if(d.group==6) {
        o[0x40/4]=w.opponentBody[0x40/4];o[0x44/4]=F::integer(w.camera.top).bits;
    }
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
    } else if(d.group==8) {
        // 16c680: expire/hit/block ACTs kept for the flight and the catch.
        o[0x134/4]=uint32_t(table.action(id,3,variant));o[0x12c/4]=uint32_t(table.action(id,1,variant));
        o[0x130/4]=uint32_t(table.action(id,2,variant));o[0x11c/4]=0;o[0x128/4]=0;
    } else if(d.group==15) {
        o[0x128/4]=0xa000;o[0x12c/4]=0x3000; // life and drift time
    } else if(d.group>=9&&d.group<=11) {
        o[0x104/4]|=8;
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
    if(mode==2) {
        // 16dcc0 mode 2 -> 16c4e0(cb, act, 0, 0): an own kind-6 effect (tag
        // 0x1392 + seat, no callback) at the body position with a forced ACT
        // request and 108 |= 0x1a000; row.projectile is the ACT, not a descriptor.
        const auto handle=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x1392 + w.player,6,0);
        if(!handle)return 0;
        auto& o=w.pools.objects.at(handle-1);
        w.objects.request(o,id,false,true);
        o[0x108/4]|=0x1a000;
        // 16dd44: the shared tail adds the ACT attachment offset only while body 104 has 0x8000.
        if(w.body[0x104/4]&0x8000)AuxiliaryObjects::applyAttachmentOffset(o,w.body);
        return handle;
    }
    if(mode==4) {
        // 16d0e0(cb, act): an own kind-6 object (tag 0x1396, task 16d1a0)
        // marked by the body ACT (603/604 -> 0x400000, 605/606 -> 0x800000);
        // the unarmed body requests act + 1.
        const auto handle=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x1396,6,0x16d1a0);
        if(!handle)return 0;
        auto& o=w.pools.objects.at(handle-1);
        const auto bodyAct=w.body[0x24/4];
        if(bodyAct-0x25bu<2)o[0x108/4]|=0x400000;
        else if(bodyAct-0x25du<2)o[0x108/4]|=0x800000;
        w.objects.request(o,id+!(a.flags23c&0x1000),false,true);
        if(w.body[0x104/4]&0x8000)AuxiliaryObjects::applyAttachmentOffset(o,w.body);
        return handle;
    }
    if(mode==3) {
        // 16dcc0 mode 3 -> 16c408(cb, act, 0, 0): an own kind-6 effect (tag
        // 0x1396, no callback) at the body with a forced ACT request,
        // 108 |= 0x2000 there and 0x8000 here, then the shared 16dd44 tail.
        const auto handle=w.objects.create(w.pools,w.registry,w.player,a.flags23c,w.body,0x1396,6,0);
        if(!handle)return 0;
        auto& o=w.pools.objects.at(handle-1);
        w.objects.request(o,id,false,true);
        o[0x108/4]|=0x2000|0x8000;
        if(w.body[0x104/4]&0x8000)AuxiliaryObjects::applyAttachmentOffset(o,w.body);
        return handle;
    }
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
    return h==0x16def0||h==0x16c9e0||h==0x16f088||h==0x16f510||h==0x16d1a0||h==0x16d270||h==0x16cac0||h==0x16c818||h==0x16c8d0||h==0x16c940||
           h==0x16ccb8||h==0x16cd60||h==0x16ce50||h==0x16cf40||h==0x16f8e8;
}
namespace {
// 16ff18: the thrown weapon lands and becomes the owner's ordinary dropped
// weapon (kind 4, ACT 467, task tag 0x1390 + seat), which 140f00 picks up.
void dropThrownWeapon(ProjectileOwner& w,uint32_t task,AuxiliaryObject& o) {
    AuxiliaryObjects::stop(o);hold(w.pools,task);o[0x44/4]=0;
    o[0x108/4]&=~0x3000u;w.objects.request(o,467,false,false);
    o[0xcc/4]=4;o[0x10/4]=o[0xc/4];o[0xd0/4]=0xffffffffu;
    w.pools.tasks.at(task-1)[5]=0x1390+w.player;
}
// 16c5f8(cb, 0, act, 0): a callback-less kind-2 effect of the same owner.
AuxiliaryObject& weaponEffect(ProjectileOwner& w,unsigned act) {
    const auto handle=w.objects.create(w.pools,w.registry,w.player,w.actor.flags23c,w.body,0x138e + w.player,2,0);
    if(!handle)throw std::runtime_error("Original 16c5f8 writes through a null object");
    auto& n=w.pools.objects.at(handle-1);
    w.objects.request(n,act,false,true);
    n[0xd0/4]=0xffffffffu;n[0xd4/4]=uint32_t(w.actor.stateIndex()-64);
    return n;
}
bool landed(const AuxiliaryObject& o){return (o[0x3c/4]&0x100)||Y(o).less(F{0});}
}
namespace {
// 16f088 (group 8): fly out, then home on the owner and be caught.
void updateReturningWeapon(ProjectileOwner& w,AuxiliaryObject& o) {
    auto& owner=w.actor;
    const uint32_t none=0xffffffffu;
    o[0x104/4]&=~0x100u;
    if(o[0x130/4]!=none&&owner.stateTable()==2)o[0x130/4]=none; // hurt owner: no catch ACT
    if(o[0x134/4]!=none) { // outbound
        bool go=(o[0xc0/4]&&!(o[0x104/4]&1))||(o[0x100/4]&2);
        if(!go&&owner.character==8&&owner.stateTable()==2)go=std::bit_cast<int32_t>(o[0x24/4])<0x200;
        if(go){w.objects.request(o,o[0x134/4],false,true);o[0x134/4]=none;return;}
        if(o[0x12c/4]==none)return;
        if((o[0x104/4]&0x2c0000)||Y(o).less(F{0})){w.objects.request(o,o[0x12c/4],false,true);o[0x134/4]=o[0x12c/4]=none;}
        return;
    }
    // Homing return: target the owner + (dx0, dy0); 4e87d8 overrides it per catch ACT.
    F dx0{0},dy0=F::integer(owner.character==8?48:12),near=F::integer(12);
    constexpr int16_t catches[7][3]{{266,74,74},{267,38,98},{268,110,20},{269,83,33},{270,-24,116},{649,25,22},{656,0,50}};
    for(const auto& c:catches)if(int32_t(o[0x130/4])==c[0]){dx0=F::integer(c[1]);dy0=F::integer(c[2]);near=F::integer(4);break;}
    const auto& body=w.body;
    const F bx{body[0x40/4]},by{body[0x44/4]};
    const F tx=(body[0x38/4]&mirror)?bx.sub(dx0):bx.add(dx0);
    const F ty=by.add(dy0);
    const F ox=X(o);
    F ax=tx.sub(ox);const F ay=ty.sub(Y(o));
    if(ax.less(F{0}))ax.bits^=0x80000000u;
    const F dist=ax.mul(ax).add(ay.mul(ay)).sqrt(); // MULA.S / MADD.S then SQRT.S
    if(near.less(dist)) {
        const F k=F::integer(100).div(dist),gain{std::bit_cast<uint32_t>(0.092f)},fixed=F::integer(65536);
        const F vy=F::integer(ay.mul(k).mul(gain).mul(fixed).truncate());
        F vx=F::integer(ax.mul(k).mul(gain).mul(fixed).truncate());
        const bool flipped=o[0x38/4]&mirror;
        if(!flipped&&tx.less(ox))vx.bits^=0x80000000u;
        if(flipped&&ox.less(tx))vx.bits^=0x80000000u;
        if(!o[0x128/4]){AuxiliaryObjects::stop(o);o[0x50/4]=uint32_t(vx.truncate());o[0x5c/4]=uint32_t(vy.truncate());o[0x128/4]=1;}
        else {
            // libgcc fp-bit: see soft_double.hpp.
            const auto blend=[](F fresh,uint32_t old){return uint32_t(softBlend(std::bit_cast<float>(fresh.bits),int32_t(old),0.6,0.4));};
            o[0x50/4]=blend(vx,o[0x50/4]);o[0x5c/4]=blend(vy,o[0x5c/4]);
        }
        return;
    }
    // Caught: the owner is armed again.
    owner.flags23c|=0x1000;o[0x108/4]|=0x1000;
    if(o[0x130/4]!=none) {
        capture::queue(owner,int32_t(o[0x130/4]));
        owner.callbacks260[0]=(owner.flags23c&0x10)?0x173880:0x169a50;owner.callbacks260[1]=1;owner.callbacks260[2]=none;
        if(!(owner.flags23c&0x10))owner.callbacks260[5]=0;
    } else if(owner.stateTable()==0&&owner.stateIndex()<4) {
        if(!w.enterStateNow)throw std::runtime_error("The returning weapon needs the owner's state entry");
        owner.request18c=1;w.enterStateNow();
    }
}
}
namespace {
// 16c408(cb, act, 0, 0) for the owner: kind 6, tag 0x1396, forced ACT, 108 |= 0x2000.
AuxiliaryObject& ownEffect(ProjectileOwner& w,unsigned act,uint32_t handler=0) {
    const auto handle=w.objects.create(w.pools,w.registry,w.player,w.actor.flags23c,w.body,0x1396,6,handler);
    if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& n=w.pools.objects.at(handle-1);
    w.objects.request(n,act,false,true);n[0x108/4]|=0x2000;
    return n;
}
// 16f510 (group 15): drift, then home on the opponent; burst on a hit.
void updateHomingShot(ProjectileOwner& w,uint32_t task,AuxiliaryObject& o) {
    // 142120: the opponent's system effect in state 3 quarters the decay.
    const bool slowed=w.opponentActor&&w.opponentConfig&&StateCallbacks::hasSystemEffect(*w.opponentConfig)&&
                      w.opponentActor->systemState13c==3;
    const int32_t delta=std::bit_cast<int32_t>(o[0x30/4]);
    const int32_t q=slowed?delta/4:delta; // C division toward zero
    o[0x128/4]=uint32_t(std::bit_cast<int32_t>(o[0x128/4])-q);o[0x12c/4]=uint32_t(std::bit_cast<int32_t>(o[0x12c/4])-q);
    const auto& opp=w.opponentBody;
    if(std::bit_cast<int32_t>(o[0x12c/4])>0) {
        AuxiliaryObjects::stop(o);o[0x50/4]=o[0x5c/4]=0x19999; // the slow drift
    } else {
        const F tx{opp[0x40/4]},ty=F{opp[0x44/4]}.add(F::integer(32)),ox=X(o);
        F ax=tx.sub(ox);const F ay=ty.sub(Y(o));
        if(ax.less(F{0}))ax.bits^=0x80000000u;
        const F dist=ax.mul(ax).add(ay.mul(ay)).sqrt();
        const F k=F::integer(100).div(dist),gain{std::bit_cast<uint32_t>(0.018f)},fixed=F::integer(65536);
        const F vy=F::integer(ay.mul(k).mul(gain).mul(fixed).truncate());
        F vx=F::integer(ax.mul(k).mul(gain).mul(fixed).truncate());
        const bool flipped=o[0x38/4]&mirror;
        if(!flipped&&tx.less(ox))vx.bits^=0x80000000u;
        if(flipped&&ox.less(tx))vx.bits^=0x80000000u;
        // libgcc fp-bit: see soft_double.hpp.
        o[0x50/4]=uint32_t(softBlend(std::bit_cast<float>(vx.bits),std::bit_cast<int32_t>(o[0x50/4]),0.03,0.97));
        o[0x5c/4]=uint32_t(softBlend(std::bit_cast<float>(vy.bits),std::bit_cast<int32_t>(o[0x5c/4]),0.02,0.98));
    }
    const auto f104=o[0x104/4];
    if(f104&0x40000) { // hit: two bursts at the shot and one on the opponent
        auto& a=ownEffect(w,0x235);a[0x40/4]=o[0x40/4];a[0x44/4]=o[0x44/4];
        auto& b=ownEffect(w,0x236,0x16d270);b[0x108/4]&=~0x2000u;b[0x40/4]=o[0x40/4];b[0x44/4]=o[0x44/4];
        auto& c=ownEffect(w,0x237);c[0x40/4]=opp[0x40/4];c[0x44/4]=opp[0x44/4];c[0x108/4]|=0x20000;
        if(!w.opponentActor)throw std::runtime_error("16e788 requires the opponent");
        const auto anchor=w.objects.bodyAnchor(w.opponentActor->character); //16e788(c, opp, 0)
        c[0xec/4]=F{c[0xec/4]}.add(F::integer(anchor[0])).bits;c[0xf0/4]=F{c[0xf0/4]}.add(F::integer(anchor[1])).bits;
        hold(w.pools,task);o[0x108/4]|=0x1000;
    } else if((f104&0x280000)||(o[0x100/4]&2)||Y(o).less(F{0})||std::bit_cast<int32_t>(o[0x128/4])<=0) {
        AuxiliaryObjects::stop(o);w.objects.request(o,0x234,false,true);o[0x108/4]|=0x2000;hold(w.pools,task);
    } else if(f104&4){hold(w.pools,task);o[0x108/4]|=0x1000;}
}
}
void updateDescriptorProjectile(const ProjectileTable& table,ProjectileOwner& w,uint32_t task) {
    auto& t=w.pools.tasks.at(task-1);auto& o=w.pools.objects.at(t[7]-1);
    const auto& cam=w.camera;
    switch(t[0]) {
    case 0x16f088:updateReturningWeapon(w,o);return;
    case 0x16f510:updateHomingShot(w,task,o);return;
    case 0x16c9e0: // group 4: recalled once past its first record, else 570 then 16def0
        if(std::bit_cast<int32_t>(o[0x28/4])>0&&(w.actor.flags244&0x400000)) {
            AuxiliaryObjects::stop(o);w.actor.flags244&=~0x400000u;
            w.objects.request(o,0x23b,false,false);o[0x108/4]|=0x2000;hold(w.pools,task);
        } else if(o[0xc0/4]&&!(o[0x104/4]&1)){w.objects.request(o,0x23a,false,false);t[0]=0x16def0;}
        return;
    case 0x16d1a0: // mode-4 object: at its end it stops, plays 0x259 and leaves 0x25a behind
        if(!o[0xc0/4]||(o[0x104/4]&1))return;
        AuxiliaryObjects::stop(o);w.objects.request(o,0x259,false,false);o[0x108/4]|=0x2000;hold(w.pools,task);
        {
            auto& n=ownEffect(w,0x25a,0x16d270);n[0x108/4]&=~0x2000u;
            std::copy_n(o.begin()+0x40/4,12,n.begin()+0x40/4); //11da98
        }
        return;
    case 0x16f8e8: // group 16: below the floor -> y = 0, stop, ACT 0x23a, then the default 16def0
        if(Y(o).less(F{0})){o[0x44/4]=0;AuxiliaryObjects::stop(o);w.objects.request(o,0x23a,false,false);t[0]=0x16def0;}
        return;
    case 0x16d270: // deleted once out of view
        if(o[0x104/4]&4){o[0x108/4]|=0x1000;hold(w.pools,task);}
        return;
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
    case 0x16ccb8: // group 9
        if(o[0x104/4]&0x2c0000) {
            AuxiliaryObjects::stop(o);o[0x44/4]=0;w.objects.request(o,569,false,false);t[0]=0x16cf40;
        } else if(landed(o))dropThrownWeapon(w,task,o);
        return;
    case 0x16cd60: // group 10: also stops at the camera edge it travels toward
        if((o[0x104/4]&0x2c0000)||reachedEdge(cam,X(o).truncate(),40,!(o[0x38/4]&mirror))) {
            auto& n=weaponEffect(w,570);n[0x108/4]|=0x2000;n[0x44/4]=o[0x44/4];n[0x40/4]=o[0x40/4];
            AuxiliaryObjects::stop(o);o[0x44/4]=0;w.objects.request(o,569,false,false);t[0]=0x16cf40;
        }
        return;
    case 0x16ce50: // group 11
        if(landed(o)) {
            auto& n=weaponEffect(w,o[0xd0/4]==0x8e?591:553);
            n[0x108/4]|=0x2000;n[0x44/4]=0;n[0x40/4]=o[0x40/4];n[0xd0/4]=o[0xd0/4];
            AuxiliaryObjects::stop(o);o[0x44/4]=0;w.objects.request(o,552,false,false);t[0]=0x16cf40;
        }
        return;
    case 0x16cb88: // group 12 (descriptors 0x7d, 0x9f): on the ground an owner effect, then 16cc70
        if(F{0}.less(F{o[0x44/4]}))return;
        {
            AuxiliaryObjects::stop(o);o[0x44/4]=0;
            const bool alt=o[0xd0/4]==0x9f;
            const auto h=w.objects.create(w.pools,w.registry,w.player,w.actor.flags23c,w.body,0x1396,6,0); //16c408
            if(!h)throw std::runtime_error("Original 16c408 writes through a null object");
            auto& n=w.pools.objects.at(h-1);w.objects.request(n,alt?555:608,false,true);n[0x108/4]|=0x2000;
            n[0x40/4]=o[0x40/4];n[0x44/4]=o[0x44/4];
            w.objects.request(o,alt?556:609,false,false);t[0]=0x16cc70;
        }
        return;
    case 0x16cc70:if(o[0x104/4]&4){t[0]=0x147540;o[0x108/4]|=0x1000;}return;
    case 0x16cf40: // 16ff18 can run twice in one visit
        if(F::integer(int32_t(o[0x5c/4])).bits==0&&F::integer(int32_t(o[0x60/4])).bits==0)dropThrownWeapon(w,task,o);
        if(landed(o))dropThrownWeapon(w,task,o);
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
    if(d.group==4&&(w.actor.flags244&0x400000)){sel=3;w.actor.flags244&=~0x400000u;} // recalled by the owner
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
