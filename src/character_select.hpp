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
    // 12db80's Kuroko view (K = 1239e48 + 16*seat): Start toggles it; while on, the columns
    // from the cursor's column show Kuroko, one more column every third update.
    bool kuroko=false,kurokoFaces=false;
    int kurokoDivider=0,kurokoColumns=1;
    // 128c78 creates a seat task only for the seats of the mode word; an absent seat keeps
    // phase 0 and draws nothing.
    bool present=true;
    // Single-seat modes (128c78 flag 0x80, word 1239e30): the fighter object 1239e44 shows
    // 1293d0(seat, previewCharacter, previewAction). previewLoaded is 1239e38;
    // previewRestarted marks the visits on which 1293d0 ran. randomChosen is P+0x24.
    bool previewLoaded=false,previewRestarted=false,kurokoPreview=false,randomChosen=false;
    int previewCharacter=-1,previewAction=0;
};
struct SpiritSelectSeat {
    int phase=0, count=0, drawPhase=0, drawCount=0;
    int cursor=5, progress=0, secondary=0,drawCursor=5,drawProgress=0;
    std::array<int,9> choices{};
    int choiceCount=0;
    // 4c8d88 + 4*seat: set by 12f8e8, cleared when this seat has nothing left to choose.
    bool present=false,active=false;
};
struct SelectVoice {int bank=0,tone=0;};
class CharacterSelect {
public:
    // The fully unlocked Japanese VS roster (unlock bytes 43d06e+40..48 all 0): 1281e0
    // selects 8 columns x 6 rows; 0x5dffa0 is column-major with Purple Nakoruru (42) in
    // cell 36 and the 8th column 41,44,45,47,46,40. P2 mirrors P1's horizontal movement.
    static constexpr int cells=48,columns=8;
    const std::array<int,cells> roster{
        31,30,22,0,33,32,34,35,37,38,36,39,1,3,7,6,4,5,24,23,25,
        12,14,15,2,8,9,10,16,17,19,29,28,18,20,21,42,11,27,13,26,53,
        41,44,45,47,46,40};
    // 128dcc: every character present in the active cells, ascending (128c78 builds it
    // per seat; identical for both seats when nothing is locked).
    static constexpr std::array<int,47> randomPool{
        0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,
        30,31,32,33,34,35,36,37,38,39,40,41,42,44,45,46,47};
    // g_GameData+0 and +0xa0, set before the first tick. Mode 1/2 ARCADE and 0xb/0xc SURVIVAL
    // run one seat (0 for the odd word); 3 (challenger), 6 (VS menu) and 9/10 PRACTICE run
    // both, PRACTICE with one pad. The defaults are the VS menu's (1cd3e4).
    int mode=6,submode=2;
    void configure(int modeWord) {
        mode=modeWord;
        submode=modeWord==6?2:modeWord==9||modeWord==10?3:modeWord==11||modeWord==12?4:1;
    }
    bool twoSided() const {return mode==3||mode==6||mode==9||mode==10;}
    // The seat of a single-seat mode.
    unsigned soleSeat() const {return mode==2||mode==12;}
    std::array<CharacterSelectSeat,2> seats{};
    std::array<SpiritSelectSeat,2> spirits{};
    GameRandom random{};
    int frame=0,drawFrame=0,remaining=1800,drawRemaining=1800,firstChooser=-1;
    int stage=10,stageCursor=10,stageOption=0,stageOwner=0;
    int spiritDrawFrame=0;
    bool spiritDirectorVisible=false,characterDirectorVisible=false;
    bool spiritRequested=false,complete=false;
    // Countdown service 127f00: remaining = limit - count; it only runs outside submodes 2/3.
    bool countdownPaused=true;
    // 4c8294: PRACTICE visits left before the pad drives the second cursor.
    int handoverDelay=10;
    std::vector<SelectVoice> audio; // exact a0/a1 passed to 1e7b70 and 1e7ba0
    void tick(const std::array<NormalizedPadSample,2>& pads);
    // Whether this seat's grid cell currently shows Kuroko's face (0x31).
    bool kurokoCell(unsigned side,int cell) const {
        const auto& s=seats[side];
        if(!s.kurokoFaces)return false;
        const int span=(cell/6-s.cell/6+columns)%columns;
        return span<s.kurokoColumns;
    }
private:
    std::array<std::array<int,4>,2> delays_{};
    unsigned sync_=0,visits_=0,spiritAge_=0;
    int limit_=1800,elapsed_=0;
    bool colorsResolved_=false;
    using Pads=std::array<NormalizedPadSample,2>;
    using Repeats=std::array<uint32_t,2>;
    void characterTick(unsigned,const Pads&,const Repeats&);
    void spiritTick(unsigned,const Repeats&);
    void startSpirits();
    void commit(unsigned side,uint32_t buttons);
    void preview(unsigned side,int character,int action);
    int randomCharacter();
    void settings(SpiritSelectSeat&);
    void restart(int limit,bool paused) {elapsed_=0;limit_=limit;countdownPaused=paused;remaining=limit;}
};
}
