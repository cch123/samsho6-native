#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
struct MotionState {
    // Original object +0x4c..0x60. Values wrap as EE 32-bit words; position
    // offsets use 16 fractional bits, even though ACT velocities shift by 8.
    int32_t dx = 0, vx = 0, ax = 0, dy = 0, vy = 0, ay = 0;
    float x = 0, y = 0;
};
struct MotionCommand {
    int16_t kind = 0;
    std::array<int16_t, 6> values{}; // ACT +0x22..0x2c: dx,dy,vx,vy,ax,ay.
};
void enterMotion(MotionState& state, const MotionCommand& command,
                 bool reverseVelocity = false, bool suppressOffset = false);
void advanceMotion(MotionState& state, uint32_t delta, bool commitPosition = true,
                   bool mirrorX = false, bool mirrorY = false);
// 0x11deb0 runs before movement integration, including frozen updates. It
// prevents retreat acceleration from carrying an actor back toward the hit.
void clampRetreat(MotionState& state,uint32_t& flags108);
} // namespace ss6
