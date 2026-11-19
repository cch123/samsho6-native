#include "damage.hpp"
#include "state_entry.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

namespace ss6 {
DamageTables::DamageTables(const std::filesystem::path& assets) {
    std::ifstream stream(assets/"damage_00.bin",std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(stream)),{});
    if (bytes.size()!=352) throw std::runtime_error("Expected 352-byte damage_00.bin");
    size_t offset=0;
    auto word=[&]() {
        const auto* p=bytes.data()+offset;
        offset+=4;
        return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);
    };
    for (auto& value:rules_) value=std::bit_cast<int32_t>(word());
    offset+=28; // Resource 00 is duplicated here in the historical single-fighter fixture.
    // The legacy damage fixture contains the Rage row before its constants.
    // The full 0x50dee0 table is already packaged for input permissions.
    offset+=40;
    for (auto& value:constants_) value.bits=word();
    // 1a3c18 indexes attack power by the source, 1a3f90 indexes defense
    // by the target. Each character can therefore be on either controller.
    std::ifstream characterTable(assets/"callback_character_parameters.bin",std::ios::binary);
    bytes.assign(std::istreambuf_iterator<char>(characterTable),{});
    if(bytes.size()!=51*28)throw std::runtime_error("Invalid character damage table");
    offset=0;
    for(auto& character:characters_)for(auto& value:character)value=std::bit_cast<int32_t>(word());
    std::ifstream spiritTable(assets/"permission_systems.bin",std::ios::binary);
    bytes.assign(std::istreambuf_iterator<char>(spiritTable),{});
    if(bytes.size()!=9*40) throw std::runtime_error("Expected 360-byte permission_systems.bin");
    offset=0;
    for(auto& spirit:systems_)
        for(auto& value:spirit) value=std::bit_cast<int32_t>(word());
}
DamageResult DamageTables::calculate(int32_t auxiliary,const DamageActor& source,const DamageActor& target,
                                    uint32_t mode) const {
    if (mode!=0 && mode!=0x10 && mode!=0x11 && mode!=1 && mode!=2)
        throw std::runtime_error("Damage mode outside admitted scalar subset");
    if (auxiliary<0 || source.swordCurrent<0 || source.swordMaximum<0 || target.life<0)
        throw std::runtime_error("Invalid ordinary damage state");
    const auto& attacking=systems_.at(source.system);
    const auto& defending=systems_.at(target.system);
    auto f=ScalarFloat::integer;
    auto percent=constants_[3];
    // 0x1a3c18: maintain instruction order, including multiplying by the
    // original inexact 0.01 constant. Algebraic percentage simplification
    // can change integer damage at truncation boundaries.
    if (source.state194==0x260001 && !(mode&0x10) && (source.system==3||source.system==4)) {
        // A connected Issen replaces the JDG attack value with a value
        // interpolated from the remaining explosion bar before normal scaling.
        const bool concentration=source.concentrationUsed11c!=0;
        const int rule=(concentration?0xe0:0xd8)/4;
        const auto amount=concentration?source.systemAmount140:source.rageAmount;
        auto spread=f(rules_[rule+1]-rules_[rule]).mul(f(amount));
        auxiliary=f(rules_[rule]).add(spread.div(f(concentration?0xc800:0xb800))).truncate();
    }
    auto base=f(auxiliary).mul(f(rules_[0xe8/4]).div(constants_[2]));
    auto damage=base.mul(f(attacking[3]).mul(percent));
    if (mode!=1 && mode!=2) {
        int32_t current=std::min(source.swordCurrent,source.swordMaximum-0xa00);
        int32_t capacity=attacking[6]*256;
        int32_t denominator=source.swordMaximum>capacity ? capacity : (attacking[6]-10)*256;
        auto minimum=f(rules_[0x98/4]).mul(percent);
        auto ratio=f(current).div(f(denominator));
        auto factor=ratio.mul(constants_[4].sub(minimum)).add(minimum);
        if (source.swordCurrent>=source.swordMaximum) factor=factor.mul(f(attacking[0]).mul(percent));
        damage=damage.mul(factor);
    }
    if (uint32_t(source.rageState)-1<2) {
        damage=damage.mul(f(attacking[2]).mul(percent));
        damage=damage.mul(f(characters_.at(source.character)[target.armed ? 3 : 4]).mul(percent));
    }
    auto minimum=base.mul(f(rules_[0])).mul(percent);
    if (damage.less(minimum)) damage=minimum;
    auto sourceAmount=damage;
    // 0x1a3f90: the life bucket is calculated with DIV then MUL, not integer
    // life/20. Preserve this even though many ordinary values coincide.
    auto targetPercent=constants_[5];
    damage=damage.mul(f(200-defending[4]).mul(targetPercent));
    damage=damage.mul(f(200-characters_.at(target.character)[target.armed ? 1 : 2]).mul(targetPercent));
    int bucket=f(target.life).div(f(200)).mul(constants_[6]).truncate();
    bucket=std::min(bucket,9);
    damage=damage.mul(f(200-rules_[1+bucket]).mul(targetPercent));
    if (target.defenseAdjustment)
        damage=damage.mul(f(target.defenseAdjustment+100).mul(targetPercent));
    return {sourceAmount,damage.add(constants_[8]).truncate()};
}
int32_t DamageTables::applyOrdinaryContact(int32_t auxiliary,DamageActor& source,DamageActor& target,bool guard,bool sourceSpecialMove,uint32_t sourceMode) const {
    if (source.attackStrength>2 || target.rageAmount<0 || target.rageAmount>0xb800)
        throw std::runtime_error("Contact meter state outside ordinary subset");
    // 155d38/155f38 pass 1/0x11 for a projectile touching the opponent.
    // A later scripted slam goes through 1413d8, which passes 2. The sword
    // ratio exclusion compares the complete mode, including the guard bit.
    const uint32_t mode=(guard?0x10u:0u)|sourceMode;
    const int32_t damage=calculate(auxiliary,source,target,mode).damage;
    if (guard) {
        // A blocked swing consumes sword energy once, protected by the
        // actor flag. Normal hit consumption is deliberately not gated here.
        if (!(source.flags23c&0x40000000)) {
            const unsigned cost=source.state194==0x150001 ? 0xa8/4 : 0x9c/4+source.attackStrength;
            source.swordCurrent=std::max(0,source.swordCurrent-rules_[cost]*256);
            source.flags23c|=0x40000000;
        }
    } else {
        source.swordCurrent=std::max(0,source.swordCurrent-damage*256);
    }
    auto gainRage=[&](DamageActor& actor,int points){
        actor.rageAmount+=points*256;
        if(actor.rageAmount>=0xb800) {
            actor.rageAmount=0xb800;actor.rageState=1;actor.rageDecay=decay(actor.system,actor.character);
            actor.swordCurrent=actor.swordMaximum=systems_[actor.system][7]*256;
        }
    };
    const auto f=ScalarFloat::integer;
    const auto onHit=[&](unsigned side,int coefficient){
        return f(damage).mul(f(coefficient*systems_[side][1])).mul(constants_[9]).truncate()+rules_[0xd4/4];
    };
    if(!target.rageState && target.system!=5 && (!guard || sourceSpecialMove))
        gainRage(target,guard?rules_[0xd4/4]:onHit(target.system,characters_.at(target.character)[5]));
    if(!source.rageState && source.system==5) {
        // Ken builds its lower gauge by landing attacks. On a block each
        // contact has a fixed reward even if sword consumption already ran.
        const int blocked=source.state194==0x150001?4:source.attackStrength+1;
        gainRage(source,guard?blocked:onHit(source.system,characters_.at(source.character)[6]));
    }
    if (!guard&&(target.flags248&8)) target.flags248|=0x10000;
    return damage;
}
int32_t DamageTables::decay(int system,unsigned character) const {
    auto f=ScalarFloat::integer;
    const auto duration=f(characters_.at(character)[0]).mul(f(systems_.at(system)[9])).mul(constants_[10]);
    return constants_[11].div(duration).truncate();
}
void DamageTables::beginTenExplosion(StateEntryActor& a,int system) const {
    if(system==4) {
        // Zero's explosion always has the full 420-update nominal duration.
        // It spends concentration even when the fighter never activated it.
        a.rageState120=2;a.rageAmount124=0xb800;a.rageDecay128=0xb800/rules_[0x88/4];
        a.swordCurrent134=a.swordMaximum138=systems_[4][8]*256;
        a.systemState13c=4;a.systemTime144=0;
        return;
    }
    const auto f=ScalarFloat::integer;
    const auto one=f(1);
    auto fraction=one.sub(f(a.fieldA30).div(f(200)));
    // 11f330 snaps missing health of at least 99% to a full gauge. In
    // particular 2 HP and 3 HP have different initial amounts.
    if(!fraction.less({0x3f7d70a4}))fraction=one;
    a.rageState120=2;
    a.rageAmount124=fraction.mul(f(0xb800)).truncate();
    // At full health the EE performs +0/+0, then CVT.W.S saturates to
    // INT_MAX. The bar survives startup but expires on the first eligible
    // update. The usual finite arithmetic model deliberately rejects 0/0.
    a.rageDecay128=fraction.bits==0?INT32_MAX:
        f(a.rageAmount124).div(f(rules_[0x84/4]).mul(fraction)).truncate();
    a.swordCurrent134=a.swordMaximum138=systems_[3][8]*256;
}
void DamageTables::spendKenGuard(StateEntryActor& a) {
    // Full defense costs 40 of the lower gauge and restores the normal
    // 95-point sword ceiling even when the gauge was previously full.
    if(a.rageAmount124<40*256)return;
    a.rageAmount124-=40*256;a.rageState120=0;a.swordMaximum138=95*256;
    a.swordCurrent134=std::min(a.swordCurrent134,a.swordMaximum138);
}
void DamageTables::gainKenSecret(int auxiliary,const DamageActor& source,const DamageActor& target,unsigned mode,
                                  StateEntryActor& defender,int factoryLimit) const {
    const auto f=ScalarFloat::integer;
    const auto damage=calculate(auxiliary,source,target,mode).damage;
    const auto threshold=f(0x6400);
    auto stored=f(defender.systemMeter158);
    auto gain=f(damage).mul(f(rules_[0xc8/4])).mul(constants_[3]);
    const auto sum=stored.add(gain);
    if(threshold.less(sum)) {
        // This routine compares 8.8 storage to an as-yet unshifted gain.
        // Keep the original units and the crossing branch at 100 points.
        if(stored.less(threshold)) { gain=sum.sub(threshold);stored=threshold; }
        gain=gain.mul(f(1).sub(stored.sub(threshold).div(threshold)));
    }
    defender.systemMeter158+=std::max(1,gain.truncate())*256;
    if(defender.systemMeter158>0xc800)defender.systemMeter158=0xc800;
    else if(defender.bonusState14c==1&&defender.systemMeter158>=factoryLimit*256) {
        defender.bonusTime150=0;defender.bonusState14c=0;
    }
}
void DamageTables::transferMeditation(StateEntryActor& a) const {
    if(!(a.flags23c&0x8000)||a.rageState120||!a.rageAmount124||a.systemAmount140>=0xc800)return;
    const auto f=ScalarFloat::integer;
    const auto rule=f(rules_[0xbc/4]),character=f(characters_.at(a.character)[5]),percent=ScalarFloat{0x38d1b717};
    int gain=50;
    int cost=rule.mul(f(50)).mul(character).mul(percent).truncate();
    if(a.rageAmount124<cost) {
        cost=a.rageAmount124;
        gain=f(cost).div(rule.mul(character).mul(percent)).truncate();
    }
    if(a.systemAmount140>0x6400)
        gain=f(gain).mul(f(0xc800-a.systemAmount140)).div(f(0x6400)).truncate();
    a.systemAmount140=std::min(0xc800,a.systemAmount140+std::max(1,gain));
    a.rageAmount124-=cost;
}
void DamageTables::activateConcentration(StateEntryActor& a) const {
    const auto f=ScalarFloat::integer;
    const auto capacity=f(0xc800),rageCapacity=f(0xb800);
    const auto minimum=f(rules_[0x8c/4]*256);
    if(f(a.systemAmount140).mul(rageCapacity).div(capacity).less(minimum))
        a.systemAmount140=minimum.mul(capacity).div(rageCapacity).truncate();
    a.systemState13c=3;a.systemTime144=a.systemAmount140;
    const auto duration=f(a.systemAmount140).div(capacity).mul(f(rules_[0x90/4]));
    a.systemDecay148=f(a.systemAmount140).div(duration).truncate();
    a.rageAmount124=0;a.rageState120=3;
}
void DamageTables::updateCriticalRage(StateEntryActor& a,int system) const {
    // 14ace0 tests living HP inclusively through 20. 14edc0 refills sword
    // only on entry from an inactive rage, even though the rage bar is
    // continually restored on every eligible low-health actor update.
    if(system==2 && a.fieldA30>0 && a.fieldA30<=20 && a.rageState120<2) {
        if(a.rageState120<=0)a.swordCurrent134=a.swordMaximum138=systems_[2][7]*256;
        a.rageState120=1;a.rageAmount124=0xb800;a.rageDecay128=0;a.rageCharge12c=0;
    } else if(a.rageState120==1 && !a.rageDecay128) {
        a.rageDecay128=decay(system,a.character);
    }
}
void DamageTables::resetOrdinaryRoundMeters(DamageActor& a) const {
    const auto& spirit=systems_.at(a.system);
    if(a.rageState<0||a.rageState>3)throw std::runtime_error("Invalid round rage phase");
    // An exhausted explosion becomes disabled and loses its amount/decay.
    // Already-disabled state3 is left alone by the original reset helper.
    if(a.rageState==2) {a.rageState=3;a.rageAmount=a.rageDecay=0;}
    // 14f780 makes Zan discard ordinary rage between rounds. The
    // exhausted phases above bypass this reset in 14ecd4.
    if(a.system==2 && a.rageState<2)a.rageState=a.rageAmount=a.rageDecay=0;
    a.swordCurrent=a.swordMaximum=spirit[a.rageState==1?7:6]*256;
}
bool DamageTables::advanceOrdinaryMeters(DamageActor& a,int table,int state,
                                         uint32_t flags104,uint32_t& flags108,bool roundTransition,bool* chargeFilled) const {
    if(chargeFilled)*chargeFilled=false;
    const auto& spirit=systems_.at(a.system);
    if (a.rageState<0||a.rageState>3||a.rageAmount<0||a.rageAmount>0xb800||
        a.rageDecay<0||a.swordCurrent<0||a.swordMaximum<=0||a.swordWait<0||
        a.attackStrength>2)
        throw std::runtime_error("Invalid ordinary gauge state");
    bool phaseChanged=false;
    // Expiry is strictly below zero. Reaching exactly zero keeps rage for
    // this update, including its sword capacity. Damage-state pauses decay.
    if (((a.rageState==1&&a.system!=5)||a.rageState==2)&&table!=2&&!roundTransition&&
        !(a.rageState==2&&table==1&&state==36)) {
        a.rageAmount-=a.rageDecay;
        if (a.rageAmount<0) {
            phaseChanged=a.rageState==2;
            a.rageAmount=0;a.rageState=phaseChanged?3:0;
            a.swordMaximum=spirit[6]*256;
            a.swordCurrent=std::min(a.swordCurrent,a.swordMaximum);
        }
    }
    if(a.system==2 && !a.rageState && (a.flags23c&0x10000)) {
        // 11eb94 integrates the previous charge counter and increments it
        // even on the crossing update. Exactly 0xb800 remains inactive until
        // the next positive gain, unlike a hit filling the same meter.
        auto f=ScalarFloat::integer;
        const auto gain=f(a.rageCharge).mul(f(rules_[0xc0/4])).mul(f(characters_.at(a.character)[5])).mul(constants_[9]);
        ++a.rageCharge;
        a.rageAmount+=gain.truncate();
        if(a.rageAmount>0xb800) {
            a.rageAmount=0xb800;a.rageState=1;a.rageDecay=decay(a.system,a.character);
            a.swordCurrent=a.swordMaximum=spirit[7]*256;
            if(chargeFilled)*chargeFilled=true;
        }
    }
    if ((flags108&0x10)&&!(flags104&0xc0000)) {
        const unsigned cost=table==1&&state==21 ? 0xa8/4 : 0x9c/4+a.attackStrength;
        a.swordCurrent=std::max(0,a.swordCurrent-rules_[cost]*256);
        flags108&=~uint32_t(0x10);
        // A whiff-cost update does not also decrement the recovery wait.
    } else if (a.swordWait) --a.swordWait;
    else if (a.swordCurrent<a.swordMaximum) {
        auto f=ScalarFloat::integer;
        const auto percent=constants_[3];
        int32_t amount=f(spirit[5]).mul(f(256)).mul(percent).truncate();
        const int32_t missing=a.swordMaximum-a.swordCurrent;
        if (missing<=30*256) amount=f(amount).mul(f(missing)).div(f(30*256)).truncate();
        amount=std::max(3,f(amount).mul(f(rules_[0xb0/4])).mul(percent).truncate());
        if (table==1) amount=f(amount).mul(f(rules_[0xac/4]).mul(percent)).truncate();
        a.swordCurrent+=amount;
    }
    a.swordCurrent=std::min(a.swordCurrent,a.swordMaximum);
    return phaseChanged;
}
} // namespace ss6
