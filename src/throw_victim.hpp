#pragma once

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ContactMarks;

// Resource 00, ordinary raw-32 grab after the route-4 consumption gate.
void catchGroundThrow(PlayerObject& thrower,StateEntryActor& source,ContactMarks& sourceMarks,
                      PlayerObject& victim,StateEntryActor& target,ContactMarks& targetMarks);
void breakGroundThrows(StateEntryActor& first,StateEntryActor& second);
void beginThrowVictim(PlayerObject& victim,StateEntryActor& target,const PlayerObject& thrower);
void updateThrowVictim(PlayerObject& victim,StateEntryActor& target,PlayerObject& thrower);
}
