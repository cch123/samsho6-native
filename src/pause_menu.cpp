#include "pause_menu.hpp"
#include <cstring>
#include <stdexcept>
#include "menu_widgets.hpp"

namespace ss6 {
namespace {
// 1dae40: the owner's pad as command bits.
enum : uint32_t {Up=1,Down=2,Right=4,Left=8,Confirm=0x10,Cancel=0x20,Leave=0x40};
uint32_t command(const MenuPad& pad) {
    uint32_t v=0;
    if(pad.pressed&0x80000)v|=Leave;
    if(pad.pressed&0x404)v|=Cancel;
    if(pad.pressed&0x20a)v|=Confirm;
    if(pad.repeat&0x10)v|=Up;
    if(pad.repeat&0x20)v|=Down;
    if(pad.pressed&0x80)v|=Right;
    if(pad.pressed&0x40)v|=Left;
    return v;
}
}

PauseMenuAssets::PauseMenuAssets(const std::filesystem::path& assets) {
    const AssetSections file(assets/"pause_menu.bin");
    const auto fill=[&](const char* tag,auto& to) {
        const auto text=file.strings(tag);
        if(text.size()!=to.size())throw std::runtime_error("Unexpected pause-menu string table");
        for(size_t i=0;i<to.size();++i)to[i]=text[i];
    };
    fill("ITEM",items);fill("ITM5",items5);fill("HELP",help);fill("HLP5",help5);
    const auto ask=file.strings("ASK_");
    if(ask.size()!=5)throw std::runtime_error("Unexpected pause-menu prompt table");
    answers={ask[0],ask[1]};askLand=ask[2];askTitle=ask[3];askSelect=ask[4];
    const auto x=file.section("ASKX");
    if(x.size()!=sizeof answerX)throw std::runtime_error("Unexpected pause-menu answer table");
    std::memcpy(answerX.data(),x.data(),sizeof answerX);
}

unsigned PauseMenu::ownerSeat(const ArcadeGameData& game) const {
    switch(game.mode) {
    case 2:case 0xc:return 1;
    case 3:return unsigned(owner);
    default:return 0;
    }
}
const std::string& PauseMenu::helpText(const ArcadeGameData& game) const {
    // Neither accessor bounds the cursor; it stays inside the visible rows.
    return game.submode==5?assets_->help5.at(size_t(cursor)):assets_->help.at(size_t(cursor));
}
void PauseMenu::refreshHelp(const ArcadeGameData& game) {
    chrome.setHelp(int(helpText(game).size()));
}
void PauseMenu::reset() {
    cursor=0;active=1;state=Menu;locked=0;choice=1;
    chrome.content=15;chrome.legend=5;   // 1cf798(f), 1cf7d8(5)
    window=Open;delay=0;suspended=0;
    tallyPaused=1;
}
bool PauseMenu::poll(ArcadeGameData& game,const std::array<MenuPad,2>& pads,bool survivalFade) {
    if((game.transitionLock!=0||game.challengerInhibit!=0)&&game.wordA4!=1)return false;
    if(game.submode==3||game.submode==6)return false;
    const auto pressed=[&](unsigned seat){return (pads[seat].pressed&0x80000)!=0;};
    const int before=active;
    if(game.mode==1||(game.mode==0xb&&!survivalFade)) {
        if(pressed(0)&&!survivalFade)open(game);
    } else if(game.mode==2||(game.mode==0xc&&!survivalFade)) {
        if(pressed(1))open(game);
    } else if(game.mode==3) {
        // The owner word is written before 1d9cd8 tests the active flag,
        // so a second press on the same visit moves the ownership.
        for(unsigned seat=0;seat<2;++seat)
            if(pressed(seat)){owner=int(seat);open(game);}
    }
    return !before&&active;
}
void PauseMenu::open(ArcadeGameData& game) {
    if(active)return;
    windowTask={Asleep,Asleep};
    abortHook=true;
    reset();
    if(game.submode!=5)game.challengerInhibit=1;
    refreshHelp(game);
}
void PauseMenu::close(ArcadeGameData& game) {
    active=0;game.challengerInhibit=0;window=Closed;tallyPaused=0;
}
void PauseMenu::windowReturned() {
    cursor=0;windowTask={Asleep,Asleep};suspended=0;
}
void PauseMenu::wake(Window which) {
    windowTask[which==KeyConfig?0:1]=Woken;
    window=which;suspended=1;
}
void PauseMenu::leaveToTitle(ArcadeGameData& game,PauseTick& r) {
    if(game.submode==5){r.networkCancel=true;r.scene=PauseScene::NeoGeoLand;}
    else r.scene=PauseScene::Title;
    r.musicFade=true;
    close(game);r.closed=true;
}
void PauseMenu::askTitle(ArcadeGameData& game,PauseTick& r) {
    if(state==AskTitle&&choice==0) {
        leaveToTitle(game,r);
        game.challengerFreeze=1;locked=1;
    } else if(state==AskTitle&&choice==1)state=Menu;
    else state=AskTitle;
}
void PauseMenu::confirm(ArcadeGameData& game,std::array<ArcadePlayer,2>& players,PauseTick& r) {
    enum Row {Resume,Select,Skills,Keys,Hide,Title,None};
    Row row=None;
    if(game.submode==5) {
        constexpr Row rows[]{Resume,Skills,Keys,Title};
        if(unsigned(cursor)<4)row=rows[cursor];
    } else if(unsigned(cursor)<6)row=Row(cursor);
    switch(row) {
    case Resume:state=Cancelled;close(game);r.closed=true;break;
    case Select:
        if(state==AskSelect&&choice==0) {
            r.scene=PauseScene::CharacterSelect;
            close(game);r.closed=true;
            locked=1;r.musicFade=true;
            game.challengerFreeze=1;
            if(game.submode==1)
                for(auto& p:players)p.previousCharacter=p.character;
        } else if(state==AskSelect&&choice==1)state=Menu;
        else state=AskSelect;
        break;
    case Skills:wake(SkillList);break;
    case Keys:wake(KeyConfig);break;
    case Hide:state=state==WindowOff?Menu:WindowOff;break;
    case Title:askTitle(game,r);break;
    case None:break;
    }
}
PauseTick PauseMenu::tick(ArcadeGameData& game,std::array<ArcadePlayer,2>& players,const std::array<MenuPad,2>& pads) {
    PauseTick r;
    const unsigned seat=ownerSeat(game);
    // A child window keeps this task alive only for its pause request.
    if(suspended)return r;
    const uint32_t in=!locked&&delay>=10?command(pads[seat]):0;
    const bool land=game.submode==5;
    const auto step=[&](int rows,int by) {
        if(state==Menu) {
            cursor=(cursor+by)%rows;
            refreshHelp(game);
        } else if(state==AskSelect||state==AskTitle)choice^=1;
        else if(state==WindowOff)state=Menu;
        r.sounds.push_back(0x20);
    };
    if(in&Leave) {
        close(game);r.closed=true;r.sounds.push_back(0x25);
    } else if(in&(Up|Right))step(land?4:6,land?3:5);
    else if(in&(Down|Left))step(land?4:6,1);
    else if(in&Cancel) {
        if(state==Menu){close(game);r.closed=true;}
        else if(state==AskSelect||state==AskTitle){state=Menu;choice=1;}
        else if(state==WindowOff)state=Menu;
        r.sounds.push_back(0x25);
    } else if(in&Confirm) {
        confirm(game,players,r);
        delay=0;
        r.sounds.push_back(0);
    }
    auto& d=r.draw;
    d.menu=state!=WindowOff;
    d.owner=seat;d.rows=land?4:6;d.cursor=cursor;d.frameHeight=land?0xa0:0xd0;
    d.helpX=chrome.helpX[0];
    d.dialog=state==AskTitle?1:state==AskSelect?2:0;
    d.choice=choice;
    if(delay<10)++delay;
    return r;
}
void PauseMenu::exitScene(ArcadeGameData& game,std::array<ArcadePlayer,2>& players) const {
    const int32_t mode=game.mode,sub=game.submode;
    if(state==AskSelect) {
        switch(sub) {
        case 1:
            game.clear();
            if(mode==1||mode==2)game.mode=mode;
            else if(mode==3)game.mode=owner+1;
            game.transitionLock=1;game.submode=1;
            break;
        case 2:game.mode=6;game.submode=2;break;
        case 3:
            if(mode==1)game.mode=9;
            else if(mode==2)game.mode=0xa;
            game.submode=3;
            break;
        case 4:
            game.clear();
            if(mode==0xb||mode==0xc)game.mode=mode;
            game.transitionLock=1;game.submode=4;
            break;
        case 5:
            game.clear();
            if(mode==1||mode==2)game.mode=mode;
            game.transitionLock=1;game.submode=5;
            break;
        default:break;
        }
        players[1].colour=0;players[0].selected=0;players[1].selected=0;
        players[0].word2c=0;players[1].word2c=0;players[0].colour=0;
    } else if(state==AskTitle) {
        game.clear();
        // 11d1a8: 111508 finds mode 0 after the clear and leaves the
        // round-win words alone.
        for(auto& p:players) {
            const int32_t wins=p.roundWins;
            p=ArcadePlayer{};p.spirit=p.versusSpirit=5;p.roundWins=wins;
        }
        if(sub==5) {
            if(mode==1)game.mode=7;
            else if(mode==2)game.mode=8;
            game.submode=5;
        }
        game.transitionLock=1;
    }
}
void PauseMenu::abort(ArcadeGameData& game,std::array<ArcadePlayer,2>& players) {
    close(game);
    teardown();
    exitScene(game,players);
    abortHook=false;
}
}
