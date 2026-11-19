#pragma once
namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;
struct StateEntryContext;

// Armed resource 00 special scripts. The caller owns the ordinary 149d08
// attack prefix and tail. True requests its shared 169810 recovery.
bool haohmaruSpecialSupports(int attackState);
bool updateHaohmaruSpecial(PlayerObject&, StateEntryActor&, const ActorCommandInput&, const GroundStateFrame&);
void updateWhirlwindVictim(PlayerObject&,StateEntryActor&,const ActorCommandInput&,StateEntryContext&,const GroundStateFrame&);
}
