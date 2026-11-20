#pragma once
#include <optional>
#include "player_object.hpp"
#include "state_entry.hpp"
#include "state_callbacks.hpp"
#include "ordinary_rules.hpp"
#include "reaction.hpp"
#include "knockdown.hpp"
#include "effect_runtime.hpp"
#include "match_progress.hpp"
#include "auxiliary_objects.hpp"
#include "stage_camera.hpp"
#include "script_engine.hpp"
#include "victim_script.hpp"
#include "haohmaru_special.hpp"
#include <stdexcept>

namespace ss6 {
// A recognized source state without a native implementation. A live VS
// session can leave this fight safely instead of resuming a partial update.
struct UnportedFighterState : std::runtime_error {
    UnportedFighterState(unsigned character,int table,int state)
        :std::runtime_error("Unported state "+std::to_string(table)+"/"+std::to_string(state)+" for fighter "+std::to_string(character)),
         character(character), table(table), state(state) {traceOrigin();}
    unsigned character;
    int table,state;
    // SS6_DEBUG_HANDLER prints the throwing call stack (development aid).
    static void traceOrigin();
};
//Borrow actual battle services:152440 moves BOTH bodies and152600 creates
//a weapon in this player's48-slot registry using the shared entry task pool.
struct WeaponLockActorContext {
    PlayerObject& opponentBody;
    StateEntryActor& opponent;
    const StageCamera& camera;
    int32_t cachedDistance; //battle+144, published by the prior stage phase
    AuxiliaryObjects& objects;
    std::span<uint32_t> objectTasks;
};
class SoundSelection;
struct BattleRoundState;
struct GroundStateFrame {
    float opponentX=0;
    int remainingSeconds=-1;
    bool training=false;
    int trainingRage=0;
    //Required for attack registration; the caller owns live auxiliary-object
    //identities, including the first kind3 object's command field.
    CallbackContext* objects=nullptr;
    uint32_t opponentFlags23c=0x1000;
    int opponentAuxiliary=0; //151728's actual auxiliary query result
    BattleEffects* effects=nullptr;
    GameRandom* random=nullptr;
    //Victory selection reads the live player's wins/requiredWins at entry.
    const PlayerMatchStats* matchStats=nullptr;
    PlayerMatchStats* opponentStats=nullptr;
    unsigned opponentCharacter=0;
    int opponentSelected=-1; // the opponent's a14 (selected id); -1 = opponentCharacter
    unsigned opponentSystem=0; // 168750 reads the attacker's spirit for weapon loss.
    WeaponLockActorContext* weaponLock=nullptr;
    SoundSelection* sound=nullptr;
    ActorCommandInput* opponentInput=nullptr;
    const ActorCommandInput* ownInput=nullptr; // this actor's features (Kim's lock reads 1720b0 on the victim) // Air throw commits the opponent's state on the thrower's turn.
    std::function<void(unsigned)> spawnMikiri; // 16e5f0 uses the stance-specific armed or unarmed afterimage.
    std::function<void(int)> captureDamage;
    std::span<uint32_t> opponentObjectTasks{};
    std::span<uint32_t> ownObjectTasks{}; // this seat's 48-slot registry (140c68 registers here)
    unsigned seat=0; // actor+a24
    std::function<void()> suppressCaptureObjects; // 168400 gates existing attackers when a pair takes control.
    std::function<void()> seizeOpponent; // GroundStateRuntime::seizeOpponent for this actor
    std::function<void()> clearInputs;
    std::function<uint32_t(unsigned,unsigned)> spawnDescriptor; // 16d2b0(cb, id, variant): object handle // 178920(seat) press latches, then 1797a8 this actor's command buffers
    std::function<void(unsigned,uint32_t,unsigned,float,float,float,float)> startWorld; // 124430(id, flags, seat, x, y, z, scale)
    std::function<void()> startExplosion; // 11f248, exceptional release when the opponent is already defeated
    std::function<void(bool)> issenMusic; // 13ab78 stops on capture; 13aaf8(1) restarts on surviving set
    std::function<void(uint8_t)> scriptEvent; // 164c58 entry events that spawn character objects (33, 34)
    BattleRoundState* battle=nullptr; // Wall impact replaces the live camera command queue.
    const InputSystemConfig* config=nullptr; // The actor's own spirit, for script rage gains (165580).
    std::function<void(unsigned,uint32_t,float,float,float)> worldEffect; // 1242c0(id, facing, x, y, z), scale 1
    TaggedTaskPools* pools=nullptr; // the shared object pools behind weaponLock->objectTasks (140d78 searches)
};
//Ordinary ground moves, heavy knockdown and KO in149d08, with native callbacks.
//Input selection happens before visit; commitAction/body commit follow it. This
//keeps tail state entry separate from next-visit callback/action registration.
class GroundStateRuntime {
public:
    explicit GroundStateRuntime(const std::filesystem::path& assets):entries_(assets),callbacks_(assets),ordinary_(assets),reactions_(assets),scriptTables_(assets),victimTables_(assets) {}
    //After animation/stage and before input sampling. Timer predicates use
    //the PREVIOUS published features, as in the original scheduler.
    void prepareInput(StateEntryActor&,const PermissionActor&,const ActorCommandInput&,CallbackContext&,int32_t distance) const;
    //142580..142618: after contact requests, before body animation. This
    //installs the original temporary callback, not just a zero clock delta.
    void afterContacts(PlayerObject&,StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&) const;
    //14b880 runs after input requests and before149d08, even while input
    //is locked. Returns the number of original diagnostic events.
    static unsigned beforeCallbacks(PlayerObject&,StateEntryActor&);
    DownedEvents visit(PlayerObject&,StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&);
    //149918 is separate from149d08. First-round initialization captures
    //history between them; each actor must retain its own pending action.
    static void commitAction(PlayerObject&,StateEntryActor&);
    static void captureBody(const PlayerObject&,StateEntryActor&);
    // 169810 for an actor outside its own visit (Iroha's 200710 recovers the attacker); turns by opponentX.
    static void takeLoser(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&); // 20a9a0
    static void recoverStanding(PlayerObject& o,StateEntryActor& a,float opponentX);
    // The opponent enters capture state 2/96 (254 = this fighter, body +124 = 0)
    // and 1491e0 runs on it immediately, inside this actor's visit.
    void seizeOpponent(StateEntryActor&,StateEntryContext&,const GroundStateFrame&) const;
    // 1491e0 on an actor outside its own visit (e.g. inside an object task):
    // context.player/opponentFlagsB8 are those of `player` for the call.
    void enterStateNow(PlayerObject&,StateEntryActor&,ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,
                       unsigned player,uint32_t& opponentFlagsB8) const;
    static void restoreBody(PlayerObject&,const StateEntryActor&);
    static bool supports(int table,int index);
    const StateEntryRules& entryRules() const {return entries_;}
    const ScriptEngine& scripts() const {return scripts_;}
    const FighterTables& fighterTables() const {return victimTables_.fighters();}
    uint8_t damageFlags(const StateEntryActor& a) const {return entries_.descriptor(2,a.stateIndex(),a.damageCharacterA18)[0];}
private:
    int formQueueDepth_=0; // the outermost visit applies 14d788 (see visit)

    StateEntryRules entries_;
    StateCallbacks callbacks_;
    OrdinaryRules ordinary_;
    ReactionTables reactions_;
    ScriptTables scriptTables_;
    ScriptEngine scripts_{scriptTables_,&callbacks_};
    VictimTables victimTables_;
    // Table-B rows 0..2 of the whirlwind form (row 0 adopts the delivering
    // object, flag 40, and requests object ACT 535) for the victim's source.
    std::optional<WhirlwindRows> whirlwindRows(const StateEntryActor& victim) const;
    void begin(PlayerObject&,StateEntryActor&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&);
    void beginAttack(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    void beginDamage(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&);
    DownedEvents downedCallback(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    DownedEvents knockoutCallback(PlayerObject&,StateEntryActor&,const GroundStateFrame&,bool entering=false);
    static void minaWinnerHold(PlayerObject&,StateEntryActor&,StateEntryContext&);
    void endingCallback(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    void weaponLockCallback(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    void callback(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    static void recover(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    static void recoverGuard(PlayerObject&,StateEntryActor&);
    static void contactPause(PlayerObject&,StateEntryActor&);
};
}
