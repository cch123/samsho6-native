#include "tagged_tasks.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
void TaggedTaskPools::initializeOwners() {
    ownerGlobal3688=0;
    for(uint32_t h=1;h<=256;++h)stacks[h].flags&=~8u;
    freedStacks=256;
}
uint32_t TaggedTaskPools::allocateOwner() {
    for(uint32_t h=1;h<=256;++h)if(!(stacks[h].flags&8)) {
        stacks[h]={0xc,0};--freedStacks;return h;
    }
    return 0;
}
void TaggedTaskPools::freeOwner(uint32_t handle) {
    if(!handle)return;
    auto found=stacks.find(handle);
    if(found==stacks.end())throw std::runtime_error("Task refers to an unknown owner");
    //The active and reservation bits are independent of ownership4.
    //Freeing a header twice must not increment the free count twice.
    if(found->second.flags&4) {
        found->second={};++freedStacks;stackDiagnostics.push_back(handle);
    }
}
bool TaggedTaskPools::ownerActive(uint32_t handle) const {
    return handle&&(stacks.at(handle).flags&1);
}
void TaggedTaskPools::initializeTasks() {
    for(unsigned i=0;i<tasks.size();++i){tasks[i].fill(0);tasks[i][3]=i;}
    freeTaskHead=uint32_t(tasks.size());
}
uint32_t TaggedTaskPools::popTask() {
    const auto handle=freeTaskHead;
    if(handle)freeTaskHead=tasks.at(handle-1)[3];
    return handle;
}
uint32_t TaggedTaskPools::allocateTask(uint32_t priority,uint32_t tag) {
    const auto handle=popTask();
    if(handle){auto& task=tasks.at(handle-1);task.fill(0);task[4]=priority;task[5]=tag;}
    return handle;
}
uint32_t TaggedTaskPools::createTask(uint32_t priority,uint32_t handler,uint32_t flags,uint32_t tag) {
    const auto handle=allocateTask(priority,tag);
    if(handle){auto& task=tasks.at(handle-1);task[0]=handler;task[1]=flags;task[10]=1;}
    return handle;
}
uint32_t TaggedTaskPools::createObjectTask(uint32_t handler,uint32_t object) {
    const auto handle=createTask(0,handler,0x42,0);
    if(handle)tasks.at(handle-1)[7]=object;
    return handle;
}
void TaggedTaskPools::initializeObjects() {
    //Unlike112570, this initializer only rebuilds links. Clearing stale
    //payloads or tags here changes later tag-based cancellation behavior.
    for(unsigned i=0;i<objects.size();++i)objects[i][78]=i;
    freeObjectHead=freeObjectCount=uint32_t(objects.size());
}
uint32_t TaggedTaskPools::allocateObject(uint32_t tag) {
    const auto handle=freeObjectHead;
    if(handle) {
        auto& object=objects.at(handle-1);freeObjectHead=object[78];
        object.fill(0);object[79]=tag;--freeObjectCount;
    }
    return handle;
}
void TaggedTaskPools::freeObject(uint32_t handle) {
    auto& object=objects.at(handle-1);
    object.fill(0);object[78]=freeObjectHead;freeObjectHead=handle;++freeObjectCount;
}
void TaggedTaskPools::resetObject(uint32_t handle) {
    auto& object=objects.at(handle-1);
    //The last two words belong to the allocator, not the object payload.
    std::fill_n(object.begin(),78,0u);
    for(unsigned offset:{0x0c,0x10,0x14,0x18,0xcc,0xd0})object[offset/4]=0xffffffff;
}
uint32_t TaggedTaskPools::registerObjectTask(std::span<uint32_t> registry,uint32_t tag,uint32_t handler) {
    const auto slot=std::find(registry.begin(),registry.end(),0u);
    if(slot==registry.end())return 0;
    //1471a8 dereferences failed allocations without a null check. We admit
    //its successful domain and reject pool exhaustion before any mutation;
    //do not turn the original invalid-memory path into a successful spawn.
    if(!freeTaskHead||!freeObjectHead)throw std::runtime_error("Registered object requires nonempty task and object pools");
    const auto task=createTask(50,handler?handler:0x147540,1,tag);
    *slot=task;
    const auto object=allocateObject(tag);resetObject(object);tasks.at(task-1)[7]=object;
    return task;
}
void TaggedTaskPools::cancelTasks(uint32_t tag) {
    if(!tag)return;
    for(auto& task:tasks) {
        const auto id=task[5];
        if((tag>65535?id:uint16_t(id))!=tag)continue;
        if(const auto handle=task[6]) {
            freeOwner(handle);
            task[6]=0;
        }
        task[12]=id;task[1]=4;task[5]=0;
    }
}
void TaggedTaskPools::cancelObjects(uint32_t tag) {
    if(!tag)return;
    //Unlike112a70,11e3a0 selects full-word matching with a signed compare.
    //Negative tags therefore cannot match the zero-extended short IDs.
    const bool full=std::bit_cast<int32_t>(tag)>65535;
    for(unsigned i=0;i<objects.size();++i) {
        auto& object=objects[i];
        if((full?object[79]:uint16_t(object[79]))!=tag)continue;
        object.fill(0);object[78]=freeObjectHead;
        freeObjectHead=i+1;++freeObjectCount; //Original ascending scan/prepend order.
    }
}
void TaggedTaskPools::clearDisplay(unsigned kind,unsigned player) {
    const uint32_t tag=((uint32_t(kind)*4+player)<<16)+0x1b5b;
    cancelTasks(tag);cancelObjects(tag);
}
void TaggedTaskPools::clearRegistry(std::span<uint32_t> registry) {
    //146e88 releases OBJECTS now, but merely marks TASKS2. Returning a
    //task to its free list here would let this round reuse it too early.
    for(auto& handle:registry)if(handle) {
        auto& task=tasks.at(handle-1);freeObject(task[7]);task[1]=2;handle=0;
    }
}
void TaggedTaskPools::dispatchTasks(const TaskDispatch& handlers) {
    priorityHeads.fill(0);
    for(unsigned i=0;i<tasks.size();++i) {
        auto& t=tasks[i];
        if(!t[1]||(t[1]&8))continue;
        auto& head=priorityHeads.at(t[4]);t[3]=head;head=i+1;
    }
    //Ascending slot scan/prepend means descending slot order within each
    //priority. Build all buckets before callbacks; births wait until the
    //next dispatch even though the final active-tag scan can already see them.
    for(auto head:priorityHeads)for(auto h=head;h;h=tasks.at(h-1)[3]) {
        auto& t=tasks.at(h-1);const auto flags=t[1];
        if(!(flags&4)) {
            if(flags==0x10||flags==0x20) {
                const auto wait=std::bit_cast<int32_t>(t[2]);
                if(wait>0)--t[2];
                else {
                    currentTask=h;
                    if(flags==0x10) {
                        if(!handlers.call)throw std::runtime_error("Native task handler required");
                        handlers.call(t[0],h);
                    } else {
                        if(!handlers.resume)throw std::runtime_error("Native coroutine continuation required");
                        handlers.resume(t[9],t[11]);
                    }
                    currentTask=0;
                }
            } else if(flags==0x42) {
                if(!handlers.call)throw std::runtime_error("Native object task handler required");
                currentTask=h;handlers.call(t[0],t[7]);currentTask=0;
            }
        }
        //Use the callback's NEW flags, including a newly requested death.
        if(t[1]&6)t[1]=0;
    }
    freeTaskHead=activeCount=0;
    for(unsigned i=0;i<tasks.size();++i) {
        auto& t=tasks[i];
        if(t[1])activeTags[activeCount++]=t[5];
        else {
            t[3]=freeTaskHead;freeTaskHead=i+1;
            if(t[10]==2) {
                if(!handlers.destroy)throw std::runtime_error("Native coroutine destruction required");
                handlers.destroy(t[9]);
            }
            t[10]=t[11]=0;
        }
    }
}
}
