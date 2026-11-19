#include "auxiliary_objects.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>

namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete auxiliary fixture");return v;}
uint64_t hash(const auto& rows) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected auxiliary assets directory");unsigned operation;
    while(std::cin>>operation) {
        std::array<unsigned,3> slots;for(auto& v:slots)v=word();ss6::AuxiliaryObjects runtime(argv[1],slots);
        const auto player=word(),character=word();auto flags=word();ss6::GameRandom rng;
        rng.mode=std::bit_cast<int32_t>(word());rng.gameSeed=word();std::cin>>rng.librarySeed;
        const auto hole=word(),kind=word(),tag=word(),handler=word();const auto dx=std::bit_cast<int32_t>(word()),dy=std::bit_cast<int32_t>(word());
        const auto action=word(),requestFlags=word();ss6::AuxiliaryObject parent,child;
        for(auto& v:parent)v=word();for(auto& v:child)v=word();
        ss6::TaggedTaskPools pools;pools.initializeTasks();pools.initializeObjects();pools.objects[0]=child;
        pools.tasks[0][0]=0x1701c0;pools.tasks[0][7]=1;
        std::array<uint32_t,48> registry;registry.fill(1);if(hole<48)registry[hole]=0;
        uint32_t result=0;
        if(operation==0)runtime.initialize(pools.objects[0],parent,kind);
        else if(operation==1)result=runtime.create(pools,registry,player,flags,parent,tag,kind,handler);
        else if(operation==2)result=runtime.drop(pools,registry,rng,player,character,flags,parent);
        else if(operation==3)result=runtime.dropWithOffset(pools,registry,rng,player,character,flags,parent,dx,dy);
        else if(operation==4)result=runtime.dropSpecial(pools,registry,rng,player,character,flags,parent);
        else if(operation==5)runtime.landWeapon(pools,1);
        else if(operation==6)runtime.releaseHold(pools,1);
        else if(operation==7)runtime.request(pools.objects[0],action,requestFlags&1,requestFlags&2);
        else if(operation==8)result=runtime.dropAfterLock(pools,registry,rng,player,character,flags,parent);
        else if(operation==9)result=runtime.deliverWeapon(pools,registry,player,character,flags,parent,std::bit_cast<float>(dx));
        else throw std::runtime_error("Unknown auxiliary operation");
        std::cout<<result<<' '<<flags<<' '<<rng.gameSeed<<' '<<rng.librarySeed<<' '<<pools.freeTaskHead<<' '<<pools.freeObjectHead<<' '<<pools.freeObjectCount<<' '<<hash(pools.tasks)<<' '<<hash(pools.objects);
        for(auto v:registry)std::cout<<' '<<v;
        for(auto v:pools.objects[result?result-1:0])std::cout<<' '<<v;
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
