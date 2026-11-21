#pragma once
#include "console_menu.hpp"
#include "game_random.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace ss6 {
// Spirit-system handle actor+0x10c as the practice code reads it. `custom` is
// the 16-byte descriptor 14f4e0/152758 selects for the edited system 6.
struct PracticeSystem {
    int id=0;
    const uint8_t* custom=nullptr;
    bool hyperSlash() const;     // 14fac0: STAND option 9 is HYPER SLASH
    bool comboSlash() const;     // 14fb08: STAND option 9 is COMBO SLASH
    bool rageSkills() const;     // 14fb58: skill records of type 2 are usable
    bool systemSkills() const;   // 14fbd8: skill records of type 1 are usable
    bool freeSystemSkill() const;// 14fc30: a type-1 ACTION needs no gauge, only actor+0x244 bit 0x40 cleared
    bool hasSpiritGauge() const; // 14eb78: record h+0x30 exists
    bool hasTimeGauge() const;   // 14ebd0: record h+0x40 exists
private:
    const uint8_t* descriptor() const {return id==6?custom:nullptr;}
};

// practice_mode.bin: menu strings (Shift-JIS, verbatim), the skill-list
// records behind 15f4e8/15f518/15f558 and the 14f220 sword-gauge caps.
class PracticeTables {
public:
    enum Group {Rows,CpuType,Stand,Crouch,Jump,Action,GaugeRows,Ukemi,OffOn,GaugeLong,GaugeShort,Items,KeyConfig,Misc};
    enum MiscText {HyperSlash,ComboSlash,PromptSelect,PromptTitle,ConfirmCaption,Legend,GaugeFormat,PercentFormat,
                   Damage,TotalDamage,MaxDamage,PlayClock,RecClock,ActionFallback};
    struct Skill {int16_t id;uint8_t technique,kind,type;uint32_t name;};
    explicit PracticeTables(const std::filesystem::path& assets);
    const std::string& text(Group group,int index) const {return strings_.at(groups_.at(group).at(index));}
    const std::string& string(uint32_t index) const {return strings_.at(index);}
    int listStart(int id) const;                 // 15f4e8: record index or -1
    int listCount(int id) const;                 // 15f558
    int skillIndex(int id,int n) const;          // 15f518: global record index or -1 (no bounds check, as original)
    const Skill& skill(int index) const {return skills_.at(index);}
    int swordCap(int system,int rageState) const;// 14f220 selection, before the << 8
private:
    std::vector<std::string> strings_;
    std::vector<std::vector<uint16_t>> groups_;
    std::vector<Skill> skills_;
    std::array<std::array<int32_t,3>,9> caps_{};
};

// The dummy as the menu and 211058 see it (211c00 / 140090).
struct PracticeFighter {
    PracticeSystem system;
    int character=0;        // actor+0xa10
    bool alternate=false;   // actor+0x23c & 0x100000: skill list id + 0x32
    int listId() const {return character+(alternate?0x32:0);}
};

// Arrays A/A' (13738a0/13738d0), B/B' (1373900/1373930) and byte list L (1373960).
struct PracticeSettings {
    std::array<int32_t,12> a{},committedA{},b{},committedB{};
    std::array<uint8_t,32> actions{};
    void reset();        // 210368, mode-menu confirm only
    void commit();       // 210550
    void enterBattle();  // head of 210438: STAND option 9 and the ACTION index do not survive a scene entry
    static int optionSlot(int row,int value);            // 2117a0
    int behaviour(const PracticeSystem& dummy) const;    // 211058
    int ukemi() const {return committedA[3];}            // 211150
    int itemKind() const {return committedA[5]?committedA[5]+6:-1;} // 211160
    int spiritGauge(int seat) const {return committedB[seat?7:6];}  // 211178
    int mikiri(int seat) const {return committedB[seat?9:8];}       // 211198
    int lifePercent(int seat) const {return committedB[seat?11:10]+1;} // 2111b8
    bool dataDisplay() const {return committedA[6]!=0;}  // 2111d8
};

