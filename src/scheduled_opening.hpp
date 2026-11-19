#pragma once
#include "effect_runtime.hpp"
#include "tagged_tasks.hpp"
#include "game_random.hpp"
#include "object_frame.hpp"

namespace ss6 {
class SoundSelection;
//Native texture loading supplies residency; reference counts still belong
//to the original effect lifecycle. Missing residency is an explicit boundary.
struct EffectResidency {
    std::array<uint32_t,32> slots{};
    std::array<uint32_t,44> references{};
};
using EffectPalettes=std::array<std::array<uint32_t,24>,3>;
class ScheduledOpening {
public:
    explicit ScheduledOpening(const std::filesystem::path&,SoundSelection* sound=nullptr);
    void onConcentrationFinished(std::function<void()> callback) { concentrationFinished_=std::move(callback); }
    void onExplosionFinished(std::function<void()> callback) { explosionFinished_=std::move(callback); }
    //1249c8 and its124620 groups, using the caller's actual shared pools.
    uint32_t start(unsigned label,TaggedTaskPools&,EffectResidency&,EffectPalettes&);
    //124548 for round-end descriptors15..19 at the controller's fixed
    //screen anchor. These owners have no completion callback or palette lease.
    uint32_t startEnding(unsigned descriptor,TaggedTaskPools&,EffectResidency&);
    //124430 creates ACT world effects at their source coordinates.
    //These share the round-caption pools and auto-free their owner on finish.
    uint32_t startWorld(unsigned descriptor,uint32_t flags,unsigned resourceSlot,
        float x,float y,float z,float scale,TaggedTaskPools&,EffectResidency&,GameRandom&);
    // 1242c0 uses an unqualified task tag and zero depth for contact groups.
    void startContact(unsigned descriptor,float x,float y,float scale,TaggedTaskPools&,EffectResidency&,GameRandom&);
    //Bind this handler to112838's native dispatch; it does not dispatch or
    //clear other tasks/draws. Births and reclamation remain scheduler-owned.
    void task(uint32_t task,TaggedTaskPools&,EffectResidency&,EffectPalettes&,
              std::vector<EffectDraw>& draws,bool paused);
    //The shared queue is the presentation path for a mixed battle frame.
    //Its511-slot budget never stops effect simulation or owner reclamation.
    void task(uint32_t task,TaggedTaskPools&,EffectResidency&,EffectPalettes&,
              ObjectDrawQueue&,const GaugeState&);
private:
    using DrawEmitter=std::function<void(const AuxiliaryObject&,const EffectDraw&)>;
    void visitTask(uint32_t,TaggedTaskPools&,EffectResidency&,EffectPalettes&,bool,const DrawEmitter&);
    EffectBank bank_;
    SoundSelection* sound_;
    std::function<void()> explosionFinished_,concentrationFinished_;
    std::array<std::array<uint32_t,27>,20> descriptors_{};
    std::array<std::array<uint32_t,27>,13> worldDescriptors_{};
    std::map<unsigned,std::array<uint32_t,27>> contactDescriptors_;
    unsigned palette_=0;
    const std::array<uint32_t,27>& descriptor(unsigned nativeId) const;
    void spawnAt(unsigned descriptor,uint32_t owner,TaggedTaskPools&,EffectResidency&,
        uint32_t flags,float x,float y,float z,float scale,uint32_t tag,GameRandom*);
    void preflight(unsigned descriptor,const TaggedTaskPools&,const EffectResidency&);
    void spawn(unsigned descriptor,uint32_t owner,TaggedTaskPools&,EffectResidency&);
};
}
