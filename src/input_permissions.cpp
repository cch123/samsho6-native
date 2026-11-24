#include "asset_files.hpp"
#include "input_permissions.hpp"
#include "actor_state.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>
#include <vector>

namespace ss6 {
namespace {
std::vector<uint8_t> read(const std::filesystem::path& path,size_t count) {
    std::ifstream in(resolveAsset(path),std::ios::binary);std::vector<uint8_t> data(count);
    if(!in.read(reinterpret_cast<char*>(data.data()),count)||in.peek()!=EOF)throw std::runtime_error("Invalid input permission table: "+path.string());
    return data;
}
uint32_t word(const std::vector<uint8_t>& b,size_t i){return uint32_t(b[i])|(uint32_t(b[i+1])<<8)|(uint32_t(b[i+2])<<16)|(uint32_t(b[i+3])<<24);}
int16_t half(const std::vector<uint8_t>& b,size_t i){return int16_t(unsigned(b[i])|(unsigned(b[i+1])<<8));}
ScalarFloat scalar(float x){return {std::bit_cast<uint32_t>(x)};}
bool rawAttack(const PermissionActor& a,unsigned first,unsigned last) {
    return (a.state194&0xffff)==1&&unsigned((a.state194>>16)-first)<=last-first;
}
template<size_t N>const PermissionObject* firstObject(const std::array<std::optional<PermissionObject>,N>& objects,int kind) {
    for(const auto& object:objects)if(object&&object->kind==kind)return &*object;
    return nullptr;
}
const std::array<uint8_t,16>* descriptor(const InputSystemConfig& c) {
    if(c.system>8)throw std::runtime_error("Invalid input permission system");
    if(c.system!=6)return nullptr;
    if(!c.descriptor)throw std::runtime_error("System6 permissions need selected descriptor");
    return &*c.descriptor;
}
}
InputPermissions::InputPermissions(const std::filesystem::path& assets) {
    auto air=read(assets/"permission_air_rectangles.bin",51*8),targets=read(assets/"permission_target_ranges.bin",51*8),attacks=read(assets/"permission_attack_ranges.bin",51*36);
    for(unsigned i=0;i<51;++i) {
        for(unsigned j=0;j<4;++j){airRectangles_[i][j]=half(air,i*8+j*2);targetRanges_[i][j]=half(targets,i*8+j*2);}
        for(unsigned j=0;j<18;++j)attackRanges_[i][j]=half(attacks,i*36+j*2);
    }
    const auto systems=read(assets/"permission_systems.bin",9*40),limits=read(assets/"permission_limits.bin",5*4);
    for(unsigned i=0;i<9;++i)for(unsigned j=0;j<10;++j)systems_[i][j]=word(systems,i*40+j*4);
    for(unsigned i=0;i<5;++i)limits_[i]=word(limits,i*4);
    const auto gates=read(assets/"permission_gate_limits.bin",13*4),cancels=read(assets/"permission_cancel_conditions.bin",96*4);
    for(unsigned i=0;i<13;++i)gateLimits_[i]=word(gates,i*4);
    for(unsigned i=0;i<96;++i)cancelConditions_[i]=word(cancels,i*4);
}
bool InputPermissions::actorAllowed(const PermissionActor& a){return !(a.flags23c&0x4c0);}
bool InputPermissions::category(unsigned id,const PermissionActor& a) const {
    const bool unlocked=!(a.flags23c&0x100),airborne=a.flags23c&0x10;
    switch(id) {
    case 0:return unlocked;
    case 1:return unlocked&&!airborne;
    case 2:return unlocked&&a.timers[8]<=0&&a.state194==0x00170000;
    case 3:
        if(!unlocked)return false;
        if(a.state194==0x00170000)return a.timers[8]<=0;
        return a.timers[27]>0&&(a.state194==0||a.state194==0x00090000||a.state194==0x000a0000||a.state194==0x00010000||a.state194==0x00020000);
    case 4:return unlocked&&airborne;
    case 5:return unlocked&&airborne&&a.velocityY5c>=0&&!ScalarFloat{gateLimits_[0]}.less(scalar(a.y));
    case 6:return unlocked&&airborne&&uint32_t(uint32_t(a.velocityY5c)+0x40000)<=0x80000;
    case 7:return unlocked&&airborne&&a.velocityY5c<0;
    case 8:return unlocked&&airborne&&a.velocityX50!=0;
    case 9:return !airborne&&a.state194!=0x00240001&&(a.stateTable()!=1||a.stateIndex()<64);
    case 10:return a.stateTable()==2&&(a.effectiveFlags()&8);
    case 11:return a.state194==0x00360000||a.state194==0x00370000||(a.stateTable()==2&&(a.effectiveFlags()&4));
    default:return false;
    }
}
bool InputPermissions::auxiliaryReady(PermissionActor& a) const {
    const auto origin=[&](unsigned index) {
        const auto x=scalar(a.x);const ScalarFloat offset{gateLimits_[index]};
        return a.bodyFlags38&0x80000?x.sub(offset):x.add(offset);
    };
    const auto horizontal=[&](unsigned index) {
        const auto delta=origin(index).sub(scalar(a.auxiliaryX));
        return delta.less({gateLimits_[index+1]})&&ScalarFloat{gateLimits_[index+2]}.less(delta);
    };
    switch(a.character) {
    case 1:case 45: {
        if(std::bit_cast<int32_t>(a.auxiliaryState128)>=6)return false;
        auto dx=origin(1).sub(scalar(a.auxiliaryX));dx.bits&=0x7fffffff;
        const auto dy=scalar(a.y).add({gateLimits_[2]}).sub(scalar(a.auxiliaryY));
        //1a3b68 uses MULA/MADD then SQRT. Keep each finite-model rounding
        //step; a squared-distance shortcut can change a rounded boundary.
        return dx.mul(dx).add(dy.mul(dy)).sqrt().less({gateLimits_[3]});
    }
    case 4:return std::bit_cast<int32_t>(a.auxiliaryState128)<11&&horizontal(4);
    case 16:return a.characterBytesF14[1]&&a.auxiliaryFlag134==0;
    case 19:
        if(std::bit_cast<int32_t>(a.auxiliaryState128)>=12||ScalarFloat{0}.less(scalar(a.auxiliaryY)))return false;
        //1fa138 clears this bit before testing horizontal distance, even if
        //the resulting permission is false. The state25 exception cannot
        //occur here because this caller already required state<12.
        a.auxiliaryFlags104&=~0x100u;
        return horizontal(7);
    case 24:return uint32_t(a.auxiliaryState12c-19)>=5&&uint32_t(a.auxiliaryState12c-25)>=8;
    case 32:return true;
    case 34:return std::bit_cast<int32_t>(a.auxiliaryState128)<12&&horizontal(10);
    default:return false;
    }
}
bool InputPermissions::requirement(unsigned id,PermissionActor& a) const {
    switch(id) {
    case 0:return a.flags23c&0x1000;
    case 1:return !(a.flags23c&0x1000);
    case 2:case 7:case 8:return true;
    case 3:return auxiliaryReady(a);
    case 4:return a.flags23c&0x200000;
    case 5:return a.flags23c&0x800000;
    case 6:return uint32_t(a.rageState120)-1<2;
    default:return false;
    }
}
bool InputPermissions::cancelAllowed(unsigned index,PermissionActor& a,int specialStart,const InputBindings& bindings) const {
    if(a.stateTable()==1) {
        const int state=a.stateIndex();
        if(!(a.character==32&&state==73)&&!(a.character==48&&state==79)&&bindings.specialCategory(a.character,state))return false;
    }
    const auto& record=bindings.specialRecords().at(index);
    const auto condition=record.condition&255;
    if(condition!=255&&cancelConditions_.at(condition))return true;
    if(record.flags&0x80) {
        //179968 calls14d010, not a read-only timer query. Every visited
        //candidate decrements timer4 and tests the OLD value, even on refusal.
        ActorTimers clock{a.timerDelta,a.timers};const auto old=clock.decrease(4);
        a.timers[4]=clock.values[4];if(old>0)return true;
    }
    return a.character==22&&a.bodyAction24==564&&!(a.flags23c&0x100000)&&uint32_t(index-uint32_t(specialStart)-7)>=3;
}
void InputPermissions::apply(PermissionActor& a,const PermissionActor& opponent,const InputSystemConfig& config,PermissionContext& context,
        ActorCommandInput& input,const InputBindings& bindings) const {
    if(input.specialCount>32||(input.specialCount>0&&(input.specialStart<0||size_t(input.specialStart)+input.specialCount>bindings.specialRecords().size())))
        throw std::runtime_error("Invalid special permission block");
    std::array<uint32_t,13> categories{};std::array<uint32_t,9> requirements{};
    if(actorAllowed(a)) {
        for(unsigned i=0;i<13;++i)categories[i]=category(i,a);
        for(unsigned i=0;i<9;++i)requirements[i]=requirement(i,a);
    }
    //All gates are captured before any callback mutates actor state. A later
    //callback observes earlier writes, but must not recompute these gates.
    filter(a,opponent,config,context,input.normal,bindings.normalRecords(),categories,requirements);
    if(input.specialCount<=0)return;
    auto slots=std::span(input.special).first(size_t(input.specialCount));
    filter(a,opponent,config,context,slots,std::span(bindings.specialRecords()).subspan(size_t(input.specialStart),slots.size()),categories,requirements);
    for(unsigned i=0;i<slots.size();++i)
        slots[i].cancelAllowed=slots[i].recognized&&cancelAllowed(unsigned(input.specialStart)+i,a,input.specialStart,bindings);
}
bool InputPermissions::objectAvailable(unsigned key,const PermissionContext& context) {
    if(key>255)throw std::runtime_error("Object availability key outside original byte");
    for(const auto& object:context.ownObjects)if(object&&object->kind==2) {
        const auto subtype=object->subtype;
        if(subtype==int32_t(key)||key==255)return false;
        if((key==254&&(subtype==4||subtype==5))||(key==253&&(subtype==18||subtype==19))||
           (key==252&&(subtype==24||subtype==25))||(key==251&&(subtype==33||subtype==34||subtype==62||subtype==63))||
           (key==250&&(subtype==42||subtype==43)))return false;
    }
    return true;
}
bool InputPermissions::condition(unsigned id,PermissionActor& a,const PermissionActor& opponent,const InputSystemConfig& config,PermissionContext& context) const {
    if(id==255)return true;
    if(id>=96)throw std::runtime_error("Input condition outside original dispatch table");
    const auto* d=descriptor(config);
    const auto custom=[&](unsigned field,unsigned value){return d&&(*d)[field]==value;};
    const bool hasSystemState=custom(3,14)||custom(5,24)||custom(5,25)||config.system==4;
    const bool hasSystemMeter=custom(2,9)||config.system==5;
    const bool alternate=custom(2,8)||config.system==1;
    const bool contact=(a.bodyFlags108&0x40)!=0;
    const auto attack=[&](unsigned first,unsigned last){return contact&&rawAttack(a,first,last);};
    const auto character23=[&] { //17a230
        if(a.character!=23)return false;
        if(!(a.flags244&8))return true;
        return contact&&a.stateTable()==1&&unsigned(a.stateIndex()-69)<16;
    };
    const auto meterReady=[&] { //175858, also used by composite callbacks.
        if(!context.mode4c3808)return false;
        if(alternate)return !(a.flags244&0x40);
        return hasSystemMeter&&(a.systemMeter158>>8)>=a.fieldA30;
    };
    const auto rageReady=[&]{return context.mode4c3808&&uint32_t(a.rageState120)-1<2;};
    const auto within=[&](float center,uint32_t extent) {
        const auto x=scalar(a.x),c=scalar(center);return !x.less(c.sub({extent}))&&!c.add({extent}).less(x);
    };
    switch(id) {
    case 0: { //141118 uses the first battle kind5 object, then stage fallback.
        const auto* object=firstObject(context.battleObjects,5);
        if(object&&(object->action==76||object->action==133))return within(object->x,limits_[2]);
        return context.stageObjectIndex!=-1&&within(context.stageObjectX,limits_[2]);
    }
    case 1: {const auto* object=firstObject(context.ownObjects,4);return object&&object->action==467&&within(object->x,limits_[1]);}
    case 2:return (custom(3,15)||config.system==5)&&a.rageAmount124>=std::bit_cast<int32_t>(limits_[0]<<8);
    case 3:
        if(a.flags248&0x08000000)return true;
        if(opponent.stateTable()==2)return opponent.effectiveFlags()&2;
        return (opponent.state194==0x00360000||opponent.state194==0x00370000)&&opponent.timers[25]>0;
    case 4:return !(a.flags248&8)&&a.state194!=0x001f0000&&a.rageState120<2&&hasSystemState&&a.systemState13c==2;
    case 5:
        if((a.flags248&12)||(hasSystemState&&a.systemState13c>=3)||a.state194==0x00240001||!systems_[config.system][8]||a.state194==0x001f0000||a.rageState120>=2)return false;
        return a.stateTable()==2?(a.effectiveFlags()&1):!(a.flags244&2);
    case 6:return meterReady();
    case 7:
        if(config.system==3)return a.rageState120==2;
        if(config.system==4)return a.systemState13c==3;
        return d&&((hasSystemState&&a.systemState13c==3&&(*d)[5]==25)||(a.rageState120==2&&(*d)[6]==28));
    case 8:return rageReady();
    case 9:return !(a.flags23c&0xa00000);
    case 10:
        if(a.flags244&8)return false;
        a.flags244&=~0x400000u;return true;
    case 11:return attack(64,66);
    case 12:return attack(75,77);
    case 13:return attack(73,73);
    case 14:return (rawAttack(a,69,69)&&uint32_t(a.bodyAction24)-565<5)||attack(76,76);
    case 15:return a.stateTable()==0||attack(76,76);
    case 16: {
        if((a.flags244&4)||(a.flags23c&0xa00000)||!(opponent.flags23c&0x10)||opponent.stateTable()==2)return false;
        const auto& r=airRectangles_.at(a.character);if(r[0]==r[1]||r[2]==r[3])return false;
        const auto x=scalar(a.x),y=scalar(a.y);int32_t left,right;
        //Original truncates each world-space boundary before comparing the
        //opponent's float position. Mirror reverses which endpoint is left.
        if(a.bodyFlags38&0x80000){left=x.sub(ScalarFloat::integer(r[0])).truncate();right=x.sub(ScalarFloat::integer(r[1])).truncate();}
        else {left=x.add(ScalarFloat::integer(r[1])).truncate();right=x.add(ScalarFloat::integer(r[0])).truncate();}
        const auto bottom=y.add(ScalarFloat::integer(r[3])).truncate(),top=y.add(ScalarFloat::integer(r[2])).truncate();
        const auto ox=scalar(opponent.x),oy=scalar(opponent.y);
        return !ox.less(ScalarFloat::integer(left))&&!ScalarFloat::integer(right).less(ox)&&!oy.less(ScalarFloat::integer(bottom))&&!ScalarFloat::integer(top).less(oy);
    }
    case 17:return !(a.flags244&0x100);
    case 18:
        if(a.stateTable()!=1)return !(a.flags244&8);
        return a.timers[3]!=0&&(unsigned(a.stateIndex())<2||unsigned(a.stateIndex()-4)<2||unsigned(a.stateIndex()-8)<2);
    case 19:return attack(71,73);
    case 20:return attack(77,77);
    case 21:return contact&&uint32_t(a.bodyAction24)-599<4&&(uint32_t(a.auxiliaryAction24)-782<2||a.auxiliaryAction24==786);
    case 22:return attack(84,84);
    case 23:return attack(76,78);
    case 24:return attack(70,75);
    case 25:return a.characterBytesF14[4]!=0;
    case 26:return !(a.flags23c&0x400000);
    case 27:return !(a.flags23c&0x400000)&&rageReady();
    case 28:return !(a.flags23c&0x400000)&&meterReady();
    case 29:return a.flags23c&0x400000;
    case 30:return (a.flags23c&0x400000)&&rageReady();
    case 31:return (a.flags23c&0x400000)&&meterReady();
    case 32:return a.characterBytesF14[0]<2&&attack(71,74);
    case 33:return attack(65,67);
    case 34: {
        const auto action=a.bodyAction24;
        if(!(a.flags23c&0x800000)||!contact)return false;
        if(uint32_t(action)-657>=2&&action!=666&&action!=667&&action!=673&&action!=674&&action!=749&&action!=750)return false;
        a.bodyState128=uint32_t(action);return true;
    }
    case 35:case 49:return (a.bodyFlags104&0x40000)&&attack(69,69);
    case 36:return (a.bodyFlags104&0x40000)&&attack(68,68);
    case 37:return (a.bodyFlags104&0x40000)&&scalar(a.y).less({limits_[3]})&&attack(64,66);
    case 38:return !(a.flags244&0x80);
    case 39:return (a.characterBytesF14[5]&63)==63;
    case 40:case 41:case 42:case 43:case 44: {
        const auto bits=a.characterBytesF14[6];
        if(bits&(1u<<(id-40)))return false;
        return ((a.flags23c&0x100000)||std::popcount(unsigned(bits&31))<3)&&character23();
    }
    case 45:return a.auxiliaryState12c!=14&&a.auxiliaryState12c!=19;
    case 46:return a.auxiliaryState12c==14;
    case 47:return a.auxiliaryState12c!=17;
    case 48:return a.auxiliaryState12c==17;
    case 50:return (a.bodyFlags104&0x40000)&&attack(70,70);
    case 51:return attack(70,72);
    case 52:return a.characterBytesF14[9]&&uint32_t(a.bodyAction24)-569<4;
    case 53:
        if(!(a.flags244&8)){a.flags244&=~0x01000000u;return true;}
        if(!attack(64,66))return false;
        a.flags244|=0x01000000;return true;
    case 54:return attack(73,75);
    case 55:return !(a.flags244&0x400);
    case 56:return a.character!=4||opponent.stateTable()!=2||(opponent.stateIndex()!=81&&opponent.stateIndex()!=82&&opponent.stateIndex()!=86);
    case 57:return context.mode4c3808&&!(a.flags244&0x200000)&&a.auxiliaryState128==0;
    case 58:return (a.flags244&0x200000)&&a.timers[21]>0;
    case 59: {
        if(a.timers[7]>0)return false;
        auto distance=scalar(a.x).sub(scalar(opponent.x));if(distance.bits&0x80000000)distance.bits^=0x80000000;
        return distance.truncate()<=attackRanges_.at(a.character)[12]+targetRanges_.at(opponent.character)[opponent.flags23c&0x1000?2:3];
    }
    case 60:return !(a.flags244&0x202)&&!scalar(a.y).less({limits_[4]});
    case 61:return (a.bodyFlags104&0xc0000)&&attack(73,73);
    case 62:return (a.bodyFlags104&0xc0000)&&attack(74,74);
    case 63:return attack(72,72);
    case 64:return !(a.flags244&4);
    case 65:
        //This callback deliberately rejects while setting a follow-up flag.
        if(attack(73,75)&&a.sampledButton9)a.flags244|=0x04000000;
        return false;
    case 66:return character23();
    case 67:return character23()&&meterReady();
    case 68:return character23()&&condition(16,a,opponent,config,context);
    case 69:case 70:
        for(const auto& object:context.ownObjects)if(object&&(object->flags108&(id==69?0x400000:0x800000)))return false;
        return true;
    case 71:return attack(64,66);
    case 72:return attack(72,73);
    case 73:return a.timers[24]<=1024&&rawAttack(a,8,9);
    case 74:
        if(!contact||a.stateTable()!=1||unsigned(a.stateIndex()-64)>=15||a.characterBytesF14[12]>=3)return false;
        ++context.condition74Diagnostics;a.bodyState128=uint32_t(a.stateIndex()-64);return true;
    case 75: {
        unsigned count=0;for(const auto& object:context.ownObjects)if(object&&object->kind==2&&(object->subtype==160||object->subtype==161))++count;
        return count<2;
    }
    case 76:return opponent.state194!=0x00500002;
    case 77:return attack(79,79);
    case 78:return (a.characterBytesF14[13]&127)==127;
    case 79:return (a.characterBytesF14[13]&127)==127&&meterReady();
    case 80:case 81:case 82:return a.flags23c&0x100000;
    default:return false; //83..95 are explicit original zero-return entries.
    }
}
void InputPermissions::filter(PermissionActor& actor,const PermissionActor& opponent,const InputSystemConfig& config,PermissionContext& context,
        std::span<CommandSlot> slots,std::span<const InputBindingRecord> records,const std::array<uint32_t,13>& categories,const std::array<uint32_t,9>& requirements) const {
    if(slots.size()!=records.size())throw std::runtime_error("Input permission record/slot count mismatch");
    for(size_t i=0;i<slots.size();++i) {
        if(!slots[i].recognized)continue;
        const auto& record=records[i];bool allowed=categories.at(record.condition>>8)!=0;
        for(unsigned j=0;allowed&&j<9;++j)if((record.flags&(1u<<j))&&!requirements[j])allowed=false;
        if(allowed&&(record.flags&4))allowed=objectAvailable(record.auxiliary&255,context);
        if(allowed)allowed=condition(record.condition&255,actor,opponent,config,context);
        if(!allowed)slots[i].recognized=0;
    }
}
}
