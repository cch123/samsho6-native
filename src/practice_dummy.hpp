#pragma once
#include "cpu_tactics.hpp"
#include "state_entry.hpp"
#include "game_random.hpp"

namespace ss6 {
// The practice branch of the CPU visit 158990: behaviour code refresh
// (15aa18/15a0e0), posture frame (15ab30), air recovery by CPU UKEMI TYPE
// (1594c8) and the common tail 158fa0. AI+0x80/+0x84 are actor control88/8c,
// AI+0xc0 is controlModeC8, AI+0xac is controlFlagsB4.
struct PracticeDummyFrame {
    int code=0;              // 139c88()
    int ukemi=0;             // 139ce8()
    bool threat=false;       // 151478(actor)
    bool opponentKind2=false;// 140d78(opponent seat, 0, 2): an opposing kind-2 object exists
    unsigned system=0;       // spirit system id (14fd20 admits system 8 for the delayed recovery)
};
// 15a0e0: a changed code resets the controller (1588c0, one 112300(2) draw)
// and every code other than 0x23 raises the AI level word to 0x31.
void practiceSetBehaviour(StateEntryActor&,int code,int& level,GameRandom&);
// 15aa18: refreshes the code and the COUNTER bit actor+0x240:1. Returns true
// for the posture codes 0..3, 11..14, 20, 25, 30 and for REPLAY (0x25) while
// the replay bit actor+0x240:4 is clear.
bool practiceRefreshBehaviour(StateEntryActor&,int code,int& level,GameRandom&);
// 15ab30: one posture frame. 1588c0 runs first on every visit.
void practicePosture(StateEntryActor&,const StateEntryActor& opponent,const PracticeDummyFrame&,
                     const CpuTactics&,GameRandom&);
// 1594c8. Returns true when a recovery command was issued.
bool practiceAirRecovery(StateEntryActor&,const PracticeDummyFrame&,int level,GameRandom&);
// 158990 from 15aa18 onward, for a posture code: true when the visit was
// consumed (the caller then publishes control88/8c); false = ordinary CPU.
bool practiceDummyVisit(StateEntryActor&,const StateEntryActor& opponent,const PracticeDummyFrame&,int& level,
                        const CpuTactics&,GameRandom&);
// Codes whose AI sites (15a150 sequence replacement and the attack-code
// branches of 1618d0, 162828, 1624a4) are not ported are served by the
// posture code of the same stance: 4..10 -> 0, 15..19 -> 11, 21..24 -> 20,
// 26..29 -> 25, 31..34 -> 30, ACTION (0x26..0x45) -> 0.
int practiceSupportedBehaviour(int code);
}
