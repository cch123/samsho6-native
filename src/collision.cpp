#include "asset_files.hpp"
#include "collision.hpp"
#include "fighter_resource_path.hpp"
#include "fighter_roster.hpp"
#include <fstream>
#include <stdexcept>
#include <utility>

namespace ss6 {
JudgmentFields decodeJudgment(uint32_t word) {
    const auto field=(word>>19)&127, quotient=field/6;
    return {word>>26,quotient>>2,quotient&3,field%6,(word>>18)&1,(word>>7)&2047,word&127};
}
CollisionTables::CollisionTables(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"collision_00.bin"),std::ios::binary);
    if (!in.read(reinterpret_cast<char*>(bytes_.data()),bytes_.size()) || in.peek()!=EOF)
        throw std::runtime_error("Missing or invalid resource-00 collision tables");
    auto readProjectileTable=[&](const char* name,auto& bytes) {
        std::ifstream f(resolveAsset(assets/name),std::ios::binary);
        if(!f.read(reinterpret_cast<char*>(bytes.data()),bytes.size()) || f.peek()!=EOF)
            throw std::runtime_error("Missing or invalid projectile table: "+std::string(name));
    };
    readProjectileTable("projectile_descriptor_flags.bin",projectileFlags_);
    readProjectileTable("projectile_hitstop.bin",sharedHitstop_);
    for(unsigned id:playableFighterIds) {
        if(!id)continue;
        auto& table=characterClasses_.at(id);loaded_[id]=true;
        const auto path=fighterResourcePath(assets,"collision",id);
        std::ifstream f(resolveAsset(path),std::ios::binary);
        if(!f.read(reinterpret_cast<char*>(table.data()),table.size())||f.peek()!=EOF)
            throw std::runtime_error("Invalid fighter collision table: "+path.string());
    }
}
bool CollisionTables::sharesProjectileHitstop(unsigned character,unsigned action) const {
    // 1690b0 stores an 8-bit resource and a little-endian 16-bit ACT per row.
    for(size_t i=0;i<sharedHitstop_.size();i+=4)
        if(sharedHitstop_[i]==character && (sharedHitstop_[i+2]|unsigned(sharedHitstop_[i+3])<<8)==action)return true;
    return false;
}
uint8_t CollisionTables::classByte(unsigned type,unsigned profile,unsigned offset) const {
    if(type>=64)throw std::out_of_range("Invalid six-bit JDG type");
    if(type<36)return bytes_[type*2+offset];
    const auto local=(type-36)*2+offset;
    if(profile==0)return bytes_[396+local];
    if(profile>=loaded_.size()||!loaded_[profile])throw std::runtime_error("Unsupported character collision profile");
    return characterClasses_[profile][local];
}
uint8_t CollisionTables::classFor(uint32_t type,unsigned profile) const {
    const auto category=classByte(type,profile,0);
    if (category>=18) throw std::runtime_error("Undefined JDG class in character profile");
    return category;
}
bool CollisionTables::usesAttackDamage(unsigned type,unsigned profile) const {
    return classByte(type,profile,1)==0xff;
}
uint8_t CollisionTables::route(uint8_t a, uint8_t b) const {
    if (a>=18 || b>=18) throw std::runtime_error("Invalid collision class");
    return bytes_[72+a*18+b];
}

