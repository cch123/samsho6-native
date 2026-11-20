#pragma once
#include <bit>
#include <cstdint>

namespace ss6 {
// Finite scalar compatibility model for the damage port. Each operation
// rounds separately; host floating-point modes and fused operations cannot
// change the result. This is NOT a claim of a complete EE FPU implementation:
// hardware MUL can lose one additional mantissa bit. See damage-model.txt.
struct ScalarFloat {
    uint32_t bits;
    static ScalarFloat integer(int32_t value);
    int32_t truncate() const;
    bool less(ScalarFloat other) const;
    ScalarFloat add(ScalarFloat other) const;
    ScalarFloat sub(ScalarFloat other) const;
    ScalarFloat mul(ScalarFloat other) const;
    ScalarFloat div(ScalarFloat other) const;
    ScalarFloat sqrt() const;
};
// EE add.s / sub.s on host floats (rounding toward zero, ScalarFloat model).
inline float eeAdd(float a,float b){return std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(a)}.add(ScalarFloat{std::bit_cast<uint32_t>(b)}).bits);}
inline float eeSub(float a,float b){return std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(a)}.sub(ScalarFloat{std::bit_cast<uint32_t>(b)}).bits);}
} // namespace ss6
