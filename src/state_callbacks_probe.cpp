#include "state_callbacks.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace {
template<class F>void fields(ss6::StateEntryActor& a,F f) {
#define FIELD(off,member) f(off,a.member,#member)
    FIELD(0x23c,flags23c);FIELD(0x244,flags244);FIELD(0x248,flags248);FIELD(0xa10,character);
    FIELD(0x194,state194);FIELD(0x1a4,state1a4);FIELD(0x198,stateCharacter198);FIELD(0x1a8,aliasCharacter1a8);
    FIELD(0x19a,stateFlags19a);FIELD(0x1aa,aliasFlags1aa);FIELD(0xa18,damageCharacterA18);
    FIELD(0x120,rageState120);FIELD(0x124,rageAmount124);FIELD(0x128,rageDecay128);
    FIELD(0x130,swordWait130);FIELD(0x134,swordCurrent134);FIELD(0x138,swordMaximum138);
    FIELD(0x13c,systemState13c);FIELD(0x144,systemTime144);FIELD(0x14c,bonusState14c);FIELD(0x150,bonusTime150);
    FIELD(0x154,bonusRate154);FIELD(0x158,systemMeter158);
    for(unsigned i=0;i<a.callbacks260.size();++i)FIELD(0x260+i*4,callbacks260[i]);
#undef FIELD
}
uint32_t readWord(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete callback fixture");return v;}
template<class T>void readValue(T& v) {
    const auto bits=readWord();
    if constexpr(std::is_signed_v<T>)v=std::bit_cast<T>(static_cast<std::make_unsigned_t<T>>(bits));
    else v=static_cast<T>(bits);
}
}
int main(int argc,char** argv) {
 try {
    if(argc<2)throw std::runtime_error("Expected assets or --layout");
    if(std::string(argv[1])=="--layout") {
        ss6::StateEntryActor a;fields(a,[](unsigned off,auto& v,const char* name){std::cout<<off<<' '<<sizeof(v)<<' '<<name<<'\n';});return 0;
    }
    const ss6::StateCallbacks rules(argv[1]);const ss6::StateEntryRules entries(argv[1]);unsigned op;
    while(std::cin>>op) {
        ss6::StateEntryActor a;ss6::InputSystemConfig config;ss6::CallbackContext context;ss6::StateEntryContext entry;
        entry.player=readWord();config.system=readWord();config.character=readWord();
        std::array<uint8_t,16>d;for(auto& v:d)v=uint8_t(readWord());config.descriptor=d;
        const auto amount=std::bit_cast<int32_t>(readWord());entry.attackMarker12d2300=readWord();
        fields(a,[](unsigned,auto& v,const char*){readValue(v);});
        for(auto& h:context.ownObjects)h=readWord();
        const auto count=readWord();for(unsigned i=0;i<count;++i) {
            const auto handle=readWord();auto& object=context.objects[handle];readValue(object.kindCC);object.fieldD4=readWord();
        }
        ss6::CallbackSystemEffects effects;
        if(op==5) {
            for(auto& v:effects.flags46a918)v=readWord();for(auto& v:effects.phases46a910)v=readWord();
            effects.scale1239d84=readWord();const auto seed=readWord();
            for(unsigned i=0;i<1024;++i)effects.flags3ebf30[i]=uint16_t(seed+i*137);
        }
        ss6::CallbackContext pooled;std::array<uint32_t,48> registry{};
        const bool taskPools=argc==3&&std::string(argv[2])=="--task-pools";
        if(taskPools) {
            for(const auto& [handle,object]:context.objects) {
                auto& row=entry.tasks.objects.at(handle-1);
                row[0xcc/4]=uint32_t(object.kindCC);row[0xd4/4]=object.fieldD4;
            }
            for(unsigned i=0;i<registry.size();++i)if(const auto h=context.ownObjects[i]) {
                //Separate tasks may alias one object; lookup must retain
                //registration order, holes and shared object identity.
                registry[i]=i+1;entry.tasks.tasks[i][7]=h;
            }
            pooled.bindTasks(entry.tasks,registry);
        }
        auto& activeContext=taskPools?pooled:context;
        uint32_t result=0;
        if(op==0)result=rules.registerNormal(a);
        else if(op==1)result=rules.registerAttack(a,config,activeContext);
        else if(op==2)rules.registerAlias(a);
        else if(op==3)rules.addRage(a,config,amount);
        else if(op==4){entries.updateMetadata(a,entry);result=rules.registerAttack(a,config,activeContext);}
        else if(op==5)rules.endSystemEffect(a,config,effects,entry.player);
        else if(op==6)result=rules.damageDropsWeapon(a,config.character,amount);
        else if(op==7)result=rules.hasSystemEffect(config);
        else throw std::runtime_error("Unknown callback fixture");
        std::cout<<result<<' '<<entry.attackMarker12d2300;
        fields(a,[](unsigned,auto& v,const char*){std::cout<<' '<<uint32_t(static_cast<std::make_unsigned_t<std::remove_reference_t<decltype(v)>>>(v));});
        for(auto h:context.ownObjects)std::cout<<' '<<h;
        for(auto [handle,object]:context.objects)std::cout<<' '<<handle<<' '<<uint32_t(object.kindCC)<<' '
            <<(taskPools?entry.tasks.objects.at(handle-1)[0xd4/4]:object.fieldD4);
        if(op==5) {
            for(auto v:effects.flags46a918)std::cout<<' '<<v;for(auto v:effects.phases46a910)std::cout<<' '<<v;
            std::cout<<' '<<effects.scale1239d84;for(auto v:effects.flags3ebf30)std::cout<<' '<<v;
        }
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
