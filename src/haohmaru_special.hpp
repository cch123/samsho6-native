#pragma once
#include <cstdint>
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
// Table-B rows 0..2 of a whirlwind source (Haohmaru 4e2858, Rasetsumaru
// 4e3570), resolved from victim_rows.bin by the caller.
struct WhirlwindRows {
    unsigned source=0;      // character owning the delivering whirlwind (object +14)
    uint32_t entry=0;       // the source's damage-source stub (4e97a8)
    uint32_t base=0;        // address of row 0 of script k (r[12])
    bool thirdRowFE=false;  // row 2 has type 0x08: 166e98 sets the victim body FE bit 1
};
void updateWhirlwindVictim(PlayerObject&,StateEntryActor&,const ActorCommandInput&,StateEntryContext&,const GroundStateFrame&,const WhirlwindRows&);
}
