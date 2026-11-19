#pragma once
#include "input_permissions.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor : PermissionActor {
    //These historical field names hold the weapon/range variant (0..3),
    //not a character ID.14b798 writes the main variant even in alias mode.
    int16_t stateCharacter198=0,aliasCharacter1a8=0;
    uint32_t damageCharacterA18=0;
    uint32_t bodyFieldE4=0,bodyFieldE8=0,bodyField124=0;
    uint32_t bodyColor8c=0xff808080,bodyField20=0,fieldA28=0;
    int32_t queuedActionA3c=-1;
    int32_t pickedItemA40=-1;
    int32_t jumpDirectionA44=0;
    int32_t maximumLifeA34=200,pendingDamageA38=0;
    uint32_t fieldA50=0,auxiliaryObject04=0;
    int32_t weaponLockPhaseA54=0,weaponLockResultA58=-1,controlFieldF4=0;
    std::array<uint8_t,9> characterBytesF22{};
    //Control-owner fields touched by1588c0. Existing B4/B8/C0/C8 fields
    //remain authoritative; do not reset a parallel AI/input snapshot.
    std::array<uint32_t,10> controlTimers0c{},controlMotion38{};
    // 1588c0 resets motion+00..24. The following per-command scratch words
    // survive a sequence change until its next callback overwrites them.
    std::array<uint32_t,10> controlMotion60{};
    int32_t cpuTimerDelta08=256;
    // The final word identifies a script table row. It is a row handle in
    // native code, independent of where the resource is mapped.
    std::array<uint32_t,6> cpuTechnique98{};
    uint32_t controlTimer34=0; // Eleventh timer. The ten earlier counters share older probe layouts.
    uint32_t controlB0=0; // 158990 stores whether a forced reaction consumed this decision.
    uint32_t control88=0,control8c=0,controlFlagsBC=0,controlC4=0;
    uint32_t controlCC=0,controlD8=0,controlE4=0,controlE8=0;
    uint32_t controlD0=0,controlDC=0,controlEC=0,controlF0=0,controlF8=0;
    // Signed halfwords published by the CPU perception pass. Mode 3 can
    // recalculate the threat's distance independently during dispatch.
    int16_t cpuRange168=0,cpuRange16a=0,cpuRange16c=0,cpuRange16e=0,cpuRange170=0;
    uint32_t cpuWall178=0;
    int16_t cpuPrevious174=0,cpuSituation180=0,cpuSituation182=0,cpuSituation184=0;
    int16_t cpuSituation186=0,cpuSituation188=0,cpuSituation18a=0;
    std::array<uint32_t,7> callbacks260{};
    std::array<uint32_t,4> override27c{};
    std::array<uint32_t,13> registry28c{};
    std::array<uint32_t,3> conditions15c{};
    //151238(254) also reads bit30 of actor+17c after testing160:70.
    //151298 resets only160/164; preserve this separate raw word on entry.
    uint32_t conditionWord17c=0;
    uint32_t controlCounterC0=0,fieldA2c=0,fieldF10=0;
    uint8_t concentrationUsed11c=0; // 14f580 selects Issen's concentration or Rage Explosion damage formula.
    int32_t rageDecay128=0,rageCharge12c=0,swordWait130=0,swordCurrent134=0,swordMaximum138=0;
    int32_t bonusState14c=0,bonusTime150=0,bonusRate154=0;
    int32_t systemAmount140=0,systemTime144=0,systemDecay148=0;
    int32_t recoveryA4c=0;
    uint32_t flagsB8=0;
};
struct StateEntryPlan {
    bool required=false;
    int previousTable=0,previousIndex=0,table=0,index=0;
    //1491e0 invokes14f1a0 only AFTER14a348 returns. This records the
    //continuation without prematurely changing attack-meter state.
    bool finishAttackAfterEntry=false;
};
bool stateRequestDiffers(const SelectionActor&); //150000
void commitStateRequest(SelectionActor&); //150038
//1491e0 prefix ending immediately before14a348. The caller must perform
//the complete state-entry helper before using this as a gameplay update.
StateEntryPlan prepareStateEntry(StateEntryActor&);
struct StateEntryContext {
    unsigned player=0;
    uint32_t opponentFlagsB8=0;
    uint32_t attackMarker12d2300=0;
    //registry28c[10] is an opaque object reference. Its live flags are
    //resolved separately; never reinterpret a saved PS2 word as a pointer.
    std::optional<uint32_t> linkedObjectFlags108;
    TaggedTaskPools tasks;
    bool resolvePoolLinks=false;
};
class StateEntryRules {
public:
    explicit StateEntryRules(const std::filesystem::path& assets);
    std::span<const uint8_t> descriptor(unsigned table,unsigned index,unsigned character,unsigned variant=0) const;
    static void pose(StateEntryActor&,unsigned index); //16a8f8
    void conditions(StateEntryActor&,StateEntryContext&,unsigned index) const; //151298
    bool attackWindow(unsigned character,unsigned index) const; //14bb08/169308
    void enter(StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,unsigned table,unsigned index) const; //14a348
    StateEntryPlan transition(StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&) const; //1491e0
    bool transitionAlias(StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&) const; //14cbc8
    void updateMetadata(StateEntryActor&,StateEntryContext&) const; //14b798
private:
    std::array<uint8_t,64*5> normal_;
    std::array<uint8_t,51*4*64*5> attack_;
    std::array<uint8_t,51*32*5> special_;
    std::array<uint8_t,(80+51*32)*14> damage_;
    std::array<uint8_t,69*3> conditions_;
    std::array<uint8_t,69*2> specialExceptions_;
    std::array<int32_t,9> swordLimits_;
};
}
