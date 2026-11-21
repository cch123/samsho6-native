#pragma once
#include <array>
#include <cstdint>
#include <span>

namespace ss6 {
struct GameRandom;
class SystemData;

// Scene entries requested through 1252f0; the value is the original entry.
enum class ArcadeScene : uint32_t {
    None=0, CharacterSelect=0x128008, VersusFaceoff=0x125e10, Opening=0x1c60c8, Map=0x1c1b20,
    WalkIn=0x1c4428, Dialogue=0x1c5290, PreFinal=0x1c6cc0, Battle=0x139760, WinQuote=0x135e30,
    VersusResult=0x136a60, Continue=0x1376d0, GameOver=0x138340, Ending=0x182968,
    Ranking=0x1e8850, UnlockNotice=0x1e5d88
};
// Arguments of the last 1252f0 call. Kind 1 white fade, 2 black fade,
// 3 immediate cut, 4 challenger banner (speed 0) or intruder banner (speed 1).
struct ArcadeTransition {
    int32_t kind=0,speed=0;
    uint32_t destructor=0;
    ArcadeScene next=ArcadeScene::None;
};

// arcade_run.bin, written by work/ss6/extract_arcade_run.py.
struct ArcadeTables {
    static constexpr size_t byteSize=1932;
    std::array<std::array<int16_t,14>,0x33> opponents{}; // 4edf70
    std::array<int32_t,5> stages{};                      // 4ee508
    std::array<int32_t,4> bosses{};                      // 4ee520
    std::array<int16_t,8> intruder{};                    // 4ee530
    std::array<int32_t,4> versusLimits{};                // 5dfb30
    std::array<std::array<char,4>,45> glyphs{};          // 582998
    std::array<std::array<char,4>,52> names{};           // 582458
    std::array<std::array<char,4>,16> filtered{};        // 3bd950
    unsigned filteredCount=0;
    explicit ArcadeTables(std::span<const uint8_t> asset);
};

// g_GameData 4c3808, a8 bytes; field order is the original layout.
struct ArcadeGameData {
    int32_t mode=0;              // +00: 1/2 arcade seat, 3 two-seat versus
    int32_t stage=0;             // +04
    int32_t winner=-1;           // +08
    int32_t previousWinner=-1;   // +0c
    int32_t selectingSeat=-1;    // +10: challenger, or the loser of a submode-2 match
    int32_t drawSeat=-1;         // +14
    int32_t challengerFreeze=0;  // +18
    int32_t versusInterrupted=0; // +1c
    std::array<int32_t,3> word20{};
    int32_t transitionLock=0;    // +2c
    int32_t challengerInhibit=0; // +30
    int32_t levelEnding=0;       // +34
    int32_t versusStreak=0;      // +38
    std::array<int32_t,20> defeated{}; // +3c
    int32_t endingChoice=0;      // +8c
    int32_t score=0;             // +90
    int32_t challengerBanner=0;  // +94
    int32_t scheduleValid=0;     // +98
    int32_t word9c=-1;
    int32_t submode=0;           // +a0
    int32_t wordA4=0;
    void clear() {*this=ArcadeGameData{};} // 124d50
};
static_assert(sizeof(ArcadeGameData)==0xa8);

// Player setup record 456890 + 30*seat.
struct ArcadePlayer {
    int32_t character=0,colour=0;
    int32_t spirit=0;            // +08: arcade battle parameter
    int32_t versusSpirit=0;      // +0c: mode-3 battle parameter
    int32_t selected=0;          // +10
    int32_t stageIndex=0;        // +14: schedule fights won, 0..8
    int32_t progress=0;          // +18: 0 new run, 1 opening shown, 2 map entered
    int32_t preFinalSeen=0;      // +1c
    int32_t roundWins=0;         // +20
    int32_t randomSelect=0;      // +24
    int32_t previousCharacter=0; // +28
    int32_t word2c=0;
};
static_assert(sizeof(ArcadePlayer)==0x30);

// Schedule record 12d3668 (+00..+38 and the 17bb38 block at +11c).
struct ArcadeSchedule {
    std::array<int16_t,7> stages{},opponents{};
    std::array<uint8_t,7> rolls{},bonus{},wins{};
    int32_t intruderDisabled=0,substitutionDisabled=0;
    int16_t word11c=0,word11e=0;
    std::array<int16_t,49> characterRolls{},characterOrder{};
};

// Words 1398c0 stores into the battle parameter block.
struct ArcadeBattleSetup {
    int32_t stageIndex=0,stage=0; // +00 is also the CPU level argument of 148df0
    std::array<int32_t,2> control{},character{},colour{},spirit{},roundWins{};
};

class ArcadeRun {
public:
    ArcadeRun(const ArcadeTables& tables,SystemData& system,GameRandom& random)
        :tables_(tables),system_(system),random_(random) {}

