#include "soft_double.hpp"
#include <cfenv>

#pragma STDC FENV_ACCESS ON
namespace ss6 {
namespace {
template<class Op> double towardZero(Op op) {
    const int mode=std::fegetround();
    std::fesetround(FE_TOWARDZERO);
    const double r=op();
    std::fesetround(mode);
    return r;
}
}
double softMul(double a,double b) {
    volatile double x=a,y=b;
    return towardZero([&]{volatile double r=x*y;return double(r);});
}
double softAdd(double a,double b) {
    volatile double x=a,y=b;
    return towardZero([&]{volatile double r=x+y;return double(r);});
}
int32_t softBlend(float fresh,int32_t old,double kFresh,double kOld) {
    return int32_t(softAdd(softMul(double(fresh),kFresh),softMul(double(old),kOld)));
}
}
