#include "player_object.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
PlayerObject::PlayerObject(ActionBank& bank,unsigned action):timeline(bank,action),bank_(bank) {
    timeline.clock_.chainedAction=int32_t(action);
    refreshJudgment();publishJudgmentFlags();
}
std::array<uint32_t,80> PlayerObject::childParentWords() const {
    std::array<uint32_t,80> result{};const auto& c=timeline.clock();const auto& m=timeline.motion();
    // The upload slot, owning clock, character resource and color group are
    // separate EE fields. Mirrored roster picks can share art while keeping
    // independent clocks and costume selection.
    result[0xc/4]=resourceSlot0c;result[0x10/4]=resourceSlot0c;
    result[0x14/4]=bank_.resource();result[0x18/4]=bank_.resource()==42?1:bank_.resource();
    result[0x1c/4]=bank_.resource()*5;
    result[0x20/4]=field20;result[0x30/4]=delta30;
    result[0x38/4]=c.objectFlags;result[0x70/4]=scale70;result[0xcc/4]=ownerCC;
    result[0xd8/4]=timeline.pendingRecordDamage_;
    result[0xc8/4]=1; //PlayerObject's admitted position-commit mode.
    result[0x40/4]=std::bit_cast<uint32_t>(m.x);result[0x44/4]=std::bit_cast<uint32_t>(m.y);
    for(auto [off,value]:{std::pair{0x4c,m.dx},{0x50,m.vx},{0x54,m.ax},{0x58,m.dy},{0x5c,m.vy},{0x60,m.ay}})
        result[off/4]=uint32_t(value);
    result[0x48/4]=zWords[0];result[0x64/4]=zWords[1];result[0x68/4]=zWords[2];result[0x6c/4]=zWords[3];
    result[0xb0/4]=depthOffsetB0;
    return result;
}
void PlayerObject::setFlags(uint32_t a,uint32_t b) { timeline.clock_.flags104=a;timeline.clock_.flags108=b; }
void PlayerObject::rewindFirstRecord() {
    timeline.clock_.step=timeline.clock_.fractionalTime=0;
    refreshJudgment(false);
}
void PlayerObject::markActorActionPending() {
    //1493c0 marks the body before149918 copies the actor's queued action
    // into body.c4. Keep that second queue boundary: first-round history
    // and the intervening animation pass still refer to the previous clip.
    timeline.clock_.flags104|=1;timeline.clock_.endReached=0;
}
bool PlayerObject::request(unsigned action,bool force) {
    if (!force&&timeline.action().id()==action) return false;
    // Validate before modifying the live object. Unsupported resource commands
    // must fail here, not halfway through committing an actor transition.
    bank_.get(action);
    auto& clock=timeline.clock_;
    clock.chainedAction=int32_t(action);clock.flags104|=1;clock.endReached=0;
    return true;
}
void PlayerObject::commitRequested() {
    auto& clock=timeline.clock_;
    if (!(clock.flags104&1)) return;
    if (pendingFlags&0x100) clock.objectFlags^=0x80000; //11db88 toggles facing before ACT entry.
    clock.endReached=0;
    clock.flags104&=~uint32_t(1|0x40000|0x80000|0x200000|0x04000000);
    constexpr uint16_t source[]={1,2,4,8,0x200,0x400};
    constexpr uint32_t dest[]={0x400000,0x10,0x20,0x40,0x400,0x800};
    for (unsigned i=0;i<6;++i) {
        clock.flags104&=~dest[i];
        if (pendingFlags&source[i]) clock.flags104|=dest[i];
    }
    pendingFlags=0;
    timeline.start(bank_.get(unsigned(clock.chainedAction)));
    clock.chainedAction=int32_t(timeline.action().id());
    refreshJudgment();publishJudgmentFlags();
}
void PlayerObject::refreshJudgment(bool enteredRecord) {
    auto& clock=timeline.clock_;
    // 120d10 updates the movement gate when entering a record. Rewinding
    // recovery through 11d850 only refreshes judgment and preserves this bit.
    if(enteredRecord)pendingFlags=(pendingFlags&~uint16_t(0x10))|((timeline.record().headerFlags&0x1000)?0x10:0);
    if((timeline.record().headerFlags&0x800)&&!(clock.objectFlags&0x02000000))pendingFlags|=0x80;
    if((timeline.record().motion.kind==2||timeline.record().motion.kind==16)&&!(clock.objectFlags&0x02000000)&&
       !(clock.flags104&0x40)&&(!clock.endReached||(clock.flags104&1)))pendingFlags|=0x80;
    const uint32_t bits=timeline.record().judgmentFlags;
    // JDG bits are not only box metadata: the original projects ten of them
    // into two object flag words, including per-attack consumption behavior.
    for (unsigned i=0;i<10;++i) {
        if (i==2||i==6||i==7) {
            uint32_t mask=1u<<(i==2 ? 28 : i==6 ? 29 : 30);
            clock.flags104=(clock.flags104&~mask)|((bits&(1u<<(i+6))) ? mask : 0);
        } else {
            const unsigned position=31+i;
            uint32_t& word=position<32 ? clock.flags104 : clock.flags108;
            uint32_t mask=1u<<(position%32);
            word=(word&~mask)|((bits&(1u<<(i+6))) ? mask : 0);
        }
    }
    clock.flags104&=~uint32_t(0x02000000);
    if (clock.flags104&0x40000) clock.flags108&=~uint32_t(0x10);
    clock.flags104&=~uint32_t(0x100);
    // Zero duration is a callback-controlled hold, not an instant frame.
    // Movement continues until the landing callback calls 0x11d990.
    if (timeline.record().duration==0) clock.flags104|=0x100;
    if (timeline.motion_.y<0) {
        timeline.motion_.y=0;clock.endControl|=0x100;
    }
}
void PlayerObject::publishJudgmentFlags() {
    auto& clock=timeline.clock_;
    constexpr uint32_t source[]={0x20000000,0x40000000,0x10000000};
    constexpr uint32_t dest[]={0x20,0x40,2};
    for (unsigned i=0;i<3;++i)
        clock.flags108=(clock.flags108&~dest[i])|((clock.flags104&source[i]) ? dest[i] : 0);
}
void PlayerObject::animate(uint32_t delta) {
    auto& clock=timeline.clock_;
    if ((clock.flags104&(0x10|0x100))||(pendingFlags&0x20)) return;
    const int32_t previous=std::bit_cast<int32_t>(clock.fractionalTime);
    // 0x11d730 sets the global jump-inhibit bit for these object flags.
    // Damage callbacks reassert 0x2000 each tick: their terminal ACT jump
    // becomes a completion code so a KO cannot animate into getting up.
    bool changed=timeline.advanceClock(delta,clock.flags104&(0x2000|0x4000));
    // 0x11d730 publishes the PREVIOUS cached JDG on a record change, then
    // refreshes it. Reversing these calls shifts guard/attack flags one tick.
    if (changed) { publishJudgmentFlags();refreshJudgment(); }
    else if (previous/256<std::bit_cast<int32_t>(clock.fractionalTime)/256) publishJudgmentFlags();
    clock.flags104&=~uint32_t(0x2000);
}
void PlayerObject::move(uint32_t delta) {
    auto& clock=timeline.clock_;
    clampRetreat(timeline.motion_,clock.flags108);
    if (pendingFlags&(0x10|0x20)) return;
    // Frozen integration still commits any already accumulated displacement.
    advanceMotion(timeline.motion_,(clock.flags104&0x20) ? 0 : delta,true,
                  clock.objectFlags&0x80000,clock.objectFlags&0x40000);
}
}
