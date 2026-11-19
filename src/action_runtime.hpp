#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <map>
#include <vector>
#include "motion.hpp"

namespace ss6 {
struct ActionRecord {
    uint32_t headerFlags=0;
    std::array<int16_t, 5> parts;
    int16_t duration;
    int16_t endKind;
    uint32_t sourceRecord;
    MotionCommand motion;
    std::array<int16_t, 8> judgmentRefs{};
    uint16_t judgmentFlags = 0;
    int16_t soundCommand = 0;
    std::array<int16_t,3> effectCommand{}; //ACT+2e/30/32 when header400 is set
};

// Convert the signed ACT clock step to its physical record in the fighter bank.
int fighterActionRecord(unsigned resource,unsigned action,int start,unsigned count,int32_t step);
class ActionBank;

// Standalone inspection requires explicit admission of sound-bearing
// records. The battle installs its dispatcher before starting the actors.
class ActionClip {
public:
    explicit ActionClip(const std::filesystem::path& assets, unsigned id = 0, bool mutedInspection = false,
                        unsigned resource = 0);
    const ActionRecord& record(uint32_t step) const;
    uint32_t size() const { return recordCount_; }
    uint32_t cycleTicks() const;
    unsigned id() const { return id_; }
private:
    friend class ActionBank;
    ActionClip(const std::vector<uint8_t>& aid,const std::vector<uint8_t>& act,unsigned id,
               bool mutedInspection,unsigned resource);
    std::vector<ActionRecord> records_;
    unsigned id_;
    unsigned recordCount_=0;
};

struct ActionClock {
    uint32_t step = 0;
    uint32_t fractionalTime = 0;
    uint32_t endReached = 0;
    uint32_t endControl = 0;
    uint32_t objectFlags = 0x10000000;
    uint32_t flags104 = 0, flags108 = 0;
    int32_t chainedAction = 0; // object+0xc4, written only by an ACT jump.
};

// Stable ownership is required: a live action may jump to another clip while
// renderer and judgment collection still refer to the actor's current record.
class ActionBank {
public:
    explicit ActionBank(std::filesystem::path assets,bool mutedInspection=false,unsigned resource=0)
        : assets_(std::move(assets)),mutedInspection_(mutedInspection),resource_(resource) {}
    const ActionClip& get(unsigned id);
    unsigned resource() const {return resource_;}
private:
    std::filesystem::path assets_;
    bool mutedInspection_;
    unsigned resource_;
    std::vector<uint8_t> aid_,act_;
    std::map<unsigned,ActionClip> clips_;
};

class ActionTimeline {
public:
    explicit ActionTimeline(const ActionClip& action) : action_(&action) { reset(); }
    ActionTimeline(ActionBank& bank,unsigned action) : action_(&bank.get(action)),bank_(&bank) { reset(); }
    bool advance(uint32_t resolvedDelta);
    // The game scheduler advances animation, then movement in separate
    // passes. Keep advance() for existing standalone inspection fixtures.
    bool advanceClock(uint32_t resolvedDelta,bool suppressActionJump=false);
    void advanceMovement(uint32_t resolvedDelta);
    void reset();
    void start(const ActionClip& action);
    const ActionClip& action() const { return *action_; }
    const ActionRecord& record() const { return action_->record(clock_.step); }
    void stopMotion();
    void setPosition(float x,float y) { motion_.x=x; motion_.y=y; }
    void setMotion(const MotionState& motion) { motion_=motion; }
    void setObjectFlags(uint32_t flags38,uint32_t flags104,uint32_t flags108) {
        clock_.objectFlags=flags38; clock_.flags104=flags104; clock_.flags108=flags108;
    }
    const ActionClock& clock() const { return clock_; }
    const MotionState& motion() const { return motion_; }
    // ACT+2 is latched at record entry and consumed on the next collision pass.
    // It can cause damage before hitbox resolution, even while the pose is held.
    uint8_t takeRecordDamage() {const auto value=pendingRecordDamage_;pendingRecordDamage_=0;return value;}
    int16_t lastSoundCommand() const { return lastSound_; }
    unsigned soundEvents() const { return soundEvents_; }
    const std::array<int32_t,3>& attachedEffect() const { return attachedEffect_; }
    //Immediate ACT effects execute during record entry, before sound/motion.
    //The owner binds this to the same scheduled pool and RNG as both actors.
    void setEffectObserver(std::function<void(unsigned,uint32_t,float,float)> observer) { effectObserver_=std::move(observer); }
    void setSoundObserver(std::function<void(int16_t,const ActionClock&)> observer) { soundObserver_=std::move(observer); }
private:
    friend class PlayerObject;
    void enterRecord();
    const ActionClip* action_;
    ActionBank* bank_=nullptr;
    ActionClock clock_;
    MotionState motion_;
    std::array<int32_t,3> attachedEffect_{}; //object10c/110/114; persists across unflagged records
    std::function<void(unsigned,uint32_t,float,float)> effectObserver_;
    uint8_t pendingRecordDamage_=0;
    int16_t lastSound_ = 0;
    unsigned soundEvents_ = 0;
    std::function<void(int16_t,const ActionClock&)> soundObserver_;
};
} // namespace ss6
