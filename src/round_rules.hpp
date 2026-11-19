#pragma once
#include <cstdint>
#include <array>

namespace ss6 {
// Resource00 ordinary actor subset of 0x151b00. The range bit is supplied by
// the existing original-table range helper; special actor swaps are excluded.
uint32_t ordinaryStateGates(uint32_t flags244,uint32_t flags23c,int table,int state,
                            uint8_t descriptor,uint32_t flags108,int32_t timer5,bool far);
// Actor-dispatch order: optional 0x149980, then unconditional 0x14b880.
// Returns a damage-table state, or -1. The caller owns timer15's reset.
int knockoutRequest(uint32_t flags23c,uint32_t flags244,int table,int state,
                    int32_t timer15,bool inputLocked);
enum class VictoryRequest { Wait, Queue, Ready, Dismount };
// Ordinary branch of 0x145240(actor,52). Condition254 includes both the
// three low-word condition flags and bit254 of the original bitset.
VictoryRequest victoryRequest(uint32_t flags23c,uint32_t flags244,int table,int state,
                              bool ended,bool condition254);
uint8_t roundInputFlags(uint8_t flags24c,int currentState,int lock);
bool ordinaryMetersActive(int requestedState,bool globallyPaused);
struct StageCamera;
//1441e0 camera portion; actor requests remain with the round controller.
void beginVictoryCamera(StageCamera&,int winner,bool draw,const std::array<uint32_t,2>& postures);
struct BattlePause {
    int remaining=0,delay=0;
    bool paused=false;
    // 0x139290 stores counts of outer coroutine visits, not actor time.
    void request(int count,int wait);
    bool advance();
};
}