// Battle-type byte 123a0c0 with the replay/recording words and the wrappers
// that add the practice predicate (non-practice value in brackets).
struct PracticeState {
    int battleType=0;      // 0 ordinary, 1 practice, 2 survival (139280)
    int mode=9;            // g+0: 9 = pad 1 practises, 10 = pad 2 practises
    int otherModeSeat=0;   // 178f90() for the modes that are not 9/10
    bool replay=false;     // 123a0d8
    bool recording=false;  // 123a0dc
    PracticeSettings settings;
    bool practice() const {return battleType==1;}                  // 139388
    bool survival() const {return battleType==2;}                  // 1393a0
    bool replayActive() const {return practice()&&replay;}         // 1393b8
    bool recordingActive() const {return practice()&&recording;}   // 1393e0
    int localSeat() const {return mode==9?0:mode==10?1:otherModeSeat;} // 178f90, see practiceLocalSeat
    int humanSeat() const;                                         // 139488
    int dummySeat() const;                                         // 1394e0
    int menuDummySeat() const {return mode==10?0:1;}               // 211c00 ignores the recording swap
    int behaviour(const PracticeSystem& dummy) const;              // 139c88 [0x23]
    int ukemi() const {return practice()?settings.ukemi():3;}      // 139ce8 [3]
    int itemKind() const {return practice()?settings.itemKind():-1;}            // 139d20 [-1]
    int spiritGauge(int seat) const {return practice()?settings.spiritGauge(seat):-1;} // 139d78 [-1]
    int mikiri(int seat) const {return practice()?settings.mikiri(seat):-1;}    // 139dc0 [-1]
    int lifePercent(int seat) const {return practice()?settings.lifePercent(seat):-1;} // 139e08 [-1]
};

// 178f90 for every mode word: versusSeat = 1da838() (mode 3), linkSeat = [12d35c4] (modes 13/14).
int practiceLocalSeat(int mode,int versusSeat,int linkSeat);

// Selector widget 20dff8/20e028/20e0a0/20e0d0/20e128.
struct PracticeSelector {
    uint32_t flags=5;
    const uint32_t* disabled=nullptr;   // flag 0x800 bitmap
    int min=0,max=1,step=1,value=0,page=0;
    void init();
    void setRange(int lo,int hi,int stepSize,int pageSize);
    void setFlag(int bit,bool on) {flags=on?flags|(1u<<bit):flags&~(1u<<bit);}
    void setValue(int v);
    // Return codes: 0 none, 1 moved, 2 page down, 3 page up, 4 confirm, 5 cancel, 6 refused.
    int input(const MenuPad& pad,std::vector<int>& sounds);
};

// Slide animation record 17f330..17f4b0.
struct PracticeSlide {
    int x=0,y=0,frames=0,duration=0,startX=0,startY=0,targetX=0,targetY=0,closed=0;
    int closedX=0,closedY=0,openX=0,openY=0;
    void set(int cx,int cy,int ox,int oy,int frameCount);   // 17f428
    void snap(int px,int py);                               // 17f3a0
    void open();                                            // 17f468
    void close();                                           // 17f4b0
    int step();                                             // 17f330: 2 moving, 1 open and idle, 0 closed and idle
    bool idle() const {return frames<1;}                    // 17f400
private:
    void move(int tx,int ty,int frameCount);                // 17f3c0
};
int practiceScrollPage(int code,int visible,int scroll,int count);   // 17f528
int practiceScrollFollow(int cursor,int visible,int scroll,int count); // 17f560

// Requests to the help window 12d3870; presentation only.
struct PracticeHelp {
    enum Kind {Text,Skill,Page,Open,Close,Snap,List};
    // Text: 182268(id,arg). Skill: 1820f8 with skill record `id` (-1 = "必殺技を出しつづけます").
    // Page: 182318(id). Open 182648, Close 1826b0, Snap 182700. List: 1827c0(id,arg).
    int kind=Text,id=0,arg=0;
};

// Main menu object 12d39d8 (210438 init, 210630 update).
struct PracticeMenu {
    int visible=12,scroll=0,active=0,focused=0;
    PracticeSlide slide;
    PracticeSelector rows,values;
    uint8_t counter=0;       // +0x6c: arrow blink, not reset by 210438
    int level=0,prevLevel=-1;
    int standOptions=9;      // 10 once 211550 patched 59cdec
    int standNinth=-1;       // PracticeTables::HyperSlash or ComboSlash after that patch
    void init(PracticeSettings& settings,std::vector<PracticeHelp>& help);
    // Event: 1 PRACTICE START, 2 CPU RECORDING, 3 cancel, 4 SKILL LIST, 5 KEY CONFIGURATION,
    // 6 WINDOW OFF, 7 CHARACTER SELECT, 8 RETURN TO TITLE.
    int update(const MenuPad& pad,PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,
               std::vector<int>& sounds,std::vector<PracticeHelp>& help);
    void describe(const PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,
                  std::vector<PracticeHelp>& help) const;     // 2111e8
    bool gaugeWindow() const {return level!=0&&rows.value==4;} // 211878
private:
    void enterValue(const PracticeSettings& settings,int row);   // 211418
    void enterOption(PracticeSettings& settings,const PracticeFighter& dummy,const PracticeTables& tables,int row); // 211550
};

// YES/NO dialog 12d4c48 (212820 init, 2128f8 update).
struct PracticeConfirm {
    int visible=1,scroll=0,active=0,focused=0;
    PracticeSlide slide;
    PracticeSelector choice;   // 0 YES, 1 NO
    int prompt=PracticeTables::ConfirmCaption;
    void init();
    int update(const MenuPad& pad,std::vector<int>& sounds);   // 4 only for YES; a confirmed NO reads as 5
};

