#pragma once
#include "tagged_tasks.hpp"
#include "game_random.hpp"
#include "action_runtime.hpp"
#include "scalar_float.hpp"
#include "object_frame.hpp"

namespace ss6 {
//Source object words are kept for allocator/state interoperability. Pointer
//fields contain native handles, except bc which is an ACT byte offset+1 in
//the resource selected by c. No PS2 address is dereferenced at runtime.
class AuxiliaryObjects {
public:
    AuxiliaryObjects(const std::filesystem::path& assets,std::array<unsigned,3> resourceSlots);
    // 168ea0 indexes nine signed coordinate pairs per fighter; the first
    // anchors elemental damage to the victim's body.
    std::array<int16_t,2> bodyAnchor(unsigned character) const {return anchor(character,0);}
    std::array<int16_t,2> anchor(unsigned character,unsigned index) const { //168ea0(character, index)
        const auto& row=positions_.at(character);
        return {row.at(2*index),row.at(2*index+1)};
    }
    void initialize(AuxiliaryObject&,const AuxiliaryObject& parent,unsigned kind); //11d9c8, kinds2/4/6
    uint32_t create(TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,uint32_t actorFlags,
                    const AuxiliaryObject& parent,uint32_t tag,unsigned kind,uint32_t handler); //140c68
    ActionRecord record(const AuxiliaryObject&,unsigned* actionLength=nullptr);
    static void stop(AuxiliaryObject&); // 11d990
    static void applyAttachmentOffset(AuxiliaryObject&,const AuxiliaryObject& parent); // 16dd44
    uint32_t spawnWhirlwind(TaggedTaskPools&,std::span<uint32_t>,unsigned player,uint32_t actorFlags,
                            const AuxiliaryObject& parent,unsigned strength); // 16d9c8, descriptor 0
    void updateWhirlwind(TaggedTaskPools&,uint32_t task); // 16def0, descriptor 0
    uint32_t spawnRisingSlashTrail(TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                                  uint32_t flags,const AuxiliaryObject& parent,unsigned state);
    uint32_t spawnActAttachment(TaggedTaskPools&,std::span<uint32_t> ownerRegistry,std::span<uint32_t> commonRegistry,
                            unsigned player,uint32_t flags,const AuxiliaryObject& body,const AuxiliaryObject& emitter,
                            unsigned action,bool sharedBank);
    uint32_t spawnSlashEffect(TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                             uint32_t flags,const AuxiliaryObject& parent,unsigned action);
    void spawnMikiri(TaggedTaskPools&,std::span<uint32_t>,unsigned player,uint32_t flags,
                     const AuxiliaryObject& parent,unsigned action);
    void reflectProjectile(AuxiliaryObject&,unsigned newTeam);
    static void pauseWhirlwind(AuxiliaryObject&,int first,int second); // 15169c/11db00
    //140a78, kind7: the battle's64-slot registry and resident common slot2.
    //Only facing is inherited; actor-specific position/motion is not copied.
    uint32_t createCommonEffect(TaggedTaskPools&,std::span<uint32_t> registry,
                    const AuxiliaryObject* parent,uint32_t tag,uint32_t handler);
    uint32_t createCommonObject(TaggedTaskPools&,std::span<uint32_t> registry,
                    const AuxiliaryObject* parent,uint32_t tag,unsigned kind,uint32_t handler);
    uint32_t drop(TaggedTaskPools&,std::span<uint32_t> registry,GameRandom&,unsigned player,
                  unsigned character,uint32_t& actorFlags,const AuxiliaryObject& parent); //170440
    // 16fe20 places a stationary kind-4 weapon at the owner's discard offset.
    uint32_t placeWeapon(TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,
                         unsigned character,uint32_t& actorFlags,const AuxiliaryObject& parent);
    //16ffb0 uses the lock-loss position pair (kind3), distinct from170440.
    uint32_t dropAfterLock(TaggedTaskPools&,std::span<uint32_t> registry,GameRandom&,unsigned player,
                  unsigned character,uint32_t& actorFlags,const AuxiliaryObject& parent);
    uint32_t dropWithOffset(TaggedTaskPools&,std::span<uint32_t>,GameRandom&,unsigned player,
                  unsigned character,uint32_t& actorFlags,const AuxiliaryObject&,int32_t x,int32_t y); //170070
    uint32_t dropSpecial(TaggedTaskPools&,std::span<uint32_t>,GameRandom&,unsigned player,
                  unsigned character,uint32_t& actorFlags,const AuxiliaryObject&); //170240
    uint32_t deliverWeapon(TaggedTaskPools&,std::span<uint32_t> registry,unsigned player,unsigned character,
                           uint32_t actorFlags,const AuxiliaryObject& parent,float refereeX); // 170480
    void landWeapon(TaggedTaskPools&,uint32_t task); //1701c0
    bool shatterWeapon(TaggedTaskPools&,std::span<uint32_t> registry,uint32_t task,unsigned player,
                       uint32_t actorFlags,const AuxiliaryObject& parent); //170340
    static void releaseHold(TaggedTaskPools&,uint32_t task); //147540
    void request(AuxiliaryObject&,unsigned action,bool immediate,bool force); //11d908, kinds2/4/6/7
    void commitRequested(AuxiliaryObject&); //11d958, same admitted action paths
    //The sink performs the original sound selection/channel dispatch. It is
    //required for audible ACT commands even when the output device is silent.
    void setSoundObserver(std::function<int32_t(int16_t,const AuxiliaryObject&)> sink) { sound_=std::move(sink); }
    using WorldEffectObserver=std::function<void(unsigned,uint32_t,unsigned,float,float)>;
    void setEffectObserver(WorldEffectObserver sink){effect_=std::move(sink);}
    void animate(AuxiliaryObject&,const GaugeState&,uint32_t& jumpFlags); //11d730
    static void move(AuxiliaryObject&,const GaugeState&); //11d6c8, auxiliary kinds
    void updateRegistry(TaggedTaskPools&,std::span<const uint32_t>,const AuxiliaryFrame&); //147028
    static void visitRegistry(TaggedTaskPools&,std::span<uint32_t>,const std::function<void(uint32_t)>&); //146ef8
    void drawRegistry(TaggedTaskPools&,std::span<const uint32_t>,const AuxiliaryFrame&,ObjectDrawQueue&); //1470a8
private:
    std::function<int32_t(int16_t,const AuxiliaryObject&)> sound_;
    WorldEffectObserver effect_;
    struct Resource {std::vector<uint8_t> aid,act;};
    std::filesystem::path assets_;
    std::array<unsigned,3> slots_;
    std::map<unsigned,Resource> resources_;
    std::array<std::array<int16_t,18>,51> positions_{};
    std::array<ScalarFloat,4> constants_;
    void initializeBase(AuxiliaryObject&,unsigned slot,unsigned kind);
    void enter(AuxiliaryObject&);
    void judgment(AuxiliaryObject&);
    static void publishJudgment(AuxiliaryObject&);
    static void requireDropCapacity(const TaggedTaskPools&,std::span<const uint32_t>);
};
}
