#pragma once
#include "game_random.hpp"
#include "system_data.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {
// SURVIVAL (mode words b/c, battle kind 2): candidate generation 17aca8, the
// in-battle controller 180510/180630, the 145628 match-end branch, the
// Game Over record and the survival variants of round-end and item rules.
// Strings are the original Shift-JIS bytes.

struct SurvivalAssets {
    explicit SurvivalAssets(const std::filesystem::path& assets); // survival_run.bin
    std::array<uint8_t,22> rewardRule{};   // jump table 5f1ea4 of 17b9e8
    std::array<uint8_t,22> missionKind{};  // jump table 5f2160 of 180fd0
    std::array<uint16_t,9> gains{};        // 181498: life for rewards 0..3, clock for 4..6, life and clock for 7
    std::vector<std::string> rewards,missions,fighters;
    std::vector<std::string> messages;     // ids 31..35, then 36 + reward 0..8
    std::vector<std::string> legends;      // 5f2100, 5f2118, 5f22c0, 1821f8(22,7)
    std::vector<std::string> hud,selector;
};

// One row of the candidate window (12d4f20, 18 bytes each).
struct SurvivalCandidate {
    int32_t stage=0,humanSpirit=0,character=0,colour=0,reward=0,mission=0;
    bool operator==(const SurvivalCandidate&) const=default;
};

// charaTable 12d3668. Only `wins` is cleared when a battle scene starts
// (17ac98); the history rows and the confirmed candidate keep the values of
// the previous run until they are overwritten.
struct SurvivalTable {
    int16_t wins=0;                           // +3c, 17b880
    std::array<int16_t,49> stageHistory{};    // +3e
    std::array<int16_t,49> defeated{};        // +a0
    SurvivalCandidate current{};              // +104, accessors 17b988..17b9d8
    int cpuLevel() const;                     // 17b890
    void confirm(int n,const SurvivalCandidate& row) {wins=int16_t(n);current=row;} // 17b840
    // 17aca8. Returns the row count (always 3). `assertion` reports the
    // 316140 diagnostic of an empty character pool.
    int generate(const SurvivalAssets& assets,GameRandom& random,int n,int lastStage,int defeatedCharacter,
                 int humanCharacter,bool clockLow,std::array<SurvivalCandidate,3>& rows,bool* assertion=nullptr);
};
int survivalReward(const SurvivalAssets& assets,unsigned mission,int spirit,bool lifeTurn); // 17b9e8
bool survivalAdmits(const SurvivalAssets& assets,int mission,int spirit,const std::array<SurvivalCandidate,3>& rows,int row); // 17ba88
bool survivalUnarmedBoss(int character);   // 169388: 2b..2f
bool survivalNoDeflect(int character);     // 1693c0: 2c..2f

// g_PlayerData 456890 + 30*seat and the battle setup block [4d3d04].
struct SurvivalSeatConfig {
    int32_t character=0,colour=0,spiritChosen=0,spirit=0,arcadeProgress=0,roundsToWin=0,version=0; // +0 +4 +8 +c +14 +20 +2c
};
struct SurvivalSetup {
    int32_t level=0,stage=0;                               // +0 +4
    std::array<int32_t,2> control{},character{},colour{},spirit{},rounds{}; // +8 +10 +18 +20 +28
};
// 139c50: spirit of a CPU fighter given the RNG(6) draw.
int survivalCpuSpirit(int character,int drawn);
// 13a6c0 (inPlace) and the survival branch of 1398c0: the assignment of the
// confirmed candidate. The human seat is 0 only for mode word b.
void survivalApplyCandidate(const SurvivalTable& table,GameRandom& random,int modeWord,
                            std::array<SurvivalSeatConfig,2>& config,SurvivalSetup& setup,bool inPlace);

