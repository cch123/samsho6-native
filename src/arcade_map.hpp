#pragma once
#include "arcade_run.hpp"
#include "arcade_tally.hpp"
#include "game_random.hpp"
#include "menu_canvas.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <vector>

namespace ss6 {
// ARCADE MODE travel map 1c1b20 (task 1c25e0) and walk-in 1c4428 (coroutine
// 1c4568 over the map redraw task 1c43f0): logic, sound / exit requests and
// the MenuDrawList submissions of both scenes.

// arcade_map.bin (work/ss6/extract_arcade_map.py).
struct ArcadeMapTables {
    // Order of FLOATS in the extractor.
    enum Constant:unsigned {
        InitC,InitD,InitE,
        Layer0Step,SpeedUnit,Layer3Y,Word648,Layer1Y,Layer2Y,Layer1Step,Layer2Step,Layer3Step,
        MeshE,MeshD,MeshScale,MeshEighth,
        CloudLimit,CloudZ,Respawn0,RespawnUnit,Respawn1,CloudLeft,Respawn2,Respawn3,
        NameAlphaStep,NameAlpha,NameZ,NameCommonX0,NameCommonY0,NameCommonX1,NameCommonY1,
        PathPi,PathSteps,PathHalf,PathQuarter,
        ArrivalPi,ArrivalSteps,ArrivalHalf,ArrivalQuarter,ArrivalScale,ArrivalBase,
        OpenY0,OpenShrink,OpenY1From,OpenY1To,OpenY2From,OpenY2To,OpenY3From,OpenY3To,
        CloseY0,CloseShrink,CloseY1From,CloseY1To,CloseY2From,CloseY2To,CloseY3From,CloseY3To,
        EasePi,EaseSteps,EaseHalf,EaseQuarter,Ease2Pi,Ease2Steps,Ease2Half,Ease2Quarter,
        MapCamera0,MapCamera1,MapCamera2,MapCamera3,MapCamera4,
        RedrawCamera0,RedrawCamera1,RedrawCamera2,RedrawCamera3,RedrawCamera4,
        WalkCamera0,WalkCamera1,WalkCamera2,WalkCamera3,WalkCamera4,
        BalloonZ,ConstantCount
    };
    // Order of DOUBLES in the extractor: immediates of 1c3608 / 1c3888.
    enum Double:unsigned {
        PathA,PathB,PathCScale,PathCBase,PathDScale,PathDBase,PathEScale,PathEBase,
        ArrivalDScale,ArrivalDBase,ArrivalEScale,ArrivalEBase,DoubleCount
    };
    static constexpr unsigned cloudCount=17,pairCount=51;
    // Clouds are stored layer by layer: 5, 4, 3 and 5 sprites.
    static constexpr std::array<unsigned,5> layerFirst={0,5,9,12,17};

    struct Message {int32_t balloon=0,word4=0;std::array<int32_t,4> text{};}; // 1a26b0 list, strings by index
    struct Speaker {std::array<int32_t,2> generic{};std::array<int32_t,pairCount> pair{};};

    std::array<float,ConstantCount> floats{};
    std::array<double,DoubleCount> doubles{};
    std::array<std::array<double,2>,60> sine{};    // {argument, 30bd00(argument)} for steps 1..60
    ArcadeSpriteRecord tile{};                      // 4c6208
    std::array<ArcadeSpriteRecord,cloudCount> clouds{};
    ArcadeSpriteRecord map{};                       // 4c6598
    std::array<ArcadeSpriteRecord,11> markers{},labels{};   // 5823b0, 655000
    std::array<int32_t,11> markerX{},markerY{},labelX{},labelY{};
    std::array<ArcadeSpriteRecord,9> nameFirst{},nameSecond{}; // 654ef8, 654f70
    std::array<int32_t,9> nameFirstX{},nameFirstY{},nameSecondX{},nameSecondY{};
    std::array<ArcadeSpriteRecord,2> nameCommon{};  // 4c65b0, 4c6760
    std::array<int32_t,8> mapVoices{};              // 654ea8
    std::array<int32_t,11> stageVoices{};           // 6551b8
    std::array<float,12> arrivalX{},arrivalY{};     // 6550b0, 6550e0
    std::array<std::array<int32_t,9>,6> balloons{}; // 4eeef8
    std::vector<std::string> strings;
    std::vector<Message> messages;
    std::array<std::vector<Speaker>,2> speakers;    // 50d550 (byte 43d052 == 0), 50d618

