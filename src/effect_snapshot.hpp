#pragma once
#include "effect_runtime.hpp"
#include "object_frame.hpp"

namespace ss6 {
EffectState readEffectState(std::span<const uint32_t> object);
void writeEffectState(AuxiliaryObject& object,const EffectState& state);
//Decode the queued snapshot, never its recycled live-pool handle. The final
//draw can outlive the task/object that emitted it during the same visit.
EffectDraw decodeEffectDraw(const ObjectDrawQueue::Record&,EffectBank&);
}
