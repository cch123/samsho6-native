#pragma once
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
#include <stdexcept>

namespace ss6 {
// A recognized source state without a native implementation. A live VS
// session can leave this fight safely instead of resuming a partial update.
struct UnportedFighterState : std::runtime_error {
    UnportedFighterState(unsigned character,int table,int state)
        :std::runtime_error("Unported state "+std::to_string(table)+"/"+std::to_string(state)+" for fighter "+std::to_string(character)),
         character(character), table(table), state(state) {}
    unsigned character;
    int table,state;
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
    unsigned opponentSystem=0; // 168750 reads the attacker's spirit for weapon loss.
    WeaponLockActorContext* weaponLock=nullptr;
    SoundSelection* sound=nullptr;
    ActorCommandInput* opponentInput=nullptr; // Air throw commits the opponent's state on the thrower's turn.
    std::function<void(unsigned)> spawnMikiri; // 16e5f0 uses the stance-specific armed or unarmed afterimage.
    std::function<void(int)> captureDamage;
    std::span<uint32_t> opponentObjectTasks{};
    std::function<void()> suppressCaptureObjects; // 168400 gates existing attackers when a pair takes control.
    std::function<void()> startExplosion; // 11f248, exceptional release when the opponent is already defeated
    std::function<void(bool)> issenMusic; // 13ab78 stops on capture; 13aaf8(1) restarts on surviving set
    BattleRoundState* battle=nullptr; // Wall impact replaces the live camera command queue.
};
//Ordinary ground moves, heavy knockdown and KO in149d08, with native callbacks.
//Input selection happens before visit; commitAction/body commit follow it. This
//keeps tail state entry separate from next-visit callback/action registration.
class GroundStateRuntime {
public:
    explicit GroundStateRuntime(const std::filesystem::path& assets):entries_(assets),callbacks_(assets),ordinary_(assets),reactions_(assets) {}
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
    static void restoreBody(PlayerObject&,const StateEntryActor&);
    static bool supports(int table,int index);
    uint8_t damageFlags(const StateEntryActor& a) const {return entries_.descriptor(2,a.stateIndex(),a.damageCharacterA18)[0];}
private:
    StateEntryRules entries_;
    StateCallbacks callbacks_;
    OrdinaryRules ordinary_;
    ReactionTables reactions_;
    void begin(PlayerObject&,StateEntryActor&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&);
    void beginAttack(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    void beginDamage(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&);
    DownedEvents downedCallback(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const InputSystemConfig&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    DownedEvents knockoutCallback(PlayerObject&,StateEntryActor&,const GroundStateFrame&,bool entering=false);
    void endingCallback(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    void weaponLockCallback(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&,bool entering=false);
    void callback(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    static void recover(PlayerObject&,StateEntryActor&,const GroundStateFrame&);
    static void recoverGuard(PlayerObject&,StateEntryActor&);
    static void contactPause(PlayerObject&,StateEntryActor&);
};
}
