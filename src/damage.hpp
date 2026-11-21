#pragma once
#include "scalar_float.hpp"
#include <array>
#include <filesystem>

namespace ss6 {
struct StateEntryActor;
// Local human fighters with Rage, Shin, Zan, Ten, Zero or Ken spirit.
// CPU difficulty modifiers and other spirit tables use separate rules.
struct DamageActor {
    int32_t swordCurrent=0, swordMaximum=0, rageState=0;
    int32_t life=200, defenseAdjustment=0;
    bool armed=true;
    int32_t rageAmount=0, rageDecay=0;
    int32_t swordWait=0; // actor+0x130: whole update calls, not 8.8 time.
    uint32_t flags23c=0x1000, flags248=0;
    uint8_t attackStrength=0; // 0x1696c8: stateFlags bit4 ->2, bit2 ->1, else0.
    int32_t system=0; // actor+0x10c, owned independently by each player.
    uint32_t state194=0;
    int32_t rageCharge=0; // actor+0x12c accumulates whole held updates.
    int32_t systemAmount140=0;
    uint8_t concentrationUsed11c=0;
    unsigned character=0;
};
struct DamageResult { ScalarFloat sourceAmount; int32_t damage; };
class DamageTables {
public:
    explicit DamageTables(const std::filesystem::path& assets);
    DamageResult calculate(int32_t auxiliary,const DamageActor& source,const DamageActor& target,
                           uint32_t mode=0) const;
    // 0x1a41b8 for ordinary strikes and character specials. The amount is
    // separate from the guard handler’s fixed chip and life commit.
    // the original queues it separately, then 0x151968 updates life/KO state.
    int32_t applyOrdinaryContact(int32_t auxiliary,DamageActor& source,DamageActor& target,bool guard,bool sourceSpecialMove=false,uint32_t sourceMode=0) const;
    //14ec80: ordinary configuration (no forced gauge options).
    // Sword is refilled, rage generally carries, and swordWait is preserved.
    void resetOrdinaryRoundMeters(DamageActor& actor) const;
    void beginTenExplosion(StateEntryActor&,int system=3) const; // 11f248
    // 14da6c: an attack on a dodge afterimage is valued as damage but only
    // changes the defender's secret-technique meter.
    void gainKenSecret(int auxiliary,const DamageActor& source,const DamageActor& target,unsigned mode,
                       StateEntryActor& defender,int factoryLimit=32) const;
    static void spendKenGuard(StateEntryActor&); // 1a4a00, ordinary Ken factory row.
    void transferMeditation(StateEntryActor&) const; // 11e880
    void activateConcentration(StateEntryActor&) const; // 11f028
    void updateCriticalRage(StateEntryActor&,int system) const; // 14ba18 during actor update
    // Original 0x11e760 meter paths. Call once at the gauge scheduler phase,
    // independently of animation delta. Raw rage phases0..3 are supported;
    // explosion meters have their own object. chargeFilled reports the
    // manual Zan threshold crossing that emits a shake and sound once.
    //Returns true only for rage2->3, whose caller must publish11e6f0(2,player).
    bool advanceOrdinaryMeters(DamageActor& actor,int stateTable,int stateIndex,
                               uint32_t flags104,uint32_t& flags108,bool roundTransition=false,bool* chargeFilled=nullptr) const;
    int32_t decay(int system,unsigned character) const;
    // 14ee14: the sword-gauge capacity while rage is raised (system row +0x1c).
    int32_t raisedSwordLimit(int system) const {return systems_.at(unsigned(system))[7]*256;}
private:
    std::array<int32_t,59> rules_{};
    std::array<std::array<int32_t,7>,51> characters_{};
    std::array<std::array<int32_t,10>,9> systems_{}; // 0x50dee0: systems 0..8 (8 = the companion fighters 44..47)
    std::array<ScalarFloat,12> constants_{};
};
} // namespace ss6
