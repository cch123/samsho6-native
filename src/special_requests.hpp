#pragma once
#include "input_permissions.hpp"

namespace ss6 {
//These callers enqueue logical states; state entry and buffer consumption
//remain later phases of the original actor dispatcher.
bool requestSpecial(PermissionActor&,const ActorCommandInput&); //14c7d0
bool requestSpecialCancel(PermissionActor&,const ActorCommandInput&,const InputSystemConfig&,const InputBindings&); //14c608
bool requestDamageSpecial(PermissionActor&,const ActorCommandInput&); //14cd78
}