// Shell shared by the key-configuration window, the skill list and its
// sub-list: their update functions step the slide and gate on these words.
struct PracticeSubWindow {
    int active=0,focused=0;
    PracticeSlide slide;
    bool gate();
};
// Event codes returned by the opaque sub-window updates (2121c8, 20ee70 x2, 210210).
struct PracticeSubEvents {
    int keyConfig=0,list=0,subList=0,detail=0;
    int listCursor=0;   // 12d3b54
};
struct PracticeWindowResult {
    std::vector<int> sounds;          // 1e7b70(-1,id): 0x20 move, 0 confirm, 0x24 cancel/refused
    std::vector<PracticeHelp> help;
    bool pause=false;           // 1392e8: the next battle frame is skipped
    bool reset=false;           // 1392d0: full re-initialisation 13f9f0(0) before the next battle frame
    bool clearLockCounters=false; // 142168: both actors +0xa54/+0xa58 = 0, battle+0x138 bit 1 cleared
    bool clearRecording=false;  // 1772d0
    bool fillSubList=false;     // entry 7 arriving from the list: 20e8c0 (cursor 0) or 20eae0/20ed70
    bool openDetail=false;      // entry 8 arriving from the sub-list: 210138
    int exit=0;                 // 1252f0(2,0,139778,x): 1 character select 128008, 2 title 127940; g+0x18 = 1
};
// 17f5a0 init and 17f790 per outer battle frame.
struct PracticeWindow {
    int state=1,lastState=-1,dim=0,startCode=-1,pendingKind=-1;
    PracticeMenu menu;
    PracticeConfirm confirm;
    PracticeSubWindow keyConfig,list,subList;
    int detailActive=0,detailFocused=0;
    bool resetDamage=false;     // 139550 requested by init; consumed by the caller
    void init(PracticeState& practice,std::vector<PracticeHelp>& help);
    // First half: menu and dialog updates; the returned gates say which opaque
    // sub-window would read the pad this frame (key config, list, sub-list, detail).
    std::array<bool,4> begin(const MenuPad& pad,PracticeState& practice,const PracticeFighter& dummy,const PracticeTables& tables);
    // Second half: entry/update handlers. On exit==1 the caller zeroes cfg+0x10 and cfg+0x2c of both seats.
    PracticeWindowResult finish(const MenuPad& pad,const PracticeSubEvents& sub,PracticeState& practice,const PracticeFighter& dummy);
    bool menuDrawn() const {return lastState!=2;}
private:
    int menuEvent_=0,confirmEvent_=0;
    PracticeWindowResult out_;
};

// The words 180260 reads and writes for one actor.
struct PracticeGaugeActor {
    PracticeSystem system;
    int seat=0;             // +0xa24
    int controlKind=0;      // +0xa20
    int behaviour=0;        // +0xc8
    int character=0;        // +0xa10
    bool alternate=false;   // +0x23c & 0x100000
    int32_t life=0,maxLife=0;                       // +0xa30, +0xa34
    std::array<int32_t,4> rage{};                   // h+0x14: state, value, two work words
    std::array<int32_t,3> sword{};                  // h+0x24: state, value, cap
    std::array<int32_t,4> spirit{},timeGauge{};     // h+0x30, h+0x40 (timeGauge[1] is actor+0x150)
    uint32_t flags244=0,flags248=0;
};
// 180260: every outer frame for both actors, after the window update. `paused` is 139308().
void practiceEnforceGauges(PracticeGaugeActor& actor,const PracticeState& practice,const PracticeTables& tables,bool paused);

// 151968: pending damage is committed, timer 28 (actor+0x220) is armed with
// 30 << 8 (14cfe8) whenever any was pending, and a practice fighter keeps one life point
// without receiving the KO flag actor+0x23c & 0x80 (which is then left as it was).
struct PracticeLifeCommit {
    int32_t life;
    int knockedOut;     // 1 set the flag, 0 clear it, -1 leave it unchanged
    bool armTimer28;
};
PracticeLifeCommit practiceCommitLife(int32_t life,int32_t pending,int32_t maxLife,bool practice);
// 14959c: with timer 28 expired the life returns to its maximum (character 0xc is held while body action 0x279 runs).
bool practiceRefillsLife(const PracticeState& practice,int timer28,int character,int bodyAction);
// 1495ec: the actor reads a pad (instead of the CPU 158990) when it is human, a HUMAN dummy or replaying.
inline bool practiceHumanSampled(int controlKind,int behaviour,uint32_t flags240) {return controlKind==0||behaviour==0x24||(flags240&4);}
// 1418f8: clock value handed to the CPU.
inline int practiceCpuClock(const PracticeState& practice,int clock) {return practice.practice()?0x31:clock;}
// 13fbe0..13fc18: battle+0x13c. timeOption = byte 43d05d, linkSubmode = 139408().
int practiceTimeMode(const PracticeState& practice,int timeOption,bool linkSubmode);
// 145068: item kind for the delivery scheduler or -1 (no delivery); RANDOM draws 112300(0x13).
int practiceItemDelivery(const PracticeState& practice,GameRandom& random);

