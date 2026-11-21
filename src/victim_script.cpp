#include <cstdio>
#include <cstdlib>
#include "victim_script.hpp"
#include "script_engine.hpp"
#include "andrew_ammo.hpp"
#include "nakoruru_capture.hpp"
#include "battle_round.hpp"
#include "knockout.hpp"
#include "contact_presentation.hpp"
#include "knockdown.hpp"
#include "sound_selection.hpp"
#include "script_fighter.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <span>
#include <fstream>
#include <stdexcept>
#include <utility>

#include "soft_double.hpp"
#include <cmath>
namespace ss6 {
namespace {
std::vector<uint8_t> readAll(const std::filesystem::path& p) {
    std::ifstream f(p,std::ios::binary);
    if(!f)throw std::runtime_error("Missing "+p.string());
    return {std::istreambuf_iterator<char>(f),{}};
}
uint32_t word(const uint8_t* p){return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
int16_t half(const uint8_t* p){return int16_t(uint16_t(p[0]|p[1]<<8));}
// 168690: the attacker keeps 244 bit 0x1000 (no object freeze in 168400).
bool keepsObjects(unsigned c,unsigned k) {
    switch(c) {
    case 0:case 18:return k<3;
    case 4:return k==1||k==6;
    case 25:case 29:return k==0;
    default:return false;
    }
}
unsigned strength(const StateEntryActor& a) { //1696c8
    const auto f=a.effectiveFlags();
    return (f&4)?2:(f&2)?1:0;
}
void request(StateEntryActor& a,int table,int index){a.pendingTable=int16_t(table);a.pendingIndex=int16_t(index);}
[[noreturn]] void unportedAt(const StateEntryActor& v,int line) {
    if(std::getenv("SS6_DEBUG_HANDLER"))std::fprintf(stderr,"victim_script.cpp:%d\n",line);
    throw UnportedFighterState(v.character,2,v.stateIndex());
}
#define unported(v) unportedAt(v,__LINE__)
}

VictimTables::VictimTables(const std::filesystem::path& assets):fighters_(assets) {
    const auto data=readAll(assets/"victim_rows.bin");
    if(data.size()<51*8)throw std::runtime_error("Invalid victim_rows.bin");
    size_t at=51*8;
    for(unsigned c=0;c<51;++c) {
        auto& t=tables_[c];t.base=word(&data[c*8]);
        const auto n=word(&data[c*8+4]);
        if(at+size_t(n)*20>data.size())throw std::runtime_error("Truncated victim_rows.bin");
        for(unsigned i=0;i<n;++i,at+=20) {
            const uint8_t* p=&data[at];VictimRow r;
            r.id=p[0];r.victimAct=half(p+2);r.attackerAct=half(p+4);r.childAct=half(p+6);
            r.wait={p[8],p[9],p[10]};r.end={p[11],p[12],p[13]};
            r.parameter=half(p+14);r.damage=half(p+16);r.flags=p[18];r.type=p[19];
            t.rows.push_back(r);
        }
    }
    if(at!=data.size())throw std::runtime_error("Trailing bytes in victim_rows.bin");
}
uint32_t VictimTables::find(unsigned character,unsigned id) const {
    const auto& t=tables_.at(character);
    for(size_t i=0;i<t.rows.size();++i) {
        if(t.rows[i].id==id)return t.base+uint32_t(20*i);
        if(t.rows[i].id==0xff)return 0;
    }
    return 0;
}
const VictimRow& VictimTables::row(uint32_t address) const {
    for(const auto& t:tables_)
        if(address>=t.base&&address<t.base+20*t.rows.size()&&!((address-t.base)%20))return t.rows[(address-t.base)/20];
    throw std::runtime_error("Victim row address outside table B");
}

namespace {
// 1699f8: completion test that always consumes the ACT hold marker 104:100.
bool holdReached(PlayerObject& b,const StateEntryActor& a) {
    const auto c=b.timeline.clock();
    const bool done=actionEnded(b,a.queuedActionA3c)||(c.flags104&0x100);
    b.setFlags(c.flags104&~0x100u,c.flags108);
    return done;
}
struct Script {
    PlayerObject& body;StateEntryActor& v;StateEntryContext& context;const GroundStateFrame& f;const VictimTables& tables;
    const ScriptEngine& scripts;StateEntryActor& a;PlayerObject& sourceBody;
    AuxiliaryObject* child() const {return v.bodyField124?&context.tasks.objects.at(v.bodyField124-1):nullptr;}
    const VictimRow& row() const {return tables.row(v.registry28c[12]+20*v.registry28c[0]);}
};
// 166ce8: follow o (x, y) with the latched offset of the current ACT record.
void follow(Script& s,float ox,float oy) {
    auto& r=s.v.registry28c;
    const auto& m=s.body.timeline.record().motion;
    if(m.kind>=5&&m.kind<=8){r[4]=uint32_t(m.values[0])<<16;r[5]=uint32_t(m.values[1])<<16;}
    const int dx=std::bit_cast<int32_t>(r[4])>>16,dy=std::bit_cast<int32_t>(r[5])>>16;
    s.body.timeline.setPosition(capture::shifted(ox,(s.body.timeline.clock().objectFlags&0x80000)?float(-dx):float(dx)),
                                capture::shifted(oy,float(dy)));
    s.body.timeline.stopMotion();
}
// 165f18: enter row r[0] (exact order).
AuxiliaryObject& attackerOwnedEffect(Script& s,unsigned act);
// 16e818: the attacker's marker over the cursed victim (Mizuki 0x21f, Nicotine 0x256); an existing
// one is reused. Task callback 16e9b8 deletes it when the victim's timer 20 runs out.
void curseMarker(Script& s) {
    const unsigned c=s.a.character;
    if(c!=0x1b&&c!=0x27)return;
    const unsigned act=c==0x1b?0x21f:0x256;
    AuxiliaryObject* o=nullptr;
    for(auto t:s.f.opponentObjectTasks)if(t) { // 140d78(A, n, -1): any kind, registry order
        auto& x=s.context.tasks.objects.at(s.context.tasks.tasks.at(t-1)[7]-1);
        if(x[0x24/4]==act){o=&x;break;}
    }
    if(c==0x1b) {
        if(o)s.f.weaponLock->objects.request(*o,act,false,true);
        else o=&attackerOwnedEffect(s,act);
    } else {
        if(!o)o=&attackerOwnedEffect(s,act);
        (*o)[0x104/4]|=0x1000;
    }
    auto& x=*o;
    x[0x108/4]=((x[0x108/4]|0x20000)&~0x1000u)&~0x2000u;
    x[0xec/4]=x[0xf0/4]=0;
    const auto anchor=s.f.weaponLock->objects.anchor(s.v.character,4); // 16e788(o, V, 4)
    const auto m=s.body.timeline.motion();
    x[0x40/4]=std::bit_cast<uint32_t>(m.x);x[0x44/4]=std::bit_cast<uint32_t>(m.y);
    x[0xec/4]=ScalarFloat{x[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
    x[0xf0/4]=ScalarFloat{x[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;
    x[0xf0/4]=ScalarFloat{x[0xf0/4]}.add(ScalarFloat{0x41400000u}).bits; // + 12.0
    s.context.tasks.tasks.at(x[1]-1)[0]=0x16e9b8;
}
void enterRow(Script& s) {
    using namespace capture;
    auto& v=s.v;auto& a=s.a;auto& r=v.registry28c;
    if(r[0]==r[1])return;
    const auto& row=s.row();
    const unsigned str=r[3];
    if(row.damage) { // 1413d8(V.a24, damage, child ? child : A.body, 1)
        // With a child (Galford's Poppy rows 0x19/0x1a) 1413d8 credits the object: on a lethal
        // hit 1576e8 then classifies the finish from the object (14dc00), not the attacker's
        // state. Damage and life are identical; that finish category is not yet distinguished.
        if(!s.f.captureDamage)unported(v);
        s.f.captureDamage(row.damage);
    }
    if(row.flags&8){splitAnchor(s.body,s.sourceBody);r[4]=r[5]=0;}
    else if(row.flags&0x10) {
        // 166c28(reg, V, child): the victim takes the child's position, then
        // both move 0.2 (5f11c8) apart along the child's facing.
        if(auto* c=s.child()) {
            const float x=std::bit_cast<float>((*c)[0x40/4]),y=std::bit_cast<float>((*c)[0x44/4]);
            const float split=((*c)[0x38/4]&0x80000)?0.2f:-0.2f;
            (*c)[0x40/4]=std::bit_cast<uint32_t>(shifted(x,split));
            s.body.timeline.setPosition(shifted(x,-split),y);
            s.body.timeline.stopMotion();r[4]=r[5]=0;
        }
    }
    r[7]=r[8]=r[9]=0;
    if(row.victimAct!=-1) {
        const int act=0x500+row.victimAct;
        queue(v,(row.type==6||row.type==0x58)?act:act+!(v.flags23c&0x1000));
        if(row.flags&4)s.body.pendingFlags|=8;
        if((row.flags&0x18)&&(row.type==3||row.type==5||row.type==0x1c)) {
            // 166db0(reg, V, V.a3c, 0): latch record 0 of the queued ACT when it is a motion kind 5..8.
            auto* bank=s.body.timeline.bank();
            if(!bank)throw std::runtime_error("166db0 requires the victim's action bank");
            const auto& m=bank->get(unsigned(v.queuedActionA3c)).record(0).motion;
            if(uint16_t(m.kind)-5u<4){r[4]=uint32_t(m.values[0])<<16;r[5]=uint32_t(m.values[1])<<16;}
        }
    }
    // 0x4a keeps the attacker ACT only while it is in attack state 80..83.
    const bool attackerKept=!(row.type==0x4a&&!(a.stateTable()==1&&unsigned(a.stateIndex()-80)<4));
    if(row.attackerAct!=-1&&attackerKept) {
        int act=row.attackerAct;
        if(row.type==0x29)act+=a.characterBytesF14[2];
        if(row.type==0x41)act+=(2-int(a.characterBytesF14[7]))*2; // f1b
        if(row.flags&2) {
            if(row.type==1)act+=2*int(str);
            queue(a,act+!(a.flags23c&0x1000));
        } else {
            if(row.type==1)act+=int(str);
            queue(a,act);
        }
        if(row.flags&4)s.sourceBody.pendingFlags|=8;
    }
    if(row.childAct!=-1) {
        // 11d908(child, act, 0, 0); the original has no null check.
        auto* c=s.child();
        if(!c||!s.f.weaponLock)throw std::runtime_error("Victim row child ACT without a child object");
        if(!(*c)[0x04/4]) { // a freed companion (zeroed slot): the queued request only stores its words
            if((*c)[0x24/4]!=unsigned(row.childAct)){(*c)[0xc4/4]=unsigned(row.childAct);(*c)[0x104/4]|=1;(*c)[0xc0/4]=0;}
        } else s.f.weaponLock->objects.request(*c,unsigned(row.childAct),false,false);
        if((*c)[0x14/4]==4&&row.childAct==0x328)(*c)[0x38/4]^=0x80000; // 11db88
        if(row.flags&4)(*c)[0xfc/4]|=8u<<16; // child.FE |= 8
    }
    if(row.flags&0x80)loseWeapon(s.body,v,s.context,s.f);
    // 166e98 type handler.
    const auto battle=[&]()->BattleRoundState& {
        if(!s.f.battle)throw std::runtime_error("Victim script row requires the live battle");
        return *s.f.battle;
    };
    // Constants 5f11e8 (32.0) and 5f11ec (20.0), each add separately rounded.
    const bool mirror=s.sourceBody.timeline.clock().objectFlags&0x80000;
    const auto shiftX=[&](PlayerObject& o,float dx){const auto m=o.timeline.motion();o.timeline.setPosition(shifted(m.x,dx),m.y);};
    // 16c408(cb, act, 0, 1): an attacker-owned kind-6 effect (tag 0x1396) at
    // the attacker's body with a forced ACT request and 108 |= 0x2000;
    // 16e788(o, V, 0) then moves it onto the victim's body anchor.
    const auto attackerEffect=[&](unsigned act,bool place,bool anchored=true)->AuxiliaryObject* {
        auto& world=*s.f.weaponLock;
        const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,1-s.context.player,a.flags23c,
                                               s.sourceBody.childParentWords(),0x1396,6,0);
        if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
        auto& o=s.context.tasks.objects.at(handle-1);
        world.objects.request(o,act,false,true);o[0x108/4]|=0x2000;
        if(place) {
            const auto m=s.body.timeline.motion();
            o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x44/4]=std::bit_cast<uint32_t>(m.y);
            if(anchored) { // 16e788(o, V, 0)
                const auto anchor=world.objects.bodyAnchor(v.character);
                o[0xec/4]=ScalarFloat{o[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
                o[0xf0/4]=ScalarFloat{o[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;
            } else o[0xec/4]=o[0xf0/4]=0; // 16e788(o, V, -1)
        }
        return &o;
    };
    using F=ScalarFloat;
    const auto camera=[&]()->const StageCamera& {return s.f.weaponLock?s.f.weaponLock->camera:battle().camera;};
    const auto setMirror=[](PlayerObject& o,bool mirrored) {
        const auto c=o.timeline.clock();
        o.timeline.setObjectFlags(mirrored?c.objectFlags|0x80000:c.objectFlags&~0x80000u,c.flags104,c.flags108);
    };
    switch(row.type) {
    case 0x0a: // 166ff8: 1414b8, 1414f8(3, e)
        battle().camera.commands.clear();battle().camera.appendCommand(3,uint32_t(row.parameter));
        break;
    case 0x04:case 0x0b: // 167018: 1414b8, 1414f8(6 + (V seat + 1) % 2, e)
        battle().camera.commands.clear();battle().camera.appendCommand(6+(s.context.player+1)%2,uint32_t(row.parameter));
        break;
    case 0x36: { // 16793c: the attacker leaps toward the far camera edge
        auto& o=s.sourceBody;o.timeline.stopMotion();o.pendingFlags|=8;
        auto m=o.timeline.motion();
        m.vy=0x10c28f;m.ay=int32_t(0xffff4ccdu);
        const bool mirrored=o.timeline.clock().objectFlags&0x80000;
        // 5f11f8 = 40, 5f11fc = 65536, 5f11d4 = 48; cvt.w.s truncates.
        const auto edge=mirrored?F::integer(camera().left).add(F::integer(40)):F::integer(camera().right).sub(F::integer(40));
        const int32_t vx=edge.sub(F{std::bit_cast<uint32_t>(m.x)}).mul(F::integer(65536)).div(F::integer(48)).truncate();
        m.vx=mirrored?-vx:vx;
        o.timeline.setMotion(m);
        battle().camera.commands.clear();battle().camera.appendCommand(0,0);
        v.flags244|=0x20000;a.flags244|=0x20000;
        break;
    }
    case 0x37: { // 167a30: the victim is placed 104 beyond the camera edge the attacker faces, at height 80
        const bool mirrored=s.sourceBody.timeline.clock().objectFlags&0x80000;
        const auto x=mirrored?F::integer(camera().left).sub(F::integer(104)):F::integer(camera().right).add(F::integer(104));
        s.body.timeline.setPosition(std::bit_cast<float>(x.bits),80.f);
        setMirror(s.body,mirrored);
        battle().camera.commands.clear();battle().camera.appendCommand(3,0x28);
        v.flags244|=0x40000;
        break;
    }
    case 0x38: { // 167af8: the attacker lands mid-screen, the victim 48 in front of it
        const int32_t mid=(camera().left+camera().right)/2; // sra after the sign fix: truncation toward zero
        s.sourceBody.timeline.setPosition(float(mid),0.f);
        const auto ax=F{std::bit_cast<uint32_t>(float(mid))};
        const bool mirrored=s.sourceBody.timeline.clock().objectFlags&0x80000;
        s.body.timeline.setPosition(std::bit_cast<float>((mirrored?ax.sub(F::integer(48)):ax.add(F::integer(48))).bits),0.f);
        break;
    }
    case 0x14:case 0x15: { // 1670c8 / 167110: the attacker moves onto the victim plus 168ea0(V, 4 / 5)
        s.sourceBody.timeline.stopMotion();
        const auto m=s.body.timeline.motion();s.sourceBody.timeline.setPosition(m.x,m.y);
        const auto anchor=s.f.weaponLock->objects.anchor(v.character,row.type==0x14?4:5); // 16e788(A.body, V, 4 / 5)
        s.sourceBody.historyOffsetEc=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(s.sourceBody.historyOffsetEc)}.add(ScalarFloat::integer(anchor[0])).bits);
        s.sourceBody.historyOffsetF0=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(s.sourceBody.historyOffsetF0)}.add(ScalarFloat::integer(anchor[1])).bits);
        break;
    }
    case 0x35: { // 167910: 14f148 and 14ef38(V+10c, -1000) on the victim; A.244 |= 0x20000000
        const auto* callbacks=s.scripts.callbacks();
        if(!callbacks||!s.f.config)throw std::runtime_error("Victim row type 0x35 requires the victim's spirit tables");
        callbacks->resetRage(v,*s.f.config);
        callbacks->addRage(v,*s.f.config,-1000); // 14ef38 passes non-positive amounts unscaled
        a.flags244|=0x20000000u;
        break;
    }
    case 0x24: // 167444: 16c408(cb, 0x213, 0, 1), not placed
        attackerEffect(0x213,false);
        break;
    case 0x26: // 167460: 14a978(V, 1), then 11db88 toggles the victim's facing
        GroundStateRuntime::captureBody(s.body,v);v.opponentX=s.sourceBody.timeline.motion().x;v.faceOpponent(true);
        GroundStateRuntime::restoreBody(s.body,v);
        setMirror(s.body,!(s.body.timeline.clock().objectFlags&0x80000));
        break;
    case 0x27: { // 16747c: the delivering object joins the victim, plus the attacker's 0x222
        auto* child=s.child();
        if(!child)throw std::runtime_error("Victim row 0x27 needs the delivering object");
        (*child)[0x108/4]|=0x20000;
        {const auto anchor=s.f.weaponLock->objects.bodyAnchor(v.character); // 16e788(child, V, 0)
         const auto m=s.body.timeline.motion();
         (*child)[0x40/4]=std::bit_cast<uint32_t>(m.x);(*child)[0x44/4]=std::bit_cast<uint32_t>(m.y);
         (*child)[0xec/4]=ScalarFloat{(*child)[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
         (*child)[0xf0/4]=ScalarFloat{(*child)[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;}
        auto& o=*attackerEffect(0x222,true,false); // 16e788(o, V, -1)
        o[0x108/4]&=~0x2000u;
        // o+8 = 1681c0: the effect's own callback (native dispatch reads the task word).
        o[2]=0x1681c0;s.context.tasks.tasks.at(o[1]-1)[0]=0x1681c0;
        a.bodyLatch12c=uint32_t(&o-s.context.tasks.objects.data())+1; // A.body+12c
        break;
    }
    case 0x28: { // 1674ec: the attacker's body+12c object leaves; 0x224 at the victim, on the ground
        if(!a.bodyLatch12c)throw std::runtime_error("Victim row 0x28 needs the attacker's body+12c object");
        s.context.tasks.objects.at(a.bodyLatch12c-1)[0x108/4]|=0x1000;
        auto& o=*attackerEffect(0x224,true,false);o[0x44/4]=0;
        break;
    }
    case 0x29: { // 167530: two effects chosen by the attacker's byte f16
        const unsigned n=a.characterBytesF14[2];
        for(unsigned act:{0x26du+n,0x26eu+n}){auto& o=*attackerEffect(act,true);o[0x108/4]&=~0x20000u;}
        break;
    }
    case 0x13: // 1670b0: 14a890(V, e, -1): element byte 252, then 14b120's colour and attached effect
        v.contactKind252=uint8_t(row.parameter);v.fieldA2c=v.contactKind252;
        if(v.contactKind252) {
            v.landingCount253=(v.landingCount253+1)&15;
            if(!s.f.battle)throw std::runtime_error("Victim row 0x13 needs the battle");
            spawnElementHurt(s.f.weaponLock->objects,*s.f.battle,s.context.player,s.body,v);
        }
        break;
    case 0x18:attackerEffect(0x233,true,false);break; // 167154 -> 16713c
    case 0x4e:attackerEffect(0x23f,true,false);break; // 167ed4 -> 16713c (Rasetsu Galford)
    case 0x57:case 0x58:attackerEffect(0x23d,true,false);break; // 168090 -> 16713c
    case 0x56: // 168078: the attacker stands on the victim's x at y = 0
        s.sourceBody.timeline.setPosition(s.body.timeline.motion().x,0.f);
        break;
    case 0x4f:attackerEffect(0x28a,true,false);break; // 167ee8 -> 16713c
    case 0x50: { // 167efc: both face away from the camera centre (camera+4) by the attacker's side
        const bool right=ScalarFloat{std::bit_cast<uint32_t>(s.f.weaponLock->camera.x)}.less(ScalarFloat{std::bit_cast<uint32_t>(s.sourceBody.timeline.motion().x)});
        const auto ka=s.sourceBody.timeline.clock(),kv=s.body.timeline.clock();
        s.sourceBody.timeline.setObjectFlags(right?ka.objectFlags|0x80000u:ka.objectFlags&~0x80000u,ka.flags104,ka.flags108);
        s.body.timeline.setObjectFlags(right?kv.objectFlags&~0x80000u:kv.objectFlags|0x80000u,kv.flags104,kv.flags108);
        break;
    }
    case 0x51:case 0x5b: { // 1680e0: the victim is thrown back
        s.body.timeline.stopMotion();auto m=s.body.timeline.motion();
        m.vx=int32_t(0xfffd999au);m.vy=0x000a3333;m.ay=int32_t(0xffff8000u);s.body.timeline.setMotion(m);
        break;
    }
    case 0x52: { // 167f68: the victim is launched, then 1414b8 and 1414f8(8 + V seat, 0xf0)
        s.body.timeline.stopMotion();auto m=s.body.timeline.motion();
        m.vx=0x10000;m.vy=0x00106666;m.ay=int32_t(0xffff999au);s.body.timeline.setMotion(m);
        battle().camera.commands.clear();battle().camera.appendCommand(8+int(s.context.player),0xf0);
        break;
    }
    case 0x53: { // 167fa8: the attacker steps 140 forward (5f120c) and turns round
        const ScalarFloat x{std::bit_cast<uint32_t>(s.sourceBody.timeline.motion().x)},d=ScalarFloat::integer(140);
        const auto k=s.sourceBody.timeline.clock();const bool left=k.objectFlags&0x80000;
        s.sourceBody.timeline.setPosition(std::bit_cast<float>((left?x.sub(d):x.add(d)).bits),s.sourceBody.timeline.motion().y);
        s.sourceBody.timeline.setObjectFlags(left?k.objectFlags&~0x80000u:k.objectFlags|0x80000u,k.flags104,k.flags108);
        break;
    }
    case 0x54: { // 168018: the attacker leaps
        s.sourceBody.timeline.stopMotion();auto m=s.sourceBody.timeline.motion();
        m.vx=0x00024ccc;m.vy=0x00140000;m.ay=int32_t(0xffff6667u);s.sourceBody.timeline.setMotion(m);
        break;
    }
    case 0x55: { // 168050: the attacker's velocities are cleared, FE |= 8
        auto m=s.sourceBody.timeline.motion();m.vx=0;m.ax=0;m.vy=0;m.ay=0;s.sourceBody.timeline.setMotion(m);
        s.sourceBody.pendingFlags|=8;
        break;
    }
    case 0x4b:s.scripts.queue(s.body,v,s.f,0x242);break; // 167e90: 1493c0(V, 0x242, 0), including 168c18's action lock
    case 0x19:case 0x1a: { // 167168: the attacker's companion (Galford's Poppy) becomes the delivering object
        s.body.timeline.stopMotion();
        const float ax=s.sourceBody.timeline.motion().x;
        if(row.type==0x19) {
            const ScalarFloat x{std::bit_cast<uint32_t>(ax)},d=ScalarFloat::integer(22);
            s.body.timeline.setPosition(std::bit_cast<float>((mirror?x.sub(d):x.add(d)).bits),s.body.timeline.motion().y);
        } else s.sourceBody.timeline.setPosition(s.body.timeline.motion().x,s.sourceBody.timeline.motion().y);
        if(!a.auxiliaryObject04)throw std::runtime_error("Victim rows 0x19/0x1a need the attacker's companion");
        auto& p=s.context.tasks.objects.at(a.auxiliaryObject04-1);
        v.bodyField124=a.auxiliaryObject04;r[10]=a.auxiliaryObject04;
        p[0xe8/4]=p[0xdc/4]=p[0xe4/4]=0; //11db30
        // 147530 stores through p+4. The companion is never respawned mid-round (1efdc0's only caller is
        // 1a3220), so after an end op 23..25 freed it (the pool zeroes freed objects) the original stores
        // through task pointer 0, outside the game state; the other writes land in the freed slot as here.
        if(p[1])s.context.tasks.tasks.at(p[1]-1)[0]=0x147540; //147530
        {auto m=s.sourceBody.timeline.motion();m.vx=0;m.ax=0;s.sourceBody.timeline.setMotion(m);}
        p[0x50/4]=0;p[0x54/4]=0;
        if(row.type==0x1a) {
            const auto m=s.sourceBody.timeline.motion();
            p[0x40/4]=std::bit_cast<uint32_t>(m.x);p[0x44/4]=std::bit_cast<uint32_t>(m.y);
        }
        p[0x38/4]=(p[0x38/4]&~0x80000u)|(s.sourceBody.timeline.clock().objectFlags&0x80000); //11dbb8
        {const float x=s.body.timeline.motion().x;
         if(x<70.0f)s.body.timeline.setPosition(70.0f,s.body.timeline.motion().y);
         if(570.0f<s.body.timeline.motion().x)s.body.timeline.setPosition(570.0f,s.body.timeline.motion().y);}
        break;
    }
    case 0x39: { // 167b80: a curse timer on the victim (Mizuki 300, Nicotine 360) and 16e818's marker
        if(a.character==0x1b)v.timers[20]=0x12c*256;
        else if(a.character==0x27) {
            v.timers[20]=0x168*256;
            auto& o=*attackerEffect(0x255,true);(*&o)[0x108/4]|=0x20000;o[0x104/4]|=0x1000;
        }
        curseMarker(s);
        break;
    }
    case 0x3a: { // 167c0c
        auto& o=*attackerEffect(0x228,true,false);o[0x104/4]|=0x4000;
        break;
    }
    case 0x3b: { // 167c44: camera 3/0x82; the attacker lands in its idle pose
        battle().camera.commands.clear();battle().camera.appendCommand(3,0x82);
        s.sourceBody.timeline.stopMotion();
        s.sourceBody.timeline.setPosition(s.sourceBody.timeline.motion().x,0);
        capture::queue(a,!(a.flags23c&0x1000)?1:0); // 1494c0(A, 0, 1, 0)
        break;
    }
    case 0x3c:attackerEffect(0x229,true,false);break; // 167c84 -> 16713c: 16e788(o, V, -1)
    case 0x3d:attackerEffect(0x258,true,false);break; // 167c98
    case 0x2e: // 1676f0: camera command 10 for 0xb4
        battle().camera.commands.clear();battle().camera.appendCommand(10,0xb4);
        break;
    case 0x1d: // 167304: two attacker effects on the victim's anchor
        attackerEffect(0x220,true);attackerEffect(0x221,true);
        break;
    case 0x1e: { // 167350: the attacker's lasting effect, kept in the victim's body+134
        auto& o=*attackerEffect(0x284,true);
        o[0x38/4]=(o[0x38/4]&~0x80000u)|(s.sourceBody.timeline.clock().objectFlags&0x80000); //11dbb8
        o[0x108/4]=(o[0x108/4]|0x20000)&~0x2000u;
        s.body.scriptLatch134=uint32_t(&o-s.context.tasks.objects.data())+1; // the object's handle
        battle().camera.commands.clear();battle().camera.appendCommand(10,0x258);
        break;
    }
    case 0x1f:case 0x20:case 0x21:case 0x22:case 0x23: { // 1673b4
        auto& o=*attackerEffect(0x267+row.type,true);
        o[0x38/4]=(o[0x38/4]&~0x80000u)|(s.sourceBody.timeline.clock().objectFlags&0x80000); //11dbb8
        if(row.type==0x1f||row.type==0x23) {
            if(!s.body.scriptLatch134)throw std::runtime_error("Victim row needs the body+134 object");
            auto& kept=s.context.tasks.objects.at(s.body.scriptLatch134-1);
            if(row.type==0x1f)s.f.weaponLock->objects.request(kept,0x285,false,false);
            else {
                kept[0x108/4]|=0x1000;
                battle().camera.commands.clear();battle().camera.appendCommand(10,0x3c);
            }
        }
        break;
    }
    case 0x4c: // 167ea8: V.body.y = 107 (5f1208)
        s.body.timeline.setPosition(s.body.timeline.motion().x,107.f);
        break;
    case 0x40: { // child.x = V.x; stop(child) (no null check in the original)
        auto* c=s.child();
        if(!c)throw std::runtime_error("Victim row type 0x40 without a child object");
        (*c)[0x40/4]=std::bit_cast<uint32_t>(s.body.timeline.motion().x);AuxiliaryObjects::stop(*c);
        break;
    }
    case 0x43: // 167ce4: three attacker effects on the victim
        for(unsigned act:{0x260u,0x261u,0x262u})attackerEffect(act,true,false);
        break;
    case 0x44:attackerEffect(0x263,true,false);break; // 167d40
    case 0x45:attackerEffect(0x264,true,false);break; // 167d54
    case 0x46: { // 167d68: the attacker lands 80 (5f1204) in front of the victim's facing
        s.sourceBody.timeline.stopMotion();
        const bool mirrored=s.body.timeline.clock().objectFlags&0x80000;
        const ScalarFloat vx{std::bit_cast<uint32_t>(s.body.timeline.motion().x)},d=ScalarFloat::integer(80);
        s.sourceBody.timeline.setPosition(std::bit_cast<float>((mirrored?vx.sub(d):vx.add(d)).bits),0.f);
        break;
    }
    case 0x47: // 167db4
        for(unsigned act:{0x266u,0x267u,0x268u,0x265u})attackerEffect(act,true,false);
        break;
    case 0x31: // 167858
        attackerEffect((a.flags23c&0x100000)?0x288:0x24c,true);
        break;
    case 0x32: // 167884: the victim's script variant selects the ACT
        attackerEffect(0x241+r[3],true);
        break;
    case 0x33: // 16789c
        attackerEffect(0x25e,false);
        break;
    case 0x34: { // 1678a8
        // 16c4e0(A, 0x268, 0, 0): kind 6, tag 0x1392 + seat, 108 |= 0x1a000, at A's body.
        auto& world=*s.f.weaponLock;
        const unsigned seat=1-s.context.player;
        if(const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,seat,a.flags23c,
                                                  s.sourceBody.childParentWords(),0x1392 + seat,6,0)) {
            auto& o=s.context.tasks.objects.at(handle-1);
            world.objects.request(o,0x268,false,true);o[0x108/4]|=0x1a000;
        }
        (*attackerEffect(0x269,true))[0x108/4]|=0x20000;
        a.characterBytesF14[5]=0xff; // A.f19
        break;
    }
    case 0x00:s.body.timeline.stopMotion();s.sourceBody.timeline.stopMotion();break;
    case 0x02:a.flags244&=~0x20000u;break;
    case 0x07:a.flags23c|=0x20000000u;break;
    case 0x08:s.body.pendingFlags|=1;break;
    case 0x09: // 1e7b70(-1, 0x45); FE |= 0x80; 1242c0(e, V mirror, V.x, V.y, -50, 1)
        if(s.f.sound)s.f.sound->sample(-1,0x45);
        s.body.pendingFlags|=0x80;
        if(!s.f.worldEffect)throw std::runtime_error("Victim row type 9 requires the world-effect pool");
        s.f.worldEffect(unsigned(row.parameter),s.body.timeline.clock().objectFlags&0x80000,
                        s.body.timeline.motion().x,s.body.timeline.motion().y,-50.f);
        break;
    case 0x3e: // 167cac: 1414b8 then 1414f8(0, 0)
        battle().camera.commands.clear();battle().camera.appendCommand(0,0);
        break;
    case 0x3f: // 167cc0: 1414b8 only
        battle().camera.commands.clear();
        break;
    case 0x2d: // 1676dc: 1414b8, then 1414f8(10, 0x94)
        battle().camera.commands.clear();battle().camera.appendCommand(10,0x94);
        break;
    case 0x0c: // 167048: 1414b8 empties the camera queue, then 1414f8(10, e).
        battle().camera.commands.clear();battle().camera.appendCommand(10,row.parameter);
        break;
    case 0x48: // 167e34: Andrew gains a round (f1c, capped at 16) and shows it
    case 0x49: // 167e70: 23c bit 0x20000000; the shown count follows f1c
        if(row.type==0x48){auto& stock=a.characterBytesF14[8];++stock;if(stock>16)stock=16;}
        else a.flags23c|=0x20000000u;
        a.characterBytesF14[9]=a.characterBytesF14[8];
        if(!s.f.pools)throw std::runtime_error("Row types 48/49 require the live object pools");
        showAndrewAmmo(s.f.weaponLock->objects,*s.f.pools,s.f.opponentObjectTasks,1-s.context.player,a,s.sourceBody);
        break;
    case 0x16:case 0x59: {
        const float x=s.sourceBody.timeline.motion().x;
        s.body.timeline.setPosition(shifted(x,mirror?-48.f:48.f),s.body.timeline.motion().y);
        break;
    }
    case 0x2a: { // 1675ac
        // 16c408(cb, 0x24a, 0, 1): a kind-6 effect owned by the attacker,
        // then 16e788 places it on the victim's body.
        auto& world=*s.f.weaponLock;
        const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,1-s.context.player,a.flags23c,
                                               s.sourceBody.childParentWords(),0x1396,6,0);
        if(handle) {
            auto& o=s.context.tasks.objects.at(handle-1);
            world.objects.request(o,0x24a,false,true);o[0x108/4]|=0x2000;
            const auto m=s.body.timeline.motion();
            o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x44/4]=std::bit_cast<uint32_t>(m.y);
        }
        shiftX(s.sourceBody,mirror?32.f:-32.f);shiftX(s.body,mirror?-20.f:20.f);
        battle().camera.commands.clear();battle().camera.appendCommand(10,0x118);
        break;
    }
    case 0x2b: { // 167658: 139290(6, 0), 140930(5, 4), then move the victim.
        auto& b=battle();b.pause.request(6,0);
        b.timers.set(5,4,b.gauges.paused46a940?8:1);
        shiftX(s.body,mirror?20.f:-20.f);
        break;
    }
    case 0x4d:battle().pause.request(2,0);break; // 167ec0: 139290(2, 0)
    case 0x30: { // 16777c: the attacker 1 ahead of the victim on the floor, then two attacker effects 0x262 / 0x263
        const ScalarFloat vx{std::bit_cast<uint32_t>(s.body.timeline.motion().x)},one=ScalarFloat::integer(1);
        const bool attackerMirrored=s.sourceBody.timeline.clock().objectFlags&0x80000;
        s.sourceBody.timeline.setPosition(std::bit_cast<float>((attackerMirrored?vx.add(one):vx.sub(one)).bits),0.0f);
        a.flags244|=0x20000;
        for(unsigned act:{0x262u,0x263u}) { // 16c408(cb, act, 0, 1), 108 |= 0x20000, 11dff8(o, A.b0 + 1.0)
            auto& o=*attackerEffect(act,false);o[0x108/4]|=0x20000;
            o[0xb0/4]=ScalarFloat{s.sourceBody.childParentWords()[0xb0/4]}.add(one).bits;o[0x104/4]|=0x20000;
        }
        break;
    }
    case 0x2f: { // 167704: the victim 35 ahead of the attacker and 75 up; attacker 248 |= 0x100
        const auto am=s.sourceBody.timeline.motion();
        const ScalarFloat ax{std::bit_cast<uint32_t>(am.x)},ay{std::bit_cast<uint32_t>(am.y)};
        const auto x=(s.sourceBody.timeline.clock().objectFlags&0x80000)?ax.sub(ScalarFloat::integer(35)):ax.add(ScalarFloat::integer(35));
        s.body.timeline.setPosition(std::bit_cast<float>(x.bits),std::bit_cast<float>(ay.add(ScalarFloat::integer(75)).bits));
        a.flags248|=0x100;
        break;
    }
    case 0x1b:case 0x1c: { // 16728c / 1672a4: stop the victim; the child (V.body.124, no null check) moves onto it
        s.body.timeline.stopMotion();
        auto* c=s.child();
        if(!c)throw std::runtime_error("Original victim rows 0x1b/0x1c write through a null child");
        const ScalarFloat x{std::bit_cast<uint32_t>(s.body.timeline.motion().x)};
        if(row.type==0x1b){(*c)[0x40/4]=x.bits;break;}
        // 0x1c: 16 behind the child's facing, then 1414b8 and 1414f8(8 + V seat, e).
        (*c)[0x40/4]=((*c)[0x38/4]&0x80000)?x.add(ScalarFloat::integer(16)).bits:x.sub(ScalarFloat::integer(16)).bits;
        battle().camera.commands.clear();battle().camera.appendCommand(8+int(s.context.player),row.parameter);
        break;
    }
    case 0x5c: { // 168118: the victim at the attacker plus its own anchor 7 (168ea0(V.a10, 7))
        if(!s.f.weaponLock)throw std::runtime_error("Victim row 0x5c reads the anchor table");
        const auto v7=s.f.weaponLock->objects.anchor(v.character,7);
        const auto am=s.sourceBody.timeline.motion();
        const ScalarFloat ax{std::bit_cast<uint32_t>(am.x)},ay{std::bit_cast<uint32_t>(am.y)};
        const bool attackerMirrored=s.sourceBody.timeline.clock().objectFlags&0x80000;
        const auto x=attackerMirrored?ax.sub(ScalarFloat::integer(v7[0])):ax.add(ScalarFloat::integer(v7[0]));
        s.body.timeline.setPosition(std::bit_cast<float>(x.bits),std::bit_cast<float>(ay.add(ScalarFloat::integer(v7[1])).bits));
        a.flags23c|=0x20000000u;v.flags244|=0x20000u;
        {const auto k=s.body.timeline.clock();s.body.setFlags(k.flags104|0x80,k.flags108);}
        break;
    }
    case 0x2c: // 1676bc: 141528(0, 0x20) shake and the shared sample 1e7b70(-1, 11).
        battle().camera.requestShake(0,0x20);
        if(s.f.sound)s.f.sound->sample(-1,0xb);
        break;
    case 0x01:case 0x03:case 0x05:case 0x06:case 0x25:case 0x41:case 0x42:case 0x4a:case 0x5a:break;
    default:if(row.type<0x5d){if(std::getenv("SS6_DEBUG_HANDLER"))std::fprintf(stderr,"victim row type 0x%x\n",unsigned(row.type));unported(v);}
    }
    r[1]=r[0];
    v.timers[23]=a.timers[23]=0;
}
// 1667f8: end ops of the current row. Returns true when the victim's op is
// 169810 (the caller runs the recovery).
bool endOps(Script& s) {
    using namespace capture;
    const auto& row=s.row();
    bool recover=false;
    for(unsigned slot=0;slot<2;++slot) {
        auto& actor=slot?s.a:s.v;
        switch(const auto op=row.end[slot]) {
        case 0:break;
        case 1:request(actor,0,row.parameter);actor.flags248|=0x20;break;
        case 2:request(actor,1,row.parameter);actor.request18c=1;actor.flags248|=0x20;break;
        case 3: {
            int i=row.parameter;
            if((actor.flags23c&0x10)&&(i==19||unsigned(i-32)<26))i=i==54?75:74; // airborne remap
            request(actor,2,i);actor.request18c=1;actor.flags248|=0x20;break;
        }
        case 4:if(slot)unported(s.v);recover=true;break;
        case 5:case 6:callback(actor,0x169a50,0,op==5?0:4);break;
        case 7:case 8:callback(actor,0x169a50,2,op==7?5:6);break;
        case 9: { // 166e10 for the actor; body+128 keeps the life change it applies
            auto& o128=slot?s.a.bodyState128:s.v.bodyState128;
            if(row.type==0x41){const auto n=actor.characterBytesF14[7];o128=uint32_t(n==0?-16:n==1?-8:-4);}
            else if(row.type==0x42)o128=uint32_t(-16);
            callback(actor,0x166e10,1,actor.callbacks260[5]);
            break;
        }
        case 10: // 169a50 mode 0, only while the actor is in attack state 80..83
            if(actor.stateTable()==1&&unsigned(actor.stateIndex()-80)<4)callback(actor,0x169a50,0,0);
            break;
        case 11:case 12:case 13:case 14:callback(actor,0x174158,1,op-11);break;
        case 15:case 16:case 17:case 18:case 19:case 20:case 21:case 22:callback(actor,0x174158,2,op-11);break;
        case 27:case 28:case 29:case 30:case 31:case 32:case 33:case 34: {
            // 163450 clears the actor's registry, then 163590 starts its own
            // table-A script op + 37 (64..71) with variant 0.
            actor.registry28c.fill(0);actor.registry28c[2]=0xffffffffu;
            if(!slot){s.scripts.start(s.body,actor,s.f,op+37,0);break;}
            auto& world=*s.f.weaponLock;
            WeaponLockActorContext reverse{s.body,s.v,world.camera,world.cachedDistance,world.objects,s.f.opponentObjectTasks};
            GroundStateFrame frame=s.f;frame.opponentX=s.body.timeline.motion().x;frame.weaponLock=&reverse;
            frame.config=nullptr; // the copied spirit is the victim's
            GroundStateRuntime::captureBody(s.sourceBody,actor);
            s.scripts.start(s.sourceBody,actor,frame,op+37,0);
            break;
        }
        default:unported(s.v);
        }
    }
    // Slot 2: the child object (V.body.124).
    if(const auto op=row.end[2]) {
        auto& r=s.v.registry28c;
        auto* c=s.child();
        switch(op) {
        case 23:case 24:case 25:
            // 0x1000 deletes at the end of the registry visit, 0x2000 when its
            // ACT ends, 0x4000 becomes 0x2000 at the next completion check.
            if(c){(*c)[0x108/4]|=op==23?0x1000u:op==24?0x2000u:0x4000u;s.v.bodyField124=0;r[10]=0;}
            break;
        case 26: // TCB STOP: park the child's task on 147540
            if(c){if((*c)[0x04/4])s.context.tasks.tasks.at((*c)[0x04/4]-1)[0]=0x147540;s.v.bodyField124=0;r[10]=0;} // a freed child stores through 0
            break;
        default:unported(s.v);
        }
    }
    return recover;
}
bool instant(const VictimRow& row){return (row.flags&1)&&row.wait==std::array<uint8_t,3>{};} //166330
// 1663b8: all waits of the current row complete.
// 168960: Kim (source 40) places or animates the held victim from his own ACT frame:
// ACT 0x261/0x262 puts the victim 56 ahead at his height once the VICTIM's record is >= 3;
// ACT 0x26c/0x26d drives its record from his frames 8..21 ((frame - 8) % 4) and 22 (record 7).
void kimHoldFixup(Script& s) {
    if(s.v.pendingCharacter254!=40)return;
    const auto& ab=s.sourceBody;
    const int act=ab.timeline.action().id();const int frame=int(ab.timeline.clock().step);
    if(unsigned(act-0x261)<2) {
        if(int(s.body.timeline.clock().step)<3)return;
        const float ax=ab.timeline.motion().x;
        const float x=(ab.timeline.clock().objectFlags&0x80000)?eeSub(ax,56.0f):eeAdd(ax,56.0f);
        s.body.timeline.setPosition(x,ab.timeline.motion().y);
    } else if(unsigned(act-0x26c)<2) {
        if(unsigned(frame-8)<14)s.body.timeline.setRecordStep(uint32_t((frame-8)%4));
        else if(frame==22)s.body.timeline.setRecordStep(7);
    }
}
bool waitsDone(Script& s) {
    auto& r=s.v.registry28c;const auto& row=s.row();
    bool all=true;
    for(unsigned slot=0;slot<3;++slot) {
        if(r[7+slot])continue;
        const auto w=row.wait[slot];
        if(!w){r[7+slot]=1;continue;}
        if(slot==0)kimHoldFixup(s);
        if(slot==2) {
            // The child (V.body.124) has no actor: ended(o) = c0 != 0 && !(104 & 1).
            auto* c=s.child();
            if(!c){all=false;continue;} // the original prints an ASSERT and waits
            auto& o=*c;
            const bool ended=o[0xc0/4]&&!(o[0x104/4]&1);
            const ScalarFloat y{o[0x44/4]};
            const bool grounded=!ScalarFloat{0}.less(y); // y <= 0.0
            bool done=false;
            const auto release=[&]{if(o[0x104/4]&0x100){o[0x104/4]&=~0x100u;return true;}return false;};
            switch(w) {
            case 1:case 9:done=ended;break;
            case 10:if(grounded){AuxiliaryObjects::stop(o);o[0x44/4]=0;done=true;}break;
            case 11:done=release();break;
            case 12:if(grounded){AuxiliaryObjects::stop(o);o[0x44/4]=0;done=release();}break;
            case 13: { // the child passes the victim in its facing direction
                const auto vx=std::bit_cast<uint32_t>(s.body.timeline.motion().x);
                const ScalarFloat ox{o[0x40/4]},bx{vx};
                if((o[0x38/4]&0x80000)?!bx.less(ox):!ox.less(bx)) {
                    o[0x40/4]=vx;AuxiliaryObjects::stop(o);done=true;
                }
                break;
            }
            default:unported(s.v);
            }
            if(done)r[9]=1;else all=false;
            continue;
        }
        auto& actor=slot?s.a:s.v;auto& o=slot?s.sourceBody:s.body;
        bool done=false;
        switch(w) {
        case 1:done=actionEnded(o,actor.queuedActionA3c);break;
        case 2:done=holdReached(o,actor);break;
        case 3:if(touchedGround(o,actor.queuedActionA3c)){stopAtGround(o);done=true;}break;
        case 4:if(!ScalarFloat{0x41800000u}.less(ScalarFloat{std::bit_cast<uint32_t>(o.timeline.motion().y)})) {
                   stopAtGround(o);o.timeline.setPosition(o.timeline.motion().x,0.f);done=true;
               }
               break;
        case 5:if(landingReady(o,actor.queuedActionA3c)){stopAtGround(o);done=true;}break;
        case 6: {
            const auto old=actor.timers[23];
            actor.timers[23]=std::min(0x173400,old+actor.timerDelta);
            done=old>=int32_t(row.parameter)<<8;break;
        }
        case 7:if(!(o.timeline.motion().y>0)){stopAtGround(o);done=true;}break;
        case 8: { // "VS LEVER CHECK": the mash contest restarts the slot's ACT until one side wins
            auto& vb=s.v;
            if(!actionEnded(o,actor.queuedActionA3c)) { // 168588: (#A presses) - (#V presses)
                if(!s.f.ownInput||!s.f.opponentInput)throw std::runtime_error("Victim wait 8 reads both fighters' buttons");
                const auto count=[](const auto& h){int n=0;for(int i:{6,7,8,9,10,58,59,60,61})n+=h[i]!=0;return n;};
                vb.bodyState128=uint32_t(int32_t(vb.bodyState128)+count(s.f.opponentInput->sampledFeatures)-count(s.f.ownInput->sampledFeatures));
                break;
            }
            const int32_t n=int32_t(vb.bodyLatch12c);
            if(n>=10||(n>0&&int32_t(vb.bodyState128)<=0))done=true;
            else {vb.bodyState128=0;vb.bodyLatch12c=uint32_t(n+1);o.request(o.timeline.action().id(),true);}
            break;
        }
        default:unported(s.v);
        }
        if(done)r[7+slot]=1;else all=false;
    }
    return all;
}
// ---- Gaira's k == 4 grab (1f3be0 -> 1f3cc8 and its victim callbacks) ----
constexpr uint32_t gairaMash=0x1f3db8,gairaThrow=0x1f4010,gairaWall=0x1f4098;
// 1699f8: completion test that always consumes the ACT hold marker 104:100.
bool consumeHold(PlayerObject& b,const StateEntryActor& a) {
    const auto c=b.timeline.clock();
    const bool done=actionEnded(b,a.queuedActionA3c)||(c.flags104&0x100);
    b.setFlags(c.flags104&~0x100u,c.flags108);
    return done;
}
void queue2(StateEntryActor& a,int armed){capture::queue(a,armed+!(a.flags23c&0x1000));} //1494c0
void bind(StateEntryActor& a,uint32_t pc,unsigned table) { //1522a0 (274 untouched)
    a.callbacks260[0]=pc;a.callbacks260[1]=table;a.callbacks260[2]=0xffffffffu;
}
void copyPosition(PlayerObject& to,const PlayerObject& from) { //14a8b0
    const auto m=from.timeline.motion();to.timeline.setPosition(m.x,m.y);
}
// 168400 for this routine (it does not go through 165a78).
void captureObjects(Script& s,unsigned character,unsigned k) {
    if(!(s.a.flags244&0x1000)&&s.f.suppressCaptureObjects)s.f.suppressCaptureObjects();
    // 168400: not for (27, 0), nor (40, 2) unless 13a858 (byte 43d05e, 0 under console VS).
    if(!(character==27&&k==0)&&!(character==40&&k==2))s.v.flags244|=0x10;
    if(s.body.timeline.action().id()!=1578)s.body.timeline.stopMotion();
    if(s.tables.fighters().weaponHold(character,k))s.v.flags244|=0x20000;
}
void gairaGrabStart(Script& s) { // 1f3cc8
    auto& v=s.v;auto& a=s.a;
    // 168318(cb, 1): the source check passed in 1657b0; a paired grab needs
    // an undamaged, living attacker.
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;}
    capture::queue(a,0x24b);a.callbacks260={};a.override27c={};
    a.bodyState128=0xffffffffu;a.bodyLatch12c=0;a.bodyCounter130=0;s.sourceBody.scriptLatch134=0;
    a.timers[23]=0;
    copyPosition(s.body,s.sourceBody);
    queue2(v,0x57e);bind(v,gairaMash,2);
    captureObjects(s,10,4);
}
// ---- Sogetsu's k == 0 catch (1f7918 -> 1f7b88 and its victim callback 1f7c30) ----
constexpr uint32_t sogetsuCatch=0x1f7c30;
void sogetsuCatchStart(Script& s) { // 1f7b88
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    capture::queue(a,0x26d);a.callbacks260={};a.override27c={};
    queue2(v,0x5ba);bind(v,sogetsuCatch,2);
    captureObjects(s,17,0);
}
void sogetsuCatchVisit(Script& s) { // 1f7c30: when Sogetsu's ACT ends both leave
    auto& v=s.v;auto& a=s.a;
    if(!actionEnded(s.sourceBody,a.queuedActionA3c))return;
    bind(v,0x169a50,2);v.callbacks260[5]=4;
    capture::queue(a,0x26e);bind(a,0x169a50,1);a.callbacks260[5]=0;
    // 16c408(cb(A), 0x26f, 0, 0): Sogetsu's effect, then both 72 (663d00) to either side of the victim.
    auto& world=*s.f.weaponLock;
    const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,1-s.context.player,a.flags23c,
                                           s.sourceBody.childParentWords(),0x1396,6,0);
    if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& e=s.context.tasks.objects.at(handle-1);
    world.objects.request(e,0x26f,false,true);e[0x108/4]|=0x2000;
    const bool mirrored=s.body.timeline.clock().objectFlags&0x80000;
    const auto c=s.sourceBody.timeline.clock();
    s.sourceBody.timeline.setObjectFlags(mirrored?c.objectFlags&~0x80000u:c.objectFlags|0x80000u,c.flags104,c.flags108);
    e[0x38/4]=mirrored?e[0x38/4]&~0x80000u:e[0x38/4]|0x80000u;
    const ScalarFloat vx{std::bit_cast<uint32_t>(s.body.timeline.motion().x)},d=ScalarFloat::integer(72);
    s.sourceBody.timeline.setPosition(std::bit_cast<float>((mirrored?vx.sub(d):vx.add(d)).bits),s.sourceBody.timeline.motion().y);
    e[0x40/4]=(mirrored?vx.add(d):vx.sub(d)).bits;
}
bool isSogetsuCallback(uint32_t h){return h==sogetsuCatch;}
// ---- Kyoshiro's k == 0 catch (1f17a8; victim callbacks 1f1890 / 1f1900 / 1f1b90 / 1f1c88) ----
constexpr uint32_t kyoWait=0x1f1890,kyoPull=0x1f1900,kyoFall=0x1f1b90,kyoLand=0x1f1c88;
AuxiliaryObject& sceneObject(Script& s,uint32_t h) {
    if(!h)throw std::runtime_error("Kyoshiro's catch reads a null object");
    return s.context.tasks.objects.at(h-1);
}
float wordF(const AuxiliaryObject& o,unsigned off){return std::bit_cast<float>(o[off/4]);}
void setF(AuxiliaryObject& o,unsigned off,float v){o[off/4]=std::bit_cast<uint32_t>(v);}
void kyoshiroCatchStart(Script& s) { // 1f17a8
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    const auto m=s.sourceBody.scriptLatch134; // read before the callbacks are cleared
    a.callbacks260={};a.override27c={};
    s.f.weaponLock->objects.request(sceneObject(s,m),0x266,false,false);
    s.body.timeline.stopMotion();
    queue2(v,0x54d);bind(v,kyoWait,2);
    v.timers[23]=16*256; //14cfe8
    captureObjects(s,5,0);
    v.flags244&=~0x20000u;
}
void kyoshiroCatchVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& vb=s.body;auto& ab=s.sourceBody;
    switch(v.callbacks260[0]) {
    case kyoWait: {
        ActorTimers t{v.timerDelta,v.timers};const auto old=t.decrease(23);v.timers=t.values; //14d010
        if(old==0&&holdReached(vb,v))bind(v,kyoPull,2);
        return;
    }
    case kyoPull: { // 1f1900: drawn 16 per visit toward Kyoshiro
        auto& s2=sceneObject(s,a.bodyCounter130);auto& s3=sceneObject(s,ab.scriptLatch134);
        const bool left=ab.timeline.clock().objectFlags&0x80000;
        const float ax=ab.timeline.motion().x,x0=vb.timeline.motion().x;
        float x=left?eeAdd(x0,16.0f):eeSub(x0,16.0f);bool caught=false;
        const float lim=left?eeSub(ax,32.0f):eeAdd(ax,32.0f);
        if(left?lim<=x:x<=lim){caught=true;x=left?eeSub(lim,1.0f):eeAdd(lim,1.0f);}
        vb.timeline.setPosition(x,vb.timeline.motion().y);
        if(caught) {
            s.f.weaponLock->objects.request(sceneObject(s,a.bodyState128),0x263,false,false);
            s3[0x104/4]|=2;s2[0x104/4]|=2;s3[0x108/4]|=0x1000;s2[0x108/4]|=0x1000;
            v.bodyState128=a.bodyState128;v.bodyLatch12c=a.bodyLatch12c;
            queue2(a,0x25f);bind(a,0x174158,1);a.callbacks260[5]=1;
            const auto c=vb.timeline.clock();vb.setFlags(c.flags104|2,c.flags108);
            bind(v,kyoFall,2);
            if(!s.f.battle)throw std::runtime_error("Kyoshiro's catch needs the battle camera");
            s.f.battle->camera.appendCommand(3,0x5a);
        } else {
            const float d=eeSub(x,x0);
            setF(s3,0x40,eeAdd(wordF(s3,0x40),d));setF(s2,0x40,eeAdd(wordF(s2,0x40),d));
            if(!left?eeSub(wordF(s2,0x40),12.0f)<ax:ax<eeAdd(wordF(s2,0x40),12.0f))s2[0x104/4]|=2;
        }
        return;
    }
    case kyoFall: { // 1f1b90
        auto& o=sceneObject(s,v.bodyState128);
        if(!o[0xc0/4]||(o[0x104/4]&1))return;
        auto& n=sceneObject(s,v.bodyLatch12c);
        const bool faceLeft=!(o[0x38/4]&0x80000);
        n[0x108/4]|=0x1000;o[0x108/4]|=0x1000;
        {const auto c=vb.timeline.clock();vb.setFlags(c.flags104&~2u,c.flags108);}
        queue2(v,0x54f);bind(v,kyoLand,2);
        const auto c=vb.timeline.clock();
        vb.timeline.setObjectFlags(faceLeft?c.objectFlags|0x80000:c.objectFlags&~0x80000u,c.flags104,c.flags108);
        return;
    }
    case kyoLand: { // 1f1c88: 14aad8(V, (int)(14adf0 + 2.0), 0, 0), then 174158 mode 9
        const auto* camera=s.f.weaponLock?&s.f.weaponLock->camera:nullptr;
        if(!camera)throw std::runtime_error("Kyoshiro's catch needs the live camera");
        const int m=(v.character==0x2e?8:v.character==0x2f?16:34)+2;
        const int x=int(vb.timeline.motion().x);
        if(!(x>=camera->right-m||x<=camera->left+m))return;
        if(!holdReached(vb,v))return;
        bind(v,0x174158,2);v.callbacks260[5]=9;
        return;
    }
    }
}
// ---- Shizumaru's k == 1 umbrella catch (1f39a8; victim callback 1f3a70) ----
constexpr uint32_t shizuCarry=0x1f3a70;
void shizumaruCatchStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    capture::queue(a,int(s.sourceBody.scriptLatch134)+0x272); // queued before the callbacks are cleared
    a.callbacks260={};a.override27c={};
    copyPosition(s.body,s.sourceBody);
    queue2(v,0x56e);bind(v,shizuCarry,2);
    captureObjects(s,9,1);
    v.flags244&=~0x20000u;
}
void shizumaruCatchVisit(Script& s) { // 1f3a70: carried until Shizumaru reaches the wall he faces
    auto& v=s.v;auto& a=s.a;
    const auto k=s.sourceBody.scriptLatch134;
    copyPosition(s.body,s.sourceBody);
    if(!s.f.weaponLock)throw std::runtime_error("Shizumaru's catch needs the live camera");
    const auto& camera=s.f.weaponLock->camera;
    const int m=a.character==0x2e?8:a.character==0x2f?16:34; // 14aad8(A, 14adf0(A), 1, 0): facing edge only
    const int x=int(s.sourceBody.timeline.motion().x);
    if(!((s.sourceBody.timeline.clock().objectFlags&0x80000)?x<=camera.left+m:x>=camera.right-m))return;
    capture::queue(a,int(k)+0x277);bind(a,0x169a50,1);a.callbacks260[5]=0;
    // 172828(cb, 1): the victim's voice, 1e8298(seat, 1727a0 ? 0x1f : 0x20, a14).
    constexpr unsigned quiet[]{10,13,25,32,36,37,38,40};
    const bool loud=std::find(std::begin(quiet),std::end(quiet),v.character)==std::end(quiet);
    if(s.f.sound&&s.f.random)s.f.sound->act(loud?0x1f:0x20,int(s.context.player),voiceCharacter(v),v.flags23c,3,0,*s.f.random);
    holdReached(s.body,v); // 1699f8, result ignored
    bind(v,0x169a50,2);v.callbacks260[5]=5;
}
// ---- Amakusa's k == 3 catch (1f4948): the victim waits in 169a50 while Amakusa runs 1f4ac0.. ----
void amakusaCatchStart(Script& s,bool alternate) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    queue2(v,0x5a2);bind(v,0x169a50,1);v.callbacks260[5]=4;
    s.sourceBody.scriptLatch134=alternate?0xaa:0;
    capture::queue(a,int(s.sourceBody.scriptLatch134)+0x246);
    s.sourceBody.timeline.stopMotion();
    a.callbacks260={};a.override27c={};
    // 16c408(cb, 0x24a, 0, 1): Amakusa's effect, task callback 1f4838.
    auto& world=*s.f.weaponLock;
    const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,1-s.context.player,a.flags23c,
                                           s.sourceBody.childParentWords(),0x1396,6,0);
    if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& e=s.context.tasks.objects.at(handle-1);
    world.objects.request(e,0x24a,false,true);
    e[0x108/4]&=~0x2000u;e[0x104/4]|=0x4000;
    s.context.tasks.tasks.at(e[1]-1)[0]=0x1f4838;
    e[0x40/4]=std::bit_cast<uint32_t>(s.body.timeline.motion().x);
    a.bodyLatch12c=handle;
    bind(a,0x1f4ac0,1);
    {const auto c=s.sourceBody.timeline.clock();s.sourceBody.setFlags(c.flags104|0x2000,c.flags108);}
    captureObjects(s,11,3);
}
// ---- Mizuki's k == 3 throw (1fec20; victim callbacks 1fedc8 / 1fee40 / 1fef00) ----
constexpr uint32_t mizukiHold=0x1fedc8,mizukiToss=0x1fee40,mizukiBounce=0x1fef00;
// 16c408(cb, act, 0, 1): an attacker-owned kind-6 effect at the attacker's body (forced ACT, 108 |= 0x2000).
AuxiliaryObject& attackerOwnedEffect(Script& s,unsigned act) {
    auto& world=*s.f.weaponLock;
    const auto handle=world.objects.create(s.context.tasks,s.f.opponentObjectTasks,1-s.context.player,s.a.flags23c,
                                           s.sourceBody.childParentWords(),0x1396,6,0);
    if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& o=s.context.tasks.objects.at(handle-1);
    world.objects.request(o,act,false,true);o[0x108/4]|=0x2000;
    return o;
}
void mizukiThrowStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    capture::queue(a,0x264);a.callbacks260={};a.override27c={};
    // 140d78(A, n, 2): reuse the first kind-2 object with d0 == 0x37, else a new 0x267 effect.
    AuxiliaryObject* o=nullptr;
    for(auto t:s.f.opponentObjectTasks)if(t) {
        auto& x=s.context.tasks.objects.at(s.context.tasks.tasks.at(t-1)[7]-1);
        if(x[0xcc/4]!=2||x[0xd0/4]!=0x37)continue;
        AuxiliaryObjects::stop(x);x[0xd0/4]=0;x[0xcc/4]=6;s.f.weaponLock->objects.request(x,0x267,false,true);
        s.context.tasks.tasks.at(x[1]-1)[0]=0x147540;o=&x;break;
    }
    if(!o)o=&attackerOwnedEffect(s,0x267);
    (*o)[0x104/4]|=0x1000;(*o)[0x108/4]|=0x20000;
    {const auto anchor=s.f.weaponLock->objects.bodyAnchor(v.character); // 16e788(o, V, 0)
     const auto m=s.body.timeline.motion();
     (*o)[0x40/4]=std::bit_cast<uint32_t>(m.x);(*o)[0x44/4]=std::bit_cast<uint32_t>(m.y);
     (*o)[0xec/4]=ScalarFloat{(*o)[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
     (*o)[0xf0/4]=ScalarFloat{(*o)[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;}
    (*o)[0x108/4]&=~0x2000u;
    v.bodyState128=uint32_t(o-s.context.tasks.objects.data())+1;
    queue2(v,0x608);bind(v,mizukiHold,2);
    if(!s.f.battle)throw std::runtime_error("Mizuki's throw needs the battle camera");
    s.f.battle->camera.appendCommand(0,0);
    captureObjects(s,27,3);
    v.flags244&=~0x20000u;
}
void mizukiThrowVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& vb=s.body;auto& ab=s.sourceBody;
    const auto mark=[&]{const auto c=ab.timeline.clock();ab.setFlags(c.flags104|0x2000,c.flags108);};
    const bool attackerEnded=actionEnded(ab,a.queuedActionA3c);
    switch(v.callbacks260[0]) {
    case mizukiHold:
        if(attackerEnded){capture::queue(a,0x265);bind(v,mizukiToss,2);}
        mark();return;
    case mizukiToss: {
        if(!attackerEnded){mark();return;}
        vb.timeline.stopMotion();vb.scriptLatch134=0;
        auto m=vb.timeline.motion();m.vx=int32_t(0xfff9999au);m.vy=0x33333;m.ax=-0x3333;m.ay=0x1999;vb.timeline.setMotion(m);
        capture::queue(a,0x266);bind(v,mizukiBounce,2);
        mark();return;
    }
    case mizukiBounce: {
        auto& battle=*s.f.battle;
        int bounce=-1;
        if(touchedGround(vb,v.queuedActionA3c)) {
            const int32_t t=std::bit_cast<int32_t>(vb.scriptLatch134);
            if(t>0) { // final landing
                vb.timeline.stopMotion();
                auto& o=s.context.tasks.objects.at(v.bodyState128-1);
                vb.timeline.setPosition(vb.timeline.motion().x,0);
                s.f.weaponLock->objects.request(o,0x268,false,false);o[0x108/4]|=0x2000;
                auto& e=attackerOwnedEffect(s,0x269);
                e[0x44/4]=std::bit_cast<uint32_t>(vb.timeline.motion().y);e[0x40/4]=std::bit_cast<uint32_t>(vb.timeline.motion().x);
                // 14fa18 on the attacker's spirit: 170240 for systems 1/7, else 170010 (the victim's weapon).
                auto& world=*s.f.weaponLock;const auto parent=vb.childParentWords();
                if(s.f.opponentSystem==1||s.f.opponentSystem==7)
                    world.objects.dropSpecial(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
                else world.objects.drop(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
                if(v.fieldA30>0){const int div=battle.gauges.paused46a940?8:1;battle.timers.set(6,12,div);battle.timers.set(5,6,div);} //140930
                capture::queue(v,0x60a);bind(v,0x174158,2);v.callbacks260[5]=6;
                bind(a,0x169a50,1);a.callbacks260[5]=0;
                battle.camera.commands.clear();
                return;
            }
            // first bounce
            auto m=vb.timeline.motion();m.ay=-m.ay;m.vy=-m.vy;vb.timeline.setMotion(m);
            vb.scriptLatch134=uint32_t(t+1);
            vb.timeline.clearEndControl(0x100); // body+3c &= ~0x100
            vb.timeline.setPosition(vb.timeline.motion().x,1.0f);
            bounce=0;battle.camera.requestShake(-1,0x10);
        } else {
            const auto& cam=s.f.weaponLock->camera;
            auto m=vb.timeline.motion();
            if(0.0f<float(m.vy)&&float(int32_t(cam.top))<=eeAdd(m.y,48.0f)) { // the ceiling
                m.vy=-m.vy;bounce=1;m.ay=-m.ay;vb.timeline.setMotion(m);battle.camera.requestShake(-1,0x10);
            }
            const bool mir=vb.timeline.clock().objectFlags&0x80000;
            const int x=int(vb.timeline.motion().x);
            if(mir?x>=cam.right-0x30:x<=cam.left+0x30) { // 146a50(cam, x, 0x30, mir, 1): the wall
                bounce=mir?3:2;
                const auto c=vb.timeline.clock();vb.timeline.setObjectFlags(c.objectFlags^0x80000,c.flags104,c.flags108); //11db88
                battle.camera.requestShake(0x10,-1);
            }
        }
        if(bounce==-1)return;
        auto& e=attackerOwnedEffect(s,0x268);
        const auto m=vb.timeline.motion();
        const float y=eeAdd(m.y,48.0f);
        e[0x40/4]=std::bit_cast<uint32_t>(m.x);e[0x44/4]=std::bit_cast<uint32_t>(y);
        if(bounce==0)e[0x44/4]=std::bit_cast<uint32_t>(eeSub(y,48.0f));
        else if(bounce==1)e[0x44/4]=std::bit_cast<uint32_t>(eeSub(y,12.0f));
        else if(bounce==2){e[0x38/4]&=~0x80000u;e[0x40/4]=std::bit_cast<uint32_t>(eeSub(m.x,32.0f));}
        else {e[0x38/4]|=0x80000u;e[0x40/4]=std::bit_cast<uint32_t>(eeAdd(m.x,32.0f));}
        return;
    }
    }
}
// ---- Iroha's k == 0 (1ffd90; victim callbacks 200228 / 2003d0 / 200560 / 200710) ----
constexpr uint32_t irohaBow=0x200228,irohaDance=0x2003d0,irohaStrike=0x200560,irohaFade=0x200710;
// Inline colour ramps on object+8c, stepped by object+30 * 0x80808 / 256.
uint32_t fadeStep(const AuxiliaryObject& e){const int32_t p=int32_t(e[0x30/4]*0x80808u);return uint32_t((p+(p<0?0xff:0))>>8);}
void fadeIn(AuxiliaryObject& e) {
    uint32_t c=e[0x8c/4];
    if(!(c>0xff80807fu)){c+=fadeStep(e);e[0x8c/4]=c;}
    if(c>0xff808080u)e[0x8c/4]=0xff808080u;
}
uint32_t fadeOut(AuxiliaryObject& e) {
    uint32_t c=e[0x8c/4];
    if(c>0xff000000u){c-=fadeStep(e);e[0x8c/4]=c;}
    if(!(c>0xfeffffffu)){e[0x8c/4]=0xff000000u;c=0xff000000u;}
    return c;
}
void irohaSparks(Script& s,int n,int yoff) { // 2008a8: around the attacker, RNG 2, 0x60, 0x30 per spark
    if(!s.f.random)throw std::runtime_error("2008a8 draws the game RNG");
    auto& rng=*s.f.random;
    for(int i=0;i<n;++i) {
        auto& o=attackerOwnedEffect(s,0x25e);
        if(rng.bounded(2)==0)o[0x38/4]|=0x80000;else o[0x38/4]&=~0x80000u;
        const auto pm=s.sourceBody.timeline.motion();
        const float r2=float(rng.bounded(0x60));
        const float x=(s.sourceBody.timeline.clock().objectFlags&0x80000)?eeSub(eeAdd(pm.x,24.0f),r2):eeAdd(eeSub(pm.x,24.0f),r2);
        o[0x40/4]=std::bit_cast<uint32_t>(x);
        const float y=eeAdd(eeAdd(pm.y,float(yoff)),float(12*i));
        o[0x44/4]=std::bit_cast<uint32_t>(eeAdd(y,float(rng.bounded(0x30))));
    }
}
void irohaStart(Script& s) { // 1ffd90
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    if(!s.f.battle||!s.f.weaponLock)throw std::runtime_error("Iroha's catch needs the live battle");
    auto& battle=*s.f.battle;const auto& cam=s.f.weaponLock->camera;
    const int32_t sum=int32_t(uint32_t(cam.left)+uint32_t(cam.right));const int32_t mid=sum/2;
    const bool left=s.sourceBody.timeline.clock().objectFlags&0x80000;
    const float x=float(left?mid+0x30:mid-0x30);
    s.sourceBody.timeline.setPosition(x,s.sourceBody.timeline.motion().y);s.body.timeline.setPosition(x,s.body.timeline.motion().y);
    {const auto c=s.body.timeline.clock();s.body.timeline.setObjectFlags(left?c.objectFlags&~0x80000u:c.objectFlags|0x80000u,c.flags104,c.flags108);}
    a.callbacks260={};a.override27c={};
    queue2(a,0x256);
    auto& e1=attackerOwnedEffect(s,0x25b);
    e1[0x44/4]=0;e1[0x38/4]&=~0x80000u;e1[0x40/4]=std::bit_cast<uint32_t>(float(mid));
    e1[0x108/4]=(e1[0x108/4]&~0x2000u)|0x80000;e1[0x38/4]|=0x40000000;
    a.bodyState128=uint32_t(&e1-s.context.tasks.objects.data())+1;e1[0x8c/4]=0xff000000u;
    auto& e2=attackerOwnedEffect(s,0x25b);
    e2[0x108/4]=(e2[0x108/4]&~0x2000u)|0x80000;e2[0x38/4]|=0x80000;e2[0x44/4]=0;
    e2[0x40/4]=std::bit_cast<uint32_t>(float(mid+2));e2[0x8c/4]=0xff000000u;
    a.bodyLatch12c=uint32_t(&e2-s.context.tasks.objects.data())+1;e2[0x38/4]|=0x40000000;
    queue2(v,0x61e);bind(v,irohaBow,2);
    v.timers[23]=0;v.timers[22]=0x8a*256;
    battle.flags138|=0x20; //200aa8
    captureObjects(s,31,0);
    battle.paletteState[0].fill(0xffffffffu);battle.paletteState[1].fill(0);battle.paletteState[2].fill(0); //1159d0
    // The victim's own kind-2 objects that the scene removes (o.14 = owner character, o.d0 = type).
    const auto kill=[&](AuxiliaryObject& o){s.context.tasks.tasks.at(o[1]-1)[0]=0x147540;o[0x104/4]|=2;o[0x108/4]|=0x1000;};
    for(auto t:s.f.weaponLock->objectTasks)if(t) {
        auto& o=s.context.tasks.objects.at(s.context.tasks.tasks.at(t-1)[7]-1);
        if(o[0xcc/4]!=2)continue;
        const uint32_t c=o[0x14/4],d=o[0xd0/4];
        bool k=c==2||c==0xc||c==0xf||c==0x17||c==0x19||c==0x25||c==0x2f||c==0x30||
               (c==0x23&&d!=0x93)||(c==0x27&&d!=0x92)||c==0xb||c==0xd||c==0x10||c==0x11||c==0x1e||(c==0x18&&d!=0xbc);
        if(!k)k=d==0x2f||d==0x37||d==0x7d||d==0x85||d==0x87||d==0x99||d==0||d==0xb||d==0xf||d==0x10||d==0x1e||d==0x2d;
        if(k)kill(o);
    }
    for(auto t:s.f.weaponLock->objectTasks)if(t) {
        auto& o=s.context.tasks.objects.at(s.context.tasks.tasks.at(t-1)[7]-1);
        if(o[0xcc/4]!=6)continue;
        const uint32_t c=o[0x14/4],act=o[0x24/4];
        if((c==10&&act-0x274u<2)||(c==7&&act-0x283u<0xd))kill(o);
    }
}
void irohaVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& ab=s.sourceBody;
    auto& battle=*s.f.battle;
    auto& e1=s.context.tasks.objects.at(a.bodyState128-1);auto& e2=s.context.tasks.objects.at(a.bodyLatch12c-1);
    const bool aEnded=actionEnded(ab,a.queuedActionA3c);
    switch(v.callbacks260[0]) {
    case irohaBow: {
        if(aEnded) {
            capture::queue(a,0x258);copyPosition(s.body,ab);queue2(v,0x620);bind(v,irohaDance,2);
            v.timers[23]=0;v.timers[22]=0xa*256;
        }
        ActorTimers t{v.timerDelta,v.timers};const auto old=t.decrease(22);v.timers=t.values;
        if(old==0){irohaSparks(s,4,0x18);v.timers[22]=0x3e7*256;}
        battle.flags138|=0x20;fadeIn(e1);fadeIn(e2);
        return;
    }
    case irohaDance: {
        if(aEnded) {
            queue2(a,0x259);copyPosition(s.body,ab);
            if(a.flags23c&0x1000)queue2(v,0x622);else queue2(v,0x624);
            bind(v,irohaStrike,2);e1[0x8c/4]=e2[0x8c/4]=0xff000000u;
        } else if(int32_t(ab.timeline.clock().step)>=0x1a){fadeOut(e1);fadeOut(e2);}
        { // 200a28
            ActorTimers t{v.timerDelta,v.timers};const auto old=t.decrease(22);v.timers=t.values;
            if(old==0){const int r=s.f.random->bounded(0x30);irohaSparks(s,1,r+0x30);v.timers[22]=0x18*256;}
        }
        battle.flags138|=0x20;
        return;
    }
    case irohaStrike: {
        bool done=aEnded;
        if(!done) {
            const auto act=ab.timeline.action().id();const int32_t r=int32_t(ab.timeline.clock().step);
            if(act==0x259)done=r>=0x18;else if(act==0x25a)done=r>=0x19;
        }
        if(done)bind(v,irohaFade,2);
        fadeIn(e1);fadeIn(e2);
        const auto c=ab.timeline.clock();
        if(c.flags104&0x100) {
            ab.setFlags(c.flags104&~0x100u,c.flags108);
            irohaSparks(s,5,0x18);
            auto& world=*s.f.weaponLock;const auto parent=s.body.childParentWords();
            if(s.f.opponentSystem==1||s.f.opponentSystem==7) // 14fa18 on the attacker's spirit
                world.objects.dropSpecial(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
            else world.objects.drop(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
        }
        battle.flags138|=0x20;
        return;
    }
    case irohaFade: {
        fadeOut(e1);
        if(fadeOut(e2)!=0xff000000u){battle.flags138|=0x20;return;}
        e1[0x108/4]|=0x1000;e2[0x108/4]|=0x1000;
        a.flags23c|=8;a.fieldA2c=0;
        GroundStateRuntime::recoverStanding(ab,a,s.body.timeline.motion().x); //169810(A)
        v.fieldA2c=0;
        bind(v,0x169a50,0);v.callbacks260[5]=5;
        return;
    }
    }
}
// ---- Gen-an's chain catch (k == 0x10: 205b30; victim callback 205c18) ----
constexpr uint32_t genanPull=0x205c18;
void genanCatchStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    auto& p=s.context.tasks.objects.at(a.bodyState128-1);
    a.callbacks260={};a.override27c={};
    s.f.weaponLock->objects.request(p,0x233,false,false);
    genanChainLayout(s.context.tasks,s.sourceBody,a);
    v.flags244|=0x80000;
    queue2(v,0x63c);bind(v,genanPull,2);
    captureObjects(s,35,0x10);
}
void genanCatchVisit(Script& s) { // 205c18: drawn in with the chain head
    auto& v=s.v;auto& a=s.a;auto& ab=s.sourceBody;
    auto& p=s.context.tasks.objects.at(a.bodyState128-1);
    const float ax=ab.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
    const bool left=ab.timeline.clock().objectFlags&0x80000;
    const bool back=left?eeSub(ax,50.0f)<=px:px<=eeAdd(ax,50.0f);
    if(back) {
        p[0x108/4]|=0x1000;
        for(auto h:{a.bodyLatch12c,a.bodyCounter130,ab.scriptLatch134})s.context.tasks.objects.at(h-1)[0x108/4]|=0x1000;
        bind(a,0x169a50,1);v.flags244&=~0x80000u;a.callbacks260[5]=0;
        bind(v,0x169a50,2);v.callbacks260[5]=0;
        return;
    }
    genanChainLayout(s.context.tasks,ab,a);
    s.body.timeline.setPosition(left?eeSub(px,64.0f):eeAdd(px,64.0f),s.body.timeline.motion().y);
}
// ---- Nicotine's chain catch (k == 0: 207088; victim callback 207150) ----
constexpr uint32_t nicoPull=0x207150;
void nicotineCatchStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    auto& p=s.context.tasks.objects.at(a.bodyState128-1);
    a.callbacks260={};a.override27c={};
    s.f.weaponLock->objects.request(p,0x222,false,false);
    nicotineChainLayout(s.context.tasks,s.sourceBody,a);
    queue2(v,0x65a);bind(v,nicoPull,2);
    captureObjects(s,39,0);
}
void nicotineCatchVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& ab=s.sourceBody;auto& vb=s.body;
    if(a.stateTable()==2){bind(v,0x169a50,2);v.callbacks260[5]=0;return;} // 1500a8(A) == 2
    auto& p=s.context.tasks.objects.at(a.bodyState128-1);
    const float ax=ab.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
    const bool left=ab.timeline.clock().objectFlags&0x80000;
    const bool reached=!left?px<=eeAdd(ax,62.0f):eeSub(ax,62.0f)<=px;
    if(!reached) {
        nicotineChainLayout(s.context.tasks,ab,a);
        vb.timeline.setPosition(!left?eeAdd(px,32.0f):eeSub(px,32.0f),vb.timeline.motion().y);
        return;
    }
    p[0x108/4]|=0x1000;
    for(auto h:{a.bodyLatch12c,a.bodyCounter130,ab.scriptLatch134})s.context.tasks.objects.at(h-1)[0x108/4]|=0x1000;
    capture::queue(a,0x223);bind(a,0x169a50,1);a.callbacks260[5]=0;
    const float vx=vb.timeline.motion().x,bx=ab.timeline.motion().x;
    {const auto c=ab.timeline.clock();
     if(vx<bx)ab.timeline.setObjectFlags(c.objectFlags|0x80000,c.flags104,c.flags108);
     else if(bx<vx)ab.timeline.setObjectFlags(c.objectFlags&~0x80000u,c.flags104,c.flags108);}
    copyPosition(vb,ab);
    queue2(v,0x65c);bind(v,0x169a50,2);v.callbacks260[5]=4;
}
// ---- Kim's locks (k == 0: 207530 mash; k == 1: 207a80 by strength). Body+128..134 are counters. ----
constexpr uint32_t kimMash=0x207620,kimRelease=0x207880,kimFly=0x2078f8,kimAir=0x2079b0,kimLand=0x207a20,kimFixed=0x207b70;
void kimLockStart(Script& s,bool mash,unsigned str) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    capture::queue(a,mash?0x213:0x280);a.callbacks260={};a.override27c={};
    a.bodyState128=0xffffffffu;
    if(mash){a.bodyLatch12c=0;a.bodyCounter130=0;s.sourceBody.scriptLatch134=0;}
    else a.bodyLatch12c=str;
    a.timers[23]=0;
    copyPosition(s.body,s.sourceBody);
    queue2(v,0x57e);bind(v,mash?kimMash:kimFixed,2);
    captureObjects(s,40,mash?0:1);
}
// 1720b0 then 172008 on the victim (the downed tech-roll producers), reusing the knockdown helpers.
bool kimRecover(Script& s,bool choose) {
    auto& v=s.v;auto& o=s.body;
    DownedState down;
    down.flags23c=v.flags23c;down.flags244=v.flags244;down.flags248=v.flags248;down.flags24c=v.flags24c;
    down.flagsB8=v.flagsB8;down.opponentFlagsB8=s.context.opponentFlagsB8;
    down.landingCount253=v.landingCount253;down.recoveryA4c=v.recoveryA4c;
    down.table=v.stateTable();down.index=v.stateIndex();
    DownedInput controls;
    if(s.f.config)controls.system=*s.f.config;
    controls.character=v.character;controls.controlKind=v.controlKindA20;controls.opponentX=s.f.opponentX;
    if(!s.f.ownInput)throw std::runtime_error("Kim's lock reads the victim's recovery input");
    const auto& h=s.f.ownInput->sampledFeatures;
    controls.pressRecovery=h[0x28/4];controls.back100=h[0x100/4];controls.down=h[0xfc/4];
    bool issued=false;
    if(choose) {
        if(!s.f.random)throw std::runtime_error("1720b0 draws the game RNG");
        KnockdownPlayback::chooseRecovery(o,down,controls,*s.f.random);
    } else issued=KnockdownPlayback::requestRecovery(o,down,controls);
    v.flags23c=down.flags23c;v.flags244=down.flags244;v.flags248=down.flags248;v.flags24c=down.flags24c;
    v.flagsB8=down.flagsB8;v.landingCount253=down.landingCount253;v.recoveryA4c=down.recoveryA4c;
    if(down.pendingTable!=-1){v.pendingTable=int16_t(down.pendingTable);v.pendingIndex=int16_t(down.pendingIndex);}
    if(down.forceState)v.request18c=1;
    return issued;
}
void kimLockVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& vb=s.body;auto& ab=s.sourceBody;
    const auto attackerEnded=[&]{return actionEnded(ab,a.queuedActionA3c);};
    const auto timer=[&]{ActorTimers t{a.timerDelta,a.timers};const auto old=t.decrease(23);a.timers=t.values;return old;};
    switch(v.callbacks260[0]) {
    case kimMash: {
        if(int32_t(a.bodyState128)>=0) {
            if(!s.f.opponentInput)throw std::runtime_error("Kim's mash reads the attacker's buttons");
            const auto& h=s.f.opponentInput->sampledFeatures;
            auto& bits=ab.scriptLatch134;
            if(h[59])bits|=1;if(h[60])bits|=2;if(h[58])bits|=4;if(h[61])bits|=8;
            if(bits==0xf){bits=0;++a.bodyCounter130;}
        }
        if(timer()!=0||!attackerEnded())return;
        a.bodyState128=uint32_t(int32_t(a.bodyState128)+1);
        const int32_t q=int32_t(a.bodyCounter130)/3;const int32_t lvl=q<3?q:2;
        a.timers[23]=(6-2*lvl)*256;
        if(int32_t(a.bodyState128)>=6) {
            a.bodyState128=0;++a.bodyLatch12c;
            if(int32_t(a.bodyLatch12c)>=4) {
                capture::queue(a,0x226);bind(a,0x169a50,1);a.callbacks260[5]=0;
                queue2(v,0x58c);bind(v,kimRelease,2);
                return;
            }
        }
        copyPosition(vb,ab);
        capture::queue(a,int32_t(a.bodyState128)+6*lvl+0x214);
        queue2(v,0x580+2*int32_t(a.bodyState128));
        return;
    }
    case kimFixed: {
        if(timer()!=0||!attackerEnded())return;
        a.bodyState128=uint32_t(int32_t(a.bodyState128)+1);
        const int32_t st=int32_t(a.bodyLatch12c);
        a.timers[23]=(6-2*st)*256;
        if(int32_t(a.bodyState128)>=6) {
            capture::queue(a,0x293);bind(a,0x169a50,1);a.callbacks260[5]=0;
            v.pendingTable=2;v.pendingIndex=int16_t(st+0x18);v.request18c=1;
            return;
        }
        if(int32_t(a.bodyState128)==4-st) { // 140930(5, 2*s + 4)
            auto& b=*s.f.battle;b.timers.set(5,2*st+4,b.gauges.paused46a940?8:1);
        }
        copyPosition(vb,ab);
        capture::queue(a,int32_t(a.bodyState128)+6*st+0x281);
        queue2(v,0x580+2*int32_t(a.bodyState128));
        return;
    }
    case kimRelease:
        if(!actionEnded(vb,v.queuedActionA3c))return;
        queue2(v,0x58e);bind(v,kimFly,2);v.flags244&=~0x20000u;
        return;
    case kimFly: { // 14aad8(V, (int)(14adf0 + 2.0), 0, 0): either camera edge
        const auto& cam=s.f.weaponLock->camera;
        const int m=(v.character==0x2e?8:v.character==0x2f?16:34)+2;
        const int x=int(vb.timeline.motion().x);
        if(!(x>=cam.right-m||x<=cam.left+m))return;
        if(!holdReached(vb,v))return;
        bind(v,kimAir,2);
        v.flags244&=~0x10u; // 13a858 (byte 43d05e) is 0 under console VS
        return;
    }
    case kimAir:
        kimRecover(s,true); //1720b0
        if(!landingReady(vb,v.queuedActionA3c))return;
        stopAtGround(vb);
        if(kimRecover(s,false))return; //172008
        bind(v,kimLand,2);
        return;
    case kimLand:
        if(!landingReady(vb,v.queuedActionA3c))return;
        stopAtGround(vb);bind(v,0x169a50,2);v.callbacks260[5]=6;
        return;
    }
}
// ---- Character 32's k == 1 lock (201510; victim callbacks 2015e0 / 201708 / 201818 / 201928 / 201a20) ----
constexpr uint32_t kgStart=0x2015e0,kgLevel1=0x201708,kgLevel2=0x201818,kgLevel3=0x201928,kgRelease=0x201a20;
void karakuriLockStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    a.callbacks260={};a.override27c={};
    capture::queue(a,0x264);a.characterBytesF14[10]=0; // f1e
    copyPosition(s.body,s.sourceBody);v.bodyState128=0;
    queue2(v,0x62b);bind(v,kgStart,2);
    captureObjects(s,32,1);
}
void karakuriLockVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& ab=s.sourceBody;auto& vb=s.body;
    auto& level=a.characterBytesF14[10]; // f1e
    const auto hold=[&]{return bool(ab.timeline.clock().flags104&0x100);};
    const auto release=[&]{const auto c=ab.timeline.clock();ab.setFlags(c.flags104&~0x100u,c.flags108);};
    if(!s.f.opponentInput)throw std::runtime_error("Character 32's lock reads the attacker's commands");
    const auto& in=*s.f.opponentInput;
    const auto step=[&](uint8_t need,unsigned slot,uint8_t next,int act,uint32_t follow,bool last) {
        if(hold()) {
            vb.markActorActionPending();capture::queue(v,0x62e); // 1493c0(V, 0x62e, 1)
            release();
            if(level==next){capture::queue(a,act);bind(v,last?kgRelease:follow,2);}
            else bind(v,kgRelease,2);
            return;
        }
        const bool latch=ab.timeline.clock().flags108&0x40; // read at entry
        if(level!=need||!in.special.at(slot).recognized)return;
        if(latch)level=next;
    };
    switch(v.callbacks260[0]) {
    case kgStart:
        if(!actionEnded(ab,a.queuedActionA3c))return;
        capture::queue(a,0x265);level=0;
        copyPosition(vb,ab);vb.timeline.stopMotion();
        {const ScalarFloat x{std::bit_cast<uint32_t>(vb.timeline.motion().x)},y{std::bit_cast<uint32_t>(vb.timeline.motion().y)};
         const auto nx=(ab.timeline.clock().objectFlags&0x80000)?x.sub(ScalarFloat::integer(32)):x.add(ScalarFloat::integer(32));
         vb.timeline.setPosition(std::bit_cast<float>(nx.bits),std::bit_cast<float>(y.add(ScalarFloat::integer(48)).bits));}
        capture::queue(v,0x62d);bind(v,kgLevel1,2);
        return;
    case kgLevel1:step(0,6,1,0x266,kgLevel2,false);return;
    case kgLevel2:step(1,7,2,0x267,kgLevel3,false);return;
    case kgLevel3:
        if(hold()) {
            vb.markActorActionPending();capture::queue(v,0x62e);release();
            if(level==3)capture::queue(a,0x268);
            bind(v,kgRelease,2);
            return;
        }
        {const bool latch=ab.timeline.clock().flags108&0x40;
         if(level!=2||!in.special.at(8).recognized)return;
         if(latch)level=3;}
        return;
    case kgRelease:
        if(!hold())return; // the attacker's hold bit stays set here
        bind(a,0x169a50,1);a.callbacks260[5]=0;
        v.pendingTable=2;v.pendingIndex=0x3f;v.request18c=1;
        return;
    }
}
// ---- Character 33's row-missing sequences: k 0 (202a78), k 1 (202bf0), k 2 (202e48) ----
constexpr uint32_t ofuRelease0=0x202b28,ofuRelease1=0x202ca8,ofuSlide=0x202d98,
                   ofuWait=0x202f50,ofuCards=0x2030a0,ofuBurst=0x203130,ofuFall=0x203408,ofuDrop=0x2034f0;
