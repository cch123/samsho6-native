#pragma once
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
} // namespace ss6
