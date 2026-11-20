#include "pakupaku_orbit.hpp"
#include "scalar_float.hpp"
#include <bit>

namespace ss6 {
void updatePakuOrbit(AuxiliaryObjects& objects,AuxiliaryObject& o,uint32_t& callback,const ActorHistory& history,const AngleTrig& trig) {
    // 16ee10: the start ACT ended with nothing pending -> queue 0x24f (not forced), callback 16ee80.
    if(callback==0x16ee10&&o[0xc0/4]&&!(o[0x104/4]&1)){objects.request(o,0x24f,false,false);callback=0x16ee80;}
    using F=ScalarFloat;
    const auto word=[&](unsigned off){return std::bit_cast<int32_t>(o[off/4]);};
    const int32_t d=word(0x30),k=word(0x128);
    // 16ee98 (int32 wrap, C truncating division and remainder): the angle turns one degree per
    // 256 clock units, the four slots 90 degrees apart; the radius bounces with half that period.
    const int32_t r=std::bit_cast<int32_t>(o[0x12c/4]+uint32_t(d))%0x16800;o[0x12c/4]=uint32_t(r);
    const int32_t deg=std::bit_cast<int32_t>(uint32_t(r/256)+uint32_t(k)*90u)%360;
    const int32_t r2=std::bit_cast<int32_t>(o[0x130/4]+uint32_t(d))%0xb400;o[0x130/4]=uint32_t(r2);
    const int32_t b=r2/256,amplitude=b<90?b:180-b;
    const int32_t ry=amplitude/9+12,rx=amplitude/3+40;
    const auto angle=uint32_t(F::integer(deg).mul(F{0x43360b60u}).truncate()); // 182.04443f, cvt.w.s
    const auto& sample=history.samples.at(size_t(k+1)); // owner + a80 / a84 + 20 * o.128 (no bound check)
    o[0x40/4]=F{std::bit_cast<uint32_t>(sample.x)}.add(F::integer(rx).mul(F{trig.cosine(angle)})).bits;
    o[0x44/4]=F{std::bit_cast<uint32_t>(sample.y)}.add(F{0x41c00000u}).add(F::integer(ry).mul(F{trig.sine(angle)})).bits;
    o[0xb0/4]=deg<180?0x42200000u:0x41a00000u;o[0x104/4]|=0x20000; //11dff8: depth 40 / 20
}
}