void ofudaPin(PlayerObject& b){b.timeline.stopMotion();const auto c=b.timeline.clock();b.setFlags(c.flags104|0x132,c.flags108);} //11e238
void clear104(PlayerObject& b,uint32_t bits){const auto c=b.timeline.clock();b.setFlags(c.flags104&~bits,c.flags108);}
void ofudaElement(Script& s,int state) { // 14a890(V, 1, state)
    auto& v=s.v;
    v.contactKind252=1;v.fieldA2c=1;v.landingCount253=(v.landingCount253+1)&15;
    if(!s.f.battle)throw std::runtime_error("14a890 needs the battle");
    spawnElementHurt(s.f.weaponLock->objects,*s.f.battle,s.context.player,s.body,v,state);
}
float stageMiddle(Script& s){const auto& c=s.f.weaponLock->camera;return float((c.left+c.right)/2);}
void ofudaStart(Script& s,unsigned k) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    a.callbacks260={};a.override27c={};
    capture::queue(a,k==0?0x22a:k==1?0x231:0x240);
    copyPosition(s.body,s.sourceBody);ofudaPin(s.body);
    if(k==2) {
        if(!s.f.battle)throw std::runtime_error("202e48 needs the battle camera");
        auto& cam=s.f.battle->camera;cam.commands.clear();cam.appendCommand(4,0x30);cam.appendCommand(1,0);cam.appendCommand(0,0);
        ActorTimers t{v.timerDelta,v.timers};t.set(22,0x3c);v.timers=t.values;
    }
    bind(v,k==0?ofuRelease0:k==1?ofuRelease1:ofuWait,2);
    if(k==2){v.bodyCounter130=0;a.bodyState128=0;a.bodyLatch12c=0;}
    captureObjects(s,33,k);
    if(k==1)v.flags244&=~0x20000u;
}
// 203618: the curtain fade (attacker body 128/12c/134) and the victim's shake while 130 runs.
void ofudaUpdate(Script& s) {
    auto& a=s.a;auto& v=s.v;
    const int32_t step=int32_t(s.sourceBody.childParentWords()[0x30/4]);
    s.sourceBody.scriptLatch134+=uint32_t(step);
    int32_t level=int32_t(a.bodyState128)+int32_t(uint32_t(int32_t(a.bodyLatch12c))*uint32_t(step));
    if(level>0xff00)level=0xff00;else if(level<0)level=0;
    a.bodyState128=uint32_t(level);
    if(int32_t(v.bodyCounter130)>0) {
        const int32_t q=int32_t(v.bodyCounter130)/256;
        if(q<17||!(q&1)){v.bodyFieldE4=0;v.bodyFieldE8=0;}
        else {
            if(!s.f.random)throw std::runtime_error("203618 draws the game RNG");
            v.bodyFieldE4=uint32_t(int32_t(s.f.random->bounded(5))*2-4);v.bodyFieldE8=uint32_t(int32_t(s.f.random->bounded(5))*2-4);
        }
        v.bodyCounter130=uint32_t(int32_t(v.bodyCounter130)-int32_t(s.body.childParentWords()[0x30/4]));
        if(int32_t(v.bodyCounter130)<=0&&a.bodyCounter130) {
            auto& o=s.context.tasks.objects.at(a.bodyCounter130-1);
            o[0x104/4]|=2;o[0x108/4]|=0x1000;a.bodyCounter130=0;
            s.body.timeline.setPosition(s.body.timeline.motion().x,0.f);
            const auto c=s.body.timeline.clock();s.body.setFlags(c.flags104|2,c.flags108);
        }
    }
    if(!s.f.battle)throw std::runtime_error("140630 needs the battle");
    s.f.battle->flags138|=0x40; //140630(6)
}
// (float)((double)f * 2.8) through 310be0 / 310fa0 / 311510.
float timesTwoPointEight(float f) {
    const double d=softMul(double(f),2.8);
    float r=float(d);
    if(std::fabs(double(r))>std::fabs(d))r=std::nextafter(r,0.0f);
    return r;
}
void ofudaVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& vb=s.body;auto& ab=s.sourceBody;
    const auto hold=[&]{return bool(ab.timeline.clock().flags104&0x100);};
    ActorTimers t{v.timerDelta,v.timers};
    const auto save=[&]{v.timers=t.values;};
    const auto releaseAttacker=[&]{bind(a,0x169a50,1);a.callbacks260[5]=0;};
    switch(v.callbacks260[0]) {
    case ofuRelease0:
        if(!hold())return;
        releaseAttacker();clear104(vb,2);
        v.pendingTable=2;v.pendingIndex=0x40;v.request18c=1;
        ofudaElement(s,0x40);
        return;
    case ofuRelease1:
        if(!hold())return;
        releaseAttacker();copyPosition(vb,ab);clear104(vb,2);
        queue2(v,0x632);ofudaElement(s,v.stateIndex());bind(v,ofuSlide,2);
        return;
    case ofuSlide: { // 14aad8(V, (int)(14adf0 + 2.0), 0, 0): either camera edge
        const auto& cam=s.f.weaponLock->camera;
        const int m=(v.character==0x2e?8:v.character==0x2f?16:34)+2;
        const int x=int(vb.timeline.motion().x);
        if(!(x>=cam.right-m||x<=cam.left+m)){s.f.battle->flags138|=4;return;}
        s.f.battle->camera.appendCommand(3,0x3c);
        bind(v,0x169a50,2);v.callbacks260[5]=6;
        return;
    }
    case ofuWait: {
        if(t.decrease(22)!=0){save();return;}
        auto& o=attackerOwnedEffect(s,0x243);
        o[0x38/4]&=~0x80000u;o[0x38/4]|=0x40000000u;o[0x44/4]=std::bit_cast<uint32_t>(220.0f);
        o[0x108/4]=(o[0x108/4]|0x80000)&~0x2000u;o[0x8c/4]=0x808080;
        o[0x40/4]=std::bit_cast<uint32_t>(stageMiddle(s));
        a.bodyCounter130=uint32_t(&o-s.context.tasks.objects.data())+1;ab.scriptLatch134=0;
        a.bodyState128=0;a.bodyLatch12c=12;
        t.set(22,0x1e);save();bind(v,ofuCards,2);
        return;
    }
    case ofuCards:
        if(t.decrease(22)==0){vb.scriptLatch134=0;t.set(22,0x50);t.set(23,0);bind(v,ofuBurst,2);}
        save();ofudaUpdate(s);
        return;
    case ofuBurst: {
        const float cx=stageMiddle(s);
        if(!s.f.startWorld||!s.f.sound||!s.f.random)throw std::runtime_error("203130 needs the world effects, sound and RNG");
        const unsigned seat=1-s.context.player;
        if(t.decrease(22)==0) {
            s.f.startWorld(0x2b,0,seat,cx,350.0f,0.0f,1.4f);
            s.f.sound->act(0xd2,int(seat),voiceCharacter(a),a.flags23c,3,0,*s.f.random);
            t.set(22,0x52);save();bind(v,ofuFall,2);
            queue2(v,0x634);v.fieldA2c=1;
            const auto vw=vb.childParentWords();
            for(unsigned act:{4u,5u}) { // 16c408(cb, act, 1, 0): common kind-7 at the victim
                const auto h=s.f.weaponLock->objects.createCommonEffect(s.context.tasks,s.f.battle->objectTasks,&vw,0x1396,0);
                if(!h)throw std::runtime_error("Original 16c408 writes through a null object");
                auto& e=s.context.tasks.objects.at(h-1);
                e[0x118/4]=s.context.player+1;e[0x40/4]=vw[0x40/4];e[0x44/4]=vw[0x44/4];
                s.f.weaponLock->objects.request(e,act,false,true);e[0x108/4]|=0x2000;
            }
            clear104(vb,2);stopAtGround(vb);
            vb.timeline.setPosition(cx,350.0f);v.bodyCounter130=0x4000;
            ofudaUpdate(s);
            return;
        }
        if(t.decrease(23)!=0){save();ofudaUpdate(s);return;}
        auto& rng=*s.f.random;
        const int32_t r=int32_t(rng.bounded(100));
        const auto fdiv=[](int32_t n,float d){return std::bit_cast<float>(ScalarFloat::integer(n).div(ScalarFloat{std::bit_cast<uint32_t>(d)}).bits);};
        const float sc=eeSub(eeAdd(fdiv(r+100,1600.0f),0.2f),fdiv(int32_t(vb.scriptLatch134),14.0f));
        float x;
        if(vb.scriptLatch134&1)x=eeAdd(cx,float(0x6c-int32_t(rng.bounded(40))));
        else x=eeSub(cx,float(int32_t(rng.bounded(40))+0x6c));
        const float y=eeSub(350.0f,float(int32_t(rng.bounded(48))+0x20));
        s.f.startWorld(0x2b,0,seat,x,y,0.0f,timesTwoPointEight(sc));
        s.f.sound->sample(int(seat),0x32);s.f.sound->sample(int(seat),0x33);
        ++vb.scriptLatch134;
        t.set(23,0x28);save();ofudaUpdate(s);
        return;
    }
    case ofuFall:
        if(t.decrease(22)==0) {
            a.bodyState128=0x10000;a.bodyLatch12c=uint32_t(-0x10);
            s.f.battle->camera.commands.clear();
            t.set(22,0x1e);bind(v,ofuDrop,2);
            // 2037a8: two attacker-side objects facing apart, 32 either side of the attacker.
            auto& o1=attackerOwnedEffect(s,0x23b);auto& o2=attackerOwnedEffect(s,0x23c);
            const float ax=ab.timeline.motion().x;
            if(!(ab.timeline.clock().objectFlags&0x80000)) {
                o1[0x40/4]=std::bit_cast<uint32_t>(eeAdd(ax,32.0f));o1[0x38/4]|=0x80000;
                o2[0x38/4]&=~0x80000u;o2[0x40/4]=std::bit_cast<uint32_t>(eeSub(ax,32.0f));
            } else {
                o1[0x40/4]=std::bit_cast<uint32_t>(eeSub(ax,32.0f));o1[0x38/4]&=~0x80000u;
                o2[0x38/4]|=0x80000;o2[0x40/4]=std::bit_cast<uint32_t>(eeAdd(ax,32.0f));
            }
        }
        save();
        if(v.timers[22]<0x1000&&(a.flags244&0x200000)){capture::queue(a,0x241);a.flags244&=~0x200000u;}
        ofudaUpdate(s);
        return;
    case ofuDrop:
        if(t.decrease(22)==0) {
            a.flags244&=~0x200000u;releaseAttacker();
            vb.timeline.setPosition(vb.timeline.motion().x,480.0f);clear104(vb,2);
            v.pendingTable=2;v.pendingIndex=0x46;v.request18c=1;
            save();ofudaElement(s,0x46);
            s.f.battle->camera.appendCommand(5,0x3c);
        } else save();
        ofudaUpdate(s);
        return;
    }
}
// ---- Kuroko's k == 6 grab (20b400): two optional repeats on special slot 18 ----
constexpr uint32_t kkA1v=0x20b4d0,kkA2v=0x20b588,kkA3v=0x20b648,kkB1v=0x20b7b8,kkB2v=0x20b870,kkB3v=0x20b930,kkEnd=0x20baa0;
void attackerLayer(PlayerObject& b,bool on){const auto k=b.timeline.clock();b.timeline.setObjectFlags(on?k.objectFlags|0x80000000u:k.objectFlags&0x7fffffffu,k.flags104,k.flags108);}
void kurokoGrabStart(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    s.sourceBody.timeline.stopMotion();capture::queue(a,0x2a1);
    a.callbacks260={};a.override27c={};
    copyPosition(s.body,s.sourceBody);s.body.timeline.setPosition(s.body.timeline.motion().x,0.f);
    queue2(v,0x513);bind(v,kkA1v,2);
    captureObjects(s,48,6);
}
void kurokoGrabVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;auto& ab=s.sourceBody;
    const bool e=actionEnded(ab,a.queuedActionA3c);
    const auto hold=[&](int act,bool layer,int vact,uint32_t next) {
        capture::queue(a,act);
        if(layer)attackerLayer(ab,true);
        queue2(v,vact);s.body.pendingFlags|=8;bind(v,next,2);
    };
    const auto decision=[&](int repeatAct,uint32_t repeatNext,int finishAct) {
        if(!s.f.opponentInput)throw std::runtime_error("Kuroko's grab reads special slot 18");
        if(s.f.opponentInput->special[18].recognized)a.bodyState128=1; // actor+634
        if(!e&&a.bodyState128!=1)return;
        if(a.bodyState128==0) { // FINISH
            capture::queue(a,finishAct);bind(a,0x169a50,1);a.callbacks260[5]=5;
            queue2(v,0x198);bind(v,0x169a50,2);v.callbacks260[5]=0;
            return;
        }
        capture::queue(a,repeatAct);queue2(v,0x513);s.body.pendingFlags|=8;bind(v,repeatNext,2);
    };
    switch(v.callbacks260[0]) {
    case kkA1v:if(e)hold(0x2a2,true,0x530,kkA2v);break;
    case kkA2v:if(e){capture::queue(a,0x2a3);a.bodyState128=0;attackerLayer(ab,false);queue2(v,0x513);s.body.pendingFlags|=8;bind(v,kkA3v,2);}break;
    case kkA3v:decision(0x2a5,kkB1v,0x2a4);break;
    case kkB1v:if(e)hold(0x2a6,true,0x530,kkB2v);break;
    case kkB2v:if(e){capture::queue(a,0x2a7);a.bodyState128=0;attackerLayer(ab,false);queue2(v,0x513);s.body.pendingFlags|=8;bind(v,kkB3v,2);}break;
    case kkB3v:decision(0x2a9,kkEnd,0x2a8);break;
    case kkEnd:
        if(e) {
            capture::queue(a,0x2aa);a.flags23c&=~0x10000000u;bind(a,0x20bbb0,1);attackerLayer(ab,true);
            queue2(v,0x530);s.body.pendingFlags|=8;bind(v,0x169a50,2);v.callbacks260[5]=4;
        }
        break;
    }
    const auto k=ab.timeline.clock();ab.setFlags(k.flags104|0x2000,k.flags108); // every visit
}
bool isKurokoGrabCallback(uint32_t h){return h==kkA1v||h==kkA2v||h==kkA3v||h==kkB1v||h==kkB2v||h==kkB3v||h==kkEnd;}
bool isOfudaCallback(uint32_t h) {
    return h==ofuRelease0||h==ofuRelease1||h==ofuSlide||h==ofuWait||h==ofuCards||h==ofuBurst||h==ofuFall||h==ofuDrop;
}
bool isKyoshiroCallback(uint32_t h){return h==kyoWait||h==kyoPull||h==kyoFall||h==kyoLand;}
// ---- Sieger's k == 5 carry (205f88 -> 2063e8, victim callbacks 2064a8 / 206548) ----
constexpr uint32_t siegerCarry=0x2064a8,siegerPin=0x206548;
void siegerCarryStart(Script& s) { // 2063e8
    auto& v=s.v;auto& a=s.a;
    if(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80)){request(v,2,74);v.request18c=1;return;} // 168318(cb, 1)
    capture::queue(a,0x24a);queue2(v,0x64e);
    a.callbacks260={};a.override27c={};s.sourceBody.timeline.stopMotion();
    bind(v,siegerCarry,2);
    captureObjects(s,37,5);
    v.flags244&=~0x20000u;
}
void siegerCarryVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;
    if(v.callbacks260[0]==siegerCarry) {
        // 14aad8(V, (int)(14adf0 + 2.0), 0, 0): either camera edge.
        const auto* camera=s.f.weaponLock?&s.f.weaponLock->camera:nullptr;
        if(!camera)throw std::runtime_error("Sieger's carry needs the live camera");
        const int m=(v.character==0x2e?8:v.character==0x2f?16:34)+2;
        const int x=int(s.body.timeline.motion().x);
        if(x>=camera->right-m||x<=camera->left+m){queue2(v,0x650);bind(v,siegerPin,2);}
        return;
    }
    // 206548: 16a830(cb, 16) on the victim's side, then both let go.
    const int r=v.character==0x2e?8:v.character==0x2f?16:34;
    const float x=s.body.timeline.motion().x;
    const ScalarFloat ax{std::bit_cast<uint32_t>(s.sourceBody.timeline.motion().x)},d=ScalarFloat::integer(16);
    const bool reached=(s.body.timeline.clock().objectFlags&0x80000)
        ?(x<=float(r)||x<=std::bit_cast<float>(ax.add(d).bits))
        :(float(int(640.f-float(r)))<=x||std::bit_cast<float>(ax.sub(d).bits)<=x);
    if(!reached)return;
    // 14fa18 on the attacker's spirit: 170240 for systems 1/7, else 170010.
    auto& world=*s.f.weaponLock;const auto parent=s.body.childParentWords();
    if(s.f.opponentSystem==1||s.f.opponentSystem==7)
        world.objects.dropSpecial(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
    else world.objects.drop(s.context.tasks,world.objectTasks,*s.f.random,s.context.player,v.character,v.flags23c,parent);
    // 1493c0(A, 0x24b, 1): a forced queue marks the old body first.
    s.sourceBody.markActorActionPending();capture::queue(a,0x24b);bind(a,0x169a50,1);a.callbacks260[5]=0;
    queue2(v,0x652);bind(v,0x169a50,2);v.callbacks260[5]=5;
}
bool isSiegerCallback(uint32_t h){return h==siegerCarry||h==siegerPin;}
bool behindWall(Script& s) { // 14aad8(V, (int)(14adf0 + 2.0), 1, 1) -> 146a50
    const auto* camera=s.f.weaponLock?&s.f.weaponLock->camera:nullptr;
    if(!camera)throw std::runtime_error("Gaira's throw needs the live camera");
    const unsigned c=s.v.character;
    const int m=(c==0x2e?8:c==0x2f?16:34)+2;
    const int x=int(s.body.timeline.motion().x);
    return (s.body.timeline.clock().objectFlags&0x80000)?x>=camera->right-m:x<=camera->left+m;
}
void gairaGrabVisit(Script& s) {
    auto& v=s.v;auto& a=s.a;
    auto& battle=*s.f.battle;
    switch(v.callbacks260[0]) {
    case gairaMash: { // 1f3db8: the attacker mashes all four buttons per set
        if(std::bit_cast<int32_t>(a.bodyState128)>=0) {
            const auto& f=s.f.opponentInput;
            if(!f)throw std::runtime_error("Gaira's grab reads the attacker's buttons");
            const auto& in=f->sampledFeatures; // actor+3ac..3b8 = features 58..61
            auto& m=s.sourceBody.scriptLatch134;
            if(in[59])m|=1;
            if(in[60])m|=2;
            if(in[58])m|=4;
            if(in[61])m|=8;
            if(m==0xf){m=0;++a.bodyCounter130;}
        }
        ActorTimers t{a.timerDelta,a.timers};
        const auto old=t.decrease(23);a.timers[23]=t.values[23];
        if(old!=0||!actionEnded(s.sourceBody,a.queuedActionA3c))return;
        ++a.bodyState128;
        const int32_t sets=std::bit_cast<int32_t>(a.bodyCounter130);
        int32_t tier=(sets<0?sets+3:sets)>>2;if(tier>=3)tier=2;
        t.set(23,6-2*tier);a.timers[23]=t.values[23];
        if(std::bit_cast<int32_t>(a.bodyState128)>=6) {
            a.bodyState128=0;++a.bodyLatch12c;
            if(std::bit_cast<int32_t>(a.bodyLatch12c)>=8) {
                capture::queue(a,0x25e);bind(a,0x169a50,1);a.callbacks260[5]=0;
                queue2(v,0x58c);bind(v,gairaThrow,2);
                return;
            }
        }
        copyPosition(s.body,s.sourceBody);
        capture::queue(a,0x24c+int32_t(a.bodyState128)+6*tier);
        queue2(v,0x580+2*int32_t(a.bodyState128));
        return;
    }
    case gairaThrow: // 1f4010
        if(actionEnded(s.body,v.queuedActionA3c)) {
            queue2(v,0x58e);bind(v,gairaWall,2);v.flags244&=~0x20000u;
            battle.flags138|=4; // 140630(2)
        }
        return;
    case gairaWall: // 1f4098
        if(behindWall(s)&&consumeHold(s.body,v)) {
            bind(v,0x174158,2);v.callbacks260[5]=10;
            battle.camera.requestShake(0x18,0);
            battle.camera.commands.clear();battle.camera.appendCommand(3,0x1e);
        }
        battle.flags138|=4; // 140630(2)
        return;
    default:unported(v);
    }
}
bool isGairaGrabCallback(uint32_t h){return h==gairaMash||h==gairaThrow||h==gairaWall;}
// 174158 for the victim (jump table 5f17b0, modes 0..11; every mode first
// waits for 1737d8). Returns true when mode 0 ends in 169810.
bool landing(PlayerObject& body,StateEntryActor& v) {
    using namespace capture;
    struct {PlayerObject& body;} s{body};
    auto& mode=v.callbacks260[5];
    if(!touchedGround(s.body,v.queuedActionA3c))return false;
    if(mode>=12)return false;
    switch(mode) {
    case 1:if(!consumeHold(s.body,v))return false;[[fallthrough]];
    case 0:
        if(actionEnded(s.body,v.queuedActionA3c))return true;
        bind(v,0x169a50,v.callbacks260[1]);mode=0;return false;
    case 5:if(!consumeHold(s.body,v))return false;[[fallthrough]];
    case 4:
        if(actionEnded(s.body,v.queuedActionA3c)){v.flags244&=~0x8000u;request(v,2,16);v.request18c=1;}
        else {bind(v,0x169a50,2);mode=5;}
        return false;
    case 9:if(!consumeHold(s.body,v))return false;[[fallthrough]];
    case 8:
        if(actionEnded(s.body,v.queuedActionA3c)){v.flags244|=0x8000;request(v,2,16);v.request18c=1;}
        else {bind(v,0x169a50,2);mode=6;}
        return false;
    default: // 2, 3, 6, 7, 10, 11
        if(consumeHold(s.body,v))--mode;
        return false;
    }
}
}

