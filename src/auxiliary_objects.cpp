#include "auxiliary_objects.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace ss6 {
namespace {
std::vector<uint8_t> read(const std::filesystem::path& file) {
    std::ifstream in(file,std::ios::binary|std::ios::ate);
    if(!in)throw std::runtime_error("Missing auxiliary object resource: "+file.string());
    const auto size=in.tellg();if(size<0||size>16*1024*1024)throw std::runtime_error("Invalid auxiliary resource size");
    std::vector<uint8_t> bytes(static_cast<size_t>(size));in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(bytes.data()),size))throw std::runtime_error("Truncated auxiliary resource");
    return bytes;
}
uint32_t field(const std::vector<uint8_t>& bytes,size_t offset,unsigned count) {
    uint32_t v=0;for(unsigned i=0;i<count;++i)v|=uint32_t(bytes.at(offset+i))<<(8*i);return v;
}
int16_t half(const std::vector<uint8_t>& bytes,size_t offset){return std::bit_cast<int16_t>(uint16_t(field(bytes,offset,2)));}
void admitKind(const AuxiliaryObject& o) {
    if(o[0xcc/4]!=2&&o[0xcc/4]!=3&&o[0xcc/4]!=4&&o[0xcc/4]!=5&&o[0xcc/4]!=6&&o[0xcc/4]!=7&&o[0xcc/4]!=9&&o[0xcc/4]!=10)
        throw std::runtime_error("Auxiliary action path currently admits projectile, weapon, common and afterimage objects");
}
bool noWeapon(unsigned character){return character>=43&&character<=47;}
}
AuxiliaryObjects::AuxiliaryObjects(const std::filesystem::path& assets,std::array<unsigned,3> slots):assets_(assets),slots_(slots) {
    const auto positions=read(assets/"weapon_positions.bin"),constants=read(assets/"weapon_constants.bin");
    if(positions.size()!=51*36||constants.size()!=16)throw std::runtime_error("Invalid weapon tables");
    for(unsigned c=0;c<51;++c)for(unsigned j=0;j<18;++j)positions_[c][j]=half(positions,c*36+j*2);
    for(unsigned i=0;i<4;++i)constants_[i].bits=field(constants,i*4,4);
}
ActionRecord AuxiliaryObjects::record(const AuxiliaryObject& o,unsigned* actionLength) {
    const auto resource=slots_.at(o[0xc/4]);
    auto found=resources_.find(resource);
    if(found==resources_.end()) {
        std::ostringstream name;name<<std::setfill('0')<<std::setw(2)<<resource;
        Resource r{read(assets_/ ("aid_"+name.str()+".bin")),read(assets_/("act_"+name.str()+".bin"))};
        if(r.aid.size()!=0x1800||r.act.size()%60)throw std::runtime_error("Invalid auxiliary AID/ACT");
        found=resources_.emplace(resource,std::move(r)).first;
    }
    const auto& [aid,act]=found->second;const auto action=o[0x24/4],stage=o[0x28/4];
    if(action>=2048)throw std::runtime_error("Invalid auxiliary action");
    const auto start=half(aid,action*2);
    const unsigned count=aid.at(0x1000+action);
    if(actionLength)*actionLength=count;
    const size_t offset=size_t(fighterActionRecord(resource,action,start,count,std::bit_cast<int32_t>(stage)))*60;
    ActionRecord r{};r.sourceRecord=uint32_t(start)+stage;r.headerFlags=field(act,offset,4);
    r.judgmentFlags=uint16_t(field(act,offset+0x1e,2));r.duration=half(act,offset+0x34);r.soundCommand=half(act,offset+0x38);r.endKind=half(act,offset+0x3a);
    for(unsigned j=0;j<5;++j)r.parts[j]=half(act,offset+4+2*j);
    for(unsigned j=0;j<r.judgmentRefs.size();++j)r.judgmentRefs[j]=half(act,offset + 0x0e + 2*j);
    r.motion.kind=half(act,offset+0x20);for(unsigned j=0;j<6;++j)r.motion.values[j]=half(act,offset+0x22+2*j);
    for(unsigned j=0;j<3;++j)r.effectCommand[j]=half(act,offset+0x2e + 2*j);
    return r;
}
void AuxiliaryObjects::enter(AuxiliaryObject& o) {
    admitKind(o);const auto r=record(o);
    o[0x3c/4]=0;o[0xd8/4]=(r.headerFlags>>16)&255;
    auto pending=uint16_t(o[0xfc/4]>>16);
    pending=(pending&~0x10u)|((r.headerFlags&0x1000)?0x10u:0u);
    o[0xfc/4]=(o[0xfc/4]&0xffff)|(uint32_t(pending)<<16);
    o[0x104/4]&=~0x18000u;
    if(r.headerFlags&0x400) {
        const uint16_t encoded=uint16_t(r.effectCommand[0]);
        const unsigned id=encoded&0x7ff;
        const auto mode=encoded&0x1800;
        if(mode==0||mode==0x800) {
            // 1211f0 records the request at frame entry. Only the two fighter
            // registries are scanned later in this update for nested effects.
            o[0x104/4]|=mode?0x18000:0x8000;
            o[0x10c/4]=id;
            o[0x110/4]=uint32_t(int32_t(r.effectCommand[1]));
            o[0x114/4]=uint32_t(int32_t(r.effectCommand[2]));
        } else if(mode!=0x1000)throw std::runtime_error("Unknown auxiliary ACT attachment");
        else if(id) {
            if(!effect_)throw std::runtime_error("Auxiliary world effect requires the shared effect scheduler");
            const auto flags=o[0x38/4];
            auto x=ScalarFloat{o[0x40/4]},y=ScalarFloat{o[0x44/4]};
            const auto dx=ScalarFloat::integer(std::bit_cast<int32_t>(o[0x4c/4])>>16);
            const auto dy=ScalarFloat::integer(std::bit_cast<int32_t>(o[0x58/4])>>16);
            // 1204e0 includes the uncommitted displacement of the object.
            x=(flags&0x80000)?x.sub(dx):x.add(dx);
            y=(flags&0x40000)?y.sub(dy):y.add(dy);
            const auto ox=ScalarFloat::integer(r.effectCommand[1]);
            x=(flags&0x80000)?x.sub(ox):x.add(ox);
            y=y.add(ScalarFloat::integer(r.effectCommand[2]));
            effect_(id,flags,o[0xc/4],std::bit_cast<float>(x.bits),std::bit_cast<float>(y.bits));
        }
    }
    const auto command=uint16_t(r.soundCommand);
    if(command&&command!=0x4000&&!(o[0x104/4]&0x200)&&
       ((o[0x38/4]&0x10000000)||!(command&0x8000))) {
        if(!sound_)throw std::runtime_error("Auxiliary enabled sound requires an original dispatch observer");
        const auto channel=sound_(r.soundCommand,o);
        if(channel>=0&&(command&0x4000))o[0x34/4]=uint32_t(channel)|0xc000;
    }
    //A sound command can assign34 during this same entry. Check the
    //stop boundary afterward so a newly opened channel is never skipped.
    if((r.headerFlags&0x2000)&&(o[0x34/4]&0x8000))throw std::runtime_error("Auxiliary sound-stop dispatch is not implemented");
    if(o[0x38/4]&0x02000000)return;
    if(r.headerFlags&0x800)o[0xfc/4]|=0x00800000;
    const auto flags=o[0x104/4];
    if((flags&0x40)||(o[0xc0/4]&&!(flags&1)))return;
    if(r.motion.kind==2||r.motion.kind==4||r.motion.kind==6||r.motion.kind==8||r.motion.kind==16||r.motion.kind==18)o[0xfc/4]|=0x00800000;
    MotionState m;
    m.dx=std::bit_cast<int32_t>(o[0x4c/4]);m.vx=std::bit_cast<int32_t>(o[0x50/4]);m.ax=std::bit_cast<int32_t>(o[0x54/4]);
    m.dy=std::bit_cast<int32_t>(o[0x58/4]);m.vy=std::bit_cast<int32_t>(o[0x5c/4]);m.ay=std::bit_cast<int32_t>(o[0x60/4]);
    enterMotion(m,r.motion,o[0x108/4]&0x200,flags&0x80);
    if(flags&0xc00) {
        const auto scale=constants_[(flags&0x400)?1:2];
        m.vy=ScalarFloat::integer(m.vy).mul(scale).truncate();m.ay=ScalarFloat::integer(m.ay).mul(scale).truncate();
    }
    for(auto [offset,v]:{std::pair{0x4c,m.dx},{0x50,m.vx},{0x54,m.ax},{0x58,m.dy},{0x5c,m.vy},{0x60,m.ay}})o[offset/4]=uint32_t(v);
}
void AuxiliaryObjects::publishJudgment(AuxiliaryObject& o) {
    constexpr uint32_t source[]={0x20000000,0x40000000,0x10000000},dest[]={0x20,0x40,2};
    for(unsigned i=0;i<3;++i)o[0x108/4]=(o[0x108/4]&~dest[i])|((o[0x104/4]&source[i])?dest[i]:0);
}
void AuxiliaryObjects::judgment(AuxiliaryObject& o) {
    const auto r=record(o);const uint32_t bits=r.judgmentFlags;
    o[0xb8/4]=(o[0xb8/4]&0xff000000)|bits|((bits&7)<<16);
    o[0xbc/4]=r.sourceRecord*60 + 0x0e + 1;
    for(unsigned i=0;i<10;++i) {
        const unsigned position=(i==2?28:i==6?29:i==7?30:31+i);
        auto& value=o[(position<32?0x104:0x108)/4];const uint32_t mask=1u<<(position%32);
        value=(value&~mask)|((bits&(1u<<(i+6)))?mask:0);
    }
    if(!r.duration)publishJudgment(o); //11e010 has an additional zero-duration publication.
    const auto old=o[0x104/4];o[0x104/4]&=~0x02000000u;
    if(old&0x40000)o[0x108/4]&=~0x10u;
    o[0x104/4]=(o[0x104/4]&~0x100u)|(!r.duration?0x100u:0u);
    if(ScalarFloat{o[0x44/4]}.less(ScalarFloat{0})){o[0x44/4]=0;o[0x3c/4]|=0x100;}
    //11de10 treats common effects differently: a zero-duration record
    //does not set their hold bit. Do not apply the weapon/actor rule here.
    if(o[0xcc/4]==7)o[0x104/4]&=~0x100u;
}
void AuxiliaryObjects::stop(AuxiliaryObject& o) {
    std::fill(o.begin()+0x4c/4,o.begin()+0x64/4,0u);o[0x104/4]&=~0x140u;
}
void AuxiliaryObjects::initializeBase(AuxiliaryObject& o,unsigned slot,unsigned kind) {
    o[0xc/4]=slot;const auto resource=slots_.at(slot);
    o[0xc4/4]=0;o[0xcc/4]=kind;o[0x10/4]=o[0xc/4];o[0x14/4]=resource;o[0x1c/4]=resource*5;
    for(unsigned offset:{0x20,0x24,0x28,0x2c,0x34,0x40,0x44,0x4c,0x50,0x54,0x58,0x5c,0x60})o[offset/4]=0;
    o[0x38/4]=0x10000000;o[0x70/4]=constants_[0].bits;o[0x30/4]=256;enter(o);
    o[0xb0/4]=o[0xb4/4]=0;o[0x18/4]=resource==42?1:resource;judgment(o);
}
void AuxiliaryObjects::initialize(AuxiliaryObject& o,const AuxiliaryObject& parent,unsigned kind) {
    if(kind!=2&&kind!=3&&kind!=4&&kind!=5&&kind!=6)throw std::runtime_error("Invalid fighter-owned auxiliary object kind");
    // 11d9e4 selects the resident common graphics for a thrown item while
    // retaining the fighter's clock, position, facing and owner below.
    initializeBase(o,kind==5?2:parent[0xc/4],kind);
    for(unsigned offset:{0x70,0x30,0x20,0xc8})o[offset/4]=parent[offset/4];
    o[0x10/4]=parent[0xcc/4];o[0x38/4]=(o[0x38/4]&~0x80000u)|(parent[0x38/4]&0x80000);
    for(unsigned offset=0x40;offset<=0x6c;offset+=4)o[offset/4]=parent[offset/4];
    stop(o);o[0x38/4]&=~0x40800000u;o[0x8c/4]=0xffffffff;
}
uint32_t AuxiliaryObjects::create(TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,uint32_t flags,
                                const AuxiliaryObject& parent,uint32_t tag,unsigned kind,uint32_t handler) {
    if(player>=2||registry.size()!=48)throw std::runtime_error("Invalid auxiliary owner/registry");
    const auto task=pools.registerObjectTask(registry,tag,handler);if(!task)return 0;
    const auto object=pools.tasks.at(task-1)[7];auto& o=pools.objects.at(object-1);initialize(o,parent,kind);
    o[1]=task;o[2]=handler;o[0x118/4]=player+1;
    if(flags&0x08000000)o[0x108/4]|=0x40000;
    o[0x108/4]|=0x200000;return object;
}
void AuxiliaryObjects::applyAttachmentOffset(AuxiliaryObject& o,const AuxiliaryObject& parent) {
    const auto x=ScalarFloat{o[0x40/4]},dx=ScalarFloat::integer(std::bit_cast<int32_t>(parent[0x110/4]));
    o[0x40/4]=((parent[0x38/4]&0x80000)?x.sub(dx):x.add(dx)).bits;
    o[0x44/4]=ScalarFloat{o[0x44/4]}.add(ScalarFloat::integer(std::bit_cast<int32_t>(parent[0x114/4]))).bits;
}

