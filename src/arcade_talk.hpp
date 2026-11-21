#pragma once
#include "arcade_run.hpp"
#include "menu_canvas.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <map>
#include <span>
#include <string>
#include <vector>

namespace ss6 {
// ARCADE presentation scenes with text: the opening 1c60c8 (coroutine 1c6400),
// the stage dialogue 1c5290 (coroutine 1c55d8) and the pre-final demo 1c6cc0
// (coroutine 1c6e58). One tick() is one visit of the coroutine, i.e. the code
// between two returns of the yield 112a28. See docs/mode-arcade-talk.txt.

// arcade_talk.bin (work/ss6/extract_arcade_talk.py).
struct ArcadeTalkTables {
    struct Sheet {int32_t u=0,v=0,w=0,h=0,word10=0,slot=0;};
    struct Balloon {int32_t slot=0,x=0,y=0,u=0,v=0,w=0,h=0,textX=0,textY=0;};
    struct Message {int32_t balloon=0;std::array<int32_t,4> line{};};   // 0x18-byte record; -1 = null pointer
    struct Version {
        std::array<std::array<int32_t,25>,49> characters{}; // [0] group 0, [1 + 4*(group-3) + n] groups 3..8
        std::array<std::array<int32_t,4>,5> kinds{};        // 1a31e0
    };
    std::array<float,14> portrait{};      // 60a050..60a084
    std::array<float,10> openingCamera{}; // 655398..6553bc
    std::array<float,5> talkCamera{};     // 655350..655360
    std::array<int32_t,2> talkActions{};  // 655378, 65537c
    std::array<float,5> talkPan{};        // 655380 start y, 655384 flash depth, 655388 step, 65538c limit, 655390 x
    std::array<float,5> preFinalCamera{}; // 6553c8..6553d8
    std::array<float,29> preFinal{};      // 655420..655490
    std::array<Sheet,4> sheets{};         // 4c66a0 (moji4), 4c67d8 (moji5), 4c67f0, 4c6808 (demo_mga)
    std::array<Balloon,6> balloons{};     // 4eeef8
    std::array<double,45> ease{};         // 30bd00 results of the 45 steps of 1c7a30
    std::vector<std::string> strings;     // Shift-JIS, two-byte codes only
    std::vector<Message> messages;
    std::array<std::vector<int32_t>,2> openingLines; // 4efc10 / 4ff6f0
    std::array<Version,2> versions;       // byte 43d052 == 0 / != 0
    std::map<uint16_t,std::array<uint8_t,288>> glyphs; // GOTH_24 rows by record number
    explicit ArcadeTalkTables(const std::filesystem::path& assets);
    int message(bool alternate,int character,int group,int n) const; // 1a3070; -1 where it returns 0
    int kindMessage(bool alternate,int kind,int page) const;         // 1a31e0
};

// The palette-fade registers 3ebf18.. and the text colours of 112f30. They are
// global in the original (the transition task of 1252f0 drives the same words);
// one instance must be shared by every scene and by the transition.
struct ArcadeFade {
    int32_t mode=0;                  // 3ebf18: bit 1 fade, bits 0/2 greyscale (116588)
    uint32_t colour=0;               // 3ec730, AARRGGBB
    int32_t level=0;                 // 3ec734, 0..256
    int32_t speed=0;                 // 3ec738: added to the level at the end of 116588
    int32_t maximum=256,minimum=0;   // 3ebf1c, 3ebf20 (117140)
    std::array<uint16_t,0x400> flags{}; // 3ebf30: per resident CLUT entry, OR-ed with the mode
    uint32_t textColour=0xffffff,textShadow=0x404040; // 3d3ae0, 3d3ae4 (112f30)
    void setMode(int32_t value) {mode=value;}                              // 1170c8
    void setLevel(int32_t value) {level=value<0?0:value>256?256:value;}    // 1170e8
    void set(uint32_t c,int32_t l) {colour=c;setLevel(l);speed=0;}         // 117108
    void ramp(uint32_t c,int32_t s) {colour=c;speed=s;}                    // 117158
    void range(int first,int count,uint16_t flag);                         // 117180
    void beginTransition(int kind);  // register half of 1252f0 kinds 1 / 2
    void endFrame();                 // tail of 116588: the level follows the speed
    bool vertexFade() const {return (mode&2)!=0;}                          // gate of 117288 / 117318
    // 116588 for one resident CLUT entry (5551 source) and for one of the 16
    // glyph CLUT entries of 3d3ab8; RGBA as uploaded, alpha 0x80 = opaque.
    std::array<uint8_t,4> resident(unsigned index,uint16_t source) const;
    std::array<uint8_t,4> glyph(unsigned index) const;
};

enum class ArcadeTalkEvent:uint8_t {
    Music,            // 1e7c00(a0, a1)
    StopMusic,        // 1e7ad0()
    Voice,            // 1e7d60(a0, a1)
    CameraPosition,   // 122e98(f0, f1, f2)
    CameraOffset,     // 122eb8(f0, f1, f2)
    CameraLook,       // 122ed8(f0, f1, f2)
    StageBackground,  // 1a4a98(a0): arena picture task (tag fa1)
    FreeStage,        // 11e3a0(fa1); 112a70(fa1)
    LoadCharacter,    // 11d488(seat a0, character a1)
    MapResources,     // 1c1e30: map module set-up (textures, 17 library random draws)
    MapIcon,          // 1c1ec8: map_icon_NN for the stage a0
    LoadPortrait,     // 1a1928 / 1a19e8: side a0 (1 left, 2 right), portrait a1
    ObjectCreate,     // 11e2e8 + 11fed0: object a0, seat a1, action a2, x a3, y a4, flags a5, colour a6 (-1: not written)
    ObjectAction,     // 120390(object a0, action a1)
    ObjectStep,       // 120ce0(object a0)
    HandOff,          // 1c1ac0(destructor a0, next a1): replaced without a fade
    Exit              // 1252f0(kind a0, speed a1, destructor a2, next a3)
};
struct ArcadeTalkRecord {
    ArcadeTalkEvent kind{};
    std::array<int32_t,7> a{};
    std::array<float,3> f{};
};

// Fighter objects (object queue 479250, not MenuDrawList records). The scene
// calls the host in the original order; the calls are also listed in `events`.
struct ArcadeTalkObjects {
    virtual ~ArcadeTalkObjects()=default;
    virtual void create(int object,int seat,int action,int x,int y,uint32_t flags,int colour)=0; // 11fed0, +20 = colour
    virtual void action(int object,int action)=0;   // 120390: restarts and clears +c0
    virtual void step(int object)=0;                // 120ce0: motion, draw submission, clock
    virtual bool finished(int object)=0;            // +c0 == 1
};

struct ArcadeTalkInput {
    std::array<uint32_t,2> pressed{}; // 118128(seat)+4
};

// One submission step of a visit, in original order. `fade*` is the vertex
// fade (117288) in force when the original submits it.
struct ArcadeTalkDrawOp {
    enum Kind:uint8_t {
        Colour,     // 3db900 = colour
        Rect,       // 1145c0 / 1148f0: x a, y b, w c, h d, colour, depth f0
        PortraitLeft,   // 1a22a8, portrait id a
        PortraitRight,  // 1a2380, portrait id a
        Text,       // 113028: string a, x b, y c, glyphs submitted d, colour
        Balloon,    // 1a26b0 (c == 0) / 1a2948 (c == 1, colour): balloon record a, mirrored b
        Sheet,      // 117de8(record a, flags 0, colour; x f0, y f1, z f2)
        Backdrop    // 1c7848: scroll f0, first quad f1..f4, second quad f5..f8
    } kind{};
    bool fade=false;
    int32_t fadeLevel=0;
    uint32_t fadeColour=0;
    uint32_t colour=0;
    int32_t a=0,b=0,c=0,d=0;
    std::array<float,9> f{};
};

// Shared part of the three scenes: event log, draw script and the text
// services 113028 (reveal counter), 1a22a8 / 1a2380, 1a2468 / 1a2540 / 1a2870,
// 1a26b0 / 1a2948.
class ArcadeTalkScene {
public:
    explicit ArcadeTalkScene(const ArcadeTalkTables& tables):tables_(tables) {}
    std::vector<ArcadeTalkRecord> events;   // calls of the last enter() / tick() / leave()
    std::vector<ArcadeTalkDrawOp> ops;      // submissions of the last tick()
    int32_t revealLimit=-1,revealCount=0;   // 3d3aa0, 3d3ab0
    std::array<int32_t,2> portraits{-1,-1}; // 4eeef0, 4eeef4
    // Replays `ops`. Leaves the list globals (3db900, 3db8fc, 3db8f4, 345180)
    // as the visit leaves them and the canvas fade at the last op's state.
    void draw(MenuCanvas& canvas,MenuDrawList& list) const;
protected:
    void event(ArcadeTalkEvent kind,std::array<int32_t,7> a={},std::array<float,3> f={});
    ArcadeTalkDrawOp& op(ArcadeTalkDrawOp::Kind kind,const ArcadeFade& fade);
    void colour(const ArcadeFade& fade,uint32_t value) {op(ArcadeTalkDrawOp::Colour,fade).colour=value;}
    void text(const ArcadeFade& fade,int string,int x,int y,uint32_t colour);       // 113028
    bool revealed() const {return revealCount<revealLimit;}
    void portrait(int side,int id);                                                  // 1a18e0
    void portraitQuads(const ArcadeFade& fade,bool left,bool right);                 // 1a22a8, 1a2380
    bool lines(const ArcadeFade& fade,const ArcadeTalkTables::Message& m,int x,int base); // 1a2468 / 1a2540 / 1a25f0
    bool centred(const ArcadeFade& fade,const ArcadeTalkTables::Message& m);         // 1a2870
    bool balloon(const ArcadeFade& fade,const ArcadeTalkTables::Message& m,bool alpha,uint32_t colour); // 1a26b0 / 1a2948
    const ArcadeTalkTables::Message& message(int index) const;
    const ArcadeTalkTables& tables_;
};

// Opening 1c60c8. The map picture behind it is the map module's: the task
// 1c6b10 (priority 0xa) submits 1c2920 + 1c2a38 before every visit.
class ArcadeOpening:public ArcadeTalkScene {
public:
    static constexpr uint32_t destructor=0x1c61b8;
    enum class Phase:uint8_t {Wait,Dim,Text,Object,Balloon,Fade};
    using ArcadeTalkScene::ArcadeTalkScene;
    // `held` is the +0 pad word of the human seat (17abd8 inside 17a2c8).
    void enter(ArcadeRun& run,ArcadeFade& fade,uint32_t held);
    void tick(ArcadeRun& run,ArcadeFade& fade,ArcadeTalkObjects& objects,const ArcadeTalkInput& input);
    void leave(ArcadeRun& run,ArcadeFade& fade);      // 1c61b8
    Phase phase=Phase::Wait;
    bool started=false,object=false,handedOff=false;
    int32_t wait=0x22,dim=0,reveal=0,hold=0xf0,skipped=0,alpha=0xff,fadeCount=0xff,latch=0; // latch = 58252c
    int32_t character=0;
    ArcadeTalkTables::Message list{};
private:
    void handOff(ArcadeRun& run);
    bool openingText(const ArcadeFade& fade,bool alternate);   // 1c6208
};

// Stage dialogue 1c5290. The arena picture is requested through the
// StageBackground events (1a4a98) and drawn by its own task.
class ArcadeDialogue:public ArcadeTalkScene {
public:
    static constexpr uint32_t destructor=0x1c53e0;
    enum class Phase:uint8_t {Page,WhiteOut,WhiteHold,WhiteIn,Post,Pan};
    using ArcadeTalkScene::ArcadeTalkScene;
    void enter(ArcadeRun& run,ArcadeFade& fade);
    void tick(ArcadeRun& run,ArcadeFade& fade,ArcadeTalkObjects& objects,const ArcadeTalkInput& input);
    void leave(ArcadeRun& run,ArcadeFade& fade);      // 1c53e0
    static std::array<int,2> select(int stage,int postFight);          // 1c5490: {group, pages}
    static int bossKind(int character);                                // 1c5590
    static int textType(int stage,int postFight,int page);             // 1c5e58: 1 upper, 2 lower, 0 none
    Phase phase=Phase::Page;
    bool started=false,pageOpen=false;
    std::array<int32_t,2> actions{};          // sp+10, sp+14
    int32_t stage=0,player=0,opponent=0,group=0,pages=0,kind=0,page=0;
    int32_t reveal=0,hold=0x10e,list=-1,lastPage=-1;
    int32_t flashCount=0,flashRounds=0,flashArmed=1,whiteArmed=1,white=0,whiteHold=0,leaving=0; // sp+30, +34, +38, +3c, fp, s2, s4
    float pan=0;                              // f21
private:
    void objectsStep(ArcadeTalkObjects& objects);
    void exitToMap(ArcadeRun& run,ArcadeFade& fade);
    void request(ArcadeRun& run,ArcadeFade& fade,int kind,int speed,ArcadeScene next);
};

// Pre-final demo 1c6cc0.
class ArcadePreFinal:public ArcadeTalkScene {
public:
    static constexpr uint32_t destructor=0x1c6d70;
    enum class Phase:uint8_t {Captions,CaptionFade,Zoom,Rest,Box,Text,Scroll,Pause,Leave,Still};
    using ArcadeTalkScene::ArcadeTalkScene;
    void enter(ArcadeRun& run,ArcadeFade& fade);
    void tick(ArcadeRun& run,ArcadeFade& fade,const ArcadeTalkInput& input);
    void leave(ArcadeRun& run,ArcadeFade& fade);      // 1c6d70
    // 1c7a30 on a 0x30-byte block {value[4], from x, from y, to x, to y, from x2, from y2, to x2, to y2}.
    bool ease(std::array<float,12>& block,int32_t& count) const;
    Phase phase=Phase::Captions;
    bool started=false,fresh=false;
    std::array<float,12> first{},second{};    // sp+0, sp+30
    int32_t count=0,count2=0,fadeStep=0,boxStep=0,boxAlpha=0,page=0,reveal=0,list=-1; // sp+60, sp+64, s7, fp, s3, fp', s0
    int32_t exitIssued=0,skipIssued=0;        // sp+68, sp+6c
    float scroll=0;                           // f20
private:
    void backdrop(const ArcadeFade& fade,float offset);
    void exit(ArcadeRun& run,ArcadeFade& fade);
    bool start(const ArcadeRun& run,const ArcadeTalkInput& input) const;
    void advanceScroll();
};

// Sheets of the three scenes (portraits, balloons, captions, demo_mga), the
// glyph rows of their texts and a compose-over rasteriser that applies the
// per-entry palette fade and the glyph CLUT of 116588.
class ArcadeTalkArt {
public:
    ArcadeTalkArt(const std::filesystem::path& assets,const ArcadeTalkTables& tables);
    // Paints the list over the 640x480 RGBA frame in ascending depth. Quads of
    // slots 5, 0xc, 0xd, 0x1f, 0x20, 0x22, 0x23 and every Rotated and Glyph
    // record are sampled here; Flat records go to MenuCanvas::rasterise.
    // `portraits` are 4eeef0 / 4eeef4 (ArcadeTalkScene::portraits).
    void rasterise(const MenuCanvas& canvas,const MenuDrawList& list,std::span<uint8_t> rgba,const ArcadeFade& fade,
                   std::array<int32_t,2> portraits);
private:
    struct Portrait {std::vector<uint8_t> pixels;std::array<uint16_t,64> palette{};};
    const Portrait& portrait(int id);
    std::filesystem::path assets_;
    const ArcadeTalkTables& tables_;
    std::array<std::vector<uint8_t>,4> sheets_;      // hukidasi, hukidasi2, moji4, moji5 (4-bit, 512x512)
    std::vector<uint8_t> picture_;                   // demo_mga, 1024x1024
    std::array<uint16_t,256> pictureSource_{};       // demo_mga.pal, entry 0 cleared (1c6e20)
    std::array<uint16_t,128> residentSource_{};      // obj0.pal as 113890 uploads it
    std::map<int,Portrait> portraits_;
};
}
