#include "state_entry.hpp"
#include "actor_state.hpp"

namespace ss6 {
namespace {
uint32_t packedPending(const SelectionActor& a) {
    return uint16_t(a.pendingTable)|(uint32_t(uint16_t(a.pendingIndex))<<16);
}
}
bool stateRequestDiffers(const SelectionActor& a) {
    //150000 compares the packed RAW state, even while effective state
    //lookups use the transformed alias channel.
    return a.pendingTable!=-1&&a.pendingIndex!=-1&&packedPending(a)!=a.state194;
}
void commitStateRequest(SelectionActor& a) {
    if(a.pendingTable==-1||a.pendingIndex==-1)return;
    a.state194=packedPending(a);a.pendingTable=a.pendingIndex=-1;
}
StateEntryPlan prepareStateEntry(StateEntryActor& a) {
    StateEntryPlan plan;
    plan.previousIndex=a.stateIndex();plan.previousTable=a.stateTable();
    plan.index=plan.previousIndex;plan.table=plan.previousTable;
    if(stateRequestDiffers(a)) {
        a.flags23c&=~0x200000u;
        //14ff58 resets the entire alias channel, including metadata, before
        //the new main pending state is read. Main metadata is updated later.
        a.aliasRequest19c=0;a.aliasPendingTable=a.aliasPendingIndex=-1;
        a.state1a4=0xffffffff;a.aliasCharacter1a8=0;a.aliasFlags1aa=0;
        plan.index=a.pendingIndex;plan.table=a.pendingTable;
        if(plan.table==2&&(a.flags23c&0x800000)&&uint32_t(plan.index)>=6) {
            a.flags23c&=~0x800000u;a.auxiliaryState128=27;
            //11d908 queues action776 without forcing an already running
            //instance to restart. State128 changes even in that case.
            if(a.auxiliaryAction24!=776) {
                a.auxiliaryPendingC4=776;a.auxiliaryFrameC0=0;a.auxiliaryFlags104|=1;
            }
        }
        const auto old=uint32_t(plan.previousIndex);
        if(plan.table!=2&&plan.previousTable==2&&(old<7||old==9||old==17||old-32<26)) {
            ActorTimers timers{a.timerDelta,a.timers};timers.set(6,3);a.timers[6]=timers.values[6];
        }
        commitStateRequest(a);a.request18c=1;
    }
    //An explicit entry flag survives a duplicate/missing pending request.
    //Conversely, a duplicate pending word is not cleared just by inspection.
    plan.required=a.request18c!=0;
    plan.finishAttackAfterEntry=plan.required&&plan.previousTable==1&&plan.table!=1;
    return plan;
}
}
