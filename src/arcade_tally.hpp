#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {
// arcade_tally.bin: original tables 655588 / 6555e8, the tally labels and the
// arcade HUD layout words (extract_arcade_tally.py).
struct ArcadeSpriteRecord {int32_t u=0,v=0,w=0,h=0,field10=0,texture=0;};
struct ArcadeTallyTables {
    std::array<int32_t,24> award{};            // 655588, indexed by the score kind
    std::array<int32_t,6> finish{};            // 6555e8, indexed by the finish class
    std::array<std::string,7> labels;          // FINISH TIME PERFECT LIFE rule STRAIGHT TOTAL
    std::array<int32_t,2> scoreX{};            // 582250: right-most score digit for modes 1 / 2
    std::array<ArcadeSpriteRecord,10> scoreDigits{}; // 4c5ae8
    std::array<ArcadeSpriteRecord,5> panelPieces{};  // 4c5110
    std::array<float,30> panelFloats{};        // 655510..655584
    std::array<std::array<int32_t,2>,6> promptPositions{}; // demo, demo latched, seat 0/1, seat 0/1 latched
    float promptDepth=0;
    std::array<ArcadeSpriteRecord,4> promptRecords{}; // 4c3ec8[0..2], 4c3f10[0]
    explicit ArcadeTallyTables(const std::filesystem::path& assets);
};

// ---- In-fight score (14e838 / 14e8d8) -------------------------------------
// Seat gate shared by both functions: only the arcade run's own seat scores.
constexpr bool arcadeScoreSeat(int gameMode,int seat) {return (gameMode==1&&seat==0)||(gameMode==2&&seat==1);}
// 14e838 rewrites every kind except the three item kinds while the seat's
// combo counter (record+0x0c) is positive.
constexpr int arcadeComboKind(int kind,int32_t comboCount0c) {
    return kind!=13&&kind!=14&&kind!=15&&comboCount0c>0?17:kind;
}
int arcadeBodyHitKind(int category);   // 157a58: 14dac8 class of the attacking body
int arcadeObjectHitKind(int category); // 157b50: 14dc00 class of the attacking object
int arcadeItemKind(int itemId);        // 14d8c8: stage items 4..6, otherwise -1
// 1576e8 tail: class written through 14e8d8 from the guard flag and record+0x1c.
int arcadeFinishClass(bool guarded,int outcome1c);
// 14e838 whole: returns the amount added to score (gameData+0x90), 0 when the gate refuses.
int32_t arcadeScoreAward(const ArcadeTallyTables&,int gameMode,int seat,int kind,int32_t comboCount0c,int32_t& score90);
// 14e8d8 whole: stores the tally's finish bonus word 582950. Returns false when the gate refuses.
bool arcadeFinishBonus(const ArcadeTallyTables&,int gameMode,int seat,int finishClass,int32_t& finishBonus582950);

// ---- State-9 round tally (task 1c7f08) -------------------------------------
// HUD life record 132f3a0 + 0x98*seat: the words read or written by 1c8488 / 1bee40.
struct ArcadeLifeBar {
    int32_t x00=0,width08=0,lag10=0,life14=0,mark54=0,mark68=0,mark7c=0,kind94=0;
};
// Battle, HUD and profile words the tally reads and writes. The caller copies
// them in before enter()/tick() and commits them afterwards.
struct ArcadeTallyWorld {
    int32_t clockOption13c=0;      // battle+0x13c; 3 = no round clock
    int32_t roundClock114=0;       // battle timer 0; 0x5a00 units per displayed second
    bool survival=false;           // 123a0c0 == 2: 0xb400 units per second
    uint8_t timeOption43d05d=0;    // option byte; 2 suppresses the TIME bonus
    std::array<ArcadeLifeBar,2> life{};
    std::array<int32_t,2> wins28{},required2c{}; // match records 1400d8(seat)
    std::array<int32_t,2> seatRequired20{};      // 456890 + 0x30*seat + 0x20
    int32_t score90=0;             // gameData+0x90
    int32_t sceneSwitch18=0;       // gameData+0x18: freezes the exit counter
    int32_t postMatchMenuA4=0;     // gameData+0xa4, cleared by 1c7d48
    int32_t finishBonus582950=0;   // written by 14e8d8, consumed by phase 0
    int32_t secondsLeft() const;   // 1407d0
};
struct ArcadeTallyText {std::string text;int x=0,y=0;uint32_t colour=0xff000000u;};
struct ArcadeTallyDraw {
    bool visible=false;            // the task ran this frame (panel 1c8a98 + texts)
    bool perfectLabel=false;       // row 3 label: PERFECT instead of LIFE
    bool straightRow=false;        // 1c8b54 / 1c8950 predicate
    int valueRows=0;               // FINISH, TIME, LIFE, STRAIGHT values drawn this frame
    int32_t finish=0,time=0,life=0,straight=0,total=0;
    // 113028 calls in original order (labels, value rows, total).
    std::vector<ArcadeTallyText> texts(const ArcadeTallyTables&) const;
};
struct ArcadeTallyTick {
    int sounds=0;                  // number of 1e7b70(-1, 0x42) requests
    bool musicRelease=false;       // 1e7a78 called (exit counter >= 20)
};
class ArcadeTally {
public:
    void enter(ArcadeTallyWorld&);                         // 1c7ce8 = task + 1c7d48 + 1c7e00
    ArcadeTallyTick tick(std::array<uint32_t,2> pressed,ArcadeTallyWorld&); // 1c7f08
    void leave() {active44=0;draw.visible=false;}          // 1c7d20
    void setPaused(bool on) {paused94=on;}                 // 1c9820 / 1c9810 (pause menu)
    bool active() const {return active44!=0;}              // 1c87e0, read by the HUD life bars
    bool done() const {return done48!=0;}                  // 1c87f0
    // 582940..582994
    int32_t phase40=0,active44=0,done48=0,exit4c=0,finishLatch64=0,seconds54=0,life58=0,straight5c=0;
    int32_t payout60=0,step68=1,finish6c=0,time70=0,life74=0,straight78=0,total7c=0,perfect80=0;
    int32_t wait84=0,seat88=0,straightSeat8c=0,sound90=0,paused94=0;
    ArcadeTallyDraw draw;
private:
    bool straightHolds(const ArcadeTallyWorld&) const;
    bool blip();
    int32_t finishStep(bool skip,ArcadeTallyWorld&);      // 1c82c0
    int32_t timeStep(bool skip,ArcadeTallyWorld&);        // 1c8360
    int32_t lifeStep(bool skip,ArcadeTallyWorld&);        // 1c8488
    int32_t straightStep(bool skip,ArcadeTallyWorld&);    // 1c85d0
    bool payoutStep(bool skip,ArcadeTallyWorld&,int& sounds); // 1c86c8
};
int arcadeDigits(int32_t value); // 1b9838
void arcadeLifeBarShrink(std::array<ArcadeLifeBar,2>& bars,int seat,int32_t amount); // 1bee40

// ---- Free-seat prompt blink clock (1ba120 / 1ba148) -------------------------
struct FreeSeatPrompt {
    int32_t count2230=10,shown2234=0;
    void reset() {count2230=10;shown2234=0;}  // 1ba120
    bool tick();                               // 1ba148; true = draw the prompt this frame
    // 1ba448: seat mask of the prompt (bit 0 seat 0, bit 1 seat 1). Mode 0 draws the
    // single centred demo prompt through 1ba228 instead; other modes draw nothing.
    static constexpr int seats(int gameMode) {return gameMode==1?2:gameMode==2?1:0;}
};
}
