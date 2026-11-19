#pragma once
#include "auxiliary_objects.hpp"
#include <bit>

namespace ss6 {
struct CompanionSteering {
    ScalarFloat gain,maximum,arrivalRadius,turnDistance;
};

// 1a39b8 stores velocity in the companion's local facing, even when its
// owner crosses behind it inside the turn dead zone. The two multiplications
// must round independently to preserve the tick on which it reaches its target.
inline bool steerCompanion(AuxiliaryObject& object,ScalarFloat targetX,
                           ScalarFloat dx,ScalarFloat dy,ScalarFloat length,CompanionSteering settings) {
    constexpr uint32_t mirror=0x80000;
    const bool left=targetX.less({object[0x40/4]});
    dx.bits&=0x7fffffff;
    if(settings.turnDistance.less(dx))
        object[0x38/4]=(object[0x38/4]&~mirror)|(left?mirror:0);
    if(!settings.arrivalRadius.less(length)) {
        AuxiliaryObjects::stop(object);
        return true;
    }
    const ScalarFloat one=ScalarFloat::integer(1);
    const auto scale=length.less(settings.maximum.mul(settings.gain))?one.div(settings.gain):
                     length.less(settings.maximum)?settings.maximum.div(length):one;
    const auto fixed=settings.gain.mul(ScalarFloat::integer(65536));
    dx=dx.mul(scale).mul(fixed);
    dy=dy.mul(scale).mul(fixed);
    if(left!=bool(object[0x38/4]&mirror))dx.bits^=0x80000000;
    const ScalarFloat retain{0x3e4ccccd}; // 0.2 in both companion parameter records.
    auto blend=[&](uint32_t oldValue,ScalarFloat desired) {
        auto old=ScalarFloat::integer(std::bit_cast<int32_t>(oldValue));
        return uint32_t(desired.mul(one.sub(retain)).add(old.mul(retain)).truncate());
    };
    object[0x50/4]=blend(object[0x50/4],dx);
    object[0x5c/4]=blend(object[0x5c/4],dy);
    return false;
}
}

