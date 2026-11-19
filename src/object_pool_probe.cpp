#include "tagged_tasks.hpp"
#include "game_random.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>

namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete pool fixture");return v;}
uint64_t hash(const auto& rows) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}
    return h;
}
}
int main() {
 try {
    ss6::TaggedTaskPools pools;ss6::GameRandom random;std::array<uint32_t,48> registry{};char op;
    while(std::cin>>op) {
        if(op=='R') {
            random.mode=std::bit_cast<int32_t>(word());random.gameSeed=word();
            if(!(std::cin>>random.librarySeed))throw std::runtime_error("Incomplete random fixture");
            continue;
        }
        if(op=='r') {
            const auto kind=word();const auto bound=std::bit_cast<int32_t>(word());
            const auto result=kind==0?random.nextGame():kind==1?random.nextLibrary():uint32_t(random.bounded(bound));
            std::cout<<result<<' '<<random.gameSeed<<' '<<random.librarySeed<<'\n';continue;
        }
        if(op=='P') {
            pools={};pools.freeTaskHead=word();pools.freeObjectHead=word();pools.freeObjectCount=word();
            const auto nt=word();for(unsigned i=0;i<nt;++i){auto& row=pools.tasks.at(word());for(auto& v:row)v=word();}
            const auto no=word();for(unsigned i=0;i<no;++i){auto& row=pools.objects.at(word());for(auto& v:row)v=word();}
            for(auto& v:registry)v=word();continue;
        }
        uint32_t result=0;
        if(op=='t')pools.initializeTasks();
        else if(op=='o')pools.initializeObjects();
        else if(op=='p')result=pools.popTask();
        else if(op=='a'){const auto priority=word(),tag=word();result=pools.allocateTask(priority,tag);}
        else if(op=='c'){const auto priority=word(),handler=word(),flags=word(),tag=word();result=pools.createTask(priority,handler,flags,tag);}
        else if(op=='b'){const auto handler=word(),object=word();result=pools.createObjectTask(handler,object);}
        else if(op=='j')result=pools.allocateObject(word());
        else if(op=='f')pools.freeObject(word());
        else if(op=='s')pools.resetObject(word());
        else if(op=='g'||op=='e') {
            const auto count=word(),tag=word(),handler=word();
            if(count>registry.size())throw std::runtime_error("Invalid registry fixture");
            if(op=='e') {
                //A native fail-fast boundary test, not original equivalence.
                try {pools.registerObjectTask(std::span(registry).first(count),tag,handler);throw std::logic_error("Expected exhausted-pool rejection");}
                catch(const std::runtime_error&){result=1;}
            } else result=pools.registerObjectTask(std::span(registry).first(count),tag,handler);
        } else if(op=='x')pools.cancelObjects(word());
        else throw std::runtime_error("Unknown pool fixture operation");
        std::cout<<result<<' '<<pools.freeTaskHead<<' '<<pools.freeObjectHead<<' '<<pools.freeObjectCount<<' '<<hash(pools.tasks)<<' '<<hash(pools.objects);
        for(auto v:registry)std::cout<<' '<<v;std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