    explicit ArcadeMapTables(const std::filesystem::path& assets);
    float f(Constant c) const {return floats[c];}
};

// Words 582380..5823a8 and 132f5c8..132f748: owned by 1c1e30, advanced by
// the map task, and redrawn unchanged by the walk-in. The opening 1c60c8
// runs 1c1e30 itself (1c6a68 -> 1c6af8) and draws 1c2920 / 1c2a38 from its
// task 1c6b10, so it must share this object with the map that follows it.
struct ArcadeMapState {
    int32_t frame=0;        // 582380
    int32_t pathStep=0;     // 582384
    int32_t pathDone=0;     // 582388
    int32_t arrivalStep=0;  // 58238c
    int32_t arrived=0;      // 582390
    int32_t postArrival=0;  // 582394
    int32_t exitState=0;    // 5823a8
    // 132f5c8, f5cc, f5d0, f5d4, f5d8: top inset, top drop, an unused scale
    // (passed to 1c32c8 on the stack and never read), picture right and bottom.
    float viewA=0,viewB=0,viewC=0,viewD=0,viewE=0;
    float offsetX=0,offsetY=0;                 // 132f5dc, 132f5e0
    std::array<float,4> layerY{};              // 132f638
    float word648=0;                           // 132f648, written by 1c2010 only
    std::array<float,ArcadeMapTables::cloudCount> cloudX{},cloudSpeed{},cloudH{}; // 132f5e8.., 132f700.., 132f650..
    std::array<int32_t,4> layerStep{};         // 132f6a0
    std::array<int32_t,ArcadeMapTables::cloudCount> cloudStep{}; // 132f6b0, 6c8, 6d8, 6e8
    int32_t cloudsOpened=0;                    // 132f6fc

    void reset(const ArcadeMapTables& tables,GameRandom& random);   // 1c1e30 behind its four texture loads
    bool advancePath(const ArcadeMapTables& tables);                // 1c3608
    bool advanceArrival(const ArcadeMapTables& tables,int stage);   // 1c3888
    void openClouds(const ArcadeMapTables& tables);                 // 1c3b78
    void closeClouds(const ArcadeMapTables& tables);                // 1c3ec8
    void moveClouds(const ArcadeMapTables& tables,GameRandom& random); // update half of 1c2a38
};

// Everything the draw routines read on one visit; cloud positions are the
// values 1c2a38 submits before it moves them.
struct ArcadeMapFrame {
    float viewA=0,viewB=0,viewD=0,viewE=0,offsetX=0,offsetY=0;
    std::array<float,4> layerY{};
    std::array<float,ArcadeMapTables::cloudCount> cloudX{},cloudH{};
    bool markers=false;      // 1c31f0 + 1c3260
    bool names=false;        // 1c2fe8
    int32_t pathStep=0;      // name alpha
    int32_t stage=0;         // gameData+4
    int32_t stageIndex=0;    // 582398
    void capture(const ArcadeMapState& state);
};

// Speech balloon of 1a26b0 with the reveal limit 3d3aa0 of the visit.
struct ArcadeBalloon {
    bool visible=false;
    int32_t balloon=0;               // list word 0: 6 and above mirror row id - 5
    std::array<int32_t,3> text{-1,-1,-1}; // string indices, in list order
    int32_t lines=0;
    int32_t limit=-1;                // 3d3aa0
};

// Sheets of both scenes and their compose-over rasteriser.
class ArcadeMapArt {
public:
    explicit ArcadeMapArt(const std::filesystem::path& assets);
    const ArcadeMapTables& tables() const {return tables_;}
    // Same arguments as MenuCanvas::setFade (which owns the 117288 vertex
    // fade): 116588 state of the bank CLUTs and the vertex fade of 1c32c8.
    void setFade(bool enabled,int level,uint32_t colour);
    // 1c1ec8: binds map_icon_NN (NN = min(stage, 9)) to slot 0x22, bank 0x30.
    void bindIcon(int stage);
    int boundIcon() const {return icon_;}

    void ground(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& frame) const;   // 1c2860 + 1c2920
    void markers(const MenuCanvas& canvas,MenuDrawList& list,int stage) const;                    // 1c31f0 + 1c3260
    void clouds(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& frame) const;   // draw half of 1c2a38
    void names(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeMapFrame& frame) const;    // 1c2fe8
    // 1a26b0. Returns the glyphs counted by 3d3ab0.
    int balloon(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeBalloon& balloon) const;
    // Glyphs 113028 would count for the message without a reveal limit.
    int glyphs(const ArcadeBalloon& balloon) const;

    // Paints the list over the 640x480 RGBA frame in ascending depth. Quads
    // of slots 0x1e, 0x1f, 0x20, 0x22, 0x2a, 0x2b and the mesh cells of slot
    // 0x29 are sampled here; other records go to MenuCanvas::rasterise.
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba) const;
private:
    void rebuild();
    uint32_t queueColour(const MenuCanvas& canvas,MenuDrawList& list) const;
    void plain(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeSpriteRecord& r,uint32_t colour,float x,float y) const; // 117760
    void sheet(const MenuCanvas& canvas,MenuDrawList& list,const ArcadeSpriteRecord& r,unsigned flags,uint32_t colour,
               float x,float y,float z,float w,float h) const;                                                                 // 117de8
    ArcadeMapTables tables_;
    std::filesystem::path assets_;
    std::vector<uint8_t> map_,cloud_,moji4_,moji5_,balloon1_,balloon2_,iconIndices_;
    std::array<std::array<uint8_t,4>,256> mapColours_{},iconColours_{};
    std::array<uint16_t,256> iconSource_{};
    std::array<uint16_t,16> bankSource_{};
    std::array<std::array<uint8_t,4>,16> bankColours_{};
    int icon_=-1;
    bool fadeEnabled_=false;
    int fadeLevel_=0;
    uint32_t fadeColour_=0;
};

