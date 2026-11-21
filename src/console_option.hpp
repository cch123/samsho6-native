#pragma once
#include "console_menu.hpp"
#include "system_data.hpp"
#include <array>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <string>
#include <vector>

namespace ss6 {
// Scenes reachable from OPTION MODE. KeyConfig (13cdb0) is a separate
// coroutine page; this module only reports it as a destination.
enum class OptionScene : uint8_t {None,Top,GameOption,KeyConfig,Sound,SaveLoad,Title};

// console_option.bin: original label, value and help strings (Shift-JIS
// bytes verbatim), help scroll flags, row colours and float constants.
struct ConsoleOptionTables {
    enum Group {TopLabel,TopHelp,GameLabel,GameHelp,GameTime,GameMode,CpuMatchPoint,Spirits1P,Spirits2P,
                GameFormat,SoundLabel,SoundHelp,SoundOutput,SoundBgm,SoundVoice,SoundFormat,SaveLabel,
                SaveHelp,AutoSave,GroupCount};
    enum Scalar {EaseOne,EaseThree,CommitScale,CommitUnit,RevertScale,RevertUnit,LoadScale,LoadUnit,ScalarCount};
    std::array<std::vector<std::string>,GroupCount> text;
    std::array<std::vector<uint8_t>,4> helpScroll;   // top, game, sound, save
    std::array<uint32_t,15> gameColour{};            // 657240
    std::array<uint32_t,6> soundColour{};            // 658f70
    uint8_t mikiriDefault=0,kyouchiDefault=0;        // 50d91c, 50d90c
    int32_t mixerDefault=0;                          // 1dbefc immediate
    std::array<uint32_t,ScalarCount> scalar{};       // IEEE bit patterns
    explicit ConsoleOptionTables(const std::filesystem::path& assets);
};

// One 1135e8 text submission. highlight means 1cf8f8(text,x,y,frame) is
// issued first (the blinking edit box of the value being changed).
struct OptionText {
    std::string text;
    int x=0,y=0;
    uint32_t argb=0;
    bool highlight=false;
};
// Everything the page draw routines read, sampled where they read it.
struct OptionDraw {
    OptionScene scene=OptionScene::None;
    int cursor=0,state=0,frame=0;
    int alpha=0;             // 1cf738 as passed to the banner, rows and help
    int banner=0;            // rectangle index at 4c7660 + 18*n
    bool whiteScreen=false;  // 1145c0 full-screen white at z=-400
    // 1ce660 frame: counters as drawn, before its own increment.
    bool frameDrawn=false,showPage=false;
    int band=0,legend=0,page=0,pageTotal=0;
    // 1d1e20 page slide: both bands at full alpha, outgoing rows at
    // slideOutX+44, incoming rows at slideInX+44, middle band at +1e.
    bool sliding=false;
    int slideCounter=0,slideOutX=0,slideInX=0;
    std::vector<OptionText> texts;
    // Help line at y=198: copy 1 exists only for scrolling strings; a
    // copy is submitted while its x is below 280.
    const std::string* help=nullptr;
    int helpCopies=0;
    std::array<int,2> helpX{};
    std::array<bool,2> helpVisible{};
};

class ConsoleOption {
public:
    struct Tick {
        std::vector<int> sounds;            // 1e7b70(-1,id) in call order
        OptionScene request=OptionScene::None; // 1252f0(1,0,own destructor,entry): white fade
        int saveRequests=0,loadRequests=0;  // 10f958 / 10f088 reached
        bool autoSave=false;                // 10f158 found the auto-save flag set
        std::vector<int> soundOutputs;      // 213c08(mode): 0 stereo, 1 monaural
    };
    // Memory-card replacements. save is invoked for SAVE and for the
    // auto-save on leaving to the title; load for LOAD. A load that fails
    // must leave the image unchanged (10f088 restores it).
    std::function<void()> save,load;

    ConsoleOption(const ConsoleOptionTables& tables,SystemData& data);
    void resetTopCursor() {topCursor_=0;}                 // 1cfda0, mode menu only
    // Scene entries 1cfa10 / 1d00b8 / 1dba30 / 1d30b0. libraryRandom is the
    // 316b90 result 1ce478 itself consumes for the background variant. The
    // animated background takes 1800 library draws before it (1e1620) and
    // one after it (1e2358 / 1e23a0); the caller owns that stream.
    void enter(OptionScene scene,int libraryRandom);
    Tick tick(const std::array<MenuPad,2>& pads);

    OptionScene scene() const {return scene_;}
    int cursor() const;
    int state() const;
    int topCursor() const {return topCursor_;}
    int page() const {return page_;}
    int slideCounter() const {return slideCounter_;}
    int slideState() const {return slideState_;}
    int frame() const {return frame_;}
    const std::array<uint8_t,0x98>& gameWork() const {return gameWork_;}
    const std::array<uint8_t,7>& soundWork() const {return soundWork_;}
    int32_t autoSaveWork() const {return autoSaveWork_;}
    // 1b8bc0: the mixer word the image unpack derives from the BGM volume.
    static int32_t unpackedMixerVolume(const ConsoleOptionTables& tables,uint8_t volume);

    MenuChrome chrome;
    OptionDraw draw;
    int32_t mixerVolume=0;                                // 5a9e78

private:
    void tickTop(const std::array<MenuPad,2>&,Tick&);
    void tickGame(const std::array<MenuPad,2>&,Tick&);
    void tickSound(const std::array<MenuPad,2>&,Tick&);
    void tickSave(const std::array<MenuPad,2>&,Tick&);
    void setHelp(ConsoleOptionTables::Group group,unsigned scrollTable,int index);
    void drawHelp();
    void drawFrame(bool showPage,int page,int total);
    void leave(Tick&,int& state);
    void exitToTitle(Tick&);
    void gameIncrement();
    void gameDecrement();
    void gameDefaults();
    void gameDiscard();
    void gameRows(int first,int last,int x,uint32_t labelAlpha,int valueAlpha,int cursor,int state,bool plainLabels);
    OptionText gameValue(int item,int cursor,int state,int x,int y,int alpha) const;
    void soundCommit(Tick&);
    void soundRevert(Tick&);
    int32_t volumeWord(uint8_t volume,ConsoleOptionTables::Scalar scale,ConsoleOptionTables::Scalar unit) const;
    int32_t brightness() const {return data_.word(SystemData::gameOption+0xc);}
    void setBrightness(int32_t v) {data_.setWord(SystemData::gameOption+0xc,v);}

    const ConsoleOptionTables& tables_;
    SystemData& data_;
    OptionScene scene_=OptionScene::None;
    int topCursor_=0,topState_=0;                         // 582c38, 582c3c
    int gameCursor_=0,gameState_=0;                       // 582c68, 582c6c
    int soundCursor_=0,soundState_=0;                     // 582ff0, 582ff4
    int saveCursor_=0,saveState_=0;                       // 582de8, 582dec
    int frame_=0;                                         // 582c70 / 582ff8 / 582df4
    int page_=0,slideCounter_=0,slideState_=0;            // 133f9f8, +4, +8 (bss; 2 = idle)
    std::array<uint8_t,0x98> gameWork_{};                 // 582c78
    std::array<uint8_t,7> soundWork_{};                   // 133fa38
    int32_t autoSaveWork_=0;                              // 582df0
    const std::string* help_=nullptr;
    bool helpScroll_=false;
};
}
