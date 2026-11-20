#include "fighter_tables.hpp"
#include "state_callbacks.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
template<size_t N>std::array<uint8_t,N> read(const std::filesystem::path& file,size_t extendedSize=N) {
    std::array<uint8_t,N> data;std::ifstream in(file,std::ios::binary|std::ios::ate);
    const auto size=in.tellg();
    if((size!=std::streamoff(N)&&size!=std::streamoff(extendedSize)) ||
       !in.seekg(0).read(reinterpret_cast<char*>(data.data()),N))
        throw std::runtime_error("Invalid callback table: "+file.string());
    return data;
}
uint32_t word(const uint8_t* p){return p[0]|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
const std::array<uint8_t,16>* descriptor(const InputSystemConfig& config) {
    if(config.system>8||config.character>=51)throw std::runtime_error("Invalid callback meter configuration");
    if(config.system!=6)return nullptr;
    if(!config.descriptor)throw std::runtime_error("Custom callback system requires its descriptor");
    return &*config.descriptor;
}
uint32_t registerHandler(StateEntryActor& a,uint32_t handler,int table,int argument) {
    //Source addresses serve as stable handler IDs only. The runtime must
    //dispatch these to native implementations, never call the integer.
    a.callbacks260[0]=handler;a.callbacks260[1]=uint32_t(table);a.callbacks260[2]=uint32_t(argument);
    return handler; //1522a0 preserves the remaining four callback words.
}
}
StateCallbacks::StateCallbacks(const std::filesystem::path& assets):entries_(assets),bindings_(assets),fighters_(assets) {
    const auto handlers=read<51*4>(assets/"callback_attack_handlers.bin");
    // Fighter callbacks only use the playable 51 rows. Older asset packs
    // stop there; the complete table also carries two CPU pattern banks.
    const auto special=read<51*128>(assets/"callback_special_parameters.bin",53*128);
    const auto characters=read<51*28>(assets/"callback_character_parameters.bin");
    const auto systems=read<9*40>(assets/"permission_systems.bin");
    const auto constants=read<8>(assets/"callback_constants.bin");
    for(unsigned c=0;c<51;++c) {
        attackHandlers_[c]=word(handlers.data()+c*4);
        std::copy_n(special.begin()+c*128,128,specialParameters_[c].begin());
        for(unsigned j=0;j<7;++j)characters_[c][j]=std::bit_cast<int32_t>(word(characters.data()+c*28+j*4));
    }
    for(unsigned s=0;s<9;++s)for(unsigned j=0;j<10;++j)systems_[s][j]=std::bit_cast<int32_t>(word(systems.data()+s*40+j*4));
    for(unsigned j=0;j<2;++j)rageConstants_[j].bits=word(constants.data()+j*4);
}
uint32_t StateCallbacks::registerNormal(StateEntryActor& a) {
    const int table=a.stateTable(),index=a.stateIndex();
    if(table!=0||uint32_t(index)>=64)throw std::runtime_error("Invalid normal callback state");
    return registerHandler(a,0x1743c0,table,index);
}
void CallbackContext::bindTasks(TaggedTaskPools& pools,std::span<const uint32_t> registry) {
    if(registry.size()!=48||!objects.empty()||std::any_of(ownObjects.begin(),ownObjects.end(),[](auto h){return h!=0;}))
        throw std::runtime_error("Live callback registry cannot mix task handles and snapshot identities");
    pools_=&pools;taskRegistry_=registry;
}
void CallbackContext::releaseAttackGates() {
    if(pools_) {
        for(auto task:taskRegistry_)if(task) {
            const auto object=pools_->tasks.at(task-1)[7];
            pools_->objects.at(object-1)[0x108/4]&=~0x200000u;
        }
        return;
    }
    for(auto handle:ownObjects)if(handle)objects.at(handle).flags108&=~0x200000u;
}
void CallbackContext::setFirstAttackCommand(uint32_t value) {
    if(pools_) {
        for(auto task:taskRegistry_)if(task) {
            const auto handle=pools_->tasks.at(task-1)[7];auto& object=pools_->objects.at(handle-1);
            if(object[0xcc/4]==3){object[0xd4/4]=value;break;}
        }
        return;
    }
    for(auto handle:ownObjects)if(handle) {
        auto& object=objects.at(handle);
        if(object.kindCC==3){object.fieldD4=value;break;}
    }
}
uint32_t StateCallbacks::registerOrdinaryDamage(StateEntryActor& a,const InputSystemConfig& config) const {
    const int index=a.stateIndex();
    if(!playableFighter(a.character)||a.character!=config.character||(config.system>5&&config.system!=8)||a.stateTable()!=2||uint32_t(index)>111)
        throw std::runtime_error("Ordinary damage registration requires a supported fighter, spirit and common damage state");
    //15/16 retain the facing toggle for downed-body orientation. Other
    //entries clear it as well as the motion/clock gates4/8.
    a.bodyPendingFE&=uint16_t(~(4u|8u|((index==15||index==16)?0u:0x100u)));
    if(index>=80) {
        // 14cc10 binds the source's damage-source handler (4e97a8,
        // fighter_stubs.bin). Mina's recovers through 169810 itself when
        // 4e3a80 has no row; the other hand ports admit only their own rows.
        const unsigned source=a.pendingCharacter254;
        if(fighters_.scriptVictim(source)||source==24)return registerHandler(a,fighters_.damageSource(source),2,index-80);
        if(source>3||(source==2&&index!=80)||(source==3&&index>87&&index!=96))
            throw std::runtime_error("Missing source character damage callback");
        return registerHandler(a,fighters_.damageSource(source),2,index-80);
    }
    return registerHandler(a,0x174fe0,2,index);
}
void StateCallbacks::registerAlias(StateEntryActor& a) {
    if(a.flags23c&0x200000)a.callbacks260[0]=a.character==45?0x2099e0:0x1ec728;
}
void StateCallbacks::resetRage(StateEntryActor& a,const InputSystemConfig& config) const {
    a.rageState120=a.rageState120<2?0:3;a.rageAmount124=0;
    const int32_t limit=systems_.at(config.system)[6]<<8; // 50dee0 + system*40 + 0x18
    a.swordMaximum138=limit;if(a.swordCurrent134>limit)a.swordCurrent134=limit;
}
void StateCallbacks::addRage(StateEntryActor& a,const InputSystemConfig& config,int32_t amount) const {
    descriptor(config);
    if(a.rageState120!=0)return;
    //ADDU and the shift wrap as32-bit words before the SIGNED threshold
    //test. Preserve negative gains and overflow instead of saturating early.
    const auto updated=std::bit_cast<int32_t>(uint32_t(a.rageAmount124)+(uint32_t(amount)<<8));
    a.rageAmount124=updated;
    if(updated>=0xb800) {
        a.rageAmount124=0xb800;a.rageState120=1;
        const auto& system=systems_[config.system];
        auto duration=ScalarFloat::integer(characters_[config.character][0]).mul(ScalarFloat::integer(system[9])).mul(rageConstants_[0]);
        a.rageDecay128=rageConstants_[1].div(duration).truncate();
        a.swordMaximum138=std::bit_cast<int32_t>(uint32_t(system[7])<<8);
        a.swordCurrent134=a.swordMaximum138;
    } else if(updated<0)a.rageAmount124=0;
}
void StateCallbacks::addTenChainRage(StateEntryActor& a,const InputSystemConfig& config) const {
    // 16bddc requests 90 through 14ef38, which rounds UP after both the
    // spirit gain percentage and the character gain percentage are applied.
    const int scaled=90*systems_.at(config.system)[1]*characters_.at(config.character)[5];
    addRage(a,config,(scaled+9999)/10000);
}