bool updateLanding174158(PlayerObject& body,StateEntryActor& actor,StateEntryContext&,const GroundStateFrame&){return landing(body,actor);}
void updateLifeHold(PlayerObject& body,StateEntryActor& a,StateEntryContext&,const GroundStateFrame& f) {
    if(!holdReached(body,a))return; //1699f8
    auto& n=a.characterBytesF14[7];if(++n>=3)n=2;
    if(!f.battle||!f.weaponLock)throw std::runtime_error("166e10 requires the live battle");
    f.battle->queueLifeChange(a,f.weaponLock->opponent.flags23c,std::bit_cast<int32_t>(a.bodyState128)); //14a8d0
    a.callbacks260[0]=0x169a50;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffffu;a.callbacks260[5]=0;
}
bool updateVictimScript(PlayerObject& body,StateEntryActor& v,StateEntryContext& context,const GroundStateFrame& f,const VictimTables& tables,
                        const ScriptEngine& scripts) {
    using namespace capture;
    if(!f.weaponLock)throw std::runtime_error("Victim scripts require both fighters");
    auto& world=*f.weaponLock;auto& a=world.opponent;auto& sourceBody=world.opponentBody;
    Script s{body,v,context,f,tables,scripts,a,sourceBody};
    const unsigned character=v.pendingCharacter254;
    if(v.callbacks260[0]==0x174158) {
        const bool recover=landing(body,v);GroundStateRuntime::captureBody(sourceBody,a);return recover;
    }
    if(isSiegerCallback(v.callbacks260[0])) {
        siegerCarryVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==shizuCarry) {
        shizumaruCatchVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(isKurokoGrabCallback(v.callbacks260[0])){kurokoGrabVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
    if(isOfudaCallback(v.callbacks260[0])){ofudaVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
    if(v.callbacks260[0]==kgStart||v.callbacks260[0]==kgLevel1||v.callbacks260[0]==kgLevel2||
       v.callbacks260[0]==kgLevel3||v.callbacks260[0]==kgRelease) {
        karakuriLockVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==kimMash||v.callbacks260[0]==kimRelease||v.callbacks260[0]==kimFly||
       v.callbacks260[0]==kimAir||v.callbacks260[0]==kimLand||v.callbacks260[0]==kimFixed) {
        kimLockVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==nicoPull) {
        nicotineCatchVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==genanPull) {
        genanCatchVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==irohaBow||v.callbacks260[0]==irohaDance||v.callbacks260[0]==irohaStrike||v.callbacks260[0]==irohaFade) {
        irohaVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==mizukiHold||v.callbacks260[0]==mizukiToss||v.callbacks260[0]==mizukiBounce) {
        mizukiThrowVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(isKyoshiroCallback(v.callbacks260[0])) {
        kyoshiroCatchVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(isSogetsuCallback(v.callbacks260[0])) {
        sogetsuCatchVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(isGairaGrabCallback(v.callbacks260[0])) {
        gairaGrabVisit(s);GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    if(v.callbacks260[0]==0x165cc0) {
        // 165cc0 per visit. 165da8 positions by type, then constrains all.
        const auto& row=s.row();
        auto* child=s.child();
        switch(row.type) {
        case 3:case 4:case 0x36:{const auto m=sourceBody.timeline.motion();follow(s,m.x,m.y);break;}
        case 5:case 0x1c:if(child)follow(s,std::bit_cast<float>((*child)[0x40/4]),std::bit_cast<float>((*child)[0x44/4]));break;
        case 0x5a: // Kuroko: once past record 2, the victim lands 88 units in front of the attacker, facing it
            if(int32_t(body.timeline.clock().step)>=2&&v.bodyState128==0) {
                const auto am=sourceBody.timeline.motion();
                const bool mirrored=sourceBody.timeline.clock().objectFlags&0x80000;
                const auto x=ScalarFloat{std::bit_cast<uint32_t>(am.x)};
                body.timeline.setPosition(std::bit_cast<float>((mirrored?x.add(ScalarFloat::integer(88)):x.sub(ScalarFloat::integer(88))).bits),body.timeline.motion().y);
                const auto k=body.timeline.clock();
                body.timeline.setObjectFlags(mirrored?k.objectFlags&~0x80000u:k.objectFlags|0x80000u,k.flags104,k.flags108);
                v.bodyState128=1;
            }
            break;
        default:break;
        }
        constrain(body);constrain(sourceBody);if(child)(*child)[0x104/4]|=0x2000;
        bool recover=false;
        if(waitsDone(s)) {
            recover=endOps(s);
            if(!(s.row().flags&1)) {
                ++v.registry28c[0];enterRow(s);
                if(instant(s.row()))recover=endOps(s)||recover;
            }
        }
        GroundStateRuntime::captureBody(sourceBody,a);
        return recover;
    }
    const int k=v.stateIndex()-80;
    if(!tables.handler(character)||k<0)unported(v);
    // The stub: 165780 lookup, 1696c8 strength, clear the entry callback.
    const uint32_t address=tables.find(character,unsigned(k));
    const unsigned str=strength(a);
    v.callbacks260[0]=0;
    // 1657b0 gate.
    auto* child=s.child();
    if(sourceInvalid(v,context,f)||(v.flags23c&0x10000000)) {
        // 1688c8 performs only row 0's weapon operation.
        if(address&&(tables.row(address).flags&0x80))loseWeapon(body,v,context,f);
        return false;
    }
    // 168f48, or 168700: a Sugoroku victim of Sugoroku's state-0x60 row keeps both facings.
    const bool noFacing=tables.fighters().noFacing(character,unsigned(k))||
                        (v.character==0x21&&v.pendingCharacter254==0x21&&v.stateIndex()==0x60);
    if(!child) {
        if(!(a.flags23c&0x10000000)) {
            if(!noFacing)oppositeFacing(body,sourceBody);
            else if(character==40&&(k==2||k==3)) { // Kim: the victim simply opposes the attacker's mirror
                const auto c=body.timeline.clock();const bool am=sourceBody.timeline.clock().objectFlags&0x80000;
                body.timeline.setObjectFlags(am?c.objectFlags&~0x80000u:c.objectFlags|0x80000u,c.flags104,c.flags108);
            }
        }
    } else if(!((*child)[0x104/4]&0x100000)) {
        if(!noFacing) {
            auto& flags=(*child)[0x38/4];
            const float x=body.timeline.motion().x,from=std::bit_cast<float>((*child)[0x40/4]);
            if(x<from)flags|=0x80000;else if(from<x)flags&=~0x80000u;
            const auto c=body.timeline.clock();
            body.timeline.setObjectFlags((c.objectFlags&~0x80000u)|(~flags&0x80000u),c.flags104,c.flags108);
        } else if(character==39&&k==0) { // Nicotine's chain: 14a978(V, 0), the victim faces its opponent
            GroundStateRuntime::captureBody(body,v);v.opponentX=sourceBody.timeline.motion().x;
            v.faceOpponent(false);GroundStateRuntime::restoreBody(body,v);
        }
        (*child)[0x104/4]|=0x100000;
    }
    a.flags23c|=0x10000000u;
    if(keepsObjects(character,unsigned(k)))a.flags244|=0x1000;else a.flags244&=~0x1000u;
    if(!address&&tables.fighters().victimK4Routine(character)) {
        // Damage form 2: the character's own code when the row is missing.
        if(character==10&&k==4){gairaGrabStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==48&&k==6){kurokoGrabStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;} // 20b400 (no 104 write)
        if(character==33&&k<3){ofudaStart(s,k);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==32&&k==1){karakuriLockStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==32&&k==2){GroundStateRuntime::captureBody(sourceBody,a);return false;} // returns, no recovery
        if(character==40&&(k==0||k==1)){kimLockStart(s,k==0,str);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==39&&k==0){nicotineCatchStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==35&&k==0x10){genanCatchStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==31&&k==0){irohaStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==27&&k==3){mizukiThrowStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==11&&k==3){amakusaCatchStart(s,a.flags23c&0x400000);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==9&&k==1){shizumaruCatchStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==5&&k==0){kyoshiroCatchStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==17&&k==0){sogetsuCatchStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character==37&&k==5){siegerCarryStart(s);GroundStateRuntime::captureBody(sourceBody,a);return false;}
        if(character!=5&&character!=9&&character!=11&&character!=27&&character!=31&&character!=35&&character!=39&&character!=40&&character!=32&&character!=33&&character!=48&&character!=10&&character!=17&&character!=37)unported(v); // an unported character branch
    }
    if(!address){GroundStateRuntime::captureBody(sourceBody,a);return true;} // 169810
    // 165a78 start; 1634e8 registry.
    const auto& row=tables.row(address);
    auto& r=v.registry28c;
    r[12]=address;r[3]=str;r[2]=0xffffffffu;r[0]=0;r[1]=0xffffffffu;r[7]=r[8]=r[9]=0;
    const bool paired=row.flags&0x20;
    // 168318: a paired row needs a live, undamaged attacker.
    if(paired&&(a.stateTable()==2||a.fieldA30<=0||(a.flags23c&0x80))) {
        request(v,2,74);v.request18c=1;GroundStateRuntime::captureBody(sourceBody,a);return false;
    }
    v.callbacks260={};v.override27c={};v.callbacks260[3]=str;v.bodyState128=v.bodyLatch12c=v.bodyCounter130=0;
    if(paired) {
        a.callbacks260={};a.override27c={};a.request18c=0;a.pendingTable=a.pendingIndex=-1;
        a.timers[0]=a.timers[1]=0;
    } else a.flags23c&=~0x10000000u;
    if((row.flags&0x40)&&child) {
        // Adopt the delivering object: 11db30 clears e8/dc/e4, 147530 parks
        // its task on 147540 and the pending deletion bits are cancelled.
        auto& o=*child;
        o[0xe8/4]=o[0xdc/4]=o[0xe4/4]=0;
        context.tasks.tasks.at(o[0x04/4]-1)[0]=0x147540;
        o[0x108/4]&=~0x7000u;
        r[10]=v.bodyField124;
    } else r[10]=0;
    // 168400.
    if(!(a.flags244&0x1000)&&f.suppressCaptureObjects)f.suppressCaptureObjects();
    if(!(character==27&&k==0)&&!(character==40&&k==2))v.flags244|=0x10; // 168400 (see captureObjects)
    if(body.timeline.action().id()!=1578)body.timeline.stopMotion();
    if(tables.fighters().weaponHold(character,unsigned(k)))v.flags244|=0x20000; //169218
    enterRow(s);
    bool recover=false;
    if(instant(row))recover=endOps(s);
    else callback(v,0x165cc0,2,0);
    v.timers[0]=v.timers[1]=0;
    GroundStateRuntime::captureBody(sourceBody,a);
    return recover;
}
}
