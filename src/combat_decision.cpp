#include "combat_decision.hpp"
#include <bit>
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace ss6 {
static bool systemDisablesGuard(const DefenseSnapshot& target) {
    if (target.system==6) {
        if (!target.system6DescriptorByteC) throw std::runtime_error("System 6 defense requires its selected descriptor");
        if (*target.system6DescriptorByteC==0x28) return true;
    }
    return target.system==8;
}
uint8_t selectDefense(const CollisionPlayer& source,const DefenseSnapshot& target) {
    // The caller supplies the effective table, state, and flags from 1500a8/1500d0/150158.
    uint8_t result=0;
    if (target.actorFlags244&0x80000) {
        result=target.actorFlags23c&0x10 ? 4 : 1;
    } else if (target.stateTable==2) {
        if (target.stateIndex==8) result=3;
        else if (target.stateIndex==6) result=4;
        // Original SLTIU excludes negative signed-halfword state indices.
        else if (uint32_t(int32_t(target.stateIndex))<6) {
            const bool useField=target.fieldA20==0 || target.fieldC8==0x24 || target.fieldC8==0x25;
            if (useField) result=target.field3C0 ? 2 : 1;
            else result=target.stateIndex>=3 ? 2 : 1;
        }
    } else if (target.stateTable==0) {
        if (target.stateIndex==47 || target.stateIndex==53) result=3;
        else if (target.stateIndex==8) result=4;
        else {
            if (target.stateIndex==6 || target.stateIndex==11) result=1;
            else if (target.stateIndex==7 || target.stateIndex==13) result=2;
            // This state-flag override also applies to states whose initial
            // result was zero. Do not reduce it to a standing/crouching test.
            if (target.stateFlags&0x80) {
                if (target.field39C) result=1;
                else if (target.field398) result=2;
            }
        }
    }
    if ((result==1 || result==2) && systemDisablesGuard(target)) result=0;
    if (result==3 || result==4) return result;
    if (result==1 && !(source.objectFlags108&8)) return 1;
    if (result==2 && !(source.objectFlags108&4) && !(source.objectFlags104&0x08000000)) return 2;
    return 0;
}
static void validateIndex(int index) {
    // The original table contains only -1/0/1. Byte-wide helpers support
    // 0..7 too; reject unintended aliases from MIPS variable-shift masking.
    if (index<-1 || index>7) throw std::runtime_error("Invalid contact consumption bit");
}
ProjectileContact projectileContact(const ContactEvent& event,const CollisionPlayer& source,
                                    const CollisionPlayer& target,const ContactMarks& sourceMarks) {
    // 0x156820 runs before the generic consumed-bit gate. A projectile
    // strike can therefore reach a player whose hit flag is already set.
    if ((sourceMarks.flags104&0x06000000) || source.owner==target.owner)
        return ProjectileContact::None;
    if (event.route==5 && (target.objectKind==2||target.objectKind==5)) return ProjectileContact::ReflectProjectile;
    // 156820 shares the impact path for projectiles, companions and kind 5.
    auto auxiliary=[](unsigned kind){return kind==2||kind==3||kind==5;};
    if (!auxiliary(source.objectKind)) return ProjectileContact::None;
    if (target.objectKind<2) {
        if (event.route==1) return ProjectileContact::Route1Player;
        if (event.route==4) return ProjectileContact::Route4Player;
        if (event.route==7) return ProjectileContact::StrikePlayer;
    }
    if (event.route==7 && auxiliary(target.objectKind)) return ProjectileContact::ClashProjectiles;
    return ProjectileContact::None;
}
bool markProjectileClash(ContactMarks& target,uint8_t sourcePause,uint8_t targetPause) {
    target.consumed|=2;
    return !sourcePause && !targetPause;
}
bool contactConsumed(const ContactMarks& object,int index) {
    validateIndex(index);
    if (object.objectKind>=2) return true;
    return index!=-1 && ((object.consumed>>index)&1);
}
void markContactConsumed(ContactMarks& object,int index) {
    validateIndex(index);
    if (index==-1) return;
    object.consumed|=uint8_t(1u<<index);
    if (index==0) {
        object.flags104|=0x02000000;
        if (object.flags108&0x80) object.flags104|=0x04000000;
    }
}
bool ContactRegistry::add(uint32_t identity,uint32_t character,uint32_t action,ContactMarks& object) {
    if (objects_.size()>=162) throw std::runtime_error("Original collision object capacity exceeded");
    if (object.flags104&0x00400000) return false;
    bool flag=(action-0xd1u)<10;
    if (character==39 && (action==0xd3 || action==0xd6)) flag=false;
    // 0x153450 updates this attack flag even on duplicate registration, but
    // leaves the consumed byte intact on that duplicate. The persistent
    // 0x02000000/0x04000000 flags have a separate lifetime and stay untouched.
    if (flag) object.flags104|=0x08000000;
    else object.flags104&=~uint32_t(0x08000000);
    if (std::find(objects_.begin(),objects_.end(),identity)!=objects_.end()) return false;
    object.consumed=0;objects_.push_back(identity);
    return true;
}
CombatTables::CombatTables(const std::filesystem::path& assets) {
    std::ifstream in(assets/"combat_consumption.bin",std::ios::binary);
    for (auto& v:indices_) {
        uint32_t bits=0;
        for (unsigned shift=0;shift<32;shift+=8) {
            const int b=in.get();
            if (b==EOF) throw std::runtime_error("Missing or truncated combat consumption table");
            bits|=uint32_t(b)<<shift;
        }
        v=std::bit_cast<int32_t>(bits);validateIndex(v);
    }
    if (in.peek()!=EOF) throw std::runtime_error("Unexpected combat consumption table length");
}
std::array<int,2> CombatTables::consumptionIndices(unsigned route) const {
    if (route>=12) throw std::runtime_error("Invalid contact route");
    return {indices_[route*2],indices_[route*2+1]};
}
ContactDecision inspectContactDecision(const CombatTables& tables,const ContactEvent& event,
                                      const CollisionPlayer& source,const DefenseSnapshot& target,
                                      const ContactMarks& a,const ContactMarks& b) {
    if (event.route!=7) return {DecisionKind::OtherRoute};
    if ((a.objectKind>3 && a.objectKind!=5) || b.objectKind>=2) return {DecisionKind::OtherRoute};
    const auto indices=tables.consumptionIndices(event.route);
    // 0x154918 tests consumed bits before route 7's extra source flags.
    if (a.objectKind<2 && (contactConsumed(a,indices[0]) || contactConsumed(b,indices[1])))
        return {DecisionKind::AlreadyConsumed};
    if (a.flags104&0x06000000) return {DecisionKind::SourceBlocked};
    if (source.objectFlags108!=a.flags108 || source.objectFlags104!=a.flags104)
        throw std::runtime_error("Contact decision snapshots disagree on source flags");
    const auto defense=selectDefense(source,target);
    return {defense ? DecisionKind::GuardBranch : DecisionKind::HitBranch,defense};
}
} // namespace ss6
