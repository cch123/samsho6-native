#pragma once
#include <cstdint>
#include <span>
#include "auxiliary_objects.hpp"
#include "stage_camera.hpp"
#include "tagged_tasks.hpp"

namespace ss6 {
struct StateEntryActor;
// Character 33's kind-3 karuta: 2038a0 (1a3220 at 1a330c), task 203920 with the
// mode entry 2039a8 and the per-mode update 203b20.
uint32_t spawnKaruta(AuxiliaryObjects&,TaggedTaskPools&,std::span<uint32_t> registry,
                     unsigned player,uint32_t flags,const AuxiliaryObject& body);
void updateKaruta(AuxiliaryObjects&,AuxiliaryObject&,const AuxiliaryObject& ownerBody,
                  StateEntryActor& owner,const StageCamera&);
}
