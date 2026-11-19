#pragma once
#include "scalar_float.hpp"
#include "stage_camera.hpp"
#include <array>
#include <filesystem>
#include <map>
#include <optional>
#include <vector>

namespace ss6 {
// Effects use their own 60-byte records, not character ACT/PIL records.
struct EffectRecord {
    std::array<uint16_t,30> fields{};
    uint16_t word(unsigned byte) const { return fields.at(byte/2); }
    int16_t signedWord(unsigned byte) const { return int16_t(word(byte)); }
    uint32_t color() const { return word(0x28)|(uint32_t(word(0x2a))<<16); }
};
class EffectBank {
public:
    explicit EffectBank(std::filesystem::path assets):assets_(std::move(assets)) {}
    const std::vector<EffectRecord>& action(unsigned bank,unsigned action);
private:
    std::filesystem::path assets_;
    std::map<std::pair<unsigned,unsigned>,std::vector<EffectRecord>> clips_;
};
struct EffectState {
    uint32_t step=0,time=0,speed=256,flags=0;
    float x=0,y=0,z=0,baseScale=1;
    std::array<uint32_t,6> motion{}; // +4c..60: offset, velocity, acceleration per axis
    ScalarFloat scale{0x3f800000},scaleVelocity{0},scaleAcceleration{0};
    uint32_t color=0xffffffff;
    std::array<int32_t,8> colorMotion{}; // +90..ac; stored accelerations are not integrated
};
struct EffectDraw {
    EffectRecord record;
    EffectState state;
};
struct EffectQuad {
    float left,top,right,bottom;
    int u,v,textureWidth,textureHeight;
    unsigned asset,palette;
    bool mirrorX,mirrorY;
    // Original triangle-strip order: top-left,bottom-left,top-right,
    // bottom-right before rotation. Bounds alone lose the fan's UV axes.
    std::array<std::array<float,2>,4> vertices;
    bool rotated=false;
};
EffectQuad projectEffect(const EffectDraw& draw,const StageCamera& camera);
class EffectInstance {
public:
    EffectInstance(const std::vector<EffectRecord>& clip,uint32_t flags=0,
                   float x=0,float y=0,float z=0,float scale=1);
    bool alive() const { return state.step<clip_->size(); }
    // 1235f8 queues a copy BEFORE advancing the clock. The last draw must
    // survive even when 124898 releases the owning task in this update.
    std::optional<EffectDraw> update(bool effectsPaused=false);
    void enterRecord();
    void integrate();
    void advanceClock();
    EffectState state;
private:
    const std::vector<EffectRecord>* clip_;
};
class EffectGroup {
public:
    bool alive() const;
    void update(std::vector<EffectDraw>& draws,bool effectsPaused=false);
    std::vector<EffectInstance> instances;
};
//1249c8/124b48/124bf0 share one owner across multiple effect groups.
// Only descriptor13's124cc0 callback releases that owner's active bit.
class RoundIntro {
public:
    explicit RoundIntro(EffectBank& bank):bank_(bank) {}
    void start(unsigned label);
    void reset();
    void update(std::vector<EffectDraw>& draws,bool effectsPaused=false);
    bool active() const { return active_; }
    std::vector<unsigned> descriptors() const;
private:
    struct Task { unsigned descriptor;EffectGroup group; };
    EffectBank& bank_;
    unsigned label_=0;
    bool active_=false;
    std::vector<Task> tasks_;
    void spawn(unsigned descriptor);
};
// The admitted KO descriptors have neither random actions nor end callbacks.
// Groups own instances while presentation owns independent queued snapshots.
class BattleEffects {
public:
    explicit BattleEffects(const std::filesystem::path& assets):bank_(assets),intro_(bank_) {}
    void reset();
    void update(bool effectsPaused=false);
    void landing(float x,bool mirror);
    void knockout(bool draw,bool final=false);
    void opening(unsigned label) { intro_.start(label); }
    bool openingActive() const { return intro_.active(); }
    bool knockoutActive() const { return knockout_.alive(); }
    const std::vector<EffectDraw>& draws() const { return draws_; }
private:
    EffectBank bank_;
    RoundIntro intro_;
    EffectGroup knockout_;
    std::vector<EffectGroup> world_;
    std::vector<EffectDraw> draws_;
};
} // namespace ss6
