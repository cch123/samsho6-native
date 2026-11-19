#include "ordinary_rules.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <fstream>
#include <stdexcept>
namespace ss6 {
OrdinaryRules::OrdinaryRules(const std::filesystem::path& assets) {
    std::ifstream in(assets/"ordinary_00.bin",std::ios::binary);
    std::array<uint8_t,18> data{};
    if (!in.read(reinterpret_cast<char*>(data.data()),data.size())||in.peek()!=EOF)
        throw std::runtime_error("Expected 18-byte ordinary_00.bin");
    std::ifstream movement(assets/"selection_character_flags.bin",std::ios::binary);
    if(!movement.read(reinterpret_cast<char*>(movementFlags_.data()),movementFlags_.size())||movement.peek()!=EOF)
        throw std::runtime_error("Invalid original fighter movement flag table");
    std::ifstream ranges(assets/"permission_target_ranges.bin",std::ios::binary);
    for(auto& character:ranges_)for(auto& value:character) {
        std::array<uint8_t,2> bytes{};
        if(!ranges.read(reinterpret_cast<char*>(bytes.data()),2))throw std::runtime_error("Truncated near/far ranges");
        value=std::bit_cast<int16_t>(uint16_t(bytes[0]|(bytes[1]<<8)));
    }
    if(ranges.peek()!=EOF)throw std::runtime_error("Unexpected near/far range table");
    flags_={data[8],data[13]};
    std::ifstream attacks(assets/"entry_attack.bin",std::ios::binary);
    for(unsigned variant:{0u,2u}) {
        //Resource00's standing heavy is attack state8. Preserve its actual
        //descriptor flags: these also select sword cost and clash strength.
        attacks.seekg((variant*64+8)*5);char value;
        if(!attacks.get(value))throw std::runtime_error("Missing standing-heavy descriptor");
        heavyFlags_[variant/2]=uint8_t(value);
    }
}
bool OrdinaryRules::far(int32_t distance,bool armed,bool targetArmed,unsigned source,unsigned target) const {
    // 0x168c58 uses signed halfwords and an inclusive comparison. Equality
    // selects far; using sprite bounds or <= would change the chosen attack.
    return distance>=int(ranges_.at(source)[armed ? 0 : 1])+int(ranges_.at(target)[targetArmed ? 2 : 3]);
}
int32_t playerDistance(float x,float otherX) {
    if (!std::isfinite(x)||!std::isfinite(otherX)||std::abs(x)>1000000||std::abs(otherX)>1000000)
        throw std::runtime_error("Position outside ordinary distance subset");
    // 0x1428f4 converts the signed difference first, then takes integer abs.
    // Admitted ground positions are exact binary fractions.
    return std::abs(int32_t(x-otherX));
}
unsigned standingIdleAction(int32_t life,int32_t rageState,bool armed,
                            int32_t remainingSeconds,bool training,int32_t trainingRage) {
    //The same alternate pair is selected by rage, practice settings,
    //time pressure, or low life. Infinite time is a sentinel, not <31.
    const bool alternate= rageState==1 || rageState==2 ||
        (training&&(trainingRage==1||trainingRage==2)) ||
        (remainingSeconds!=-1&&remainingSeconds<31) || life<49;
    return (alternate?2u:0u)+(armed?0u:1u);
}
ClashRequest queueWeaponClash(uint32_t flags,int table,int state,unsigned strength,bool weaponClash) {
    if (strength>2) throw std::runtime_error("Invalid clash strength");
    // 0x14d070 preserves posture when choosing normal-table recoil. The
    // attack-table state39 exception has its own flag and action callback.
    flags=(flags&~uint32_t(0x60000))|((table==1&&state==39) ? 0x40000 : 0)|
          (weaponClash ? 0x20000 : 0);
    return {flags,0,int16_t(strength+((flags&8) ? 28 : 25))};
}
void ordinaryPush(PushActor& a,PushActor& b,int32_t width) {
    if (width<0) throw std::runtime_error("Negative intersection width");
    const float amount=std::min(float(width)*0.25f,6.0f);
    if (amount==0) return;
    // 0x154bd0 resolves coincident X using height, then the fixed screen
    // midpoint. Player index is deliberately not a tie-breaker.
    bool left=a.x<b.x;
    if (a.x==b.x) { left=a.y>b.y;if (a.x>=320) left=!left; }
    a.x+=left ? -amount : amount;b.x+=left ? amount : -amount;
    a.flags248|=0x40;b.flags248|=0x40;
}
} // namespace ss6
