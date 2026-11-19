#pragma once
#include "action_runtime.hpp"

namespace ss6 {
// Native port of the ordinary kind-0/1 object wrappers around ACT playback.
// Actor state callbacks queue an action; the scheduler commits it later.
// This separation preserves contacts/animation/movement from the same tick.
class PlayerObject {
public:
    explicit PlayerObject(ActionBank& bank,unsigned action=0);
    ActionTimeline timeline;
    uint32_t sound34=0; // ACT can retain a physical voice until the next interruption.
    uint32_t scriptLatch134=0;
    uint32_t color8c=0xff808080,field20=0;
    uint32_t resourceSlot0c=0,delta30=256,scale70=0x3f800000,ownerCC=0;
    uint32_t depthOffsetB0=0; // Draw order is independent of the body's world Z.
    std::array<uint32_t,4> zWords{}; //48/64/68/6c, copied to child objects
    float historyOffsetEc=0,historyOffsetF0=0;
    //Only the parent words consumed by11d9c8; not an emulated object image.
    std::array<uint32_t,80> childParentWords() const;
    uint16_t pendingFlags=0; // object+0xfe, carried into a queued action.
    bool request(unsigned action,bool force=false); // 0x11d908
    void markActorActionPending();                //1493c0 before149918
    void commitRequested();                       // 0x11d8e0 / 0x11dbf0
    void animate(uint32_t delta);                 // 0x11d730, ordinary clock
    void move(uint32_t delta);                    // 0x11d6c8, ordinary players
    void setFlags(uint32_t flags104,uint32_t flags108);
    const ActionRecord& actionRecord(unsigned action,unsigned step) {return bank_.get(action).record(step);}
    void rewindFirstRecord(); //170de8/170ef8 +11d850, no action restart
private:
    ActionBank& bank_;
    void refreshJudgment(bool enteredRecord=true); // 0x11dda0 + 0x11e010 + 0x11de10
    void publishJudgmentFlags(); // 0x11e1c0
};
}
