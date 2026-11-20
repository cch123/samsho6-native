#pragma once
#include <cstdint>

namespace ss6 {
// The EE's libgcc fp-bit double routines (310fa0 muldf3, 310ee0 adddf3)
// return the exact result truncated toward zero to 53 bits, not the IEEE
// round-to-nearest one; 310be0/311390 widen exactly and 311440 truncates.
double softMul(double a,double b);
double softAdd(double a,double b);
// (int)((double)fresh*kFresh + (double)old*kOld) through those routines,
// the velocity blend of the homing objects (1fc420, 16f088, 16f510).
int32_t softBlend(float fresh,int32_t old,double kFresh,double kOld);
}