uint32_t StateCallbacks::registerAttack(StateEntryActor& a,const InputSystemConfig& config,CallbackContext& context) const {
    const auto* custom=descriptor(config);
    const int table=a.stateTable(),index=a.stateIndex();
    if(table!=1||uint32_t(index)>=96||a.character>=51)throw std::runtime_error("Invalid attack callback state");
    const int variant=(a.flags23c&0x200000)?a.aliasCharacter1a8:a.stateCharacter198;
    const auto d=entries_.descriptor(1,unsigned(index),a.character,unsigned(variant));
    uint32_t handler;
    if(index<64&&!(d[0]&0x80))handler=registerHandler(a,0x174b40,table,index);
    else {
        handler=registerHandler(a,attackHandlers_[a.character],table,d[1]);
        const bool rageOnAttack=config.system==5||config.system==7||(custom&&((*custom)[0]==2||(*custom)[0]==3));
        if(rageOnAttack) {
            if(bindings_.specialFirstCategory(a.character,index))a.flags244|=0x80000000;
            if(index>=64)addRage(a,config,specialParameters_[a.character][(index-64)*4]);
        }
        if(bindings_.specialSecondCategory(a.character,index)) {
            // Shin records its once-per-match secret immediately. Ken uses
            // the same ACTs but spends its reserve on leaving the attack.
            if(config.system==1||(custom&&(*custom)[2]==8))a.flags244|=0x40;
            else a.flags248|=1;
        }
    }
    //Regular attacks also write index-64, even though it is negative. A
    //generic optional-object setter that skips negatives changes the source.
    context.setFirstAttackCommand(uint32_t(index-64));
    return handler;
}
bool StateCallbacks::damageDropsWeapon(const StateEntryActor& a,unsigned sourceCharacter,int32_t index) {
    if(a.character!=33||!(a.flags244&0x200000))return false;
    if(index<80)return uint32_t(index)>=15&&index!=18;
    const auto slot=uint32_t(index)-80;
    if(sourceCharacter==12)return slot!=16&&slot!=17&&slot!=18;
    if(sourceCharacter==13)return slot!=16;
    return true;
}
bool StateCallbacks::hasSystemEffect(const InputSystemConfig& config) {
    const auto* custom=descriptor(config);
    return config.system==4||(custom&&((*custom)[3]==14||(*custom)[5]==24||(*custom)[5]==25));
}
void StateCallbacks::endSystemEffect(StateEntryActor& a,const InputSystemConfig& config,CallbackSystemEffects& effects,unsigned player) {
    if(player>=2||!hasSystemEffect(config))throw std::runtime_error("System effect termination without original mode state");
    a.systemTime144=0;a.systemState13c=4;
    effects.flags46a918[player]&=~1u;effects.phases46a910[player]=2;
    //The other player's active bit keeps the shared scale/flag range live.
    //Clearing global effects on every exit breaks simultaneous activations.
    if(!(effects.flags46a918[1-player]&1)) {
        effects.scale1239d84=256;
        std::fill(effects.flags3ebf30.begin()+512,effects.flags3ebf30.end(),uint16_t(0));
    }
}
}
