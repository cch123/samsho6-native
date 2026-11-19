#pragma once

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;

// The two armed dagger motions share the Japanese 163610 phase interpreter.
// A true result requests its normal recovery after the final phase.
bool updateNakoruruStrike(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&);
}
