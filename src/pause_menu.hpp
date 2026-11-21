#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
#include "arcade_run.hpp"
#include "console_menu.hpp"

namespace ss6 {
// Scene entries the pause menu passes to 1252f0(2, 0, 1da210, entry).
enum class PauseScene : uint32_t {None=0,CharacterSelect=0x128008,Title=0x127940,NeoGeoLand=0x1d8290};

// pause_menu.bin (work/ss6/extract_pause_menu.py), Shift_JIS strings.
struct PauseMenuAssets {
    std::array<std::string,6> items,help;     // 658ba8, 582f68
    std::array<std::string,4> items5,help5;   // 658bd0, 582f98 (sub-mode 5)
    std::array<std::string,2> answers;        // 656b58: yes, no
    std::array<int32_t,2> answerX{};          // 656b60
    std::string askLand,askTitle,askSelect;   // 656b78, 656b98, 656bb0
    explicit PauseMenuAssets(const std::filesystem::path& assets);
};

// What the draw calls of one 1d9e10 visit read.
struct PauseMenuDraw {
    bool menu=false;          // 1daca8, 1da918, 1da9c0, 1dab38, 1dae00 (skipped with WINDOW OFF)
    unsigned owner=0;         // frame edge colours: seat 0 c00000ff/c0000040, seat 1 c0ff0000/c0400000
    int rows=6,cursor=0;      // row i at (cc, b4 + 18*i): cursor ffff0000, others ffffffff
    int frameHeight=0xd0;     // box (b4, 78, 118, height), colour c0000000
    int helpX=0x10;           // help line at (helpX, 17a) while helpX < 280
    int dialog=0;             // 1cf598: 0 none, 1 title prompt, 2 character-select prompt
    int choice=1;             // 0 yes, 1 no: the selected answer is drawn (ff, 0, 0)
};

struct PauseTick {
    std::vector<int> sounds;              // 1e7b70(-1, id), in request order
    bool closed=false;                    // 1da110 ran: the battle resumes
    PauseScene scene=PauseScene::None;    // 1252f0(2, 0, 1da210, scene)
    bool musicFade=false;                 // 213be8(3)
    bool networkCancel=false;             // 11bd58 (sub-mode 5 only)
    PauseMenuDraw draw;
};

// 1d9b50..1dae40: the in-battle pause menu, words 582f30..582f5c.
class PauseMenu {
public:
    enum State {Menu=0,Cancelled=1,AskSelect=2,WindowOff=5,AskTitle=6};
    enum Window {Closed=0,Open=1,KeyConfig=2,SkillList=3};
    enum {Asleep=0x21,Woken=0x20};
    int cursor=0;        // 582f30
    int state=0;         // 582f34
    int active=0;        // 582f38
    int owner=0;         // 582f3c: seat that opened the menu in mode 3
    int choice=1;        // 582f40
    int locked=0;        // 582f44: a scene request was made
    int delay=0;         // 582f48: input opens at 10
    int window=0;        // 582f4c (1da200)
    int suspended=0;     // 582f50: a child window owns the pads
    int tallyPaused=0;   // 582994 (1c9810 / 1c9820)
    bool abortHook=false;                       // word 43d048 == 1da4d8
    std::array<int,2> windowTask{Asleep,Asleep}; // task word +4 of 582f58 (key config), 582f5c (skill list)
    MenuChrome chrome;   // 582b28..582b3c, shared with the option pages

    explicit PauseMenu(const PauseMenuAssets& assets):assets_(&assets) {}
    // 1d9b50, once per battle-thread frame. `survivalFade` is 181778()
    // (12d4cc8 > 0). Returns true when 1d9cd8 created the menu.
    bool poll(ArcadeGameData& game,const std::array<MenuPad,2>& pads,bool survivalFade);
    void open(ArcadeGameData& game);                                   // 1d9cd8
    // 1d9e10. Every visit first issues the one-frame pause request 1392e8.
    PauseTick tick(ArcadeGameData& game,std::array<ArcadePlayer,2>& players,const std::array<MenuPad,2>& pads);
    void windowReturned();                                             // 1da7e8
    void close(ArcadeGameData& game);                                  // 1da110
    // 1da210, the destructor given to 1252f0: runs at the fade midpoint,
    // after the battle teardown 139778 (which includes teardown()).
    void exitScene(ArcadeGameData& game,std::array<ArcadePlayer,2>& players) const;
    void teardown() {active=0;window=0;}                               // 1da8b0
    void abort(ArcadeGameData& game,std::array<ArcadePlayer,2>& players); // 1da4d8
    unsigned ownerSeat(const ArcadeGameData& game) const;
    int helpIndex() const {return cursor;}
    const std::string& helpText(const ArcadeGameData& game) const;     // 1dac78 / 1dac90
private:
    void reset();                                                      // 1d9da0
    void refreshHelp(const ArcadeGameData& game);                      // 1da860
    void confirm(ArcadeGameData& game,std::array<ArcadePlayer,2>& players,PauseTick& r); // 1da508
    void leaveToTitle(ArcadeGameData& game,PauseTick& r);              // 1da430
    void askTitle(ArcadeGameData& game,PauseTick& r);
    void wake(Window which);
    const PauseMenuAssets* assets_;
};
}
