#pragma once
#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <span>
#include <vector>

namespace ss6 {
struct TaskStackHeader {uint32_t flags=0,value=0;};
struct TaskDispatch {
    //Native handlers resolve these opaque IDs; no original machine code
    //is executed. Flag10 receives the task, flag42 its object argument.
    std::function<void(uint32_t handler,uint32_t argument)> call;
    std::function<void(uint32_t coroutine,uint32_t& continuation)> resume;
    std::function<void(uint32_t coroutine)> destroy;
};
//Native task/object identities are opaque handles. They are never PS2 code
//pointers; the original fixed-capacity slot/order rules are retained here.
struct TaggedTaskPools {
    std::array<std::array<uint32_t,13>,256> tasks{};
    std::array<std::array<uint32_t,80>,256> objects{};
    //Historical names retained for existing actor fixtures. These two-word
    //headers are also UI owners (3d2e88), not coroutine stack allocations.
    std::map<uint32_t,TaskStackHeader> stacks;
    uint32_t freedStacks=0,freeObjectHead=0,freeObjectCount=0;
    uint32_t ownerGlobal3688=0;
    uint32_t freeTaskHead=0;
    std::vector<uint32_t> stackDiagnostics;
    std::array<uint32_t,256> priorityHeads{},activeTags{};
    uint32_t activeCount=0,currentTask=0;
    void initializeOwners(); //1123a8; clears reservation8 only
    uint32_t allocateOwner(); //1123f0; ascending first unreserved header
    void freeOwner(uint32_t handle); //1124b8; null/already-free is harmless
    bool ownerActive(uint32_t handle) const; //112550; tests active1, not reservation8
    void initializeTasks(); //112570; separate from object/stack initialization
    uint32_t popTask(); //1125e0, preserves the popped record
    uint32_t allocateTask(uint32_t priority,uint32_t tag); //112608
    uint32_t createTask(uint32_t priority,uint32_t handler,uint32_t flags,uint32_t tag); //112670
    uint32_t createObjectTask(uint32_t handler,uint32_t object); //1129c8
    void initializeObjects(); //11e290, preserves all payloads/tags
    uint32_t allocateObject(uint32_t tag); //11e2e8
    void freeObject(uint32_t handle); //11e350
    void resetObject(uint32_t handle); //11d528, preserves allocator tail
    uint32_t registerObjectTask(std::span<uint32_t> registry,uint32_t tag,uint32_t handler); //1471a8
    void cancelTasks(uint32_t tag); //112a70/1124b8
    void cancelObjects(uint32_t tag); //11e3a0
    void clearDisplay(unsigned kind,unsigned player); //124d18
    void clearRegistry(std::span<uint32_t> registry); //146e88
    void dispatchTasks(const TaskDispatch& = {}); //112838/112780, native handler boundary
};
}
