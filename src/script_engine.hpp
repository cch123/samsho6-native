#pragma once
#include <array>
#include <cstdint>
#include <filesystem>
#include <vector>

namespace ss6 {
class PlayerObject;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;
// One 20-byte row of the per-character move-script table A (4e2788).
// See docs/script-engine.txt section 3 for the byte layout.
struct ScriptRow {
    uint8_t id=0xff,end=0xff,flags=0,spawnMode=0xff,type=0xff;
    int16_t act=-1,projectile=-1;
    std::array<int16_t,3> branch{-1,-1,-1};
};
class ScriptTables {
public:
    explicit ScriptTables(const std::filesystem::path& assets);
    // 163348: original address of the first row with this id, 0 when absent.
    uint32_t find(unsigned character,unsigned id) const;
    const ScriptRow& row(uint32_t address) const;
    // 168c18: the ACT's freeze length in 4e5458, 0 when the ACT is not listed.
    int lockTicks(unsigned character,int action) const;
private:
    struct Table {uint32_t base=0;std::vector<ScriptRow> rows;};
    std::array<Table,51> tables_{};
    std::array<std::array<int16_t,16>,51> locks_{};
};
// Native counterpart of the common interpreter 163590/163610. The registry
// keeps the original layout (actor+28c), including row ADDRESSES in r[11],
// so other callbacks and validators read the same words as the original.
class StateCallbacks;
class ScriptEngine {
public:
    explicit ScriptEngine(const ScriptTables& tables,const StateCallbacks* callbacks=nullptr):tables_(tables),callbacks_(callbacks) {}
    const StateCallbacks* callbacks() const {return callbacks_;}
    // 163570: selector -> script id, or -1.
    static int scriptId(uint32_t selector) {return selector==0xff||selector<0x80?-1:int(selector-0x80);}
    void start(PlayerObject&,StateEntryActor&,const GroundStateFrame&,unsigned id,unsigned variant) const; //163590
    // 163610. Returns true when the finished script ends in 169918, i.e.
    // the caller must run the ordinary recovery.
    bool step(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&) const;
    const ScriptRow* current(const StateEntryActor&) const;
    // The plain attack callback shared by script-only fighters (e.g. Gaoh's
    // 1fe2f0): 163570 selector lookup, 1696c8 strength, clear 260, then
    // 163590 or 169810. Returns true when the caller must run 169810.
    bool enterAttack(PlayerObject&,StateEntryActor&,const GroundStateFrame&) const;
    // 1493c0 with the 168c18 lock table; shared with character callbacks.
    void queue(PlayerObject&,StateEntryActor&,const GroundStateFrame&,int action) const;
private:
    const ScriptTables& tables_;
    const StateCallbacks* callbacks_; // 14efb8 rage gain of entry event 28
    bool enterRow(PlayerObject&,StateEntryActor&,const GroundStateFrame&) const; //164460
    bool rowComplete(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&) const; //164600
    void visitRow(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&) const; //1638e8
    void entryEvent(PlayerObject&,StateEntryActor&,const GroundStateFrame&,uint8_t type) const; //164c58
    void selfDrain(StateEntryActor&,const GroundStateFrame&,int32_t amount,int32_t rage) const; //165580
};
}
