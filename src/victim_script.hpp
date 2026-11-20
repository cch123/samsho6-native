#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <vector>
#include "fighter_tables.hpp"

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct StateEntryContext;
struct GroundStateFrame;
// One 20-byte row of the victim-side table B (4e4a68); docs/victim-script-engine.txt section 2.
struct VictimRow {
    uint8_t id=0xff;
    int16_t victimAct=-1,attackerAct=-1,childAct=-1,parameter=0,damage=0;
    std::array<uint8_t,3> wait{},end{};
    uint8_t flags=0,type=0xff;
};
class VictimTables {
public:
    explicit VictimTables(const std::filesystem::path& assets);
    // 1633c0: original address of the first row with this id, 0 when absent.
    uint32_t find(unsigned character,unsigned id) const;
    const VictimRow& row(uint32_t address) const;
    // The source's damage-source stub when victim_script owns its rows, else 0.
    uint32_t handler(unsigned source) const {return fighters_.scriptVictim(source);}
    const FighterTables& fighters() const {return fighters_;}
private:
    FighterTables fighters_;
    struct Table {uint32_t base=0;std::vector<VictimRow> rows;};
    std::array<Table,51> tables_{};
};
// One visit of that stub (or of 165cc0 for a multi-row script) for the
// victim. Returns true when the caller must run the ordinary 169810 recovery.
// Row features not yet ported (script damage, child ACTs/waits, adopting the
// delivering object, unknown types) throw UnportedFighterState.
class ScriptEngine;
// 174158: the generic landing callback (modes 0..11 in callbacks260[5]).
// Returns true when the caller must run the ordinary 169810 recovery.
// The context and frame are not read; they let validation traces record the visit.
// 166e10 (end op 9): at the hold, f1b counts up (to 2) and 14a8d0 applies body+128 as life.
void updateLifeHold(PlayerObject& body,StateEntryActor& actor,StateEntryContext&,const GroundStateFrame&);
bool updateLanding174158(PlayerObject& body,StateEntryActor& actor,StateEntryContext&,const GroundStateFrame&);
bool updateVictimScript(PlayerObject& body,StateEntryActor& victim,StateEntryContext&,const GroundStateFrame&,const VictimTables&,const ScriptEngine&);
}