// The fighters of both scenes are character sprites of the object queue
// 479250 (11e2e8 / 11fed0 / 120390 / 120ce0), owned by the caller's action
// runtime. The scenes read object+0xc0 between the steps of one visit, so
// the calls are made through this interface in original order.
class ArcadeObjectHost {
public:
    virtual ~ArcadeObjectHost()=default;
    // 11e2e8(tag), 11fed0(object, seat, action, x, 0, flags), object+0x20 = colour.
    virtual int create(int tag,int seat,int action,int x,int flags,int colour)=0;
    virtual bool finished(int object)=0;            // object+0xc0 == 1
    virtual void restart(int object,int action)=0;  // 120390
    virtual void step(int object)=0;                // 120ce0: move, animate and submit
};

struct ArcadeSceneExit {
    bool requested=false;
    // true: 1c1ac0 hand-off, kind / speed 0 (task 1c1ae8 calls destructor and entry on the
    // same frame, no fade). false: 1252f0(kind, speed, destructor, next).
    bool handOff=false;
    int32_t kind=0,speed=0;
    uint32_t destructor=0;
    ArcadeScene next=ArcadeScene::None;
};
struct ArcadeSceneEvents {
    int32_t music=-1;   // 1e7c00(music, 0)
    int32_t voice=-1;   // 1e7d60(0x31, voice)
    ArcadeSceneExit exit;
};

// Scene 1c1b20.
class ArcadeMapScene {
public:
    static constexpr uint32_t destructor=0x1c1de8;
    int object=-1;                    // 132f74c / 132f750: first-stage fighter, action 0x703
    std::array<float,5> camera{};     // 122e98(x, y, z), 122eb8(x, y, 0)
    ArcadeMapFrame frame;
    // 1c1b20. A run that arrives from the opening (progress 1) keeps the
    // state and the icon the opening prepared.
    ArcadeSceneEvents enter(ArcadeRun& run,ArcadeMapState& state,ArcadeMapArt& art,ArcadeObjectHost& objects);
    ArcadeSceneEvents tick(ArcadeRun& run,ArcadeMapState& state,const ArcadeMapArt& art,ArcadeObjectHost& objects); // 1c25e0
    void draw(const ArcadeMapArt& art,const MenuCanvas& canvas,MenuDrawList& list) const;
    static void leave(ArcadeRun& run) {run.game.transitionLock=0;}  // 1c1de8
};

// Scene 1c4428.
class ArcadeWalkInScene {
public:
    static constexpr uint32_t destructor=0x1c44f0;   // also 1e7ad0 and 1e7b40
    int32_t exitLatch=0;              // 582440
    int32_t wait=0;                   // 58244c
    std::array<int,2> object{-1,-1};  // seat 0 at x 0xf0, seat 1 at x 0x190 (flags 0x80000)
    std::array<float,5> redrawCamera{},camera{}; // 1c4358, 1c4428
    ArcadeMapFrame frame;
    ArcadeBalloon balloon;
    void enter(ArcadeRun& run,const ArcadeMapArt& art); // 1c4428 with 1c4530
    // One frame: the redraw task 1c43f0, then the coroutine from its yield
    // to the next. `held` / `pressed` are words +0 / +4 of the human seat's
    // 118128 record; `language` is byte 43d052; `fadeComplete` word 3ec73c.
    ArcadeSceneEvents tick(ArcadeRun& run,ArcadeMapState& state,const ArcadeMapArt& art,ArcadeObjectHost& objects,
                           uint32_t held,uint32_t pressed,int language=0,bool fadeComplete=false);
    void draw(const ArcadeMapArt& art,const MenuCanvas& canvas,MenuDrawList& list) const;
    // 1a3168(a0, a1): the list of speaker a1 for listener a0; draws the
    // library generator when no pair entry exists.
    static int message(const ArcadeMapTables& tables,int language,int listener,int speaker,GameRandom& random);
    static bool dialogueStage(const ArcadeRun& run);   // 1c6068
private:
    enum class Phase {Start,Solo,Pair,Message,Hold};
    void animate(ArcadeObjectHost& objects,unsigned seat,bool latch);
    void startHold(ArcadeRun& run,uint32_t held);
    bool revealed(const ArcadeMapArt& art,bool fadeComplete) const;
    Phase phase_=Phase::Start;
    std::array<int32_t,2> finished_{},delay_{};   // sp+0x20 / sp+0x24, s6 / s7
    int32_t limit_=0x3c,countdown_=0x3c;          // sp+0x60, s3
    int32_t messageFrame_=0,messageHold_=0xb4;    // s2, s1
    bool holdVisited_=false;
};
}