// 17f308..17f508 linear panel slide.
struct SurvivalSlide {
    int x=0,y=0,remaining=0,duration=0,fromX=0,fromY=0,toX=0,toY=0,closed=0,closedX=0,closedY=0,openX=0,openY=0;
    void configure(int cx,int cy,int ox,int oy,int frames);   // 17f428
    void snap(int px,int py);                                 // 17f3a0
    void open();                                              // 17f468
    void close();                                             // 17f4b0
    int tick();                                               // 17f330: 2 moving, 1 open, 0 closed
    bool settled() const {return remaining<1;}                // 17f400
};
// Pad record 118128(port): +0 held, +4 pressed edges, +8 edges with repeat.
struct SurvivalPad {
    uint32_t held=0,pressed=0,repeat=0;
};
// Fields of the human fighter 140090(humanSeat) the controller reads or writes.
struct SurvivalHuman {
    int32_t seat=0;        // +a24
    int32_t flags23c=0;    // +23c, bit 80 blocks per-event rewards
    int32_t life=0;        // +a30
    int32_t lifeA38=0;     // +a38
    int32_t word248=0;     // +248, mission bits 17, 18, 19, 21, 22, 23
    float x=0;             // [[actor+0]+40], truncated for the 1b5b80 effect
    std::array<uint8_t,9> events{}; // +f22..f2a
};
struct SurvivalBattle {
    int32_t state=0;       // battle+0
    int32_t round=0;       // battle+18
    int32_t winner=0;      // battle+24
    int32_t clock=0;       // battle+114, b400 units per displayed count
    int32_t finish=0;      // stats[human.seat]+1c
    int32_t special=0;     // stats[human.seat]+20
    int32_t opponentWins=0,opponentRequired=0; // stats[other seat]+28, +2c (14abb0)
};
struct SurvivalEvents {
    std::vector<int> sounds;        // 1e7b70(-1, id) in call order
    int pauseRequests=0;            // 1392e8: [123a0c4] = 1
    bool continueFlag=false;        // g+2c = 1 (state 1 entry)
    bool lifeEffect=false;          // 1b5b80(0, lifeEffectX, 50)
    int lifeEffectX=0;
    bool reload=false;              // 1e7df0, 1815b0, then 13a6c0: free tag fa1 (11e3a0, 112a70),
                                    // 1392c0, 141558, 1392a8; config and setup already rewritten
};

enum SurvivalMessage : int {SurvivalInitialText=-1,SurvivalChoose=0,SurvivalCleared=1,SurvivalNext=2,
                            SurvivalAchieved=3,SurvivalFailed=4,SurvivalRewardText=5};
struct SurvivalPanel {
    int visible=0,open=0;
    SurvivalSlide slide;
};
// Everything 1810f8 prints. `line` is 0 condition (white), 1 condition of a
// per-event mission (ffffff80), 2 achieved (ff80ff80).
struct SurvivalHud {
    bool visible=false,boss=false,progress=false;
    int x=0,height=0,hours=0,minutes=0,seconds=0,reward=0,mission=0,line=0,progressValue=0;
};

class SurvivalRun {
public:
    explicit SurvivalRun(const SurvivalAssets& assets):assets_(&assets) {}
    SurvivalTable table;
    // Controller words 12d4cbc..12d4cec and the 22 mission words 12d4cf0.
    int32_t state=0,prev=0,delay=0,fade=0,savedLife=0,savedClock=0,humanSeat=0,pendingReward=0;
    int32_t lifeGain=0,clockGain=0,messageTimer=0,wins=0,elapsedFrames=0;
    std::array<int32_t,22> mission{};
    std::array<SurvivalCandidate,3> rows{};
    // Message window 12d4d48 (layout 7): title, message, legend, extra legend.
    SurvivalPanel title,message,legend,extra;
    int messageText=SurvivalInitialText; // index into assets.messages, or -1 for legends[3]
    int legendText=2;                    // index into assets.legends
    // Candidate selector 12d4eb0.
    SurvivalSlide selectorSlide;
    int cursor=0,scroll=0,selectorActive=0,selectorFocus=0;
    SurvivalHud hud;

    // 180510, then 17ac98. Words not listed there keep their values.
    SurvivalEvents begin(GameRandom& random,int modeWord,int humanCharacter);
    static int padPort(int modeWord) {return modeWord==0xc?1:0;} // 178f90 for b/c
    // 180630(skipped). `pad` is the record of padPort().
    SurvivalEvents tick(bool skipped,const SurvivalPad& pad,SurvivalHuman& human,SurvivalBattle& battle,GameRandom& random,
                        int modeWord,std::array<SurvivalSeatConfig,2>& config,SurvivalSetup& setup);
    // 180e28: record a win, build the next candidates, enter the result state.
    void defeated(GameRandom& random,int n,int stage,int character,int humanCharacter,int32_t clock);
    int carriedLife() const {return table.wins>0?savedLife:-1;}    // 180e98
    int carriedClock() const {return table.wins>0?savedClock:-1;}  // 180ec8
    int playSeconds() const {return elapsedFrames/60;}             // 181468
    int winCount() const {return wins;}                            // 181488
    bool fading() const {return fade>0;}                           // 181778, blocks the pause menu
    bool perEvent(const SurvivalHuman& human,const SurvivalBattle& battle); // 180ef8
    bool achieved(const SurvivalHuman& human,const SurvivalBattle& battle) const; // 180fd0
    int grant();                                                   // 181498
    // Text rows of 1810f8 at (hud.x + 8, 5a + 14*i), formatted with the
    // original sprintf formats: elapsed time, reward, condition, progress.
    std::vector<std::string> hudLines() const;
    const SurvivalAssets& assets() const {return *assets_;}
private:
    void sample(SurvivalHuman& human,const SurvivalBattle& battle); // 1815f0
    int selectorUpdate(const SurvivalPad& pad,SurvivalEvents& events); // 211d48
    void fadeStep();
    void drawHud(const SurvivalHuman& human,const SurvivalBattle& battle); // 1810f8
    const SurvivalAssets* assets_;
};