uint32_t AuxiliaryObjects::spawnRisingSlashTrail(TaggedTaskPools& pools,std::span<uint32_t> registry,
                                                unsigned player,uint32_t flags,const AuxiliaryObject& parent,unsigned state) {
    if(((state<68||state>73)&&state!=79)||slots_.at(player)!=0)throw std::runtime_error("Invalid rising slash effect");
    // 16c4e0 inherits the owner's movement, clock and hit interruption.
    // Each strength has its own ACT. The flying hitboxes stay on the fighter.
    const auto handle=create(pools,registry,player,flags,parent,0x1392 + player,6,0);
    if(!handle)return 0;
    auto& o=pools.objects.at(handle-1);
    const unsigned action=state==79?614:state<71?555+state-68:571+state-71;
    request(o,action,false,true);
    o[0x108/4]|=0x1a000;
    applyAttachmentOffset(o,parent);
    return handle;
}
uint32_t AuxiliaryObjects::spawnActAttachment(TaggedTaskPools& pools,std::span<uint32_t> ownerRegistry,std::span<uint32_t> commonRegistry,
                                          unsigned player,uint32_t flags,const AuxiliaryObject& body,const AuxiliaryObject& emitter,
                                          unsigned action,bool sharedBank) {
    const auto handle=sharedBank?createCommonEffect(pools,commonRegistry,&body,0x1396,0):
                                 create(pools,ownerRegistry,player,flags,body,0x1396,6,0);
    if(!handle)return 0;
    auto& child=pools.objects.at(handle-1);
    if(sharedBank) {
        child[0x118/4]=player+1;
        child[0x104/4]|=0x20000;
        if(action==54)child[0xb0/4]=std::bit_cast<uint32_t>(-20.f);
    }
    child[0x40/4]=emitter[0x40/4];child[0x44/4]=emitter[0x44/4];
    request(child,action,false,true);
    child[0x108/4]|=0x2000;
    applyAttachmentOffset(child,emitter);
    return handle;
}
uint32_t AuxiliaryObjects::spawnSlashEffect(TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                                          uint32_t flags,const AuxiliaryObject& parent,unsigned action) {
    return spawnActAttachment(pools,registry,{},player,flags,parent,parent,action,false);
}
void AuxiliaryObjects::spawnMikiri(TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                                   uint32_t flags,const AuxiliaryObject& parent,unsigned action) {
    // 16e5f0 marks every older decoy for removal at the next registry visit.
    // Reusing its slot here would move the replacement ahead of other objects.
    for(auto task:registry)if(task) {
        auto& t=pools.tasks.at(task-1);
        auto& previous=pools.objects.at(t[7]-1);
        if(previous[0xcc/4]==9) {
            previous[0x108/4]|=0x1000;
            t[0]=0x147540;
        }
    }
    // 16c408 inherits the body position without applying an ACT attachment offset.
    if(const auto handle=create(pools,registry,player,flags,parent,0x1396,6,0)) {
        auto& image=pools.objects.at(handle-1);
        request(image,action,false,true);
        image[0xcc/4]=9;image[0x108/4]|=0xa000;image[0x134/4]=0;
    }
}
uint32_t AuxiliaryObjects::spawnWhirlwind(TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                                          uint32_t flags,const AuxiliaryObject& parent,unsigned strength) {
    if(strength>2||slots_.at(player)!=0)throw std::runtime_error("Whirlwind requires resource 00 and a slash strength");
    const auto handle=create(pools,registry,player,flags,parent,0x138e + player,2,0x16def0);
    if(!handle)return 0;
    auto& o=pools.objects.at(handle-1);
    // 16c5f8 queues the first ACT. The registry's draw/commit pass publishes
    // its first judgment on the birth tick, after the movement and contact passes.
    request(o,532+strength,false,true);
    o[0xd0/4]=0;o[0xd4/4]=strength;o[0x11c/4]=strength;
    applyAttachmentOffset(o,parent);
    return handle;
}
void AuxiliaryObjects::updateWhirlwind(TaggedTaskPools& p,uint32_t task) {
    auto& t=p.tasks.at(task-1);auto& o=p.objects.at(t[7]-1);
    const auto flags=o[0x104/4];
    const bool expired=(o[0xc0/4]&&!(flags&1))||(flags&4);
    unsigned ending=538;
    if(!expired&&!(o[0x100/4]&2)) {
        if(flags&0x40000)ending=535;
        else if(!(flags&0x280000))return;
    }
    // Descriptor 0 has distinct hit and block/expiry clips. An incoming
    // strike on the projectile takes precedence over its outgoing hit mark.
    stop(o);t[0]=0x147540;request(o,ending,false,true);o[0x108/4]|=0x2000;
}
void AuxiliaryObjects::pauseWhirlwind(AuxiliaryObject& o,int first,int second) {
    // The projectile freezes independently of the owner. Keep e0 (shake
    // phase) intact when two stops are queued before the next movement pass.
    o[0xdc/4]=uint32_t(first+(second+1)/2)*256;
    o[0xe4/4]=o[0xe8/4]=0;o[0xfc/4]=(o[0xfc/4]&~255u)|2;
}
uint32_t AuxiliaryObjects::createCommonEffect(TaggedTaskPools& pools,std::span<uint32_t> registry,
                                             const AuxiliaryObject* parent,uint32_t tag,uint32_t handler) {
    return createCommonObject(pools,registry,parent,tag,7,handler);
}
uint32_t AuxiliaryObjects::createCommonObject(TaggedTaskPools& pools,std::span<uint32_t> registry,
                                             const AuxiliaryObject* parent,uint32_t tag,unsigned kind,uint32_t handler) {
    if(registry.size()!=64||slots_[2]!=51)
        throw std::runtime_error("Common effect needs battle registry and original resident slot2/resource51");
    if(kind!=5&&kind!=7)throw std::runtime_error("Invalid common battle object kind");
    const auto task=pools.registerObjectTask(registry,tag,handler);if(!task)return 0;
    const auto object=pools.tasks.at(task-1)[7];auto& o=pools.objects.at(object-1);
    initializeBase(o,2,kind);o[1]=task;o[2]=handler;o[0xc8/4]=1;o[0x118/4]=0;o[0x10/4]=2;
    if(parent)o[0x38/4]=(o[0x38/4]&~0x80000u)|((*parent)[0x38/4]&0x80000);
    return object;
}
void AuxiliaryObjects::request(AuxiliaryObject& o,unsigned action,bool immediate,bool force) {
    admitKind(o);if(!force&&o[0x24/4]==action)return;
    o[0xc4/4]=action;o[0x104/4]|=1;o[0xc0/4]=0;if(!immediate)return;
    o[0x104/4]&=~0x042c0001u;const auto pending=uint16_t(o[0xfc/4]>>16);
    constexpr uint16_t source[]={1,2,4,8,0x200,0x400};constexpr uint32_t dest[]={0x400000,0x10,0x20,0x40,0x400,0x800};
    for(unsigned i=0;i<6;++i)o[0x104/4]=(o[0x104/4]&~dest[i])|((pending&source[i])?dest[i]:0);
    //11db88 toggles facing. It does NOT reset position despite its earlier
    //provisional name in PlayerObject's unsupported-pending-bit guard.
    if(pending&0x100)o[0x38/4]^=0x80000;
    o[0xfc/4]&=0xffff;
    if(slots_[0]==99)throw std::runtime_error("Combined99 auxiliary action translation is not implemented");
    o[0x24/4]=action;o[0x28/4]=o[0x2c/4]=o[0x3c/4]=o[0xc0/4]=0;o[0x38/4]|=0x10000000;
    enter(o);judgment(o);publishJudgment(o);
}
void AuxiliaryObjects::commitRequested(AuxiliaryObject& o) {
    if(o[0x104/4]&1)request(o,o[0xc4/4],true,true);
}
void AuxiliaryObjects::requireDropCapacity(const TaggedTaskPools& p,std::span<const uint32_t> registry) {
    if(!p.freeTaskHead||!p.freeObjectHead||std::find(registry.begin(),registry.end(),0u)==registry.end())
        throw std::runtime_error("Weapon creation requires available task/object/registry slots");
}
uint32_t AuxiliaryObjects::drop(TaggedTaskPools& p,std::span<uint32_t> r,GameRandom& rng,unsigned player,unsigned character,uint32_t& flags,const AuxiliaryObject& parent) {
    if(character>=positions_.size())throw std::runtime_error("Invalid weapon character");
    if(character==48)return dropSpecial(p,r,rng,player,character,flags,parent);
    return dropWithOffset(p,r,rng,player,character,flags,parent,positions_[character][4],positions_[character][5]);
}
uint32_t AuxiliaryObjects::dropAfterLock(TaggedTaskPools& p,std::span<uint32_t> r,GameRandom& rng,unsigned player,unsigned character,uint32_t& flags,const AuxiliaryObject& parent) {
    if(character>=positions_.size())throw std::runtime_error("Invalid weapon character");
    if(character==48)return dropSpecial(p,r,rng,player,character,flags,parent);
    return dropWithOffset(p,r,rng,player,character,flags,parent,positions_[character][6],positions_[character][7]);
}
uint32_t AuxiliaryObjects::dropWithOffset(TaggedTaskPools& p,std::span<uint32_t> r,GameRandom& rng,unsigned player,unsigned character,uint32_t& flags,const AuxiliaryObject& parent,int32_t x,int32_t y) {
    if(noWeapon(character)||!(flags&0x1000))return 0;
    requireDropCapacity(p,r);flags&=~0x1000u;const auto choice=rng.bounded(3);
    const auto handle=create(p,r,player,flags,parent,player+0x1390,4,0x1701c0);auto& o=p.objects.at(handle-1);
    request(o,466,true,true);
    const auto dx=std::bit_cast<int32_t>((parent[0x38/4]&0x80000)?0u-uint32_t(x):uint32_t(x));
    o[0x40/4]=ScalarFloat{o[0x40/4]}.add(ScalarFloat::integer(dx)).bits;
    o[0x44/4]=ScalarFloat{o[0x44/4]}.add(ScalarFloat::integer(y)).bits;
    o[0x50/4]=choice==0?0:choice==1?uint32_t(-0x7680):0x7680;o[0x54/4]=0;
    o[0x5c/4]=0x54000;o[0x60/4]=uint32_t(-0x1600);o[0x104/4]|=8;return handle;
}
uint32_t AuxiliaryObjects::dropSpecial(TaggedTaskPools& p,std::span<uint32_t> r,GameRandom& rng,unsigned player,unsigned character,uint32_t& flags,const AuxiliaryObject& parent) {
    if(noWeapon(character)||!(flags&0x1000))return 0;
    requireDropCapacity(p,r);flags&=~0x1000u;
    const auto handle=create(p,r,player,flags,parent,player+0x1390,6,0x170340);auto& o=p.objects.at(handle-1);request(o,468,true,true);
    if(character==11&&(flags&0x400000))o[0x38/4]|=0x80000000;
    //This branch draws its random value AFTER creation/action entry.
    const auto choice=rng.bounded(3);
    if(choice==0)o[0x50/4]=o[0x54/4]=0;
    else if(choice==1){o[0x50/4]=0u-o[0x50/4];o[0x54/4]=0u-o[0x54/4];}
    o[0x104/4]|=8;return handle;
}
uint32_t AuxiliaryObjects::deliverWeapon(TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                                         unsigned character,uint32_t flags,const AuxiliaryObject& parent,float refereeX) {
    if(character==48)return 0;
    requireDropCapacity(pools,registry);
    const auto handle=create(pools,registry,player,flags,parent,player+0x1390,4,0x1701c0);
    auto& weapon=pools.objects.at(handle-1);
    request(weapon,466,true,true);
    // The referee throws toward the owner's current position. Velocity is
    // actor-local, so the original negates it once before a mirrored throw.
    const ScalarFloat from{std::bit_cast<uint32_t>(refereeX)};
    auto dx=ScalarFloat{parent[0x40/4]}.sub(from);
    if(weapon[0x38/4]&0x80000)dx.bits^=0x80000000;
    weapon[0x40/4]=from.bits;weapon[0x44/4]=std::bit_cast<uint32_t>(64.f);
    weapon[0x50/4]=uint32_t(dx.mul(ScalarFloat::integer(65536)).div(ScalarFloat::integer(140)).truncate());
    weapon[0x54/4]=0;weapon[0x5c/4]=0x54000;weapon[0x60/4]=uint32_t(-0x1600);
    weapon[0x104/4]|=8;
    return handle;
}
void AuxiliaryObjects::landWeapon(TaggedTaskPools& p,uint32_t task) {
    auto& t=p.tasks.at(task-1);auto& o=p.objects.at(t[7]-1);
    if(!ScalarFloat{o[0x44/4]}.less(constants_[3]))return;
    o[0x44/4]=0;stop(o);request(o,467,true,true);t[0]=0x147540;
}
bool AuxiliaryObjects::shatterWeapon(TaggedTaskPools& p,std::span<uint32_t> registry,uint32_t task,
                                     unsigned player,uint32_t flags,const AuxiliaryObject& parent) {
    auto& t=p.tasks.at(task-1);auto& weapon=p.objects.at(t[7]-1);
    if(!weapon[0xc0/4]||(weapon[0x104/4]&1))return false;
    for(unsigned action:{469u,470u,471u}) {
        requireDropCapacity(p,registry);
        auto& piece=p.objects.at(spawnSlashEffect(p,registry,player,flags,parent,action)-1);
        // 11da98 copies both position and velocity before the three ACTs
        // take over. The fighter can already be far from the falling weapon.
        std::copy_n(weapon.begin()+0x40/4,12,piece.begin()+0x40/4);
    }
    t[0]=0x147540;weapon[0x108/4]|=0x1000;
    return true;
}
void AuxiliaryObjects::releaseHold(TaggedTaskPools& p,uint32_t task) {p.objects.at(p.tasks.at(task-1)[7]-1)[0x104/4]&=~0x100u;}
}