    ArcadeGameData game;
    std::array<ArcadePlayer,2> players{};
    ArcadeSchedule schedule;
    std::array<std::array<int32_t,2>,2> versusCounters{}; // 4c37f8: {wins, losses} per seat
    int32_t intruderFight=0;     // 5823ac
    int32_t mapStageIndex=0;     // 582398
    int32_t dialoguePostFight=0; // 582528
    int32_t startHoldCounter=0;  // 582444
    int32_t startHoldFlag=0;     // 582448
    int32_t scoreShadow=0;       // 582238
    int32_t rankingHighlight=-1; // 582450
    uint8_t battleKind=0;        // 123a0c0
    ArcadeTransition transition;

    // 178f90 for modes 1/2: the seat whose held pad word 17abd8 samples.
    unsigned humanSeat() const {return game.mode==2;}
    // 17a2c8. `held` is the +0 word of the human seat's 118128 pad record.
    void buildSchedule(int character,bool reroll,uint32_t held);
    int opponentAt(int index) const;      // 17a350
    int stageAt(int index);               // 17a410, always draws random(5)
    bool intruderDue() const;             // 17a548
    bool substituteKuroko();              // 17a630
    void addBonus(int index,int amount);  // 17a600
    void addRoundWin(int index,int amount); // 17a718, called by 143dd4
    void disableSpecialOpponents() {schedule.intruderDisabled=schedule.substitutionDisabled=1;} // 1451f0
    void prepareFight();                  // 1c2420

    void confirmMenu(unsigned seat);      // mode menu item 0 at 1ccfd0
    void applyRoundWins();                // 111508
    void resetPlayer(unsigned seat);      // 11d1c8
    void selectExit(uint32_t held);       // 12f100 exit dispatcher, modes 1/2
    // 1398c0. `selectedStage` is 12f878's result, read in submodes 2/3 only.
    ArcadeBattleSetup battleSetup(int selectedStage=10);
    void matchEnd(int bonus);             // 145628
    void winQuoteExit(uint32_t held);     // 1362d8
    void versusResultExit(uint32_t held); // 136fc8

    // 118148 after the pad update. Returns true when a challenge started.
    bool pollChallenger(std::array<uint32_t,2> pressed,uint32_t currentDestructor);
    void idleRandom();                    // 118298: one library draw per frame in RNG modes 0/1
    // 1253e0, run by the transition task between the old scene's last frame
    // and its destructor. `pool` is the other seat's random-select pool
    // (4c8690 + d0*seat, 4c8830 + 4*seat entries).
    void transitionMidpoint(std::span<const int32_t> pool);
    void transitionFinished() {game.challengerBanner=0;game.transitionLock=0;} // 1252e4
    void recordVersus();                  // 124da0
    bool versusLimitReached() const;      // 124f98
    void recordStreak(int seat);          // 1c4f80
    // 1c5150: inserts the arcade score; returns the new row or -1.
    int recordScore(unsigned seat,const char* name);
    bool scoreQualifies() const;          // 1c4e38(g+90)
    void resetScore() {scoreShadow=0;game.score=0;}          // 1bc1a8
    void clearStartHold() {startHoldFlag=0;startHoldCounter=0;} // 1c4e08
    void request(int kind,int speed,uint32_t destructor,ArcadeScene next); // 1252f0

