#pragma once
#include <array>
#include <cstdint>
#include <iterator>
#include <stdexcept>

namespace ss6 {
// How a fighter's character-specific callbacks are ported.
enum class FighterPort : uint8_t {
    HandPorted,  // own verified callback ports (Haohmaru, Nakoruru, Rimururu, Hanzo, Mina)
    ScriptStubs, // original handlers are the common stubs (fighter_stubs.bin); every
                 // move runs through ScriptEngine and every victim row through victim_script
};
struct ActionRange {uint16_t first,last;};
// One admitted fighter. These are native admission policy, not original data:
// heldActions lists the body ACTs whose zero-duration records wait for the
// actor callbacks (and whose attached ACTs are owned by the script engine);
// zeroEndActions lists ACTs whose final record ends with completion code 0,
// which 120c78 accepts and which have been checked for this bank.
struct FighterDescriptor {
    unsigned id;
    const char* name;
    FighterPort port;
    std::array<ActionRange,4> heldActions;
    ActionRange zeroEndActions; // contiguous; noRange = none
};
inline constexpr ActionRange noRange{1,0};
inline constexpr FighterDescriptor fighterDescriptors[]{
    {0,"HAOHMARU",FighterPort::HandPorted,{noRange,noRange,noRange,noRange},noRange},
    {1,"NAKORURU",FighterPort::HandPorted,{noRange,noRange,noRange,noRange},{162,163}},
    {2,"RIMURURU",FighterPort::HandPorted,{noRange,noRange,noRange,noRange},noRange},
    {3,"HANZO",FighterPort::HandPorted,{{{0,165},{185,445},{489,507},{529,754}}},{732,732}},
    {4,"GALFORD",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {5,"KYOSHIRO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{162,163}},
    {6,"UKYO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,599}}},noRange},
    {7,"GENJURO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {8,"BASARA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,880}}},noRange},
    {9,"SHIZUMARU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {10,"GAIRA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,518},{529,758}}},noRange},
    {11,"AMAKUSA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {12,"JUBEI",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,880}}},noRange},
    {13,"ZANKURO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,880}}},noRange},
    {14,"CHARLOTTE",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,516},{529,879}}},noRange},
    {15,"TAMTAM",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,881}}},noRange},
    {16,"KAZUKI",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{258,258}},
    {17,"SOGETSU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,512},{529,880}}},{672,675}},
    {18,"RASETSUMARU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,598}}},noRange},
    {24,"MINA",FighterPort::HandPorted,{{{0,166},{185,445},{489,509},{517,720}}},noRange},
    {19,"RERA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {20,"ENJA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,880}}},noRange},
    {21,"SUIJA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {22,"YOSHITORA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,521},{529,886}}},noRange},
    {23,"YUNFEI",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,880}}},noRange},
    {25,"KUSAREGEDO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,618}}},noRange},
    {26,"GAOH",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,579}}},noRange},
    // Makai Gaoh: the arcade boss. No grid cell; debug harnesses field it with SS6_SUBSTITUTE.
    {43,"MAKAIGAOH",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {27,"MIZUKI",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {28,"YUMEJI",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,528},{529,615}}},{507,507}},
    {29,"SANKURO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,514},{529,752}}},{611,613}},
    {30,"ANDREW",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,512},{529,768}}},noRange},
    {31,"IROHA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{598,600}},
    {32,"OCHAMARO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {33,"SUGOROKU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {34,"CHAMCHAM",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{497,497}},
    {35,"GENAN",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {45,"SHIKURUMAMAHAHA",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {48,"KUROKO",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,528},{529,880}}},noRange},
    {41,"RASETSUGALFORD",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {44,"POPPY",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {46,"CHAMPLE",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{568,568}},
    {47,"PAKUPAKU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{135,135}},
    {40,"KIM",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},noRange},
    {39,"NICOTINE",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,508},{529,880}}},{264,264}},
    {36,"EARTHQUAKE",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,507},{529,593}}},{150,151}},
    {37,"SIEGER",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,528},{529,617}}},noRange},
    {38,"WANFU",FighterPort::ScriptStubs,{{{0,165},{185,445},{489,513},{529,595}}},noRange},
};
// Victim poses queued by character routines rather than by table-B rows
// (1494c0 immediates): Gaira's k == 4 grab, 1f3cc8/1f3db8/1f4010.
struct RoutineVictimPoses {unsigned source;ActionRange poses;};
inline constexpr RoutineVictimPoses routineVictimPoses[]{{5,{0x54d,0x550}},{9,{0x56e,0x56f}},{11,{0x5a2,0x5a3}},{27,{0x608,0x60a}},{31,{0x61e,0x625}},{35,{0x63c,0x63d}},{39,{0x65a,0x65d}},{40,{0x57e,0x58f}},{32,{0x62b,0x62e}},{33,{0x632,0x635}},{10,{0x57e,0x58f}},{17,{0x5ba,0x5bb}},{37,{0x64e,0x653}}};
// Japanese battle resource IDs admitted to versus play. The IDs also index
// the selection grid and the per-character tables, so the set is sparse.
inline constexpr auto playableFighterIds=[] {
    std::array<unsigned,std::size(fighterDescriptors)> ids{};
    for(size_t i=0;i<ids.size();++i)ids[i]=fighterDescriptors[i].id;
    return ids;
}();
constexpr const FighterDescriptor* fighterDescriptor(unsigned character) {
    for(const auto& d:fighterDescriptors)if(d.id==character)return &d;
    return nullptr;
}
constexpr bool playableFighter(unsigned character) {return fighterDescriptor(character)!=nullptr;}
// 148df0: Purple Nakoruru (42) runs Nakoruru's logic (a10 = 1); a14 keeps the selected id.
constexpr unsigned logicCharacter(unsigned selected) {return selected==42?1:selected;}
constexpr bool scriptStubFighter(unsigned character) {
    const auto* d=fighterDescriptor(character);
    return d&&d->port==FighterPort::ScriptStubs;
}
constexpr bool heldFighterAction(unsigned character,unsigned id) {
    const auto* d=fighterDescriptor(character);
    if(!d)return false;
    for(auto r:d->heldActions)if(r.first<=id&&id<=r.last)return true;
    return false;
}
constexpr bool zeroEndAction(unsigned character,int id) {
    const auto* d=fighterDescriptor(character);
    return d&&id>=0&&d->zeroEndActions.first<=id&&id<=d->zeroEndActions.last;
}
inline const char* versusFighterName(unsigned character) {
    if(const auto* d=fighterDescriptor(character))return d->name;
    throw std::out_of_range("Unsupported versus fighter");
}
}
