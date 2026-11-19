#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
struct Parts { bool negative; int exponent; uint32_t significand; };
Parts unpack(ScalarFloat f) {
    unsigned exponent=(f.bits>>23)&255;
    if (exponent==255 || (!exponent && (f.bits&0x7fffff)))
        throw std::runtime_error("Exceptional float outside finite damage model");
    return {bool(f.bits>>31),int(exponent)-127,exponent ? (f.bits&0x7fffff)|0x800000 : 0};
}
ScalarFloat pack(bool negative,uint64_t significand,int scale) {
    if (!significand) return {uint32_t(negative)<<31};
    int top=63-std::countl_zero(significand), exponent=top+scale;
    if (exponent < -126 || exponent > 127)
        throw std::runtime_error("Float range outside finite damage model");
    // Removing low bits explicitly implements rounding toward zero.
    uint64_t fraction=top>23 ? significand>>(top-23) : significand<<(23-top);
    return {(uint32_t(negative)<<31)|(uint32_t(exponent+127)<<23)|(uint32_t(fraction)&0x7fffff)};
}
}
ScalarFloat ScalarFloat::integer(int32_t value) {
    int64_t wide=value;
    return pack(wide<0,uint64_t(wide<0 ? -wide : wide),0);
}
int32_t ScalarFloat::truncate() const {
    auto p=unpack(*this);
    if (!p.significand || p.exponent<0) return 0;
    if (p.exponent>31) throw std::runtime_error("Float integer conversion overflow");
    uint64_t magnitude=p.exponent>=23 ? uint64_t(p.significand)<<(p.exponent-23) : p.significand>>(23-p.exponent);
    if (magnitude>uint64_t(INT32_MAX)+p.negative) throw std::runtime_error("Float integer conversion overflow");
    return int32_t(p.negative ? -int64_t(magnitude) : int64_t(magnitude));
}
bool ScalarFloat::less(ScalarFloat other) const {
    unpack(*this); unpack(other);
    uint32_t a=bits&0x7fffffff,b=other.bits&0x7fffffff;
    if (!a&&!b) return false;
    if ((bits^other.bits)&0x80000000) return bool(bits>>31);
    return bits>>31 ? a>b : a<b;
}
ScalarFloat ScalarFloat::add(ScalarFloat other) const {
    auto a=unpack(*this),b=unpack(other);
    if (!a.significand) return b.significand ? other : ScalarFloat{bits&other.bits};
    if (!b.significand) return *this;
    int exponent=a.exponent>b.exponent ? a.exponent : b.exponent;
    // Preserve one alignment guard bit, discarding all lower bits before
    // subtraction. IEEE subtraction alone would retain extra precision.
    auto align=[exponent](Parts p)->int64_t {
        int shift=exponent-p.exponent;
        int64_t n=shift>=25 ? 0 : (uint64_t(p.significand)<<1)>>shift;
        return p.negative ? -n : n;
    };
    int64_t sum=align(a)+align(b);
    return pack(sum<0,uint64_t(sum<0 ? -sum : sum),exponent-24);
}
ScalarFloat ScalarFloat::sub(ScalarFloat other) const { return add({other.bits^0x80000000}); }
ScalarFloat ScalarFloat::mul(ScalarFloat other) const {
    auto a=unpack(*this),b=unpack(other);
    return pack(a.negative!=b.negative,uint64_t(a.significand)*b.significand,a.exponent+b.exponent-46);
}
ScalarFloat ScalarFloat::div(ScalarFloat other) const {
    auto a=unpack(*this),b=unpack(other);
    if (!b.significand) throw std::runtime_error("Division by zero outside finite damage model");
    if (!a.significand) return {uint32_t(a.negative!=b.negative)<<31};
    int extra=a.significand<b.significand ? 1 : 0;
    uint64_t numerator=uint64_t(a.significand)<<(23+extra);
    return pack(a.negative!=b.negative,numerator/b.significand,a.exponent-b.exponent-23-extra);
}
ScalarFloat ScalarFloat::sqrt() const {
    const auto p=unpack(*this);
    if(!p.significand)return *this;
    if(p.negative)throw std::runtime_error("Negative square root outside finite model");
    //Scale to a 24-bit root and discard the remainder explicitly. Host sqrt
    //rounding must not decide a strict auxiliary-distance permission boundary.
    const int exponent=p.exponent>=0?p.exponent/2:(p.exponent-1)/2;
    uint64_t remainder=uint64_t(p.significand)<<(23+p.exponent-2*exponent);
    uint64_t root=0;
    for(uint64_t bit=uint64_t(1)<<46;bit;bit>>=2) {
        if(remainder>=root+bit){remainder-=root+bit;root=(root>>1)+bit;}
        else root>>=1;
    }
    return pack(false,root,exponent-23);
}
} // namespace ss6
