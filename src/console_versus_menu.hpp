#pragma once
#include <array>
#include <cstdint>

namespace ss6 {
enum class ConsoleVersusDestination : uint32_t {
    None=0, CharacterSelect=0x128008, Rematch=0x139760, Title=0x127940
};
struct ConsoleVersusSession {
    std::array<int,2> wins{},losses{};
    int originalEntrant=1,lastEntrant=1,lastWinner=-1,streak=0;
    std::array<unsigned,20> defeatedCharacters{};
};
struct ConsoleVersusMenuDraw {
    bool visible=false;
    unsigned frame=0,borderFrame=0;
    int selection=0,dialog=0,choice=1,backgroundAlpha=0,panelAlpha=0,textAlpha=0,phase2b3c=0;
    unsigned helpRevision=0;
    bool helpChanged=false;
};
struct ConsoleVersusMenu {
    ConsoleVersusSession session;
    ConsoleVersusMenuDraw draw;
    bool active=false;
    ConsoleVersusDestination destination=ConsoleVersusDestination::None;
    ConsoleVersusDestination pending=ConsoleVersusDestination::None;
    int fadeAlpha=0;
    void samplePads(std::array<uint32_t,2> physicalHeld,std::array<uint32_t,2> physicalPressed);
    void enter(int winner,std::array<unsigned,2> characters,bool recordScore=true);
    // Up to two common-bank sounds, in controller order; -1 means no request.
    std::array<int,2> tick();
    const auto& padCommands() const {return commands_;}
    void beginSet(int confirmingSeat);
    void inheritRematch(const ConsoleVersusMenu& previous);
private:
    void record(int winner,std::array<unsigned,2> characters);
    void choose();
    int navigate(uint32_t command);
    void fade();
    std::array<std::array<int,4>,2> repeats_{};
    std::array<uint32_t,2> commands_{};
    int selection_=0,dialog_=0,choice_=1,back_=0,panel_=0,text_=0,inputDelay_=0;
    int phase_=0,level_=0,hold_=0;
    unsigned frame_=0,borderFrame_=0,helpRevision_=0;
};
}