    const ArcadeTables& tables() const {return tables_;}
    SystemData& system() {return system_;}
    GameRandom& random() {return random_;}
private:
    int drawOpponents(int character);     // 17a748
    bool postFightDialogue() const;       // 1c6008
    void reselectRandom(unsigned seat,std::span<const int32_t> pool); // 129168
    const ArcadeTables& tables_;
    SystemData& system_;
    GameRandom& random_;
};

// Countdown service of task 127f00 (priority 9, before every scene task).
struct ArcadeCountdown {
    uint32_t count=0,paused=1,limit=0,delay=0; // 4c8280, 4c8284, 4c8288, 4c828c
    void tick();                                                   // 127f00
    void start() {count=0;paused=0;}                               // 127f50
    uint32_t remaining() const {return limit-count;}               // 127f68
    void advance(uint32_t n) {count=count+n>limit?limit:count+n;}  // 127fc8
};

struct ArcadeContinueDraw {
    int32_t frame=0;
    uint32_t remaining=0;        // zero hides the counter
    int32_t seconds=0,tens=0,ones=0,phase=0;
    bool twoDigits=false,animated=false; // phase < 15 selects the scaled digit variant
    int32_t loserSeat=-1,loserCharacter=0,loserColour=0; // object action 700
};
// Task_Continue: entry 1376d0, handler 137978 (priority 1c), destructor 137c68.
class ArcadeContinue {
public:
    static constexpr int music=0x1a;      // 1e7c00(1a,0)
    int32_t frame=0,accepted=0,latch=0,entryMode=0; // 4ca1f4, 4ca1f8, 4ca1fc, 4ca200
    bool fadeRequested=false;             // 1170d8(-1); 117170(1) on this tick
    ArcadeContinueDraw draw;
    void enter(ArcadeRun& run,ArcadeCountdown& countdown);
    // `pressed` holds both seats' edge words. Returns sound f or -1.
    int tick(ArcadeRun& run,ArcadeCountdown& countdown,std::array<uint32_t,2> pressed);
    void leave(ArcadeRun& run) {run.game.challengerInhibit=0;}
};

struct ArcadeGameOverDraw {
    int32_t frame=0;
    bool textVisible=false;      // 138ba8 draws from frame 88
    bool stageBackground=false;  // 1a4a98(g+4) at entry
    int32_t loserSeat=-1,loserCharacter=0; // object action 701
};
// Task_GameOver: entry 138340, handler 1387b8 (priority 1d), destructor 138a48.
class ArcadeGameOver {
public:
    static constexpr int music=0x1b;      // 1e7c00(1b,0)
    int32_t frame=0;                      // 4ca204
    bool fadeRequested=false,voiceRequested=false,soundStopped=false,autosave=false;
    ArcadeGameOverDraw draw;
    void enter(ArcadeRun& run);
    // Seat whose pad 1387b8 reads: the loser, (g+8)^1, or (g+10)^1 after a
    // mode-3 match. A draw under option +2 leaves g+8 == -1, i.e. no seat.
    static int padSeat(const ArcadeRun& run) {return (run.game.mode==3?run.game.selectingSeat:run.game.winner)^1;}
    // `unlockPending` is 1e6180() (gallery/unlock slice), read at frame 12c.
    // Returns UnlockNotice after running the destructor itself, Ranking
    // after requesting the fade, None otherwise.
    ArcadeScene tick(ArcadeRun& run,uint32_t pressed,bool unlockPending);
    static void leave(ArcadeRun& run,bool unlockPending); // 138a48
};

// Name entry overlay of the ending: 1c9830 start, handler 1c9928.
class ArcadeNameEntry {
public:
    std::array<char,4> name{};   // 133f7d0
    int32_t glyph=0,cursor=0;    // 133f7c0, 133f7c4
    int32_t seconds=30,secondFrame=0; // 133f7c8, 133f7cc
    int32_t blinkShown=0,erase=0,blinkOn=1,blinkCounter=30; // 582a4c, 582a50, 582a54, 582a58
    int32_t finished=0,commitFrames=0,filtered=0; // 582a5c, 582a60, 582a64
    bool active=false;           // 582a68: the ending cannot be skipped
    bool begin(const ArcadeRun& run); // 1c9830: false when the score does not qualify
    // One 1c9928 visit; `pressed` is the edge word of seat (mode==1 ? 0 : 1).
    // Returns true on the visit that commits the score and ends the task.
    bool tick(ArcadeRun& run,uint32_t pressed);
private:
    void previous();
    void next();
    void finish();
    void input(const ArcadeRun& run,uint32_t pressed);
    void useDefault(const ArcadeRun& run);
};
}