// 1406e0 survival clock: ticks loaded into timer 0 from the carried clock.
int survivalRoundTicks(int carriedClock);
// 1407d0 displayed count in survival.
inline int survivalDisplayedClock(int32_t clock) {return (clock+0xb3ff)/0xb400;}
// 143f9c: a time-up (the loser by life is still alive) is always won by the CPU seat.
int survivalRoundWinner(int lifeWinner,int loserLife,int modeWord);
// 144f40 survival case. `stageKind` is 14ea68(battle+10) (ff: none). The
// drop position is 148368(where): 0/1 fighter x, 2 1482d8(), 3 float 4a2a58.
struct SurvivalItemDrop {
    int kind=0,side=0,where=0,nextDelay=0x258;
};
SurvivalItemDrop survivalItemDrop(GameRandom& random,int stageKind);
// 1498d0..149914: maximum combo byte actor+f22 from stats+c.
inline uint8_t survivalMaxCombo(uint8_t best,int32_t combo) {return combo!=0&&best<combo?uint8_t(combo<0x63?combo:0x63):best;}

// 1e3fd0: session unlock flags 13430b0..13430cc set by a survival win.
// Index: 0 character 2a (lock byte 40), 1 29 (3f), 2 28 (3e), 3 2c (42),
// 4 2d (43), 5 2f (45), 6 2e (44), 7 all 49 defeated (46).
using SurvivalSessionFlags=std::array<int32_t,8>;
void survivalSessionFlags(const SystemData& data,int modeWord,int winnerSeat,int cpuCharacter,int count,SurvivalSessionFlags& flags);

// 145628, branch for mode words b/c.
struct SurvivalMatchEnd {
    bool won=false,finished=false,cleared=false; // cleared: g+34 = 1
    int modeWord=0;                              // rewritten to 1/2 when finished
    int stage=0;                                 // g+4 when finished
};
SurvivalMatchEnd survivalMatchEnd(SurvivalRun& run,GameRandom& random,const SystemData& data,int modeWord,int winnerSeat,
                                  std::array<SurvivalSeatConfig,2>& config,const SurvivalSetup& setup,int32_t clock,
                                  SurvivalSessionFlags& flags);

// g_savedata.survival_score[i]: image + 63fc + 8*i, s8 wins and u32 seconds.
struct SurvivalRecord {
    int wins=0;
    uint32_t seconds=0;
};
int survivalRecordIndex(const SurvivalSeatConfig& seat);   // EX versions of 16..19 use 31..34
SurvivalRecord survivalRecord(const SystemData& data,unsigned index);
// 1384f8..138650 in the Game Over scene (mode word already rewritten to 1/2).
void survivalStoreRecord(SystemData& data,int modeWord,const std::array<SurvivalSeatConfig,2>& config,int wins,int seconds);

// Mode-menu confirm of the SURVIVAL row (1cd494..1cd4f0).
struct SurvivalMenuConfirm {
    int modeWord=0xb;      // g+0: b for seat 0, c for seat 1 (1ccfb8)
    int seatWord=1;        // g+10 = seat ^ 1
    int roundsToWin=1;     // 111710: both seats
    int battleKind=2;      // 139280(2)
    int subMode=4;         // g+a0
};
inline SurvivalMenuConfirm survivalMenuConfirm(int seat) {return {seat==0?0xb:0xc,seat^1,1,2,4};}

// Survival-only differences of the character-select scene 128008, to be
// applied by src/character_select.*. The scene otherwise follows the
// single-sided ARCADE branches (mode words 1/2 and b/c are tested together).
struct SurvivalSelectRules {
    bool active=false;          // mode word b or c
    bool singleSided=false;     // only humanSeat owns a cursor (128294, 12ef80)
    int humanSeat=0;            // 0 for b, 1 for c: seat-1 layout constants (12a9f8..12c63c)
    bool recordPanel=false;     // 12d410(seat): wins / time of the fighter under the cursor
    bool clearExVersions=false; // 1280e4: memset 4c8d18 (68 bytes) and 1239e68 (8 bytes) on entry
    // 12a030: phase 7 is entered without spawning the spirit task 12eee8;
    // the scene then leaves through 1252f0(1,1,129110,139760) (1285f0 / 1286d8).
    bool spiritPage=true;
    // 12de78: with option byte 94 == 1 the held pad bit 100000 selects the EX
    // version word 1239e68[seat]; 129eb0 stores config +2c = 1 for 16..19.
    bool exVersionHold=false;
};
inline SurvivalSelectRules survivalSelectRules(int modeWord) {
    const bool on=modeWord==0xb||modeWord==0xc;
    return {on,on,modeWord==0xc?1:0,on,on,!on,on};
}
}
