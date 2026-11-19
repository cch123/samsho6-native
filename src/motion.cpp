#include "motion.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
void clampRetreat(MotionState& state,uint32_t& flags108) {
    if ((flags108&0x400)&&state.vx<=0) {
        state.dx=state.vx=state.ax=0;flags108&=~uint32_t(0x400);
    }
    if ((flags108&0x800)&&state.vx>=0) {
        state.dx=state.vx=state.ax=0;flags108&=~uint32_t(0x800);
    }
    // The original uses the -0.01f sentinel at 0x5df0f0 here, not ground
    // zero. State callbacks perform their own separate zero-ground clamp.
    if (state.y<0) { state.dy=state.vy=state.ay=0;state.y=-0.01f; }
}
namespace {
int32_t word(uint32_t value) { return std::bit_cast<int32_t>(value); }
int32_t add(int32_t a, int32_t b) { return word(uint32_t(a)+uint32_t(b)); }
int32_t scaled(int32_t value, uint32_t delta) {
    // 0x120660..0x120690 discards the high product BEFORE arithmetic >> 8.
    // Using a 64-bit fixed-point multiply without this wrap changes behavior.
    return word(uint32_t(value)*delta) >> 8;
}
}
void enterMotion(MotionState& s, const MotionCommand& cmd, bool reverse, bool suppressOffset) {
    const auto& v = cmd.values;
    const int32_t direction = reverse ? -1 : 1;
    auto vx = [&] { s.vx = int32_t(v[2])*256*direction; s.vy = int32_t(v[3])*256; };
    auto ax = [&] { s.ax = int32_t(v[4])*16*direction; };
    auto ay = [&] { s.ay = int32_t(v[5])*16; };
    // Jump table 0x5df3d8: 0 retains motion, whereas 1..4 clear it.
    // 16..18 also retain motion here; their separate object flags are not
    // represented by this arithmetic helper.
    switch (cmd.kind) {
    case 0: case 16: case 17: case 18: case 19:
        // ACT163 uses 19 on every record. The EE bounds check at 120fc8
        // sends it directly past the jump table and retains all six values.
        break;
    case 1: case 2: case 3: case 4:
        s.dx=s.vx=s.ax=s.dy=s.vy=s.ay=0; break;
    case 5: case 6: case 7: case 8:
        if (!suppressOffset) { s.dx=int32_t(v[0])*65536; s.dy=int32_t(v[1])*65536; }
        s.vx=s.ax=s.vy=s.ay=0; break;
    case 9: vx(); s.ax=s.ay=0; break;
    case 10: vx(); ax(); s.ay=0; s.vx=add(s.vx,s.ax>>1); break;
    case 11: vx(); ay(); s.ax=0; s.vy=add(s.vy,s.ay>>1); break;
    case 12: vx(); ax(); ay(); s.vx=add(s.vx,s.ax>>1); s.vy=add(s.vy,s.ay>>1); break;
    case 13: ax(); break;
    case 14: ay(); break;
    case 15: ax(); ay(); break;
    default: throw std::runtime_error("Unsupported motion command");
    }
}
void advanceMotion(MotionState& s, uint32_t delta, bool commitPosition, bool mirrorX, bool mirrorY) {
    // Original integration order is displacement first, acceleration second.
    s.dx=add(s.dx,scaled(s.vx,delta)); s.dy=add(s.dy,scaled(s.vy,delta));
    s.vx=add(s.vx,scaled(s.ax,delta)); s.vy=add(s.vy,scaled(s.ay,delta));
    if (commitPosition) {
        // Airborne/fractional-speed paths can round here. Use the same
        // explicit finite FP model as camera/damage instead of host rounding;
        // this remains a compatibility model, not EE hardware certification.
        const auto dx=ScalarFloat::integer(s.dx).mul({0x37800000}); // 2^-16
        const auto dy=ScalarFloat::integer(s.dy).mul({0x37800000});
        const ScalarFloat x{std::bit_cast<uint32_t>(s.x)},y{std::bit_cast<uint32_t>(s.y)};
        s.x=std::bit_cast<float>((mirrorX ? x.sub(dx) : x.add(dx)).bits);
        s.y=std::bit_cast<float>((mirrorY ? y.sub(dy) : y.add(dy)).bits);
        s.dx=s.dy=0;
    }
}
} // namespace ss6
