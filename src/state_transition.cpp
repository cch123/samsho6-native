#include "state_entry.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
template<size_t N>void read(const std::filesystem::path& file,std::array<uint8_t,N>& out) {
    std::ifstream in(file,std::ios::binary);
    if(!in.read(reinterpret_cast<char*>(out.data()),N)||in.peek()!=EOF)throw std::runtime_error("Invalid state-entry table: "+file.string());
}
uint32_t word(const uint8_t* p){return p[0]|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
void clampSword(StateEntryActor& a,int32_t limit) {
    a.swordMaximum138=limit;if(a.swordCurrent134>limit)a.swordCurrent134=limit;
}
}
StateEntryRules::StateEntryRules(const std::filesystem::path& assets) {
    read(assets/"selection_normal_descriptors.bin",normal_);read(assets/"entry_attack.bin",attack_);
    read(assets/"entry_special.bin",special_);read(assets/"entry_damage.bin",damage_);
    read(assets/"entry_conditions.bin",conditions_);read(assets/"entry_special_exceptions.bin",specialExceptions_);
    std::array<uint8_t,9*40> systems;read(assets/"permission_systems.bin",systems);
    for(unsigned i=0;i<9;++i)swordLimits_[i]=std::bit_cast<int32_t>(word(systems.data()+i*40+24)<<8);
}
std::span<const uint8_t> StateEntryRules::descriptor(unsigned table,unsigned index,unsigned character,unsigned variant) const {
    if(table==0&&index<64)return std::span(normal_).subspan(index*5,5);
    if(table==1&&character<51&&index<96) {
        if(index>=64)return std::span(special_).subspan((character*32+index-64)*5,5);
        if(variant<4)return std::span(attack_).subspan(((character*4+variant)*64+index)*5,5);
    }
    if(table==2&&index<112&&(index<80||character<51))
        return std::span(damage_).subspan((index<80?index:80+character*32+index-80)*14,14);
    throw std::runtime_error("State descriptor outside original table");
}
void StateEntryRules::pose(StateEntryActor& a,unsigned index) {
    struct Rule {uint16_t flags;bool stop;};
    static constexpr std::array<Rule,31> rules{{
        {4,true},{12,true},{4,false},{1,true},{0x201,true},{9,true},{0x209,true},{1,false},
        {0x201,false},{0x801,true},{0x809,true},{0x801,false},{2,true},{10,true},{2,false},
        {2,true},{10,true},{2,false},{0,true},{8,true},{0,false},{0,true},{0x400,true},
        {0,true},{0x601,true},{4,true},{0x401,false},{0x404,false},{4,true},{4,false},{0,true}
    }};
    if(index>=rules.size())return; //255 and other out-of-range poses are genuine no-ops.
    const auto rule=rules[index];a.flags23c=(a.flags23c&~0xe0fu)|rule.flags;
    if(rule.stop) {
        a.offsetX4c=a.velocityX50=a.accelerationX54=a.offsetY58=a.velocityY5c=a.accelerationY60=0;
        a.bodyFlags104&=~0x140u;a.y=0;
    }
}
void StateEntryRules::conditions(StateEntryActor& a,StateEntryContext& context,unsigned index) const {
    if(index>=69)throw std::runtime_error("Unknown original condition set");
    const auto* record=conditions_.data()+index*3;
    if(record[0]&1)a.conditions15c[1]=a.conditions15c[2]=0;
    if(record[0]&2)context.opponentFlagsB8|=2;
    a.conditions15c[0]=index;
    for(unsigned j=1;j<3;++j) {
        unsigned bit=record[j];if(bit==255)continue;
        //254 is evaluated after the entry pose. A pose that stopped motion
        //therefore selects bit4, even when the previous state was moving.
        if(bit==254)bit=a.velocityX50>0?5:a.velocityX50<0?6:4;
        a.conditions15c.at(1+bit/32)|=1u<<(bit%32);
    }
}
bool StateEntryRules::attackWindow(unsigned character,unsigned index) const {
    if(index<64)return index<21;
    for(unsigned i=0;i<specialExceptions_.size();i+=2) {
        const auto c=specialExceptions_[i],slot=specialExceptions_[i+1];
        if(c==255||slot==255)break;
        if(c==character&&slot==index-64)return false;
    }
    return true;
}
void StateEntryRules::enter(StateEntryActor& a,ActorCommandInput& input,const InputSystemConfig& config,StateEntryContext& context,unsigned table,unsigned index) const {
    if(config.system>8||(config.system==6&&!config.descriptor))throw std::runtime_error("Invalid state-entry system configuration");
    if(context.player>=2)throw std::runtime_error("Invalid state-entry player");
    //152300 restores a temporary callback's saved flags BEFORE clearing
    //its registration. Reading only the body's current flags loses them.
    if(a.override27c[0]){a.bodyFlags104=a.override27c[2];a.bodyFlags108=a.override27c[3];}
    a.bodyFlags104&=~0x30u;a.bodyPendingFE&=uint16_t(~6u);a.bodyFieldE4=a.bodyFieldE8=0;
    a.callbacks260.fill(0);a.override27c.fill(0);
    a.flags23c&=~(0x04000000u|0x100u|0x10000000u|0x20000000u|0x8000u|0x10000u|0x02000000u|0x400u|0x01000000u|0x08000000u|0x40000000u);
    a.timers[3]=a.timers[15]=a.timers[4]=0;
    a.bodyFlags104&=~0x20072u;a.bodyFlags108&=~0xe00u;a.bodyPendingFE&=uint16_t(~1u);
    if(a.flags244&0x80000000u) {
        a.rageState120=a.rageState120<2?0:3;a.rageAmount124=0;
        clampSword(a,swordLimits_[config.system]); //14f148 ->14f108
        clampSword(a,swordLimits_[config.system]); //14f1e0
        a.flags244&=~0x80000000u;
    }
    if(a.flags248&1) {
        if(config.system==5||(config.system==6&&(*config.descriptor)[2]==9)) {
            a.systemMeter158=0;a.bonusRate154=256;a.bonusState14c=1;a.bonusTime150=150;
        }
        a.flags248&=~1u;
    }
    unsigned nextPose=0,nextConditions=0;
    if(table==0) {
        const auto d=descriptor(0,index,a.character);nextPose=d[1];nextConditions=d[2];
        if(index==4||index==5)a.timers[5]=32*256;
        else if(index==48||index==23||index==24||index==54||index==55||(index>=56&&index<=60))input.clearBuffers();
    } else if(table==1) {
        const unsigned variant=!(a.flags23c&0x1000)+((a.flags244&0x4000)?2:0);
        const auto d=descriptor(1,index,a.character,variant);nextPose=d[2];nextConditions=d[3];
        a.timers[3]=index<64?11*256:0;a.timers[4]=attackWindow(a.character,index)?3*256:0;
        input.clearBuffers();
    } else if(table==2) {
        const auto d=descriptor(2,index,a.damageCharacterA18);nextPose=d[10];nextConditions=d[11];a.timers[17]=0;
    }
    context.tasks.clearDisplay(6,context.player);context.tasks.clearDisplay(5,context.player);
    if(table!=2) {
        a.fieldA2c=0;a.contactKind252=0;a.bodyField124=0;
        if(table!=0&&index!=53)a.flags244&=~0x02000000u;
    }
    pose(a,nextPose);conditions(a,context,nextConditions);
    a.flags248&=~0xe300u;a.flags244&=~(0x2000u|0x04000000u|0x80000u);
    if(a.flags244&0x40000)a.flags244|=0x20000;else a.flags244&=~0x20000u;
    if(table==0&&!(a.flags23c&0x10)) {
        a.flags244&=~(0x8000u|0x800u|0x10u|0x20u|0x200u|0x80u|0x400u|0x100u);
        a.fieldF10=0;for(unsigned byte:{0u,6u,11u,12u})a.characterBytesF14[byte]=0;
        a.flags248&=~0x20000000u;
    }
    if(table!=2)a.flags23c&=~0x80000000u;
    if(table==1)a.flags248&=~0x40000000u;else a.flags248&=~0x10u;
    a.controlCounterC0=0;
    if(a.registry28c[10]) {
        if(context.resolvePoolLinks)context.tasks.objects.at(a.registry28c[10]-1)[0x108/4]|=0x4000;
        else {
            if(!context.linkedObjectFlags108)throw std::runtime_error("State-entry registry reference has no live object");
            *context.linkedObjectFlags108|=0x4000;
        }
    }
    a.registry28c.fill(0);a.registry28c[2]=0xffffffff; //163450 releases the registry after flagging its object.
}
StateEntryPlan StateEntryRules::transition(StateEntryActor& a,ActorCommandInput& input,const InputSystemConfig& config,StateEntryContext& context) const {
    const bool carried=a.flags23c&0x800000;
    const auto plan=prepareStateEntry(a);
    if(carried&&!(a.flags23c&0x800000)&&a.auxiliaryObject04&&context.resolvePoolLinks) {
        auto& child=context.tasks.objects.at(a.auxiliaryObject04-1);
        child[0x128/4]=27;
        if(child[0x24/4]!=776) {child[0xc4/4]=776;child[0xc0/4]=0;child[0x104/4]|=1;}
    }
    if(plan.required) {
        enter(a,input,config,context,unsigned(plan.table),unsigned(plan.index));
        if(plan.finishAttackAfterEntry)a.swordWait130=20; //14f1a0, after all14a348 effects.
    }
    return plan;
}
bool StateEntryRules::transitionAlias(StateEntryActor& a,ActorCommandInput& input,const InputSystemConfig& config,StateEntryContext& context) const {
    if(!(a.flags23c&0x200000)||a.aliasPendingTable==-1||a.aliasPendingIndex==-1)return false;
    const uint32_t pending=uint16_t(a.aliasPendingTable)|(uint32_t(uint16_t(a.aliasPendingIndex))<<16);
    if(pending==a.state1a4)return false;
    //The shared entry helper sees the translated state, but the alias
    //channel commits its raw index AFTER entry. The main channel is intact.
    SelectionActor translated;
    translated.flags23c=0x200000;translated.character=a.character;translated.state1a4=pending;
    const auto variant=int16_t(!(a.flags23c&0x1000));
    enter(a,input,config,context,unsigned(a.aliasPendingTable),unsigned(translated.stateIndex()));
    a.state1a4=pending;a.aliasPendingTable=a.aliasPendingIndex=-1;
    a.aliasCharacter1a8=variant;a.aliasFlags1aa=0;a.aliasRequest19c=1;
    return true;
}
void StateEntryRules::updateMetadata(StateEntryActor& a,StateEntryContext& context) const {
    const int table=a.stateTable(),index=a.stateIndex();
    const unsigned variant=!(a.flags23c&0x1000)+((a.flags244&0x4000)?2:0);
    uint8_t flags=a.effectiveFlags();
    if(table==0)flags=descriptor(0,unsigned(index),a.character)[0];
    else if(table==1) {
        flags=descriptor(1,unsigned(index),a.character,variant)[0];
        context.attackMarker12d2300=context.player==0?1:0; //1488e0
    } else if(table==2)flags=descriptor(2,unsigned(index),a.damageCharacterA18)[0];
    //14b798 reads the effective alias state, yet150080 always writes the
    //MAIN metadata. Writing back to the selected channel changes behavior.
    a.stateCharacter198=int16_t(variant);a.stateFlags19a=flags;
}
}
