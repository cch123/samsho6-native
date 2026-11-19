#include "effect_snapshot.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t bits(float v){return std::bit_cast<uint32_t>(v);}
float floating(uint32_t v){return std::bit_cast<float>(v);}
}
EffectState readEffectState(std::span<const uint32_t> o) {
    if(o.size()<78)throw std::runtime_error("Truncated effect object snapshot");
    EffectState s;
    s.step=o[0x28/4];s.time=o[0x2c/4];s.speed=o[0x30/4];s.flags=o[0x38/4];
    s.x=floating(o[0x40/4]);s.y=floating(o[0x44/4]);s.z=floating(o[0x48/4]);s.baseScale=floating(o[0x70/4]);
    std::copy_n(o.begin()+0x4c/4,6,s.motion.begin());
    s.scale={o[0x74/4]};s.scaleVelocity={o[0x78/4]};s.scaleAcceleration={o[0x7c/4]};s.color=o[0x8c/4];
    for(unsigned i=0;i<8;++i)s.colorMotion[i]=std::bit_cast<int32_t>(o[0x90/4+i]);
    return s;
}
void writeEffectState(AuxiliaryObject& o,const EffectState& s) {
    o[0x28/4]=s.step;o[0x2c/4]=s.time;o[0x30/4]=s.speed;o[0x38/4]=s.flags;
    o[0x40/4]=bits(s.x);o[0x44/4]=bits(s.y);o[0x48/4]=bits(s.z);o[0x70/4]=bits(s.baseScale);
    std::copy(s.motion.begin(),s.motion.end(),o.begin()+0x4c/4);
    o[0x74/4]=s.scale.bits;o[0x78/4]=s.scaleVelocity.bits;o[0x7c/4]=s.scaleAcceleration.bits;o[0x8c/4]=s.color;
    for(unsigned i=0;i<8;++i)o[0x90/4+i]=uint32_t(s.colorMotion[i]);
}
EffectDraw decodeEffectDraw(const ObjectDrawQueue::Record& row,EffectBank& bank) {
    if(row[0x144/4]!=1)throw std::runtime_error("Effect decoder requires a kind1 draw");
    const auto& clip=bank.action(row[0x14/4],row[0x24/4]);
    return {clip.at(row[0x28/4]),readEffectState(row)};
}
}
