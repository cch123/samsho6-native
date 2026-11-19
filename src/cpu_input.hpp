#pragma once
#include "command_input.hpp"

namespace ss6 {
// The decision routine selects a logical command directly. CPU directions
// already refer to the actor's facing and do not pass through pad recognition.
struct CpuCommand {
    uint32_t mask=0;
    int slot=-1; // Normal commands 0..30, special commands 31..62.
};

void publishCpuCommand(const CpuCommand&,bool facingLeft,ActorCommandInput&);
}