// 172158: CPU UKEMI TYPE decides the dummy's get-up type actor+0xa4c once per knock-down
// (actor+0x248 bit 0x20000000 marks the decision). HUMAN and REPLAY dummies only set the mark.
// RANDOM draws 112300(100): below 0x22 no ukemi, below 0x43 type 2, otherwise type 1.
void practiceGetUp(int32_t& getUpType,uint32_t& flags248,int controlKind,const PracticeState& practice,
                   const PracticeSystem& dummy,GameRandom& random);

// Damage counters 123a0f0..123a0fc and the per-frame flag 123a17c.
struct PracticeDamage {
    int32_t newCombo=1,maxDamage=0,total=0,last=0;
    int32_t frameFlag=0;
    void reset() {maxDamage=total=last=0;newCombo=1;}   // 139550
    void beginFrame() {frameFlag=1;}                    // 13908c
    void comboEnded() {newCombo=1;}                     // 139578
    void add(int32_t damage);                           // 139588
};
// Command history 123a100..123a138 (13a160 clear, 13a1b0 push).
struct PracticeKeyHistory {
    int32_t neutral=0,index=0;
    std::array<uint16_t,24> held{},shown{};
    void clear();
    void push(uint32_t mask);
};
// 141dd0: REC/PLAY clock digits from the recording index actor+0x2c0.
// PLAY reads actor slot 1 and REC actor slot 0 regardless of mode 9/10.
struct PracticeClock {bool shown;bool play;int seconds,thousandths;};
PracticeClock practiceClock(const PracticeState& practice,const std::array<int,2>& index);

// Recording flags actor+0x240 and the 13f9f0 reset rules.
struct PracticeRecordActor {
    uint32_t flags240=0;   // 1 COUNTER dummy, 2 record, 4 replay, 8 read the other port
    int controlKind=0;     // +0xa20
    int seat=0;            // +0xa24
    int index=0;           // +0x2c0
};
// 13fb2c..13fbd4 per actor. Returns true when the match needs a single round win (practice and survival).
// Recording swaps the control kinds: the dummy becomes pad-driven through the other port and records.
bool practiceResetControl(PracticeRecordActor& actor,const PracticeState& practice);
// 14963c..1496ac: port and recording index handed to the sampler 179530.
struct PracticeSampling {int port;int index;bool playback;};
PracticeSampling practiceSampling(const PracticeRecordActor& actor);
// 149790..1497cc: the index advances for every actor while the round runs (141820); only replay wraps, at 720.
void practiceAdvanceRecording(PracticeRecordActor& actor,bool roundRunning);

// Character-select routing in modes 9/10: which physical port a seat reads,
// or -1 while the seat is frozen. Horizontal mirroring stays keyed on the
// seat (12e50c tests the seat, not the port), so seat 1 driven by port 0
// still moves mirrored and the pad word needs no translation.
struct PracticeSelectRouting {
    int delay=10;   // 4c8294, set at scene entry 1280c8
    // 12dbd0..12dc30, character page phase 2. committed = cfg[seat]+0x10. Consumes the hand-over delay.
    int characterPort(int mode,int seat,const std::array<int,2>& committed);
    // 134ea0 / 13503c, spirit cursor and its secondary selection. progress = 4c8d18+0x34*seat+0x2c, spirit = cfg[seat]+8.
    static int spiritPort(int mode,int seat,const std::array<int,2>& progress,const std::array<int,2>& spirit);
    // 13524c stage page (phase 0x14).
    static int stagePort(int mode,int seat) {return mode==9?0:mode==10?1:seat;}
    // 135154: the item-option page (phase 0xd) is skipped when g+0xa0 == 3, i.e. always in practice:
    // the item comes from the practice menu row ITEM instead.
    static bool itemOptionPage(int submode) {return submode!=3;}
};
// Key-history mask 13a030 from the actor's input feature words.
struct PracticeKeyFeatures {
    std::array<int32_t,6> buttons{};   // +0x2dc..+0x2f0 -> 0x200..0x4000
    std::array<int32_t,9> motions{};   // +0x41c,+0x418,+0x414,+0x420,+0x388,+0x410,+0x424,+0x428,+0x42c -> 1..0x100
};
uint32_t practiceKeyMask(const PracticeKeyFeatures& features);
}
