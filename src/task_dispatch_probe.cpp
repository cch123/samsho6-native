#include "tagged_tasks.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace {
uint32_t word() {
    uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete task fixture");return v;
}
uint64_t hash(const auto& values) {
    uint64_t h=14695981039346656037ull;
    for(uint32_t v:values){h^=v;h*=1099511628211ull;}
    return h;
}
uint64_t hashRows(const auto& rows) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}
    return h;
}
}
int main() {try {
    ss6::TaggedTaskPools pools;std::array<uint32_t,64> registry{};
    std::vector<uint32_t> calls;char op;
    ss6::TaskDispatch handlers;
    handlers.call=[&](uint32_t handler,uint32_t argument) {
        calls.insert(calls.end(),{handler,argument,pools.currentTask});
        if(handler==0x147540) {
            pools.objects.at(pools.tasks.at(argument-1)[7]-1)[0x104/4]&=~0x100u;
        } else if(handler==0x11d990) {
            auto& object=pools.objects.at(argument-1);
            std::fill(object.begin()+0x4c/4,object.begin()+0x64/4,0u);
            object[0x104/4]&=~0x140u;
        } else if(handler==1) {
            //Synthetic native-contract fixtures, reported separately from
            //whole-original comparisons. Exercise mutation during dispatch.
            pools.createTask(0,2,0x10,0x1234);
            pools.tasks.at(argument-1)[1]=2;
        } else if(handler==2) {
            pools.tasks.at(argument-1)[1]=0;
        } else if(handler==3) {
            pools.tasks.at(argument-1)[1]=0;
            pools.tasks.at(254)[1]=4;
        } else throw std::runtime_error("Unknown native test handler");
    };
    handlers.resume=[&](uint32_t coroutine,uint32_t& continuation) {
        calls.insert(calls.end(),{4,coroutine,pools.currentTask,continuation});
        ++continuation;pools.tasks.at(pools.currentTask-1)[1]=2;
    };
    handlers.destroy=[&](uint32_t coroutine) {calls.insert(calls.end(),{5,coroutine,pools.currentTask});};
    while(std::cin>>op) {
        if(op=='P') {
            pools={};pools.freeTaskHead=word();pools.freeObjectHead=word();pools.freeObjectCount=word();
            pools.currentTask=word();pools.activeCount=word();
            for(auto& v:pools.priorityHeads)v=word();
            for(auto& v:pools.activeTags)v=word();
            for(auto& row:pools.tasks)for(auto& v:row)v=word();
            for(auto& row:pools.objects)for(auto& v:row)v=word();
            for(auto& v:registry)v=word();
            continue;
        }
        calls.clear();uint32_t result=0;
        if(op=='t')pools.initializeTasks();
        else if(op=='o')pools.initializeObjects();
        else if(op=='c') {
            const auto count=word();if(count>registry.size())throw std::runtime_error("Invalid registry size");
            pools.clearRegistry(std::span(registry).first(count));
        } else if(op=='d')pools.dispatchTasks(handlers);
        else if(op=='g') {
            const auto tag=word();result=pools.registerObjectTask(registry,tag,0);
        } else if(op=='s') {
            const auto priority=word(),handler=word(),flags=word(),tag=word();
            result=pools.createTask(priority,handler,flags,tag);
        } else if(op!='v')throw std::runtime_error("Unknown task fixture operation");
        std::cout<<result<<' '<<pools.freeTaskHead<<' '<<pools.freeObjectHead<<' '<<pools.freeObjectCount
                 <<' '<<pools.currentTask<<' '<<pools.activeCount
                 <<' '<<hashRows(pools.tasks)<<' '<<hashRows(pools.objects)
                 <<' '<<hash(pools.priorityHeads)<<' '<<hash(pools.activeTags);
        for(auto v:registry)std::cout<<' '<<v;
        std::cout<<' '<<calls.size();for(auto v:calls)std::cout<<' '<<v;
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