static bool ordinaryFilter(const CollisionPlayer& a, const CollisionPlayer& b,
                           const ContactSide& ja, const ContactSide& jb) {
    // Original 0x153cd8. These checks are
    // directional: swapping source and target changes the eligibility.
    if (a.objectFlags104&0x06000000) return false;
    if (a.objectKind>=2 || b.objectKind>=2) {
        // Only a class-4 projectile attacking a player consults the actor.
        // The player/player damage-state exceptions below do not apply here.
        if (a.objectKind>=2 && b.objectKind<2 && ja.category==4)
            return !(jb.fields.low7&2) && b.field1c8<=0 && b.stateTable!=2 && !(b.actorFlags&0x10);
        return true;
    }
    if (ja.category==4) {
        if ((jb.fields.low7&2) || (b.field1c8>0 && jb.category!=13) || (b.actorFlags&0x10)) return false;
        if (b.stateTable==2 && (b.stateIndex<10 || b.stateIndex>12)) return false;
    } else if (ja.category==17 && !(b.actorFlags&0x10)) return false;
    if (jb.category==9 || jb.category==10) {
        if (ja.fields.group==3 || ja.fields.group==5) return false;
        return a.actorFlags&0x1000;
    }
    if (jb.category==16) return ja.fields.group!=3 && (a.actorFlags&0x1000);
    return true;
}
// 11e268 also recognizes kind 9 on the birth tick, before an ACT can set flags.
static bool isDecoy(const CollisionPlayer& p) {return p.objectKind==9 || (p.objectFlags108&0x01000000);}
static bool allow(uint8_t route, const CollisionPlayer& a, const CollisionPlayer& b,
                  const ContactSide& ja, const ContactSide& jb) {
    switch (route) {
        case 0: return a.objectKind<2 && b.objectKind<2 && !(a.objectFlags104&0x02000000);
        case 1: return !(a.objectFlags108&8);
        case 2:
            if ((a.objectFlags108&1) && jb.category!=13) return false;
            return ordinaryFilter(a,b,ja,jb);
        case 3: case 4: case 7: case 8: return ordinaryFilter(a,b,ja,jb);
        case 5: return (b.objectKind==2||b.objectKind==5) && b.objectTypeD0!=-1 && !(b.descriptorFlagsA&0x10);
        case 6: case 11: return true;
        case 9:
            return a.objectKind<2 && b.objectKind<2 && !(a.objectFlags104&0x06000000) && !((a.objectFlags108|b.objectFlags108)&1) &&
                   !((a.actorFlags|b.actorFlags)&0x10) && (a.actorFlags&0x1000) && (b.actorFlags&0x1000) &&
                   ja.fields.group!=3 && jb.fields.group!=3;
        case 10: return !isDecoy(a) && isDecoy(b) &&
                        (ja.category==2 || ja.category==3 || ja.category==4);
        case 255: return false;
        default: throw std::runtime_error("Unknown collision route");
    }
}
static ContactSide contactSide(const CollisionTables& tables, const CollisionPlayer& object,
                               const Judgment& judgment, uint8_t slot) {
    auto fields=decodeJudgment(judgment.metadata);
    if (object.objectKind==2 && (object.objectTypeD0==0xaa || object.objectTypeD0==0xb4))
        fields.remainder=8;
    return {object.judgmentFlags,fields,tables.classFor(fields.type,object.judgmentProfile),slot,judgment.index};
}

void collectContacts(const CollisionTables& tables, const CollisionPlayer& a,
                     const CollisionPlayer& b, uint8_t aSlot, uint8_t bSlot,
                     std::vector<ContactEvent>& queue) {
    for (const auto* p:{&a,&b}) {
        if (p->objectKind>3 && p->objectKind!=5 && p->objectKind!=9) throw std::runtime_error("Unsupported collision object kind");
        if (p->judgments.size()>7 || (p->judgmentFlags&7)!=p->judgments.size())
            throw std::runtime_error("Collision snapshot disagrees with ACT judgment count");
    }
    if (a.owner==b.owner || (a.objectKind<2 && (a.actorFlags&0x400)) || (b.objectKind<2 && (b.actorFlags&0x400)) ||
        (a.objectFlags104&0x00800000) || (b.objectFlags104&0x01000000) ||
        isDecoy(a)) return;
    for (const auto& aj:a.judgments) {
        const auto ja=contactSide(tables,a,aj,aSlot);
        const auto ar=worldRect(aj,a.x,a.y,a.mirrorX,a.mirrorY);
        for (const auto& bj:b.judgments) {
            const auto jb=contactSide(tables,b,bj,bSlot);
            const uint8_t route=isDecoy(b) ? 10 : tables.route(ja.category,jb.category);
            if (!allow(route,a,b,ja,jb)) continue;
            Intersection intersection;
            if (!intersect(ar,worldRect(bj,b.x,b.y,b.mirrorX,b.mirrorY),intersection)) continue;
            if (queue.size()>=162) throw std::runtime_error("Original contact queue capacity exceeded");
            const int32_t extra=route==7 && a.objectKind<2 ? (a.stateFlags&4 ? 2 : bool(a.stateFlags&2)) : 0;
            queue.push_back({route,intersection.centerX,intersection.centerY,extra,aj.auxiliary,intersection.width,ja,jb});
        }
    }
}
void orderContacts(std::vector<ContactEvent>& queue) {
    // 0x1544a0 uses selection-sort swaps. A stable sort would change the
    // ordering of equal-priority contacts after a smaller event moves forward.
    for (size_t i=0;i+1<queue.size();++i) {
        size_t least=i;
        for (size_t j=i+1;j<queue.size();++j) if (queue[j].route<queue[least].route) least=j;
        if (least!=i) std::swap(queue[i],queue[least]);
    }
}
} // namespace ss6
