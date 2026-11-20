#pragma once
#include <functional>
#include "auxiliary_objects.hpp"
#include "state_entry.hpp"
#include <span>
#include <cstdint>

namespace ss6 {
class PlayerObject;
struct StageCamera;
struct StateEntryActor;
struct ActorCommandInput;
struct GroundStateFrame;
struct StateEntryContext;
class ScriptEngine;
// Fighters whose attack callback (table 4e8fe8) is only the common stub
// 163570 -> 163590 / 169810, with every move driven by 163610.
class FighterTables;
bool isScriptFighterAttack(const FighterTables&,unsigned character,uint32_t handler);
// Returns true when the caller must run the ordinary 169810 recovery.
class AuxiliaryObjects;struct TaggedTaskPools;
// Task callbacks of objects created by the character branches (1f5860, 1fe280).
bool isScriptFighterObject(uint32_t handler);
// The object's owner, for callbacks that create further objects (16c408/16c5f8 on o.118).
struct ScriptObjectOwner {
    std::span<uint32_t> registry;unsigned player;StateEntryActor& actor;const AuxiliaryObject& body;
    const ActorCommandInput* input=nullptr; // the owner's sampled features
    std::function<void()> enterStateNow{}; // 1491e0 on the owner (Shizumaru's returning umbrella)
    const StageCamera* camera=nullptr; // 140040 stage words
    const StateEntryActor* opponent=nullptr; // 1400a8(owner seat)
    const AuxiliaryObject* opponentBody=nullptr; // the opponent's body words
};
void updateScriptFighterObject(AuxiliaryObjects&,TaggedTaskPools&,uint32_t task,const ScriptObjectOwner&);
// 205860: Gen-an's chain head (body+128) and three links (body+12c/130/134) laid out from the owner.
void genanChainLayout(TaggedTaskPools&,const PlayerObject& body,const StateEntryActor&);
// 206db0: Nicotine's chain (same object slots, his own spacing).
void nicotineChainLayout(TaggedTaskPools&,const PlayerObject& body,const StateEntryActor&);
bool updateScriptFighterAttack(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&,
                               StateEntryContext&,const ScriptEngine&);
}
