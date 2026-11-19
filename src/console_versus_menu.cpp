#include "console_versus_menu.hpp"
#include <algorithm>
#include <stdexcept>

namespace ss6 {
void ConsoleVersusMenu::samplePads(std::array<uint32_t,2> held,std::array<uint32_t,2> pressed) {
    for(unsigned side=0;side<2;++side) {
        auto repeatWord=pressed[side];
        // 117fd8 has separate directional repeat timers. Only vertical menu
        // movement consumes repeats; horizontal movement uses initial edges.
        for(unsigned n=0;n<4;++n) {
            const uint32_t bit=0x10u<<n;
            auto& delay=repeats_[side][n];
            if(!(held[side]&bit))delay=0;
            else if(delay==0){delay=20;repeatWord|=bit;}
            else if(--delay==0){delay=2;repeatWord|=bit;}
        }
        const auto edge=pressed[side];
        commands_[side]=(repeatWord&0x30)>>4;
        if(edge&0x80)commands_[side]|=4;
        if(edge&0x40)commands_[side]|=8;
        if(edge&0x20a)commands_[side]|=16;
        if(edge&0x404)commands_[side]|=32;
    }
}
void ConsoleVersusMenu::record(int winner,std::array<unsigned,2> characters) {
    if(winner < -1 || winner>1)throw std::invalid_argument("Invalid console versus winner");
    const auto bump=[](int& value){if(value<999)++value;};
    if(winner<0) {
        for(auto& loss:session.losses)bump(loss);
        session.lastEntrant=session.originalEntrant;
        session.lastWinner=-1;
        session.streak=0;
        return;
    }
    const int loser=winner^1;
    bump(session.wins[winner]);
    bump(session.losses[loser]);
    session.lastEntrant=loser;
    if(session.lastWinner!=winner)session.streak=0;
    session.defeatedCharacters[unsigned(session.streak)%20]=characters[loser];
    ++session.streak;
    session.lastWinner=winner;
}
void ConsoleVersusMenu::enter(int winner,std::array<unsigned,2> characters,bool recordScore) {
    // 143484 calls 145628/124da0 only while gameData+18 is clear. Both
    // paths create the menu. No result portrait is scheduled in submode 2.
    if(recordScore)record(winner,characters);
    active=true;
    pending=destination=ConsoleVersusDestination::None;
    selection_=dialog_=back_=panel_=text_=inputDelay_=0;
    choice_=1;
    frame_=0;
    ++helpRevision_;
    draw={};
}
void ConsoleVersusMenu::choose() {
    if(selection_==1) {
        dialog_=2;
        pending=ConsoleVersusDestination::Rematch;
    } else {
        const int prompt=selection_==0?3:4;
        if(dialog_!=prompt){dialog_=prompt;return;}
        if(choice_!=0){dialog_=0;return;}
        pending=selection_==0?ConsoleVersusDestination::CharacterSelect:ConsoleVersusDestination::Title;
        if(pending==ConsoleVersusDestination::Title){session.wins={};session.losses={};}
    }
    // The overlay runs at priority 70, after the priority-60 transition
    // scheduler. Its first fade tick occurs in the following dispatch.
    phase_=1;level_=0;hold_=0;fadeAlpha=0;
}
int ConsoleVersusMenu::navigate(uint32_t command) {
    // Up/right win over down/left. Either direction toggles the yes/no box.
    // Cancel also wins over confirm on simultaneous edges (1db26c).
    if(command&15) {
        if(dialog_==0){selection_=(selection_+((command&5)?2:1))%3;++helpRevision_;}
        else if(dialog_==3||dialog_==4)choice_^=1;
        return 32;
    } else if(command&32) {
        if(dialog_==3||dialog_==4){dialog_=0;choice_=1;return 37;}
    } else if(command&16){choose();return 0;}
    return -1;
}
void ConsoleVersusMenu::fade() {
    fadeAlpha=level_;
    switch(phase_) {
    case 1:
        if(level_<256)level_=std::min(256,level_+25);
        else {phase_=2;hold_=0;}
        break;
    case 2:
        if(++hold_==3){phase_=3;destination=pending;}
        break;
    case 3:
        if(level_>0)level_=std::max(0,level_-25);
        else phase_=0;
        break;
    }
}
std::array<int,2> ConsoleVersusMenu::tick() {
    std::array<int,2> sounds{-1,-1};
    fade();
    if(!active)return sounds;
    if(pending!=ConsoleVersusDestination::None){draw.visible=false;return sounds;}
    const unsigned priorHelp=helpRevision_;
    if(text_>=15 && inputDelay_>=5) {
        // 1dafa0 visits P1 before P2. A confirm from P1 can open a prompt
        // that P2 answers during this same update.
        uint32_t command=0;
        for(unsigned side=0;side<commands_.size();++side) {
            // If port one starts a transition, 1db004 bypasses the next pad
            // read and retains its command. The second confirmation is audible.
            if(pending==ConsoleVersusDestination::None)command=commands_[side];
            sounds[side]=navigate(command);
        }
    }
    draw={true,frame_++,borderFrame_++,selection_,dialog_,choice_,
          back_*128/30,panel_*192/30,text_*17,inputDelay_,helpRevision_,priorHelp!=helpRevision_};
    if(back_<30)++back_;
    else {
        panel_=std::min(30,panel_+1);
        text_=std::min(15,text_+1);
        inputDelay_=std::min(5,inputDelay_+1);
    }
    return sounds;
}
void ConsoleVersusMenu::inheritRematch(const ConsoleVersusMenu& previous) {
    // The new battle receives its own menu task only after its final round.
    // Global pad repeat, menu border animation, scores and the active black
    // transition outlive the retiring battle.
    *this=previous;
    active=false;draw.visible=false;
    destination=pending=ConsoleVersusDestination::None;
}
}
