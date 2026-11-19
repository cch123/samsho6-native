#pragma once
#include "input_features.hpp"
#include "game_random.hpp"
#include <array>
#include <vector>

namespace ss6 {
struct CharacterSelectSeat {
    int cell=2, character=22, selected=-1, palette=0, spirit=5;
    int phase=1, count=0, drawPhase=0, drawCount=0;
    uint32_t controls=0;
    bool drawPortrait=false, committed=false;
};
struct SpiritSelectSeat {
    int phase=0, count=0, drawPhase=0, drawCount=0;
    int cursor=5, progress=0, secondary=0,drawCursor=5,drawProgress=0;
    std::array<int,9> choices{};
    int choiceCount=0;
};
struct SelectVoice {int bank=0,tone=0;};
class CharacterSelect {
public:
    // The factory Japanese VS roster is column-major. P2 mirrors P1's
    // horizontal movement while both cursors use the same vertical ordering.
    const std::array<int,42> roster{
        31,30,22,0,33,32,34,35,37,38,36,39,1,3,7,6,4,5,24,23,25,
        12,14,15,2,8,9,10,16,17,19,29,28,18,20,21,53,11,27,13,26,53};
    std::array<CharacterSelectSeat,2> seats{};
    std::array<SpiritSelectSeat,2> spirits{};
    GameRandom random{};
    int frame=0,drawFrame=0,remaining=1800,drawRemaining=1800,firstChooser=-1;
    int stage=10,stageCursor=10,stageOption=0,stageOwner=0;
    int spiritDrawFrame=0;
    bool spiritDirectorVisible=false,characterDirectorVisible=false;
    bool spiritRequested=false,complete=false;
    std::vector<SelectVoice> audio; // exact a0/a1 passed to 1e7b70 and 1e7ba0
    void tick(const std::array<NormalizedPadSample,2>& pads);
private:
    std::array<std::array<int,4>,2> delays_{};
    unsigned sync_=0,visits_=0,spiritAge_=0;
    bool colorsResolved_=false;
    void characterTick(unsigned,const NormalizedPadSample&,uint32_t repeat);
    void spiritTick(unsigned,uint32_t repeat);
    void startSpirits();
};
}
