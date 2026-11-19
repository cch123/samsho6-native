#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
namespace ss6 {
// 168bf8 movement flags and 168c58 distance rules are indexed by fighter ID.
class OrdinaryRules {
public:
    explicit OrdinaryRules(const std::filesystem::path& assets);
    bool far(int32_t distance,bool sourceArmed,bool targetArmed,unsigned source=0,unsigned target=0) const;
    uint8_t movementFlags(unsigned character) const {return movementFlags_.at(character);}
    uint8_t lightStateFlags(bool far) const { return flags_[far ? 1 : 0]; }
    uint8_t heavyStateFlags(bool far) const { return heavyFlags_[far ? 1 : 0]; }
private:
    std::array<uint8_t,51> movementFlags_{};
    std::array<std::array<int16_t,4>,51> ranges_{};
    std::array<uint8_t,2> flags_{};
    std::array<uint8_t,2> heavyFlags_{};
};
int32_t playerDistance(float x,float otherX);
//169d10 normal0 entry. remainingSeconds is1407d0's result (-1=infinite).
//Training settings are resolved by the caller; this does not enable a mode.
unsigned standingIdleAction(int32_t life,int32_t rageState,bool armed,
                            int32_t remainingSeconds=-1,bool training=false,int32_t trainingRage=0);
struct ClashRequest { uint32_t flags23c;int16_t table,state; };
ClashRequest queueWeaponClash(uint32_t flags23c,int table,int state,unsigned strength,bool weaponClash);
struct PushActor { float x,y;uint32_t flags248; };
void ordinaryPush(PushActor& a,PushActor& b,int32_t width);
} // namespace ss6
