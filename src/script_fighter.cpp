#include <initializer_list>
#include "script_fighter.hpp"
#include "ground_state.hpp"
#include "script_engine.hpp"
#include "fighter_tables.hpp"
#include "knockout.hpp"
#include "jump_motion.hpp"
#include "battle_round.hpp"
#include "auxiliary_objects.hpp"
#include "poppy.hpp"

// Fighters whose moves all run through ScriptEngine. The attack stub of
// form 1 has no other code; form 2 stubs run character code when the
// selector has no script. Those branches and their follow-up callbacks are
// ported here per character, with the original addresses as callback IDs.
#include "rera_wolf.hpp"
#include "nakoruru_eagle_attack.hpp"
namespace ss6 {
namespace {
struct Ctx {
    PlayerObject& o;StateEntryActor& a;const ActorCommandInput& input;const GroundStateFrame& f;const ScriptEngine& scripts;
    StateEntryContext& context;
};
bool consumeHold(PlayerObject& b,const StateEntryActor& a) { //1699f8
    const auto c=b.timeline.clock();
    const bool done=actionEnded(b,a.queuedActionA3c)||(c.flags104&0x100);
    b.setFlags(c.flags104&~0x100u,c.flags108);
    return done;
}
void bind(StateEntryActor& a,uint32_t pc,unsigned table=1) { //1522a0(260, pc, table, -1)
    a.callbacks260[0]=pc;a.callbacks260[1]=table;a.callbacks260[2]=0xffffffffu;
}
void face(Ctx& c) { //14a978(actor, 0)
    GroundStateRuntime::captureBody(c.o,c.a);c.a.opponentX=c.f.opponentX;c.a.faceOpponent();GroundStateRuntime::restoreBody(c.o,c.a);
}
void queue(Ctx& c,int act){c.scripts.queue(c.o,c.a,c.f,act);} //1493c0
bool ended(Ctx& c){return actionEnded(c.o,c.a.queuedActionA3c);} //149488
enum class Visit {NotMine,Continue,Recover};
// 1696c8: strength from the effective attack flags (4 heavy, 2 medium).
unsigned strength(const StateEntryActor& a){const auto f=a.effectiveFlags();return (f&4)?2:(f&2)?1:0;}
void setBody104(Ctx& c,uint32_t bits){const auto k=c.o.timeline.clock();c.o.setFlags(k.flags104|bits,k.flags108);}
// 16c408(cb, act, 0, 0): an own kind-6 effect (tag 0x1396, no callback) at
// the body position with a forced ACT request, 108 |= 0x2000, no attachment offset.
AuxiliaryObject& ownEffect(Ctx& c,unsigned act) {
    auto& w=*c.f.weaponLock;
    if(!c.f.pools)throw std::runtime_error("16c408 requires the live object pools");
    const auto handle=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x1396,6,0);
    if(!handle)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& o=c.f.pools->objects.at(handle-1);
    w.objects.request(o,act,false,true);o[0x108/4]|=0x2000;
    return o;
}

// ---- Ukyo (6): 1f1d38 selector 12 -> 1f1e80 -> 1f1ed8 -> 1f1f70 ----
constexpr uint32_t ukyoSecond=0x1f1ed8,ukyoThird=0x1f1f70;
bool ukyoEntry(Ctx& c,uint32_t selector) {
    if(selector!=12)return false;
    face(c);queue(c,0x246);bind(c.a,ukyoSecond);
    return true;
}
Visit ukyoVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case ukyoSecond: // a contact (104 bit 0x80000) continues with ACT 0x247
        consumeHold(c.o,c.a);
        if(ended(c))return Visit::Recover;
        if(c.o.timeline.clock().flags104&0x80000){queue(c,0x247);bind(c.a,ukyoThird);}
        return Visit::Continue;
    case ukyoThird:
        consumeHold(c.o,c.a);
        return ended(c)?Visit::Recover:Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Yumeji (28): 1ff270 selectors 9/10 -> 1ff3b8 -> 1ff450 ----
constexpr uint32_t yumejiFollow=0x1ff450;
bool yumejiEntry(Ctx& c,uint32_t selector) {
    const uint32_t n=selector-9;
    if(n>=2)return false;
    c.a.callbacks260[3]=n;face(c);c.a.bodyLatch12c=0xffffffffu;
    queue(c,n==1?0x246:0x243);bind(c.a,yumejiFollow);
    return true;
}
Visit yumejiVisit(Ctx& c) {
    if(c.a.callbacks260[0]!=yumejiFollow)return Visit::NotMine;
    auto& choice=c.a.bodyLatch12c; // body+12c: the follow-up chosen during the hold
    if(ended(c)) {
        const int act=int(c.o.timeline.action().id());
        queue(c,choice==6?act+1:choice==7?act+2:0x249);
        bind(c.a,0x169a50);c.a.callbacks260[5]=0;
        return Visit::Continue;
    }
    if(c.o.timeline.clock().flags108&0x40) {
        const auto& s=c.input.sampledFeatures; // actor+2dc..2ec = features 6..10
        if(s[6])choice=6;
        else if(s[7])choice=7;
        else if(s[8]||s[9]||s[10])choice=0xffffffffu;
    }
    return Visit::Continue;
}

// ---- Charlotte (14): 1f55a0 selectors 10..12 -> 1f56e8 -> 1f5770 ----
constexpr uint32_t charlotteHold=0x1f5770,charlotteShot=0x1f5860;
bool charlotteEntry(Ctx& c,uint32_t selector) {
    const uint32_t n=selector-10;
    if(n>=3)return false;
    c.a.callbacks260[3]=n;face(c);
    c.a.bodyState128=0;c.a.bodyLatch12c=n+0x5b; // body+128 released, +12c = watched button feature
    queue(c,int(0x211+n));bind(c.a,charlotteHold);
    return true;
}
Visit charlotteVisit(Ctx& c) {
    if(c.a.callbacks260[0]!=charlotteHold)return Visit::NotMine;
    if(consumeHold(c.o,c.a))c.a.bodyState128=1;
    // Fires at the end of the ACT, or after the hold once the button is released.
    if(!ended(c)&&(!c.a.bodyState128||c.input.sampledFeatures.at(c.a.bodyLatch12c)))return Visit::Continue;
    // 1f5828: 16c5f8(cb, 1f5860, 0x217 + n, 0), d0 = 0x1e.
    auto& w=*c.f.weaponLock;
    if(!c.f.pools)throw std::runtime_error("Charlotte's shot requires the live object pools");
    const auto handle=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x138e + c.context.player,2,charlotteShot);
    if(!handle)throw std::runtime_error("Original 1f5828 writes through a null object");
    auto& o=c.f.pools->objects.at(handle-1);
    w.objects.request(o,0x217+c.a.callbacks260[3],false,true);
    o[0xd0/4]=0x1e;o[0xd4/4]=uint32_t(c.a.stateIndex()-64);
    queue(c,int(0x214+c.a.callbacks260[3]));bind(c.a,0x169a50);c.a.callbacks260[5]=0;
    return Visit::Continue;
}

// ---- Yoshitora (22): 1faf60 selectors 7..9 -> 1fb0a8(strength) -> 1fb120 -> 1fb1b0 -> 1fb248 ----
constexpr uint32_t yoshitoraSecond=0x1fb120,yoshitoraThird=0x1fb1b0,yoshitoraLast=0x1fb248;
bool yoshitoraEntry(Ctx& c,uint32_t selector) {
    if(selector-7u>=3)return false;
    const unsigned n=strength(c.a); // the selector only gates; the ACT follows 1696c8
    c.a.callbacks260[3]=n;face(c);c.o.scriptLatch134=0;
    queue(c,int(0x22c+n));bind(c.a,yoshitoraSecond);
    return true;
}
Visit yoshitoraVisit(Ctx& c) {
    const unsigned n=c.a.callbacks260[3];
    switch(c.a.callbacks260[0]) {
    case yoshitoraSecond:
        if(ended(c)){c.a.flags244|=0x80000;queue(c,int(0x22f+n));bind(c.a,yoshitoraThird);}
        setBody104(c,0x2000);
        return Visit::Continue;
    case yoshitoraThird:
        if(ended(c)){c.a.flags244&=~0x80000u;queue(c,int(0x232+n));bind(c.a,yoshitoraLast);}
        setBody104(c,0x2000);
        return Visit::Continue;
    case yoshitoraLast:
        if(ended(c))return Visit::Recover;
        // One effect per move, at the first ACT marker 104:40000.
        if((c.o.timeline.clock().flags104&0x40000)&&!c.o.scriptLatch134) {
            auto& e=ownEffect(c,(c.a.flags23c&0x100000)?0x298:0x235);
            e[0x108/4]=(e[0x108/4]|0x20000)&~0x18000u;
            c.o.scriptLatch134=1;
        }
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Kusaregedo (25): 1fdef8 selectors 3/4 -> 1fe068/1fe0e0 -> 1fe150 -> 1fe1b8 ----
constexpr uint32_t gedoWait=0x1fe150,gedoShot=0x1fe280;
bool gedoEntry(Ctx& c,uint32_t selector) {
    if(selector!=3&&selector!=4)return false;
    c.a.callbacks260[3]=0;face(c);
    c.a.bodyLatch12c=selector==3; // body+12c picks ACT 0x230 (selector 3) or 0x22f
    queue(c,(c.a.flags23c&0x1000)?0x22d:0x22e); //1494c0
    bind(c.a,gedoWait);
    return true;
}
Visit gedoVisit(Ctx& c) {
    if(c.a.callbacks260[0]!=gedoWait)return Visit::NotMine;
    consumeHold(c.o,c.a);
    if(!(c.o.timeline.clock().flags104&0x8000))return Visit::Continue;
    // 1fe1b8: 16c5f8(cb, 1fe280, 0x22f + body12c, 0), then 82/78 units ahead/above.
    auto& w=*c.f.weaponLock;
    if(!c.f.pools)throw std::runtime_error("1fe1b8 requires the live object pools");
    const auto handle=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x138e + c.context.player,2,gedoShot);
    if(!handle)throw std::runtime_error("Original 1fe1b8 writes through a null object");
    auto& o=c.f.pools->objects.at(handle-1);
    w.objects.request(o,0x22f+c.a.bodyLatch12c,false,true);
    o[0xd4/4]=uint32_t(c.a.stateIndex()-64);o[0xd0/4]=0x34;o[0x108/4]|=0x8000;
    const auto dx=ScalarFloat{std::bit_cast<uint32_t>(82.f)},dy=ScalarFloat{std::bit_cast<uint32_t>(78.f)}; // 664188/66418c
    const ScalarFloat x{o[0x40/4]},y{o[0x44/4]};
    o[0x40/4]=((c.o.childParentWords()[0x38/4]&0x80000)?x.sub(dx):x.add(dx)).bits;
    o[0x44/4]=y.add(dy).bits;
    o[0x11c/4]=c.a.callbacks260[3];
    bind(c.a,0x169a50);c.a.callbacks260[5]=0;
    return Visit::Continue;
}

// 169a50 recovery binding; the table word differs per routine.
void recoverLater(StateEntryActor& a,unsigned table){bind(a,0x169a50,table);a.callbacks260[5]=0;}
bool grounded(Ctx& c){return !(c.o.timeline.motion().y>0.f);} // c.ole.s y <= 0.0
int armedPair(Ctx& c,int armed){return armed+!(c.a.flags23c&0x1000);} //1494c0
// 174330: screen direction of the held lever (1 toward the screen right of
// the facing, 2 the other way, 0 none), mirrored by facing.
int leverDirection(Ctx& c) {
    const auto& s=c.input.sampledFeatures;
    const bool left=c.o.timeline.clock().objectFlags&0x80000;
    if(s[0x168/4]||s[0x14c/4]||s[0x150/4])return left?2:1;
    if(s[0x160/4]||s[0x15c/4]||s[0x158/4])return left?1:2;
    return 0;
}
// 14ff80(actor+18c, 0, 0x20 + direction) without touching 18c: the jump that follows.
void requestJump(Ctx& c,int dir){c.a.pendingTable=0;c.a.pendingIndex=int16_t(dir==1?0x21:dir==2?0x22:0x20);}

// ---- Jubei (12): 1f4c90 selectors 0..2 -> 1f4dd8(strength) -> 1f4e50 -> 1f4ed8 ... 1f50c8 ----
// ACTs per strength from the word tables at 58b3e0 (6 x 4 words).
constexpr int jubeiActs[6][3]{{0x22a,0x22b,0x22c},{0x22d,0x22e,0x22f},{0x230,0x231,0x232},
                              {0x236,0x237,0x238},{0x239,0x23a,0x23b},{0x23f,0x240,0x241}};
constexpr uint32_t jubeiSecond=0x1f4e50,jubeiThird=0x1f4ed8,jubeiHit=0x1f4fb8,jubeiFollow=0x1f5040,jubeiAir=0x1f50c8;
bool jubeiEntry(Ctx& c,uint32_t selector) {
    if(selector>=3)return false;
    const unsigned n=strength(c.a); // the selector only gates; the ACTs follow 1696c8
    c.a.callbacks260[3]=n;face(c);queue(c,jubeiActs[0][n]);bind(c.a,jubeiSecond);
    return true;
}
Visit jubeiVisit(Ctx& c) {
    const unsigned n=c.a.callbacks260[3];
    switch(c.a.callbacks260[0]) {
    case jubeiSecond:if(ended(c)){queue(c,jubeiActs[1][n]);bind(c.a,jubeiThird);}return Visit::Continue;
    case jubeiThird:
        // A contact or a hit on the body (104 & 0xc0000) branches before the end check.
        if(c.o.timeline.clock().flags104&0xc0000){queue(c,jubeiActs[3][n]);bind(c.a,jubeiHit);}
        else if(ended(c)){queue(c,jubeiActs[2][n]);recoverLater(c.a,0);}
        return Visit::Continue;
    case jubeiHit:if(ended(c)){queue(c,jubeiActs[4][n]);bind(c.a,jubeiFollow);}return Visit::Continue;
    case jubeiFollow:if(ended(c)){queue(c,jubeiActs[5][n]);bind(c.a,jubeiAir);}return Visit::Continue;
    case jubeiAir:
        if(landingReady(c.o,c.a.queuedActionA3c)){stopAtGround(c.o);recoverLater(c.a,0);} //173970, 1697d0
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Zankuro (13): 1f5120 selector 4 -> 1f5268 -> 1f5310 -> 1f5378 -> 1f5440 -> 1f5508 ----
// The charge grows while the button whose feature body+12c names stays held.
constexpr uint32_t zanWind=0x1f5310,zanCharge1=0x1f5378,zanCharge2=0x1f5440,zanCharge3=0x1f5508;
bool zankuroEntry(Ctx& c,uint32_t selector) {
    if(selector!=4)return false;
    c.a.callbacks260[3]=0;face(c);
    const auto& s=c.input.sampledFeatures; // actor+430/434: features 0x5b/0x5c
    c.a.bodyLatch12c=s[0x5b]?0x5b:s[0x5c]?0x5c:0x5d;
    queue(c,0x23f);bind(c.a,zanWind);
    c.a.timers[22]=0; //14d000
    return true;
}
Visit zankuroVisit(Ctx& c) {
    const auto handler=c.a.callbacks260[0];
    if(handler!=zanWind&&handler!=zanCharge1&&handler!=zanCharge2&&handler!=zanCharge3)return Visit::NotMine;
    consumeHold(c.o,c.a);
    if(handler==zanWind) {
        if(ended(c)){queue(c,0x240);bind(c.a,zanCharge1);}
        return Visit::Continue;
    }
    const bool held=c.input.sampledFeatures.at(c.a.bodyLatch12c)!=0;
    const auto charge=[&]{ActorTimers t{c.a.timerDelta,c.a.timers};const auto old=t.increase(22);c.a.timers=t.values;return old;}; //14d038
    if(handler==zanCharge1) {
        if(!held){queue(c,0x243);recoverLater(c.a,1);}
        else if(charge()>=0x3c00){queue(c,0x241);bind(c.a,zanCharge2);}
    } else if(handler==zanCharge2) {
        if(!held){queue(c,0x244);recoverLater(c.a,1);}
        else if(charge()>=0x7800){queue(c,0x242);bind(c.a,zanCharge3);}
    } else if(!held||charge()>0xb3ff){queue(c,0x245);recoverLater(c.a,1);}
    return Visit::Continue;
}

// ---- Yunfei (23): 1fb318 selectors 4, 0x18, 0x1a ----
constexpr uint32_t yunfeiDive=0x1fb558,yunfeiBounce=0x1fb628,yunfeiDrop=0x1fb730;
bool yunfeiEntry(Ctx& c,uint32_t selector) {
    switch(selector) {
    case 4: // the opponent enters 2/96 at once (1491e0 inside this visit)
        if(!c.f.seizeOpponent)throw std::runtime_error("Yunfei's seize requires the live match");
        c.f.seizeOpponent();
        return true;
    case 0x18: // 1fb4f0
        c.a.callbacks260[3]=0;face(c);queue(c,armedPair(c,0x24a));bind(c.a,yunfeiDive);
        return true;
    case 0x1a: // 1fb6b8: ACT 0x277 with the 16c408 effect 0x278
        c.a.callbacks260[3]=0;face(c);queue(c,0x277);ownEffect(c,0x278);bind(c.a,yunfeiDrop);
        return true;
    default:return false;
    }
}
Visit yunfeiVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case yunfeiDive:
        if(grounded(c)){stopAtGround(c.o);queue(c,armedPair(c,0x24e));recoverLater(c.a,1);}
        else if(c.o.timeline.clock().flags104&0xc0000){stopAtGround(c.o);queue(c,armedPair(c,0x24c));bind(c.a,yunfeiBounce);}
        return Visit::Continue;
    case yunfeiBounce:
        if(ended(c)) {
            const int dir=leverDirection(c);
            c.a.characterBytesF14[6]=0; // f1a
            c.a.flags244=(c.a.flags244&~0x100u)|0x100000;
            requestJump(c,dir);
        }
        return Visit::Continue;
    case yunfeiDrop:
        if(grounded(c)){stopAtGround(c.o);queue(c,0x279);recoverLater(c.a,1);}
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Basara (8): 1f2900 selectors 6 and 2 ----
// 6: 1f2a70(strength) -> 1f2b08 -> 1f2b70; 2: 1f2c70 -> 1f2cc8 -> 1f2d48.
constexpr uint32_t basaraShadowWait=0x1f2b08,basaraShadowMove=0x1f2b70,basaraShadowTask=0x1f2c68;
constexpr uint32_t basaraLeap=0x1f2cc8,basaraBounce=0x1f2d48;
bool basaraEntry(Ctx& c,uint32_t selector) {
    if(selector==6) {
        c.a.callbacks260[3]=strength(c.a);
        // 16c4e0(cb, 0x22c, 0, 0): the shadow, whose task then runs the empty 1f2c68.
        auto& w=*c.f.weaponLock;
        if(!c.f.pools)throw std::runtime_error("Basara's shadow requires the live object pools");
        const auto handle=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x1392 + c.context.player,6,basaraShadowTask);
        if(!handle)throw std::runtime_error("Original 16c4e0 writes through a null object");
        auto& o=c.f.pools->objects.at(handle-1);
        w.objects.request(o,0x22c,false,true);o[0x108/4]|=0x1a000;
        c.a.bodyState128=handle; // body+128 keeps the shadow
        face(c);stopAtGround(c.o);queue(c,armedPair(c,0x228));bind(c.a,basaraShadowWait);
        return true;
    }
    if(selector==2){face(c);queue(c,armedPair(c,0x23c));bind(c.a,basaraLeap);return true;}
    return false;
}
Visit basaraVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case basaraShadowWait:
        if(ended(c)){ActorTimers t{c.a.timerDelta,c.a.timers};t.set(23,0x12);c.a.timers=t.values;bind(c.a,basaraShadowMove);}
        return Visit::Continue;
    case basaraShadowMove: {
        ActorTimers t{c.a.timerDelta,c.a.timers};const auto old=t.decrease(23);c.a.timers=t.values; //14d010
        if(old) {
            // 663b90/663b94 = +-30.0, 663b98 = 65536.0; cvt.w.s truncates.
            const int dir=leverDirection(c);
            const auto speed=ScalarFloat::integer(dir==1?30:dir==2?-30:0).mul(ScalarFloat::integer(65536)).truncate();
            auto m=c.o.timeline.motion();m.vx=speed;c.o.timeline.setMotion(m);
            return Visit::Continue;
        }
        if(c.f.pools&&c.a.bodyState128) { // 147530 parks the shadow's task on 147540
            const auto& shadow=c.f.pools->objects.at(c.a.bodyState128-1);
            c.f.pools->tasks.at(shadow[0x04/4]-1)[0]=0x147540;
        }
        stopAtGround(c.o);queue(c,armedPair(c,0x22a));bind(c.a,0x174158);c.a.callbacks260[5]=0;
        return Visit::Continue;
    }
    case basaraLeap:
        if(c.o.timeline.clock().flags104&0xc0000){stopAtGround(c.o);queue(c,armedPair(c,0x23e));bind(c.a,basaraBounce);}
        else updateAirLanding(c.o,c.a); //173880
        return Visit::Continue;
    case basaraBounce:
        if(ended(c)){const int dir=leverDirection(c);c.o.timeline.stopMotion();requestJump(c,dir);}
        else updateAirLanding(c.o,c.a);
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// 16c5f8(cb, handler, act, 0): an own kind-2 object with d0 = -1, d4 = state - 64.
AuxiliaryObject& ownProjectile(Ctx& c,uint32_t handler,unsigned act) {
    auto& w=*c.f.weaponLock;
    if(!c.f.pools)throw std::runtime_error("16c5f8 requires the live object pools");
    const auto handle=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x138e + c.context.player,2,handler);
    if(!handle)throw std::runtime_error("Original 16c5f8 writes through a null object");
    auto& o=c.f.pools->objects.at(handle-1);
    w.objects.request(o,act,false,true);
    o[0xd0/4]=0xffffffffu;o[0xd4/4]=uint32_t(c.a.stateIndex()-64);
    return o;
}
void queueForced(Ctx& c,int act){c.o.markActorActionPending();queue(c,act);} //1493c0(actor, act, 1)

// ---- Tamtam (15): 1f5918 selectors 1..3 -> 1f5a88(strength); 0xd -> 1f5d58 ----
constexpr uint32_t tamtamThrow=0x1f5b20,tamtamCharge=0x1f5dd0;
bool tamtamEntry(Ctx& c,uint32_t selector) {
    const unsigned n=strength(c.a);
    if(selector-1u<3) {
        constexpr int acts[3]{0x249,0x24b,0x24d}; // 663bd8
        c.a.callbacks260[3]=n;face(c);queue(c,armedPair(c,acts[n]));bind(c.a,tamtamThrow);
        return true;
    }
    if(selector==0xd) {
        c.a.callbacks260[3]=n;face(c);queue(c,armedPair(c,0x26a));bind(c.a,tamtamCharge);c.o.scriptLatch134=0;
        return true;
    }
    return false;
}
Visit tamtamVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case tamtamThrow:
        if(consumeHold(c.o,c.a)) {
            const unsigned n=c.a.callbacks260[3];
            auto& o=ownProjectile(c,0x1f5bd0,0x24f+n);o[0x11c/4]=n;o[0xd0/4]=0x24; //1f5b90
            recoverLater(c.a,1);
        }
        return Visit::Continue;
    case tamtamCharge: // the second hold marker releases the shot
        if(consumeHold(c.o,c.a))++c.o.scriptLatch134;
        if(c.o.scriptLatch134>=2) {
            auto& o=ownProjectile(c,0x1f5ea0,0x26c);o[0x11c/4]=0x26c;o[0xd0/4]=0x25; //1f5e60
            recoverLater(c.a,1);
        }
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Sogetsu (17): 1f7868 selector 0x14 -> 1f79e8 -> 1f7a48 ----
constexpr uint32_t sogetsuHold=0x1f7a48;
bool sogetsuEntry(Ctx& c,uint32_t selector) {
    if(selector!=0x14)return false;
    c.a.callbacks260[3]=0;face(c);queue(c,0x26b);bind(c.a,sogetsuHold);
    return true;
}
Visit sogetsuVisit(Ctx& c) {
    if(c.a.callbacks260[0]!=sogetsuHold)return Visit::NotMine;
    if(consumeHold(c.o,c.a)) {
        auto& o=ownProjectile(c,0x1f7ae0,0x26c);o[0x11c/4]=c.a.callbacks260[3]; //1f7aa0
        recoverLater(c.a,1);
    }
    return Visit::Continue;
}

// ---- Sankuro (29): 1ff558 selectors 8..10 -> 1ff6a0(strength) -> 1ff730 -> 1ff7e8 -> 1ff978 ----
// Mashing button n (latched feature 6 + n) extends the repeated ACT 0x251 + n.
constexpr uint32_t sankuroStart=0x1ff730,sankuroRepeat=0x1ff7e8,sankuroEnd=0x1ff978;
constexpr int sankuroRepeats[3]{3,4,5},sankuroWindow[3]{20,15,10}; // 593200, 593210
void setBody104(Ctx& c,uint32_t bits);
bool sankuroEntry(Ctx& c,uint32_t selector) {
    if(selector-8u>=3)return false;
    const unsigned n=strength(c.a);
    c.a.callbacks260[3]=n;face(c);stopAtGround(c.o);queue(c,int(0x24e + n));bind(c.a,sankuroStart);
    setBody104(c,0x2000);
    return true;
}
Visit sankuroVisit(Ctx& c) {
    const unsigned n=c.a.callbacks260[3];
    const auto setWindow=[&]{ActorTimers t{c.a.timerDelta,c.a.timers};t.set(23,sankuroWindow[n]);c.a.timers=t.values;};
    switch(c.a.callbacks260[0]) {
    case sankuroStart:
        if(ended(c)) {
            c.a.bodyCounter130=0;c.a.bodyLatch12c=0;setWindow();
            queueForced(c,int(0x251+n));bind(c.a,sankuroRepeat);
        }
        setBody104(c,0x2000);
        return Visit::Continue;
    case sankuroRepeat: {
        {ActorTimers t{c.a.timerDelta,c.a.timers};t.decrease(23);c.a.timers=t.values;} //14d010
        if(c.input.sampledFeatures[6+n])++c.a.bodyLatch12c;
        bool finish=false;
        const auto mashed=[&]{ // the window ran out: a press restarts it, none finishes
            if(!c.a.bodyLatch12c){finish=true;return;}
            c.a.bodyLatch12c=0;setWindow();
        };
        if(ended(c)) {
            if(int32_t(++c.a.bodyCounter130)>=sankuroRepeats[n])finish=true;
            else if(c.a.timers[23]>0)queueForced(c,int(0x251+n));
            else mashed();
        } else if(c.a.timers[23]<=0)mashed();
        if(finish){stopAtGround(c.o);queue(c,int(0x254+n));bind(c.a,sankuroEnd);return Visit::Continue;}
        // 1ff9b8: the lever steers; otherwise the speed decays by 0.9 to zero.
        const auto& s=c.input.sampledFeatures;
        auto m=c.o.timeline.motion();
        if(s[62])m.vx=0x10000;
        else if(s[64])m.vx=-0x10000;
        else {
            const int32_t v=ScalarFloat::integer(m.vx).mul(ScalarFloat{std::bit_cast<uint32_t>(0.9f)}).truncate();
            m.vx=v;
            const float f=float(v); // 6641ec/6641f0 = +-0.1
            if(f<=0.1f&&-0.1f<=f)m.vx=0;
        }
        c.o.timeline.setMotion(m);
        return Visit::Continue;
    }
    case sankuroEnd:return ended(c)?Visit::Recover:Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Sieger (37): 205ed8 selector 0xe -> 206060 -> 2060d0 -> 206150 -> 206370 ----
constexpr uint32_t siegerRise=0x2060d0,siegerFlight=0x206150,siegerBounce=0x206370;
void markBattle4(Ctx& c){if(!c.f.battle)throw std::runtime_error("140630 requires the battle");c.f.battle->flags138|=4;} //140630(2)
// ---- Kyoshiro (5) selector 6: 1f10f0 -> 1f11b8 -> 1f1370 -> 1f1450 -> 1f1520 ----
// body+128..134 keep four object handles; the victim branch (victim_script.cpp)
// later copies 128/12c and moves 130/134.
constexpr uint32_t kyoOpen=0x1f11b8,kyoDance=0x1f1370,kyoClose=0x1f1450,kyoEnd=0x1f1520;
uint32_t handleOf(Ctx& c,const AuxiliaryObject& o){return uint32_t(&o-c.f.pools->objects.data())+1;}
AuxiliaryObject& objectAt(Ctx& c,uint32_t h) {
    if(!h||!c.f.pools)throw std::runtime_error("Kyoshiro's scene reads a null object");
    return c.f.pools->objects.at(h-1);
}
float wordF(const AuxiliaryObject& o,unsigned off){return std::bit_cast<float>(o[off/4]);}
void setF(AuxiliaryObject& o,unsigned off,float v){o[off/4]=std::bit_cast<uint32_t>(v);}
bool kyoshiroEntry(Ctx& c,uint32_t selector) {
    if(selector!=6)return false;
    face(c);
    auto& o1=ownEffect(c,0x261);o1[0x108/4]=(o1[0x108/4]|0x8000)&~0x2000u;c.a.bodyState128=handleOf(c,o1);
    auto& o2=ownEffect(c,0x268);o2[0x108/4]=(o2[0x108/4]|0x8000)&~0x2000u;c.a.bodyLatch12c=handleOf(c,o2);
    queue(c,armedPair(c,0x259));bind(c.a,kyoOpen);
    return true;
}
// 1f1590 (dancers follow at most 134 ahead) / 1f1698 (they return; true when back within 64).
bool kyoshiroSlide(Ctx& c,bool back) {
    auto& t3=objectAt(c,c.a.bodyCounter130);auto& t4=objectAt(c,c.o.scriptLatch134);
    const float bx=c.o.timeline.motion().x;const bool left=c.o.timeline.clock().objectFlags&0x80000;
    const float reach=back?64.0f:134.0f,step=back?-12.0f:12.0f;
    bool hit=false;
    if(!left) {
        const float lim=eeAdd(bx,reach);setF(t4,0x40,eeAdd(wordF(t4,0x40),step));
        if(back?wordF(t4,0x40)<=lim:lim<=wordF(t4,0x40)){hit=true;setF(t4,0x40,eeAdd(bx,reach));}
        setF(t3,0x40,eeSub(wordF(t4,0x40),40.0f));
    } else {
        const float lim=eeSub(bx,reach);setF(t4,0x40,eeSub(wordF(t4,0x40),step));
        if(back?lim<=wordF(t4,0x40):wordF(t4,0x40)<=lim){hit=true;setF(t4,0x40,eeSub(bx,reach));}
        setF(t3,0x40,eeAdd(wordF(t4,0x40),40.0f));
    }
    return back?hit:true;
}
Visit kyoshiroVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case kyoOpen: {
        auto& o1=objectAt(c,c.a.bodyState128);
        if(!o1[0xc0/4]||(o1[0x104/4]&1))return Visit::Continue;
        auto& w=c.f.weaponLock->objects;
        w.request(o1,0x262,false,false);w.request(objectAt(c,c.a.bodyLatch12c),0x269,false,false);
        auto& o3=ownEffect(c,0x267);o3[0x108/4]=(o3[0x108/4]|0x8000)&~0x2000u;
        setF(o3,0x44,24.0f);o3[0xb0/4]=std::bit_cast<uint32_t>(19.0f);o3[0x104/4]|=0x20000; //11dff8
        c.a.bodyCounter130=handleOf(c,o3);
        auto& o4=ownProjectile(c,0,0x265);o4[0x108/4]=(o4[0x108/4]|0x8000)&~0x2000u;
        setF(o4,0x40,(c.o.timeline.clock().objectFlags&0x80000)?eeSub(wordF(o4,0x40),64.0f):eeAdd(wordF(o4,0x40),64.0f));
        setF(o4,0x44,24.0f);
        c.o.scriptLatch134=handleOf(c,o4);
        {ActorTimers t{c.a.timerDelta,c.a.timers};t.set(23,30);c.a.timers=t.values;} //14cfe8
        bind(c.a,kyoDance);
        return Visit::Continue;
    }
    case kyoDance: {
        const bool r=kyoshiroSlide(c,false);
        ActorTimers t{c.a.timerDelta,c.a.timers};const auto old=t.decrease(23);c.a.timers=t.values; //14d010
        if(old==0&&r){objectAt(c,c.o.scriptLatch134)[0x104/4]|=0x400000;bind(c.a,kyoClose);return Visit::Continue;}
        // 1f1370 compares only with the armed ACT, even when unarmed.
        if(ended(c)&&c.o.timeline.action().id()!=0x25b)queue(c,armedPair(c,0x25b));
        return Visit::Continue;
    }
    case kyoClose: {
        if(!kyoshiroSlide(c,true))return Visit::Continue;
        c.f.weaponLock->objects.request(objectAt(c,c.a.bodyState128),0x264,false,false);
        for(auto h:{c.a.bodyCounter130,c.o.scriptLatch134}){auto& p=objectAt(c,h);p[0x104/4]|=2;p[0x108/4]|=0x1000;}
        queue(c,armedPair(c,0x25d));bind(c.a,kyoEnd);
        return Visit::Continue;
    }
    case kyoEnd:
        if(!ended(c))return Visit::Continue;
        objectAt(c,c.a.bodyState128)[0x108/4]|=0x2000;objectAt(c,c.a.bodyLatch12c)[0x108/4]|=0x2000;
        return Visit::Recover;
    default:return Visit::NotMine;
    }
}

// ---- Shizumaru (9): selectors 5 (umbrella glide), 12 (bounce), 13 (umbrella throw) ----
constexpr uint32_t shizuOpen=0x1f3040,shizuGlide=0x1f30a8,shizuGlideEnd=0x1f3400,shizuBounce=0x1f3498,shizuHop=0x1f3530,
                   shizuThrow=0x1f36d8;
ActorTimers timersOf(Ctx& c){return ActorTimers{c.a.timerDelta,c.a.timers};}
bool shizumaruEntry(Ctx& c,uint32_t selector) {
    switch(selector) {
    case 5: { // 1f2fb8
        queue(c,0x233);bind(c.a,shizuOpen);c.a.bodyState128=0xffffffffu;
        auto t=timersOf(c);t.set(23,60);c.a.timers=t.values;
        if(!c.f.clearInputs)throw std::runtime_error("1f2fb8 clears the owner's inputs");
        c.f.clearInputs(); //178920, 1797a8
        return true;
    }
    case 12:queue(c,0x229);bind(c.a,shizuBounce);return true; // 1f3450
    case 13: { // 1f35d0
        const uint8_t n=c.a.characterBytesF14[4]; // f18
        face(c);c.a.flags23c&=~0x1000u;c.o.scriptLatch134=uint32_t(n)-1;c.a.characterBytesF14[4]=0;
        c.a.timers[19]=0; //14d000
        queue(c,n+0x267);bind(c.a,shizuThrow);
        auto& o=ownEffect(c,0x24b);o[0x108/4]&=~0x2000u;
        c.f.pools->tasks.at(o[1]-1)[0]=0x1f3778;
        const auto m=c.o.timeline.motion();
        o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x5c/4]=0x80000;o[0x44/4]=std::bit_cast<uint32_t>(eeAdd(m.y,128.0f));
        return true;
    }
    default:return false;
    }
}
Visit shizumaruVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case shizuOpen:if(ended(c)){queue(c,0x235);bind(c.a,shizuGlide);}return Visit::Continue;
    case shizuGlide: { // 1f30a8: steer by lever, 60 visits without lever ends the glide
        const int d=leverDirection(c);
        if(updateAirLanding(c.o,c.a))return Visit::Continue; //173880
        consumeHold(c.o,c.a);
        auto t=timersOf(c);
        auto m=c.o.timeline.motion();int32_t& s=reinterpret_cast<int32_t&>(c.a.bodyState128);
        bool steer=true;
        if(d==1||d==2)t.set(23,60);
        else if(c.input.sampledFeatures[63]||t.decrease(23)==0)steer=false; //3c0
        if(!steer) {c.a.timers=t.values;queue(c,armedPair(c,0x234));bind(c.a,shizuGlideEnd);return Visit::Continue;}
        if(d==1||d==2) {
            const int want=d==1?0:1;
            if(s!=want){int32_t o=0;for(int k=0;k<4;++k)o=t.decrease(22);if(o==0)s=want;}
            if(s==want){t.increase(22);m.ax=d==1?0x1999:-0x1999;}
        } else {
            t.decrease(22);if(t.decrease(22)==0)s=-1;
            const ScalarFloat f=ScalarFloat::integer(m.vx).mul(ScalarFloat{0x3f666666u}); // * 0.9
            m.vx=f.truncate();
            const ScalarFloat fi=ScalarFloat::integer(m.vx);
            if(!ScalarFloat{0x45cccccdu}.less(fi)&&!fi.less(ScalarFloat{0xc5cccccdu}))m.vx=0; // within +-6553.6
        }
        const ScalarFloat fv=ScalarFloat::integer(m.vx);
        if(!fv.less(ScalarFloat{0x48000000u}))m.vx=0x20000;           // >= 131072
        else if(!ScalarFloat{0xc8000000u}.less(fv))m.vx=int32_t(0xfffe0000u); // <= -131072
        c.o.timeline.setMotion(m);c.a.timers=t.values;
        const bool slow=c.a.timers[22]<0xc00;
        if(s==0){if(slow)queue(c,armedPair(c,0x236));else queue(c,0x237);}
        else if(s==1){if(slow)queue(c,armedPair(c,0x238));else queue(c,0x239);}
        else queue(c,armedPair(c,0x235));
        return Visit::Continue;
    }
    case shizuGlideEnd:if(ended(c)){c.a.pendingTable=0;c.a.pendingIndex=0x20;}return Visit::Continue; //14ff80, 18c untouched
    case shizuBounce:
        if(updateAirLanding(c.o,c.a))return Visit::Continue;
        consumeHold(c.o,c.a);
        if(!(c.o.timeline.clock().flags104&0x40000))return Visit::Continue;
        queue(c,0x22a);bind(c.a,shizuHop);c.a.timers[15]=0;
        return Visit::Continue;
    case shizuHop: {
        if(!ended(c))return Visit::Continue;
        const int d=leverDirection(c);
        queue(c,d==1?0x22b:d==2?0x22d:0x22c);bind(c.a,shizuBounce);
        return Visit::Continue;
    }
    case shizuThrow: {
        const auto k=c.o.scriptLatch134;
        if(ended(c))queue(c,0x27c);
        else if(!(c.o.timeline.clock().flags104&0x80000))return Visit::Continue;
        else queue(c,int(k)+0x26d);
        recoverLater(c.a,0);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Amakusa (11): selectors 15..17 (1f42f0 leap; strength is the variant) and the
// attacker half of his k == 3 catch (1f4ac0 / 1f4b40 / 1f4bd0, bound by victim_script.cpp).
constexpr uint32_t amaRise=0x1f4468,amaTop=0x1f44e0,amaAim=0x1f4588,amaLand=0x1f4768,amaDrop=0x1f47d0,
                   amaHold=0x1f4ac0,amaPull=0x1f4b40,amaCharge=0x1f4bd0;
// d * scale / div with the EE single-precision steps, truncated; negated when mirrored.
int32_t amaSpeed(float d,ScalarFloat scale,ScalarFloat div,bool negate,bool mirrored) {
    ScalarFloat f=ScalarFloat{std::bit_cast<uint32_t>(d)}.mul(scale);
    if(negate)f.bits^=0x80000000u; // neg.s
    const int32_t i=f.div(div).truncate();
    return mirrored?-i:i;
}
bool amakusaEntry(Ctx& c,uint32_t selector) {
    if(selector<15||selector>17)return false;
    const int v=strength(c.a);
    const float ox=c.f.weaponLock->opponentBody.timeline.motion().x;
    face(c);c.a.callbacks260[3]=uint32_t(v);queue(c,0x2d1);bind(c.a,amaRise);
    c.o.timeline.stopMotion();
    auto m=c.o.timeline.motion();m.vy=0x103ae1;c.o.pendingFlags|=8;m.ay=int32_t(0xffff4f5du);
    const bool left=c.o.timeline.clock().objectFlags&0x80000;
    const float tx=v==1?ox:v==0?(left?eeSub(ox,150.0f):eeAdd(ox,150.0f)):v==2?(left?eeAdd(ox,150.0f):eeSub(ox,150.0f)):eeSub(ox,150.0f);
    m.vx=amaSpeed(eeSub(tx,m.x),ScalarFloat{0x47800000u},ScalarFloat{0x41c00000u},false,left); // *65536 /24
    c.o.timeline.setMotion(m);
    return true;
}
Visit amakusaVisit(Ctx& c) {
    const auto& h=c.input.sampledFeatures;
    const auto mark2000=[&]{setBody104(c,0x2000);};
    switch(c.a.callbacks260[0]) {
    case amaRise:
        if(c.o.timeline.motion().vy>0)return Visit::Continue;
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        queue(c,0x2d2);bind(c.a,amaTop);return Visit::Continue;
    case amaTop:
        if(ended(c)){queue(c,0x2d3);c.a.timers[23]=0;bind(c.a,amaAim);return Visit::Continue;}
        if(!h[3])return Visit::Continue;
        queue(c,0x2d7);bind(c.a,amaDrop);return Visit::Continue;
    case amaAim: {
        bool end=h[3];
        if(!end){auto t=timersOf(c);const auto old=t.increase(23);c.a.timers=t.values;end=old>=0x4000;}
        if(end){queue(c,0x2d5);bind(c.a,amaLand);return Visit::Continue;}
        if(!h[45])return Visit::Continue;
        const float ox=c.f.weaponLock->opponentBody.timeline.motion().x;
        queue(c,0x2d4);ownEffect(c,0x2d9);bind(c.a,amaLand);
        c.o.timeline.stopMotion();c.o.pendingFlags|=8;
        auto m=c.o.timeline.motion();
        const bool left=c.o.timeline.clock().objectFlags&0x80000;
        float tx;
        if(h[7])tx=ox;
        else if(h[6]&&!left)tx=eeAdd(ox,30.0f);
        else if(h[8]&&left)tx=eeAdd(ox,30.0f);
        else tx=eeSub(ox,50.0f);
        m.vy=int32_t(0xfff33334u);
        m.vx=amaSpeed(eeSub(tx,m.x),ScalarFloat{0xc94ccccdu},ScalarFloat{std::bit_cast<uint32_t>(m.y)},true,left);
        c.o.timeline.setMotion(m);
        return Visit::Continue;
    }
    case amaLand:case amaDrop:
        if(!touchedGround(c.o,c.a.queuedActionA3c))return Visit::Continue;
        stopAtGround(c.o);queue(c,c.a.callbacks260[0]==amaLand?0x2d6:0x2d8);recoverLater(c.a,1);
        return Visit::Continue;
    case amaHold:
        if(ended(c)){queue(c,int(c.o.scriptLatch134)+0x247);bind(c.a,amaPull);}
        mark2000();return Visit::Continue;
    case amaPull:
        if(ended(c)){c.a.timers[23]=0;queue(c,int(c.o.scriptLatch134)+0x248);bind(c.a,amaCharge);}
        mark2000();return Visit::Continue;
    case amaCharge: {
        auto t=timersOf(c);const auto old=t.increase(23);c.a.timers=t.values;
        if(old<0x6200)return Visit::Continue;
        auto& p=ownProjectile(c,0x1f48d8,0x24e);
        p[0x40/4]=std::bit_cast<uint32_t>(c.f.weaponLock->opponentBody.timeline.motion().x);
        p[0x12c/4]=c.a.bodyLatch12c;p[0x130/4]=c.a.bodyCounter130; // object handles
        recoverLater(c.a,1);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Mizuki (27): selectors 0..2 (projectile), 3..5 (appear by the opponent), 13 (on the opponent) ----
constexpr uint32_t mizukiShot=0x1fe658,mizukiWarp=0x1fe890,mizukiFall=0x1fe9f0,mizukiCurse=0x1feac8;
bool mizukiEntry(Ctx& c,uint32_t selector) {
    if(selector<=2){c.a.callbacks260[3]=selector;face(c);queue(c,armedPair(c,0x240 + 2*int(selector)));bind(c.a,mizukiShot);return true;}
    if(selector<=5){const int i=int(selector)-3;c.a.callbacks260[3]=uint32_t(i);face(c);queue(c,armedPair(c,0x22f + 2*i));bind(c.a,mizukiWarp);return true;}
    if(selector==13){c.a.callbacks260[3]=7;face(c);queue(c,armedPair(c,0x21c));bind(c.a,mizukiCurse);return true;}
    return false; // 6..12: 169810
}
Visit mizukiVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case mizukiShot:
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        {auto& o=ownProjectile(c,0x1fe6f0,0x246);o[0xd0/4]=0x35;o[0x104/4]|=0x4000;} //1fe6b0
        recoverLater(c.a,1);return Visit::Continue;
    case mizukiWarp: { // 1fe890: beside the opponent by table 6641c8
        if(!ended(c))return Visit::Continue;
        const int i=int(c.a.callbacks260[3]);
        if(i<0||i>2)throw std::runtime_error("1fe890 reads outside its offset table");
        queue(c,armedPair(c,0x235 + 2*i));
        static constexpr int offsets[3]{-20,-60,60};
        const auto& ob=c.f.weaponLock->opponentBody.timeline.motion();
        const float d=float(offsets[i]);
        const float x=(c.o.timeline.clock().objectFlags&0x80000)?eeSub(ob.x,d):eeAdd(ob.x,d);
        float y=ob.y;
        if(y<=0.0f){y=0;c.o.timeline.setPosition(x,y);recoverLater(c.a,1);return Visit::Continue;}
        c.o.timeline.setPosition(x,y);bind(c.a,mizukiFall);
        c.a.flags23c|=0x10; // 13a858 (byte 43d05e) is 0 under console VS
        return Visit::Continue;
    }
    case mizukiFall:
        if(!ended(c))return Visit::Continue;
        {auto m=c.o.timeline.motion();m.vy=0x13000;m.ay=-0x3200;c.o.timeline.setMotion(m);}
        c.a.pendingTable=0;c.a.pendingIndex=0x20; //14ff80, 18c untouched
        return Visit::Continue;
    case mizukiCurse: {
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        auto& o=ownProjectile(c,0x1febb0,0x21e); //1feb20
        const auto& ob=c.f.weaponLock->opponentBody.timeline.motion();
        o[0x104/4]|=0x1000;o[0x11c/4]=c.a.callbacks260[3];o[0x40/4]=std::bit_cast<uint32_t>(ob.x);
        o[0xd0/4]=0x35;o[0x44/4]=std::bit_cast<uint32_t>(ob.y);
        recoverLater(c.a,1);return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Iroha (31): selector 24 (1ffcd0) jumps by lever, no callback ----
bool irohaEntry(Ctx& c,uint32_t selector) {
    if(selector!=24)return false;
    const int d=leverDirection(c);
    queue(c,armedPair(c,d==1?0x268:d==2?0x26a:0x266));
    c.a.pendingTable=0;c.a.pendingIndex=int16_t(d==1?0x21:d==2?0x22:0x20); //14ff80, 18c untouched
    c.a.flags244|=0x200;
    return true;
}
Visit irohaVisit(Ctx&){return Visit::NotMine;}

// ---- Gen-an (35): selectors 7..9 (wall jump, 204e20..205498) and 6 (chain, 205500..205750) ----
constexpr uint32_t genanWait=0x204eb0,genanRun=0x204f00,genanWall=0x205080,genanCrouch=0x2051b0,genanAir=0x205318,
                   genanLand=0x205498,genanThrow=0x205558,genanReach=0x2056c8,genanBack=0x205750;
bool genanEntry(Ctx& c,uint32_t selector) {
    if(selector==6){face(c);queue(c,0x22e);bind(c.a,genanThrow);return true;}
    if(selector<7||selector>9)return false;
    const int i=int(selector)-7;
    c.a.callbacks260[3]=uint32_t(i);face(c);c.a.bodyLatch12c=1;c.a.bodyCounter130=0xffffffffu;
    queue(c,0x238 + i);bind(c.a,genanWait);
    return true;
}
Visit genanVisit(Ctx& c) {
    const auto& h=c.input.sampledFeatures;
    const int i=int(c.a.callbacks260[3]);
    const auto held=[&]{return i>=0&&i<3&&h[0x5b + i];}; // actor+430+4i: the strength's held button
    switch(c.a.callbacks260[0]) {
    case genanWait:if(consumeHold(c.o,c.a))bind(c.a,genanRun);return Visit::Continue;
    case genanRun: {
        markBattle4(c);
        if(c.a.bodyLatch12c&&!held())c.a.bodyLatch12c=0;
        if(!c.f.weaponLock)throw std::runtime_error("204f00 needs the camera");
        const auto& cam=c.f.weaponLock->camera;
        const int m=(c.a.character==46?8:c.a.character==47?16:34)+2; // (int)(14adf0 + 2.0)
        const bool left=c.o.timeline.clock().objectFlags&0x80000;
        const int x=int(c.o.timeline.motion().x);
        if(left?x>=cam.right-m:x<=cam.left+m) { // 14aad8(actor, m, 1, 1)
            c.a.flags244|=0x20000;
            c.o.timeline.setPosition(float(left?cam.right-0x1e:cam.left+0x1e),c.o.timeline.motion().y);
            c.o.timeline.stopMotion();queue(c,0x23b);bind(c.a,genanWall);
        } else if(landingReady(c.o,c.a.queuedActionA3c)){queue(c,0x241);recoverLater(c.a,1);}
        return Visit::Continue;
    }
    case genanWall: {
        markBattle4(c);
        int sel=i;
        if(c.a.bodyLatch12c) {
            if(!held())c.a.bodyLatch12c=0;
            else if(!ended(c))sel=-1;
        }
        if(sel!=-1){c.a.flags244&=~0x20000u;queue(c,0x23d + sel);bind(c.a,genanCrouch);return Visit::Continue;}
        if(!h[9])return Visit::Continue;
        c.a.flags244&=~0x20000u;c.a.pendingTable=0;c.a.pendingIndex=0x21; //14ff80
        return Visit::Continue;
    }
    case genanCrouch: { // 2051b0 -> 205220: launched at the opponent
        markBattle4(c);
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        c.o.timeline.stopMotion();setBody104(c,0x40);
        const int32_t T=i==2?0x3c:i==1?0x2c:0x20;
        auto m=c.o.timeline.motion();
        m.ay=int32_t(0xffff4ccdu);m.vy=i==2?0x120000:i==1?0xc0000:0x70000;
        const float ox=c.f.weaponLock->opponentBody.timeline.motion().x;
        const int32_t v=ScalarFloat{std::bit_cast<uint32_t>(eeSub(ox,m.x))}.mul(ScalarFloat{0x47800000u}).div(ScalarFloat::integer(T)).truncate();
        m.vx=(c.o.timeline.clock().objectFlags&0x80000)?-v:v;
        c.o.timeline.setMotion(m);bind(c.a,genanAir);
        return Visit::Continue;
    }
    case genanAir: {
        const int d=leverDirection(c);
        auto m=c.o.timeline.motion();
        m.ax=d==1?(i==2?0x1eb8:0x2e14):d==2?(i==2?-0x1eb8:-0x2e14):0;c.o.timeline.setMotion(m);
        if(c.a.bodyCounter130==0xffffffffu) {
            if(h[6])c.a.bodyCounter130=6;else if(h[7])c.a.bodyCounter130=7;else if(h[8])c.a.bodyCounter130=8;
        }
        if(touchedGround(c.o,c.a.queuedActionA3c)){queue(c,0x241);recoverLater(c.a,1);return Visit::Continue;}
        if(!(c.o.timeline.clock().flags108&0x40))return Visit::Continue;
        const auto v=c.a.bodyCounter130;
        if(v==0xffffffffu)return Visit::Continue;
        queue(c,v==6?0x255:v==7?0x256:0x257);bind(c.a,genanLand);
        return Visit::Continue;
    }
    case genanLand:
        consumeHold(c.o,c.a);
        if(touchedGround(c.o,c.a.queuedActionA3c)){queue(c,0x241);recoverLater(c.a,1);}
        return Visit::Continue;
    case genanThrow: { // 205558: the chain head and its three links
        if(!(c.o.timeline.clock().flags104&0x8000))return Visit::Continue;
        if(c.o.childParentWords()[0x10c/4])return Visit::Continue;
        auto& p=ownProjectile(c,0,0x230);
        p[0xd0/4]=0x93;p[0x108/4]|=0x8000;
        const float px=std::bit_cast<float>(p[0x40/4]);
        p[0x40/4]=std::bit_cast<uint32_t>((c.o.timeline.clock().objectFlags&0x80000)?eeSub(px,101.0f):eeAdd(px,101.0f));
        c.a.bodyState128=handleOf(c,p);
        p[0x44/4]=std::bit_cast<uint32_t>(eeAdd(std::bit_cast<float>(p[0x44/4]),47.0f));
        uint32_t* links[3]{&c.a.bodyLatch12c,&c.a.bodyCounter130,&c.o.scriptLatch134};
        for(auto* l:links){auto& e=ownEffect(c,0x231);*l=handleOf(c,e);e[0x108/4]=(e[0x108/4]&~0x2000u)|0x8000;}
        genanChainLayout(*c.f.pools,c.o,c.a);
        queue(c,0x22f);bind(c.a,genanReach);
        return Visit::Continue;
    }
    case genanReach: {
        auto& p=objectAt(c,c.a.bodyState128);const auto f=p[0x104/4];
        if((f&0x240000)||(p[0xc0/4]&&!(f&1))){c.f.weaponLock->objects.request(p,0x232,false,false);bind(c.a,genanBack);}
        genanChainLayout(*c.f.pools,c.o,c.a);
        return Visit::Continue;
    }
    case genanBack: {
        auto& p=objectAt(c,c.a.bodyState128);
        const float bx=c.o.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
        const bool back=(p[0x38/4]&0x80000)?eeSub(bx,50.0f)<=px:px<=eeAdd(eeAdd(bx,50.0f),0.0f);
        if(!back){genanChainLayout(*c.f.pools,c.o,c.a);return Visit::Continue;}
        p[0x108/4]|=0x2000;
        for(auto hdl:{c.a.bodyLatch12c,c.a.bodyCounter130,c.o.scriptLatch134})objectAt(c,hdl)[0x108/4]|=0x1000;
        consumeHold(c.o,c.a);recoverLater(c.a,1);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Nicotine (39): selectors 0..3 (2068f0 leap) and 13 (chain, 206a38..206c88) ----
constexpr uint32_t nicoRise=0x206950,nicoFall=0x2069b8,nicoThrow=0x206a90,nicoReach=0x206c00,nicoBack=0x206c88;
bool nicotineEntry(Ctx& c,uint32_t selector) {
    if(int32_t(selector)<0)return false;
    if(selector<4){c.a.callbacks260[3]=selector;face(c);queue(c,0x213);bind(c.a,nicoRise);return true;}
    if(selector==13){face(c);queue(c,0x21d);bind(c.a,nicoThrow);return true;}
    return false;
}
Visit nicotineVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case nicoRise:if(ended(c)){queue(c,0x214);bind(c.a,nicoFall);}return Visit::Continue;
    case nicoFall:
        if(!(c.o.timeline.motion().y<=100.0f))return Visit::Continue;
        c.o.timeline.setPosition(c.o.timeline.motion().x,0);
        queue(c,int(c.a.callbacks260[3])+0x215);recoverLater(c.a,1);
        return Visit::Continue;
    case nicoThrow: {
        if(!(c.o.timeline.clock().flags104&0x8000))return Visit::Continue;
        if(c.o.childParentWords()[0x10c/4])return Visit::Continue;
        auto& p=ownProjectile(c,0,0x21f);
        p[0xd0/4]=0x92;p[0x108/4]|=0x8000;
        const float px=std::bit_cast<float>(p[0x40/4]);
        p[0x40/4]=std::bit_cast<uint32_t>((c.o.timeline.clock().objectFlags&0x80000)?eeSub(px,72.0f):eeAdd(px,72.0f));
        c.a.bodyState128=handleOf(c,p);
        p[0x44/4]=std::bit_cast<uint32_t>(eeAdd(std::bit_cast<float>(p[0x44/4]),44.0f));
        uint32_t* links[3]{&c.a.bodyLatch12c,&c.a.bodyCounter130,&c.o.scriptLatch134};
        for(auto* l:links){auto& e=ownEffect(c,0x220);*l=handleOf(c,e);e[0x108/4]=(e[0x108/4]&~0x2000u)|0x8000;}
        nicotineChainLayout(*c.f.pools,c.o,c.a);
        queue(c,0x21e);bind(c.a,nicoReach);
        return Visit::Continue;
    }
    case nicoReach: {
        auto& p=objectAt(c,c.a.bodyState128);const auto f=p[0x104/4];
        if((f&0x280000)||(p[0xc0/4]&&!(f&1))){c.f.weaponLock->objects.request(p,0x221,false,false);bind(c.a,nicoBack);}
        nicotineChainLayout(*c.f.pools,c.o,c.a);
        return Visit::Continue;
    }
    case nicoBack: { // the head's own mirror decides the side
        auto& p=objectAt(c,c.a.bodyState128);
        const float bx=c.o.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
        const bool reached=!(p[0x38/4]&0x80000)?px<=eeAdd(eeAdd(bx,62.0f),32.0f):eeSub(eeSub(bx,62.0f),32.0f)<=px;
        if(!reached){nicotineChainLayout(*c.f.pools,c.o,c.a);return Visit::Continue;}
        p[0x108/4]|=0x2000;
        for(auto hdl:{c.a.bodyLatch12c,c.a.bodyCounter130,c.o.scriptLatch134})objectAt(c,hdl)[0x108/4]|=0x1000;
        consumeHold(c.o,c.a);recoverLater(c.a,1);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Galford (4): companion commands (Poppy, poppy.cpp), dives and the 1ef608 seize ----
constexpr uint32_t galCmd9=0x1ef1b0,galCmd10=0x1ef268,galCmd11=0x1ef320,galCmd12=0x1ef3e8,galCmd18=0x1ef6c0,
                   galCmd19=0x1ef788,galCmd20=0x1ef850,galWait23=0x1efb70,galHold23=0x1efbe0,
                   galDive=0x1ef4d0,galDiveFall=0x1ef578,galDrop=0x1ef9b8,galDropFall=0x1efa70;
AuxiliaryObject& poppyOf(Ctx& c) {
    if(!c.a.auxiliaryObject04||!c.f.pools)throw std::runtime_error("Galford's commands need Poppy");
    return c.f.pools->objects.at(c.a.auxiliaryObject04-1);
}
void galfordAirFlags(Ctx& c){c.a.flags23c|=0x10;c.a.flags23c|=0x20;} // 13a858 (byte 43d05e) is 0 under console VS
bool galfordEntry(Ctx& c,uint32_t s) {
    const auto command=[&](int armed,int unarmed,uint32_t next){face(c);queue(c,(c.a.flags23c&0x1000)?armed:unarmed);bind(c.a,next);return true;};
    switch(s) {
    case 9:return command(0x257,0x258,galCmd9);
    case 10:return command(0x259,0x25a,galCmd10);
    case 11:return command(0x25d,0x25e,galCmd11);
    case 12:command(0x268,0x269,galCmd12);poppyOf(c)[0x128/4]=0x16;return true;
    case 18:return command(0x257,0x258,galCmd18);
    case 19:return command(0x261,0x260,galCmd19); // armed 0x261, unarmed 0x260
    case 20:return command(0x262,0x263,galCmd20);
    case 24:face(c);queue(c,armedPair(c,0x265));recoverLater(c.a,1);return true;
    case 23:return command(0x28e,0x28f,galWait23);
    case 13:case 14:case 16:case 17: { // 1ef448
        const int v=s==13?0:s==14?1:s==16?2:3;
        face(c);c.a.bodyState128=uint32_t(v);queue(c,v<2?0x245:0x24f);bind(c.a,galDive);return true;
    }
    case 21:case 22: { // 1ef928
        const int v=s==21?0:1;
        face(c);c.a.bodyState128=uint32_t(v);queue(c,0x279);bind(c.a,galDrop);
        auto& p=poppyOf(c);p[0x130/4]=uint32_t(v);p[0x128/4]=0x25;
        return true;
    }
    case 15: // 1ef608: the opponent is taken into 2/0x60 at once
        if(!c.f.seizeOpponent)throw std::runtime_error("1ef608 seizes the opponent");
        c.f.seizeOpponent();return true;
    default:return false;
    }
}
Visit galfordVisit(Ctx& c) {
    const auto after=[&](uint32_t state,bool reset){
        if(!consumeHold(c.o,c.a))return;
        auto& p=poppyOf(c);p[0x128/4]=state;if(reset)p[0x12c/4]=0xffffffffu;recoverLater(c.a,1);
    };
    switch(c.a.callbacks260[0]) {
    case galCmd9:after(0x0d,false);return Visit::Continue;
    case galCmd10:after(0x11,false);return Visit::Continue;
    case galCmd11:after(0x1d,false);return Visit::Continue;
    case galCmd12:after(0x18,false);return Visit::Continue;
    case galCmd18:after(0x28,true);return Visit::Continue;
    case galCmd19:after(0x1d,true);return Visit::Continue;
    case galCmd20:after(0x2c,true);return Visit::Continue;
    case galWait23:
        if(!consumeHold(c.o,c.a)&&!ended(c))return Visit::Continue;
        poppyOf(c)[0x128/4]=0x22;bind(c.a,galHold23);
        return Visit::Continue;
    case galHold23:
        if(c.f.weaponLock->opponent.state194==0x00560002){queue(c,armedPair(c,0x290));recoverLater(c.a,1);return Visit::Continue;}
        if(std::bit_cast<int32_t>(poppyOf(c)[0x12c/4])==0x22)return Visit::Continue;
        return Visit::Recover;
    case galDive: {
        if(!ended(c))return Visit::Continue;
        queue(c,armedPair(c,0x246));
        auto words=c.o.childParentWords(); // 1efc98 on the body
        dropBesideOpponent(words,c.f.weaponLock->opponentBody.childParentWords(),int(c.a.bodyState128));
        auto m=c.o.timeline.motion();c.o.timeline.stopMotion();
        m=c.o.timeline.motion();m.vx=0;m.ax=0;m.vy=int32_t(0xffff0000u);m.ay=int32_t(0xffff6000u);
        m.x=std::bit_cast<float>(words[0x40/4]);m.y=300.0f;c.o.timeline.setMotion(m);
        {const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(words[0x38/4],k.flags104,k.flags108);}
        galfordAirFlags(c);bind(c.a,galDiveFall);
        return Visit::Continue;
    }
    case galDiveFall:
        if(touchedGround(c.o,c.a.queuedActionA3c))queue(c,armedPair(c,0x24d));
        else if(c.o.timeline.clock().flags104&0xc0000)queue(c,armedPair(c,0x248));
        else return Visit::Continue;
        recoverLater(c.a,1);return Visit::Continue;
    case galDrop: {
        consumeHold(c.o,c.a);
        if(!ended(c))return Visit::Continue;
        auto words=c.o.childParentWords(); // 1efc70 = 1efc98 + 11d990
        dropBesideOpponent(words,c.f.weaponLock->opponentBody.childParentWords(),int(c.a.bodyState128));
        c.o.timeline.stopMotion();
        auto m=c.o.timeline.motion();m.x=std::bit_cast<float>(words[0x40/4]);m.y=300.0f;c.o.timeline.setMotion(m);
        {const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(words[0x38/4],k.flags104,k.flags108);}
        galfordAirFlags(c);queue(c,0x27a);bind(c.a,galDropFall);
        if(!c.f.battle)throw std::runtime_error("1ef9b8 needs the battle camera");
        c.f.battle->camera.commands.clear();c.f.battle->camera.appendCommand(5,0x30);
        return Visit::Continue;
    }
    case galDropFall:
        if(touchedGround(c.o,c.a.queuedActionA3c)||ended(c)){c.a.pendingTable=0;c.a.pendingIndex=0x16;return Visit::Continue;}
        if(!(c.o.timeline.clock().flags104&0x80000))return Visit::Continue;
        queue(c,0x27f);recoverLater(c.a,1);
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Kazuki (16): fire-level moves (f15 = fire level, f16 = level used), 16d2b0 projectiles ----
constexpr uint32_t kazRush=0x1f62d0,kazBurst=0x1f6c00,kazL1a=0x1f65d8,kazL1b=0x1f6640,kazL2a=0x1f66d0,kazL2b=0x1f6738,
                   kazL2c=0x1f67c0,kazL3a=0x1f6840,kazL3b=0x1f68a8,kazL3c=0x1f6930,kazL3d=0x1f69b0,kazL4a=0x1f6a30,
                   kazL4b=0x1f6a98,kazCharge=0x1f6ce8,kazUpper=0x1f7138,kazDive=0x1f6de8,kazDiveEnd=0x1f6e78;
bool flameStart(Ctx& c);Visit flameVisit(Ctx& c); // 1f6f28/1f6fb0, shared with Enja (below)
constexpr uint32_t kazFlameHold=0x1f6fb0;
uint8_t& fireLevel(Ctx& c){return c.a.characterBytesF14[1];} // f15
uint8_t& usedLevel(Ctx& c){return c.a.characterBytesF14[2];} // f16
bool fireLaunched(Ctx& c){return c.a.auxiliaryObject04&&c.f.pools->objects.at(c.a.auxiliaryObject04-1)[0x134/4]!=0;} //1f7628
uint8_t levelFor(Ctx& c,int arg){if(fireLaunched(c))return 0;const int t=fireLevel(c);return uint8_t(t<arg?t:arg);} //1f7208
uint32_t descriptor(Ctx& c,unsigned id,unsigned variant,unsigned act) { // 16d2b0, d0 0x26, forced 11d908
    if(!c.f.spawnDescriptor)throw std::runtime_error("16d2b0 needs the projectile engine");
    const auto h=c.f.spawnDescriptor(id,variant);
    if(!h)throw std::runtime_error("Original 16d2b0 writes through a null object");
    auto& o=c.f.pools->objects.at(h-1);o[0xd0/4]=0x26;c.f.weaponLock->objects.request(o,act,false,true);
    return h;
}
bool kazukiEntry(Ctx& c,uint32_t s) {
    const int str=strength(c.a);
    if(s<=3) { // 1f6228
        face(c);c.a.callbacks260[3]=uint32_t(str);usedLevel(c)=levelFor(c,int(s));
        c.o.scriptLatch134=0;c.a.timers[23]=8*256;
        queue(c,0x236 + usedLevel(c));bind(c.a,kazRush);return true;
    }
    if(s<=7) { // 1f6b58
        c.a.callbacks260[3]=uint32_t(str);usedLevel(c)=levelFor(c,int(s)-4);face(c);
        c.o.scriptLatch134=0;c.a.timers[23]=8*256;
        queue(c,0x267);ownEffect(c,0x268);bind(c.a,kazBurst);return true;
    }
    if(s<=11) { // 1f6448
        c.a.callbacks260[3]=uint32_t(str);usedLevel(c)=levelFor(c,int(s)-8);face(c);
        static constexpr uint32_t next[4]{kazL1a,kazL2a,kazL3a,kazL4a};
        const unsigned l=usedLevel(c);
        if(l>3)return true; // 316140 ASSERT and no recovery
        queue(c,0x211 + int(l));bind(c.a,next[l]);return true;
    }
    switch(s) {
    case 12:c.a.callbacks260[3]=0;face(c);queue(c,0x24f);bind(c.a,kazCharge);return true;
    case 13:face(c);c.a.callbacks260[3]=uint32_t(str);queue(c,armedPair(c,0x246));bind(c.a,kazUpper);return true;
    case 14:c.a.callbacks260[3]=0;face(c);queue(c,0x22d);bind(c.a,kazDive);return true;
    case 15:return false; // 1f6ef0: a debug print, then 169810
    case 16:return flameStart(c); // 1f6f28 (shared with Enja)
    default:return false;
    }
}
Visit kazukiVisit(Ctx& c) {
    const auto spend=[&]{fireLevel(c)=uint8_t(fireLevel(c)-usedLevel(c));};
    const auto hold=[&]{return consumeHold(c.o,c.a);};
    switch(c.a.callbacks260[0]) {
    case kazRush: {
        if(c.o.scriptLatch134==0) {
            ActorTimers t{c.a.timerDelta,c.a.timers};const auto old=t.decrease(23);c.a.timers=t.values;
            if(old==0){c.o.scriptLatch134=1;spend();}
        }
        const auto f=c.o.timeline.clock().flags104;
        if(f&0x40000){queue(c,0x23b + usedLevel(c));bind(c.a,0x174158);c.a.callbacks260[5]=6;return Visit::Continue;}
        bool wall=f&0x80000;
        if(!wall) { // 14aad8(actor, (int)(14adf0 + 2.0), 1, 0): the facing edge
            const auto& cam=c.f.weaponLock->camera;
            const int m=(c.a.character==46?8:c.a.character==47?16:34)+2;
            const int x=int(c.o.timeline.motion().x);
            wall=(c.o.timeline.clock().objectFlags&0x80000)?x<=cam.left+m:x>=cam.right-m;
        }
        if(!wall){if(ended(c))return Visit::Recover;return Visit::Continue;}
        queue(c,0x23a);recoverLater(c.a,1);
        return Visit::Continue;
    }
    case kazBurst: {
        if(c.o.scriptLatch134)return Visit::Continue;
        ActorTimers t{c.a.timerDelta,c.a.timers};const auto old=t.decrease(23);c.a.timers=t.values;
        if(old!=0)return Visit::Continue;
        c.o.scriptLatch134=1;spend();recoverLater(c.a,1);
        return Visit::Continue;
    }
    case kazL1a:if(hold()){ownEffect(c,0x215);bind(c.a,kazL1b);}return Visit::Continue;
    case kazL1b:if(hold()){descriptor(c,0x26,0,0x219);recoverLater(c.a,1);spend();}return Visit::Continue;
    case kazL2a:if(hold()){ownEffect(c,0x216);bind(c.a,kazL2b);}return Visit::Continue;
    case kazL2b:if(hold()){descriptor(c,0x26,1,0x21a);bind(c.a,kazL2c);spend();}return Visit::Continue;
    case kazL2c:if(hold()){descriptor(c,0x26,1,0x21b);recoverLater(c.a,1);}return Visit::Continue;
    case kazL3a:if(hold()){ownEffect(c,0x217);bind(c.a,kazL3b);}return Visit::Continue;
    case kazL3b:if(hold()){descriptor(c,0x26,2,0x21c);bind(c.a,kazL3c);spend();}return Visit::Continue;
    case kazL3c:if(hold()){descriptor(c,0x26,2,0x21d);bind(c.a,kazL3d);}return Visit::Continue;
    case kazL3d:if(hold()){descriptor(c,0x26,2,0x21e);recoverLater(c.a,1);}return Visit::Continue;
    case kazL4a:if(hold()){ownEffect(c,0x218);bind(c.a,kazL4b);}return Visit::Continue;
    case kazL4b:if(hold()){descriptor(c,0x27,0,0x21f);descriptor(c,0x27,0,0x220);recoverLater(c.a,1);spend();}return Visit::Continue;
    case kazCharge:
        if(!hold())return Visit::Continue;
        if(fireLevel(c)>=3||fireLaunched(c))queue(c,0x250);
        else fireLevel(c)=uint8_t(fireLevel(c)+1);
        recoverLater(c.a,1);return Visit::Continue;
    case kazUpper: {
        const auto f=c.o.timeline.clock().flags104;
        if(f&0x40000) {
            if(!(c.f.weaponLock->opponent.flags23c&0x10))queue(c,armedPair(c,0x248));
            recoverLater(c.a,1);return Visit::Continue;
        }
        if(f&0x80000){recoverLater(c.a,1);return Visit::Continue;}
        if(!ended(c))return Visit::Continue;
        return Visit::Recover;
    }
    case kazDive:
        if(c.o.timeline.clock().flags104&0x40000){queue(c,0x22e);bind(c.a,kazDiveEnd);return Visit::Continue;}
        if(!ended(c))return Visit::Continue;
        return Visit::Recover;
    case kazDiveEnd:
        if(!ended(c))return Visit::Continue;
        queue(c,0x22f);ownEffect(c,0x230);recoverLater(c.a,1);
        return Visit::Continue;
    case kazFlameHold:return flameVisit(c);
    default:return Visit::NotMine;
    }
}

// ---- Character 32: selector 3 (200cd8) commands the puppet and jumps by 0xa44 ----
bool karakuriEntry(Ctx& c,uint32_t s) {
    if(s!=3)return false;
    if(!c.a.auxiliaryObject04)throw std::runtime_error("200cd8 commands the puppet");
    c.f.pools->objects.at(c.a.auxiliaryObject04-1)[0x128/4]=8;
    c.a.flags244|=0x400;
    queue(c,armedPair(c,0x25f));
    const auto v=c.a.jumpDirectionA44;
    c.a.pendingTable=0;c.a.pendingIndex=int16_t(v==1?0x21:v==2?0x22:0x20); //14ff80
    return true;
}
Visit karakuriVisit(Ctx&){return Visit::NotMine;}

// ---- Character 33: selectors 0..2 repeat by mashing (2022e0), 13 throws the projectile (2026c8) ----
constexpr uint32_t ofuStart=0x202378,ofuLoop=0x2024d0,ofuThrow=0x202740,ofuFollow=0x2027d0,ofuArrive=0x202960;
constexpr int ofuStartAct[3]{0x211,0x212,0x213},ofuLoopAct[3]{0x214,0x215,0x216},ofuEndAct[3]{0x217,0x218,0x219};
constexpr int ofuWindow[3]{0x14,0x0f,0x0a},ofuLoops[3]{3,4,5};
// 14aad8(actor, m, 1, back): the facing camera edge, or with back the one behind; X truncated.
bool atEdge(Ctx& c,int m,bool back) {
    if(!c.f.weaponLock)throw std::runtime_error("14aad8 needs the camera");
    const auto& cam=c.f.weaponLock->camera;
    const bool left=c.o.timeline.clock().objectFlags&0x80000;
    const int x=int(c.o.timeline.motion().x);
    return (left!=back)?x<=cam.left+m:x>=cam.right-m;
}
bool ofudaEntry(Ctx& c,uint32_t s) {
    if(s<3) {
        c.a.callbacks260[3]=s;face(c);queueForced(c,ofuStartAct[s]);bind(c.a,ofuStart);
        c.a.bodyLatch12c=0;c.a.bodyCounter130=0;
        return true;
    }
    if(s==13) {
        c.a.callbacks260[3]=0;face(c);c.a.flags244|=0x20000;queueForced(c,0x246);bind(c.a,ofuThrow);
        return true;
    }
    return false;
}
Visit ofudaVisit(Ctx& c) {
    const unsigned s=c.a.callbacks260[3];
    auto t=timersOf(c);
    const auto press=[&]{if(c.input.sampledFeatures[6+s])++c.a.bodyLatch12c;};
    const auto reload=[&]{t.clear(23);t.set(23,ofuWindow[c.a.callbacks260[3]]);c.a.timers=t.values;};
    const auto finish=[&]{queueForced(c,ofuEndAct[s]);recoverLater(c.a,1);};
    switch(c.a.callbacks260[0]) {
    case ofuStart:
        press();
        if((c.o.timeline.clock().flags108&0x40)&&int32_t(c.a.bodyLatch12c)>=1) {
            queueForced(c,ofuLoopAct[s]);c.a.bodyLatch12c=0;reload();bind(c.a,ofuLoop);
        }
        if(ended(c))finish();
        return Visit::Continue;
    case ofuLoop:
        t.decrease(23);c.a.timers=t.values;
        press();
        if(ended(c)) {
            ++c.a.bodyCounter130;
            if(int32_t(c.a.bodyCounter130)>=ofuLoops[s]){finish();return Visit::Continue;}
            if(c.a.timers[23]>0){queueForced(c,ofuLoopAct[s]);return Visit::Continue;}
            if(int32_t(c.a.bodyLatch12c)<1){finish();return Visit::Continue;}
            queueForced(c,ofuLoopAct[s]);c.a.bodyLatch12c=0;reload();
        } else {
            if(c.a.timers[23]>0)return Visit::Continue;
            if(int32_t(c.a.bodyLatch12c)<1){finish();return Visit::Continue;}
            c.a.bodyLatch12c=0;reload();
        }
        return Visit::Continue;
    case ofuThrow:
        consumeHold(c.o,c.a);markBattle4(c);
        if(!atEdge(c,-0x3c,true))return Visit::Continue;
        c.o.timeline.setPosition(c.o.timeline.motion().x,0.f);
        queueForced(c,0x247);
        {auto& o=ownProjectile(c,0x2029d8,0x248);o[0xd0/4]=0x9c;} //2029a8
        bind(c.a,ofuFollow);
        return Visit::Continue;
    case ofuFollow: {
        AuxiliaryObject* found=nullptr;
        for(auto task:c.f.ownObjectTasks)if(task) { // 140d78(seat, n, 2): own kind-2 objects in order
            auto& x=c.f.pools->objects.at(c.f.pools->tasks.at(task-1)[7]-1);
            if(x[0xcc/4]!=2)continue;
            if(x[0x24/4]==0x248){found=&x;break;}
        }
        consumeHold(c.o,c.a);markBattle4(c);
        if(found) {
            float x=std::bit_cast<float>((*found)[0x40/4]);
            const float e4=float(int32_t((*found)[0xe4/4]));
            x=(c.o.timeline.clock().objectFlags&0x80000)?eeSub(x,e4):eeAdd(x,e4);
            c.o.timeline.setPosition(x,c.o.timeline.motion().y);
            const float b0=std::bit_cast<float>(c.o.childParentWords()[0xb0/4]);
            (*found)[0xb0/4]=std::bit_cast<uint32_t>(eeAdd(b0,1.0f));(*found)[0x104/4]|=0x20000; //11dff8
        }
        if(!atEdge(c,-200,false))return Visit::Continue;
        const auto& cam=c.f.weaponLock->camera;
        c.o.timeline.setPosition(float((c.o.timeline.clock().objectFlags&0x80000)?cam.left:cam.right),c.o.timeline.motion().y);
        queueForced(c,0x249);bind(c.a,ofuArrive);
        if(!c.f.battle)throw std::runtime_error("1414f8 needs the battle camera");
        c.f.battle->camera.appendCommand(3,0x1e);
        return Visit::Continue;
    }
    case ofuArrive:
        consumeHold(c.o,c.a);
        return ended(c)?Visit::Recover:Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Rera (19): selectors 4..23 (1f7ed0) drive the body and the wolf Shikuru (actor+4) ----
constexpr uint32_t reraJumpHold=0x1f8208,reraJumpLand=0x1f8258,reraLeap=0x1f85f0,reraLeapAir=0x1f8660,reraLeapFall=0x1f8718,
    reraDrop=0x1f8880,reraClaw1=0x1f8948,reraClaw2=0x1f89c0,reraBite1=0x1f8ab8,reraBite2=0x1f8b30,reraBite3=0x1f8b98,
    reraRush1=0x1f8c98,reraRush2=0x1f8d10,reraCall1=0x1f8de8,reraCall2=0x1f8e50,reraMount=0x1f8f10,
    reraRide1=0x1f8fe8,reraRide2=0x1f9078,reraRide3=0x1f9138,reraRide4=0x1f91e0,reraHowl1=0x1f92b8,reraHowl2=0x1f9330,
    reraVault1=0x1f9460,reraVault2=0x1f94c0;
AuxiliaryObject& wolfOf(Ctx& c) {
    if(!c.a.auxiliaryObject04||!c.f.pools)throw std::runtime_error("Rera's attack requires the wolf");
    return c.f.pools->objects.at(c.a.auxiliaryObject04-1);
}
void wolfRequest(Ctx& c,unsigned act,bool force){c.f.weaponLock->objects.request(wolfOf(c),act,false,force);} //11d908(wolf, act, 0, force)
bool wolfLive(Ctx& c){const auto& w=wolfOf(c);return w[0xc0/4]&&!(w[0x104/4]&1);}
void wolfAway(Ctx& c) { // 1fa2b8: the wolf leaps away (0x33c) with its own launch
    auto& w=wolfOf(c);w[0x128/4]=0x1b;wolfRequest(c,0x33c,false);
    w[0xfc/4]|=8u<<16;w[0x5c/4]=0x00028f5c;w[0x60/4]=0xffff4ccdu;
}
void wolfSettle(Ctx& c){auto& w=wolfOf(c);w[0x128/4]=0x1b;wolfRequest(c,0x324,false);}
void wolfFollowUp(Ctx& c) { // 1f83f0: the wolf's part after the leaps, by the body's last move (body+128)
    const auto v=c.a.bodyState128;
    if(v==0x291||v==0x292||v==0x2ed||v==0x2ee)wolfSettle(c);
    else if(v==0x2a1||v==0x2a2)wolfOf(c)[0x128/4]=0x11;
    else wolfAway(c);
    c.a.flags23c&=~0x800000u;
}
void reraLaunch(Ctx& c) { // 1f9530: the body vaults toward the wolf
    c.o.timeline.stopMotion();
    auto m=c.o.timeline.motion();
    m.vy=0x0006c28f;c.o.pendingFlags|=8;m.ay=int32_t(0xffff4ccdu);
    const float wx=std::bit_cast<float>(wolfOf(c)[0x40/4]);
    m.vx=amaSpeed(eeSub(wx,m.x),ScalarFloat{0x47800000u},ScalarFloat{0x41900000u},false,c.o.timeline.clock().objectFlags&0x80000);
    c.o.timeline.setMotion(m);
}
void reraRideStart(Ctx& c) { // 1f8f78
    wolfRequest(c,0x32f,true);face(c);queue(c,armedPair(c,0x2df));bind(c.a,reraRide1);
}
bool reraEntry(Ctx& c,uint32_t s) {
    if(s<4||s>23)return false;
    switch(s) {
    case 4:queue(c,armedPair(c,0x21a));bind(c.a,reraJumpHold);return true;
    case 5: // 1f82b0: the opponent enters Rera's capture state 2/0x60 at once
        if(!c.f.seizeOpponent)throw std::runtime_error("1f82b0 seizes the opponent");
        c.f.seizeOpponent();return true;
    case 6: { // 1f8310
        const int dir=leverDirection(c);
        auto& w=wolfOf(c);
        if(!ScalarFloat{0}.less(ScalarFloat{w[0x44/4]})){AuxiliaryObjects::stop(w);w[0x44/4]=0;wolfSettle(c);}
        else wolfAway(c);
        c.a.flags23c&=~0x800000u;requestJump(c,dir);
        return true;
    }
    case 13:case 23: // 1f8788
        queue(c,armedPair(c,0x2d8));bind(c.a,reraDrop);stopAtGround(c.o);
        if(c.a.state194==0x00570001){wolfFollowUp(c);return true;}
        {
            wolfSettle(c);
            const auto old=c.a.flags23c;c.a.flags23c=old&~0x800000u;
            if(old&0x10)wolfOf(c)[0xfc/4]|=8u<<16;else AuxiliaryObjects::stop(wolfOf(c));
        }
        return true;
    case 14:wolfRequest(c,0x32c,true);queue(c,armedPair(c,0x2a1));bind(c.a,reraClaw1);return true;
    case 15:wolfRequest(c,0x32a,true);face(c);queue(c,armedPair(c,0x29a));bind(c.a,reraBite1);return true;
    case 16:wolfRequest(c,0x327,true);face(c);queue(c,armedPair(c,0x291));bind(c.a,reraRush1);return true;
    case 17:queue(c,armedPair(c,0x211));bind(c.a,reraCall1);return true;
    case 18:face(c);queue(c,0x2de);c.a.flags23c|=0x1000000;bind(c.a,reraMount);return true;
    case 19:reraRideStart(c);return true;
    case 20:wolfRequest(c,0x333,true);face(c);queue(c,armedPair(c,0x2ed));bind(c.a,reraHowl1);return true;
    case 21:case 22: // 1f93a8
        face(c);stopAtGround(c.o);c.a.flags23c|=0x1000000;
        if(s==22){queue(c,armedPair(c,0x2fc));bind(c.a,reraVault1);}
        else{reraLaunch(c);queue(c,armedPair(c,0x228));bind(c.a,reraVault2);}
        return true;
    default: { // 7..12: 1f8498, the leap by lever direction
        const auto& f=c.input.sampledFeatures;
        const bool m=c.o.timeline.clock().objectFlags&0x80000;
        const auto s3=c.a.bodyState128;
        int d;
        if(f[90])d=m?4:1;else if(f[84])d=m?5:2;else if(f[83])d=m?3:0;
        else if(f[88])d=m?1:4;else if(f[86])d=m?2:5;else d=m?0:3;
        if(d>=3){const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(k.objectFlags^0x80000u,k.flags104,k.flags108);} //11db88
        c.a.bodyLatch12c=uint32_t(d);
        // Only the 0x2aa branch (after the wolf rush/howl) starts at y = 40.0 (663d54).
        if(s3==0x291||s3==0x292||s3==0x2ed||s3==0x2ee){queue(c,0x2aa);c.o.timeline.setPosition(c.o.timeline.motion().x,40.0f);}
        else queue(c,0x2ab);
        wolfFollowUp(c);bind(c.a,reraLeap);
        return true;
    }
    }
}
Visit reraVisit(Ctx& c) {
    const auto land=[&]{return touchedGround(c.o,c.a.queuedActionA3c);}; //1737d8
    const auto d=int(c.a.bodyLatch12c);
    switch(c.a.callbacks260[0]) {
    case reraJumpHold:if(consumeHold(c.o,c.a))bind(c.a,reraJumpLand);return Visit::Continue;
    case reraJumpLand:if(land()||ended(c)){c.a.pendingTable=0;c.a.pendingIndex=0x16;}return Visit::Continue;
    case reraLeap:if(ended(c)){queue(c,d+0x2ac);bind(c.a,reraLeapAir);}return Visit::Continue;
    case reraLeapAir:
        if(land()){stopAtGround(c.o);queue(c,d+0x2b3);recoverLater(c.a,0);}
        else if(ended(c)){queue(c,0x2b2);bind(c.a,reraLeapFall);}
        return Visit::Continue;
    case reraLeapFall:if(land()){stopAtGround(c.o);queue(c,d+0x2b3);recoverLater(c.a,0);}return Visit::Continue;
    case reraDrop:if(land()){queue(c,armedPair(c,0x2d9));recoverLater(c.a,0);}return Visit::Continue;
    case reraClaw1:if(wolfLive(c)){wolfRequest(c,0x32d,true);bind(c.a,reraClaw2);}return Visit::Continue;
    case reraClaw2:if(land()){wolfRequest(c,0x32e,true);queue(c,armedPair(c,0x2a3));recoverLater(c.a,0);}return Visit::Continue;
    case reraBite1:if(wolfLive(c)){wolfRequest(c,0x32b,true);bind(c.a,reraBite2);}return Visit::Continue;
    case reraBite2:if(ended(c)){queue(c,armedPair(c,0x29c));bind(c.a,reraBite3);}return Visit::Continue;
    case reraBite3:
        if(landingReady(c.o,c.a.queuedActionA3c)){wolfRequest(c,0x304,true);stopAtGround(c.o);queue(c,armedPair(c,0x29e));recoverLater(c.a,0);}
        return Visit::Continue;
    case reraRush1:if(wolfLive(c)){wolfRequest(c,0x328,true);bind(c.a,reraRush2);}return Visit::Continue;
    case reraRush2:if(ended(c)){wolfRequest(c,0x329,true);queue(c,armedPair(c,0x293));recoverLater(c.a,0);}return Visit::Continue;
    case reraCall1:if(ended(c)){queue(c,armedPair(c,0x213));bind(c.a,reraCall2);}return Visit::Continue;
    case reraCall2:
        if(consumeHold(c.o,c.a)) { // 1fa188: recall an idle wolf (state 12)
            auto& w=wolfOf(c);
            if(int32_t(w[0x128/4])<0xc&&!reraWolfBusy(w))w[0x128/4]=0xc;
            recoverLater(c.a,0);
        }
        return Visit::Continue;
    case reraMount:
        if(consumeHold(c.o,c.a)){wolfOf(c)[0x128/4]=0x19;c.a.flags23c|=0x800000;reraRideStart(c);}
        return Visit::Continue;
    case reraRide1:
        consumeHold(c.o,c.a);
        if(wolfLive(c)){wolfRequest(c,0x330,true);bind(c.a,reraRide2);}
        return Visit::Continue;
    case reraRide2:
        if(ended(c)) {
            wolfRequest(c,0x331,true);queue(c,armedPair(c,0x2e0));
            if(c.o.timeline.clock().flags104&0x40000)bind(c.a,reraRide3);else recoverLater(c.a,0);
        }
        return Visit::Continue;
    case reraRide3:
        if(ended(c)) {
            wolfOf(c)[0x128/4]=0x1b;wolfRequest(c,0x332,false);c.a.flags23c&=~0x800000u;
            queue(c,armedPair(c,0x2e1));bind(c.a,reraRide4);
        }
        return Visit::Continue;
    case reraRide4:if(ended(c)){queue(c,armedPair(c,0x2e2));recoverLater(c.a,0);}return Visit::Continue;
    case reraHowl1:if(wolfLive(c)){wolfRequest(c,0x334,true);bind(c.a,reraHowl2);}return Visit::Continue;
    case reraHowl2:if(ended(c)){wolfRequest(c,0x335,true);recoverLater(c.a,0);}return Visit::Continue;
    case reraVault1:if(consumeHold(c.o,c.a)){reraLaunch(c);bind(c.a,reraVault2);}return Visit::Continue;
    case reraVault2:
        if(consumeHold(c.o,c.a)||land()){c.a.flags23c|=0x800000;c.a.pendingTable=0;c.a.pendingIndex=0xf;}
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Chample (46): selectors 10..12 (20a3e0, strength) dash to the camera edge ----
constexpr uint32_t champleDash=0x20a460,champleStrike=0x20a660;
bool champleEntry(Ctx& c,uint32_t s) {
    if(s-10u>=3)return false;
    const unsigned n=strength(c.a);
    c.a.callbacks260[3]=n;face(c);queue(c,0x231+int(n));bind(c.a,champleDash);
    auto t=timersOf(c);t.set(23,8);c.a.timers=t.values;
    return true;
}
Visit champleVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case champleDash: {
        if(!c.f.weaponLock||!c.f.battle)throw std::runtime_error("20a460 needs the camera");
        const auto& cam=c.f.weaponLock->camera;
        auto t=timersOf(c);t.decrease(23);c.a.timers=t.values;
        const auto& h=c.input.sampledFeatures;
        int act=-1;
        if(h[9])act=0x238;
        else if(ended(c))act=0x239;
        else if(atEdge(c,10,true)&&c.a.timers[23]==0)act=0x239; // (int)(14adf0(46) + 2.0)
        if(act>=0) { // FINISH: 1414b8 resets the camera queue
            queue(c,act);recoverLater(c.a,1);c.f.battle->camera.commands.clear();
            return Visit::Continue;
        }
        const float x=c.o.timeline.motion().x;
        const bool hit=(c.o.timeline.clock().objectFlags&0x80000)?float(cam.right)<eeAdd(x,64.0f):eeSub(x,64.0f)<float(cam.left);
        if(!hit)return Visit::Continue;
        const int a=h[6]?0x234:h[7]?0x235:h[8]?0x236:-1;
        if(a<0)return Visit::Continue;
        queue(c,a);bind(c.a,champleStrike);c.f.battle->camera.appendCommand(3,0x30);
        return Visit::Continue;
    }
    case champleStrike:
        consumeHold(c.o,c.a);
        if(!(c.o.timeline.clock().flags104&0xc0000)&&!touchedGround(c.o,c.a.queuedActionA3c))return Visit::Continue;
        queue(c,0x237);recoverLater(c.a,1);
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Poppy (44): selectors 8/9 dive (208d18), 13 (208ec0), 12 summons a puppy (209010) ----
constexpr uint32_t poppyDive=0x208d88,poppyDiveFall=0x208e30,poppyLeap=0x208f18,poppyLeapFall=0x208f80,poppyCall=0x209068;
AuxiliaryObject& ownedObject(Ctx& c,unsigned n) { // 140d78(seat, n, -1): the n-th registered object of any kind
    unsigned k=0;
    for(auto t:c.f.ownObjectTasks)if(t){if(k++==n)return c.f.pools->objects.at(c.f.pools->tasks.at(t-1)[7]-1);}
    throw std::out_of_range("no object");
}
unsigned ownedCount(Ctx& c){unsigned n=0;for(auto t:c.f.ownObjectTasks)if(t)++n;return n;}
bool poppyEntry(Ctx& c,uint32_t s) {
    switch(s) {
    case 8:case 9:face(c);c.a.bodyState128=s-8;queue(c,0x229);bind(c.a,poppyDive);return true;
    case 13:face(c);queue(c,0x229);bind(c.a,poppyLeap);return true;
    case 12:face(c);queue(c,0x23a);bind(c.a,poppyCall);return true;
    default:return false;
    }
}
Visit poppyVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case poppyDive: {
        if(!ended(c))return Visit::Continue;
        queue(c,armedPair(c,0x22a));
        auto words=c.o.childParentWords(); // 1efc98 on the body
        dropBesideOpponent(words,c.f.weaponLock->opponentBody.childParentWords(),int(c.a.bodyState128));
        c.o.timeline.stopMotion();
        auto m=c.o.timeline.motion();m.vx=0;m.ax=0;m.vy=int32_t(0xffff0000u);m.ay=int32_t(0xffff6000u);
        m.x=std::bit_cast<float>(words[0x40/4]);m.y=300.0f;c.o.timeline.setMotion(m);
        {const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(words[0x38/4],k.flags104,k.flags108);}
        galfordAirFlags(c);bind(c.a,poppyDiveFall);
        return Visit::Continue;
    }
    case poppyDiveFall:
        if(touchedGround(c.o,c.a.queuedActionA3c))queue(c,armedPair(c,0x22c));
        else if(c.o.timeline.clock().flags104&0xc0000)queue(c,armedPair(c,0x22b));
        else return Visit::Continue;
        recoverLater(c.a,1);return Visit::Continue;
    case poppyLeap:if(ended(c)){queue(c,armedPair(c,0x240));bind(c.a,poppyLeapFall);}return Visit::Continue;
    case poppyLeapFall:
        if(touchedGround(c.o,c.a.queuedActionA3c))queue(c,armedPair(c,0x241));
        else if(c.o.timeline.clock().flags104&0x80000)queue(c,armedPair(c,0x242));
        else return Visit::Continue;
        recoverLater(c.a,1);return Visit::Continue;
    case poppyCall: {
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        if(!c.f.pools)throw std::runtime_error("209068 counts the puppies");
        const unsigned total=ownedCount(c);
        int puppies=0;std::array<int,3> free{1,1,1};
        for(unsigned i=0;i<total;++i) { // 2094f0 / 209558
            const auto& o=ownedObject(c,i);
            if(int32_t(o[0x24/4])<0x301)continue;
            ++puppies;free.at(o[0x130/4])=0;
        }
        if(puppies<3) {
            int k=0;for(int j=0;j<3;++j)if(free[j]){k=j;break;}
            auto& o=ownEffect(c,0x301); // 2090f8
            o[0x108/4]&=~0x2000u;o[0x40/4]=std::bit_cast<uint32_t>(c.o.timeline.motion().x);
            o[0x44/4]=std::bit_cast<uint32_t>(300.0f);
            c.f.pools->tasks.at(o[1]-1)[0]=0x2091d8;
            const ScalarFloat f=ScalarFloat::integer(k+1).mul(ScalarFloat{std::bit_cast<uint32_t>(-2.0f)});
            o[0xec/4]=0;o[0xf0/4]=f.bits;o[0xb4/4]=f.less(ScalarFloat{0})?f.add(ScalarFloat::integer(1)).bits:0u; //1a3ba8
            const ScalarFloat kk=ScalarFloat::integer(k);
            o[0xb0/4]=ScalarFloat{std::bit_cast<uint32_t>(-10.0f)}.sub(kk.add(kk)).bits;o[0x104/4]|=0x20000; //11dff8
            o[0x130/4]=uint32_t(k);o[0x128/4]=0xffffffffu;o[0x12c/4]=0xffffffffu;
        } else queue(c,0x23b);
        recoverLater(c.a,1);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

// ---- Rasetsu Galford (41): dives 12/13 (+14), throw 15, replica 16/17 (207d00) ----
constexpr uint32_t rgDiveStart=0x207f70,rgDiveFall=0x208018,rgImitate=0x208100,rgReplica=0x208260,
                   rgReplica2=0x2083c8,rgReplica3=0x208450,rgReplica4=0x2084c0;
void rasetsuDive(Ctx& c,uint32_t v) { // 207ee0
    face(c);c.a.bodyState128=v;
    if(v<2)queue(c,0x24c);else queue(c,armedPair(c,0x259));
    bind(c.a,rgDiveStart);
}
bool rasetsuGalfordEntry(Ctx& c,uint32_t s) {
    switch(s) {
    case 12:case 13:rasetsuDive(c,s-12);return true;
    case 14:face(c);queue(c,armedPair(c,0x257));bind(c.a,rgImitate);return true;
    case 15: // 208188 = Galford's 1ef608
        if(!c.f.seizeOpponent)throw std::runtime_error("208188 seizes the opponent");
        c.f.seizeOpponent();return true;
    case 16:case 17:face(c);c.a.bodyState128=s==16;queue(c,armedPair(c,0x26c));bind(c.a,rgReplica);return true;
    default:return false;
    }
}
Visit rasetsuGalfordVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case rgDiveStart: {
        if(!ended(c))return Visit::Continue;
        queue(c,armedPair(c,0x24d));
        auto words=c.o.childParentWords(); // 1efc98 on the body
        dropBesideOpponent(words,c.f.weaponLock->opponentBody.childParentWords(),int(c.a.bodyState128));
        c.o.timeline.stopMotion();
        auto m=c.o.timeline.motion();m.vx=0;m.ax=0;m.vy=int32_t(0xffff0000u);m.ay=int32_t(0xffff6000u);
        m.x=std::bit_cast<float>(words[0x40/4]);m.y=300.0f;c.o.timeline.setMotion(m);
        {const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(words[0x38/4],k.flags104,k.flags108);}
        galfordAirFlags(c);bind(c.a,rgDiveFall);
        return Visit::Continue;
    }
    case rgDiveFall:
        if(touchedGround(c.o,c.a.queuedActionA3c))queue(c,armedPair(c,0x24d));
        else if(c.o.timeline.clock().flags104&0xc0000)queue(c,armedPair(c,0x24f));
        else return Visit::Continue;
        recoverLater(c.a,1);return Visit::Continue;
    case rgImitate:
        if(c.o.timeline.clock().flags104&0x40000){rasetsuDive(c,2);return Visit::Continue;} // "IMITATE REPLICA"
        return ended(c)?Visit::Recover:Visit::Continue;
    case rgReplica: {
        markBattle4(c);
        if(!ended(c))return Visit::Continue;
        const bool d=c.a.bodyState128!=0;const bool armed=c.a.flags23c&0x1000;
        auto& o=ownEffect(c,armed?0x26e:0x26f);o[0x128/4]=armed?0:1;
        o[0x108/4]=(o[0x108/4]&~0x2000u)|0x1000000|0x4000000;
        c.f.pools->tasks.at(o[1]-1)[0]=0x208508;
        const auto k=c.o.timeline.clock();
        if(d){c.o.timeline.setObjectFlags(k.objectFlags&~0x80000u,k.flags104,k.flags108);o[0x38/4]|=0x80000;}
        else{c.o.timeline.setObjectFlags(k.objectFlags|0x80000u,k.flags104,k.flags108);o[0x38/4]&=~0x80000u;}
        queue(c,armedPair(c,0x26e));bind(c.a,rgReplica2);
        return Visit::Continue;
    }
    case rgReplica2:
        markBattle4(c);consumeHold(c.o,c.a);
        if(!ended(c))return Visit::Continue;
        c.a.flags244|=0x2000;queue(c,armedPair(c,0x270));bind(c.a,rgReplica3);
        return Visit::Continue;
    case rgReplica3:
        markBattle4(c);
        if(!consumeHold(c.o,c.a))return Visit::Continue;
        c.a.flags244|=0x2000;bind(c.a,rgReplica4);
        return Visit::Continue;
    case rgReplica4:
        markBattle4(c);
        return ended(c)?Visit::Recover:Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Kuroko (48): selectors 19/20 hold B+C and fire 0xb2 / 0xb5, 0xb5, 0xb6 (20ae00 / 20b078) ----
constexpr uint32_t kkA1=0x20ae90,kkA2=0x20af20,kkFire=0x20afe8,kkB1=0x20b108,kkB2=0x20b198,kkShot1=0x20b260,kkShot2=0x20b2e8,kkShot3=0x20b370,
                   kkThrown=0x20bbb0;
// 16fae0: place a fresh shot at the body's ACT attachment offset (body+110/114) while 104:8000 is set.
void kurokoPlace(Ctx& c,uint32_t handle) {
    const auto k=c.o.timeline.clock();
    if(!(k.flags104&0x8000)||!handle)return;
    auto& p=c.f.pools->objects.at(handle-1);
    const auto& att=c.o.timeline.attachedEffect(); // body+10c id, +110 dx, +114 dy
    const auto m=c.o.timeline.motion();const float dx=float(int32_t(att[1]));
    p[0x40/4]=std::bit_cast<uint32_t>((k.objectFlags&0x80000)?eeSub(m.x,dx):eeAdd(m.x,dx));
    p[0x44/4]=std::bit_cast<uint32_t>(eeAdd(m.y,float(int32_t(att[2]))));
}
bool kurokoEntry(Ctx& c,uint32_t s) {
    if(s!=19&&s!=20)return false;
    face(c);c.a.bodyState128=1;queue(c,s==19?0x24f:0x280);bind(c.a,s==19?kkA1:kkB1);
    c.a.timers[22]=0; //14d000
    setBody104(c,0x2000);
    return true;
}
Visit kurokoVisit(Ctx& c) {
    const auto h=c.input.sampledFeatures;
    const auto released=[&]{if(!h[92]||!h[93])c.a.bodyState128=0;}; // actor+434 / +438: B and C held
    const auto fire=[&](unsigned id)->bool{
        consumeHold(c.o,c.a);
        if(!(c.o.timeline.clock().flags104&0x8000))return false;
        if(!c.f.spawnDescriptor)throw std::runtime_error("Kuroko's shot needs 16d2b0");
        kurokoPlace(c,c.f.spawnDescriptor(id,0));
        return true;
    };
    Visit r=Visit::Continue;
    switch(c.a.callbacks260[0]) {
    case kkA1:case kkB1:
        released();
        if(ended(c)){const bool a=c.a.callbacks260[0]==kkA1;queue(c,a?0x251:0x282);bind(c.a,a?kkA2:kkB2);}
        break;
    case kkA2:case kkB2: {
        released();
        const bool go=ended(c)||((c.o.timeline.clock().flags108&0x40)&&c.a.bodyState128==0);
        if(go){const bool a=c.a.callbacks260[0]==kkA2;queue(c,a?0x252:0x284);bind(c.a,a?kkFire:kkShot1);}
        break;
    }
    case kkFire:if(fire(0xb2))recoverLater(c.a,1);break;
    case kkShot1:if(fire(0xb5))bind(c.a,kkShot2);break;
    case kkShot2:if(fire(0xb5))bind(c.a,kkShot3);break;
    case kkShot3:if(fire(0xb6))recoverLater(c.a,1);break;
    case kkThrown: // 20bbb0: after the final throw
        if(ended(c)) {
            const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(k.objectFlags&0x7fffffffu,k.flags104,k.flags108);
            queue(c,armedPair(c,0x2ab));recoverLater(c.a,1);
        }
        break;
    default:return Visit::NotMine;
    }
    setBody104(c,0x2000); // every visit of both selectors
    return r;
}

// ---- Shikuru & Mamahaha (45): jumps 9..14 (209a70), ride the hawk 18 (209d60), hawk attack 27 (209ef0) ----
constexpr uint32_t skJump=0x209bb8,skJumpAir=0x209c38,skJumpFall=0x209cf0,skCatch=0x209dc8,skMount=0x209e38,
                   skAtk1=0x209f58,skAtk2=0x209fc0,skAtk3=0x20a030,skAtkHit=0x20a118,skAtkHold=0x20a198,skAtkEnd=0x20a1f8,skAtkWall=0x20a238;
AuxiliaryObject& hawkOf(Ctx& c) {
    if(!c.a.auxiliaryObject04||!c.f.pools)throw std::runtime_error("Character 45 needs the hawk");
    return c.f.pools->objects.at(c.a.auxiliaryObject04-1);
}
bool shikuruEntry(Ctx& c,uint32_t s) {
    if(s>=9&&s<=14) { // 209a70: the same six directions as Rera's 1f8498
        const auto& f=c.input.sampledFeatures;
        const bool m=c.o.timeline.clock().objectFlags&0x80000;
        const auto s3=c.a.bodyState128;
        int d;
        if(f[90])d=m?4:1;else if(f[84])d=m?5:2;else if(f[83])d=m?3:0;
        else if(f[88])d=m?1:4;else if(f[86])d=m?2:5;else d=m?0:3;
        if(d>=3){const auto k=c.o.timeline.clock();c.o.timeline.setObjectFlags(k.objectFlags^0x80000u,k.flags104,k.flags108);}
        c.a.bodyLatch12c=uint32_t(d);stopAtGround(c.o);
        if(s3<3){queue(c,0x22a);c.o.timeline.setPosition(c.o.timeline.motion().x,8.0f);}
        else queue(c,0x22b);
        bind(c.a,skJump);
        return true;
    }
    if(s==18){face(c);queue(c,0x23e);c.a.flags23c|=0x01000000;bind(c.a,skCatch);return true;}
    if(s==27){face(c);queue(c,0x27c);c.a.flags23c|=0x01000000;bind(c.a,skAtk1);return true;}
    return false;
}
Visit shikuruVisit(Ctx& c) {
    const auto land=[&]{return touchedGround(c.o,c.a.queuedActionA3c);}; //1737d8
    const int d=int(c.a.bodyLatch12c);
    switch(c.a.callbacks260[0]) {
    case skJump:if(ended(c)){++c.a.characterBytesF14[12];queue(c,d+0x22c);bind(c.a,skJumpAir);}return Visit::Continue; // f20++
    case skJumpAir:
        if(land()){stopAtGround(c.o);queue(c,d+0x233);recoverLater(c.a,0);}
        else if(ended(c)){queue(c,0x232);bind(c.a,skJumpFall);}
        return Visit::Continue;
    case skJumpFall:if(land()){stopAtGround(c.o);queue(c,d+0x233);recoverLater(c.a,0);}return Visit::Continue;
    case skCatch:
        if(approachNakoruruEagle(c.o,hawkOf(c))){stopAtGround(c.o);queue(c,armedPair(c,0x23f));bind(c.a,skMount);}
        return Visit::Continue;
    case skMount:
        if(ended(c)) { // 209e38: into the alias (riding) mode
            c.o.timeline.stopMotion();queue(c,armedPair(c,0x240));
            c.a.callbacks260[0]=0;c.a.callbacks260[1]=0;c.a.callbacks260[2]=0xffffffffu;
            c.a.request18c=0;c.a.pendingTable=c.a.pendingIndex=-1;c.a.state194=0xffffffff; //14ff58
            c.a.stateCharacter198=0;c.a.stateFlags19a=0;
            c.a.flags23c|=0x200000;c.a.aliasPendingTable=c.a.aliasPendingIndex=0;c.a.timers[23]=0;
        }
        return Visit::Continue;
    case skAtk1:if(ended(c)){queue(c,armedPair(c,0x27d));bind(c.a,skAtk2);}return Visit::Continue;
    case skAtk2:
        if(approachNakoruruEagle(c.o,hawkOf(c))){stopAtGround(c.o);queue(c,armedPair(c,0x27e));bind(c.a,skAtk3);}
        return Visit::Continue;
    case skAtk3: {
        const auto f=c.o.timeline.clock().flags104;
        if(f&0x40000){queue(c,armedPair(c,0x282));bind(c.a,skAtkHit);}
        else if(f&0x80000){queue(c,armedPair(c,0x280));bind(c.a,skAtkWall);}
        else if(land()){queue(c,0x27f);recoverLater(c.a,0);}
        return Visit::Continue;
    }
    case skAtkHit:if(land()){c.a.flags23c&=~0x01000000u;queue(c,armedPair(c,0x283));bind(c.a,skAtkHold);}return Visit::Continue;
    case skAtkHold:if(consumeHold(c.o,c.a)){hawkOf(c)[0x128/4]=7;bind(c.a,skAtkEnd);}return Visit::Continue;
    case skAtkEnd:return ended(c)?Visit::Recover:Visit::Continue;
    case skAtkWall:if(land()){queue(c,0x281);recoverLater(c.a,0);}return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Suija (21): 1fa460 selector dispatch (663e98), every group indexed by strength ----
constexpr uint32_t suijaDrop=0x1fa900,suijaFall=0x1faa00,suijaRise=0x1fa6d0,suijaTop=0x1fa750,suijaLand=0x1fa7c0,
                   suijaDive=0x1fab90,suijaBurst=0x1fac88,suijaLeap=0x1fad58,suijaBounce=0x1fae28,suijaSpin=0x1faf00;
bool suijaEntry(Ctx& c,uint32_t selector) {
    const int n=strength(c.a);
    switch(selector) {
    case 0:case 1:case 2: // 1fa888
        c.a.callbacks260[3]=uint32_t(n);face(c);queue(c,0x239 + n);bind(c.a,suijaDrop);return true;
    case 4:case 5:case 6: // 1fa660
        c.a.callbacks260[3]=uint32_t(n);face(c);queue(c,0x211);c.a.flags244|=0x80;bind(c.a,suijaRise);return true;
    case 7:case 8:case 9: // 1fab20: 26c is left as it was; 1fab90 reads it later
        face(c);queue(c,0x22e + n);bind(c.a,suijaDive);return true;
    case 10:face(c);queue(c,armedPair(c,0x254));bind(c.a,suijaBurst);return true; // 1fac30
    case 11:face(c);queue(c,armedPair(c,0x249));setBody104(c,0x2000);bind(c.a,suijaLeap);return true; // 1face8
    case 13:face(c);queue(c,0x26e);bind(c.a,suijaSpin);return true; // 1faea8
    default:return false; // 3, 12 and beyond: 169810
    }
}
Visit suijaVisit(Ctx& c) {
    const auto landed=[&]{ // 1737d8 -> 1697d0, 169a50 mode 0
        if(touchedGround(c.o,c.a.queuedActionA3c)){stopAtGround(c.o);recoverLater(c.a,1);}
    };
    switch(c.a.callbacks260[0]) {
    case suijaDrop: {
        const unsigned n=c.a.callbacks260[3];
        if(consumeHold(c.o,c.a)) {
            if(n>2)throw std::runtime_error("1fa900 reads outside its projectile table");
            static constexpr unsigned ids[3][3]{{0x23c},{0x23d,0x23e},{0x23f,0x240,0x241}}; // 58f6b0
            for(unsigned k=0;k<=n;++k){auto& o=ownProjectile(c,0x1faa98,ids[n][k]);o[0x11c/4]=n;} //1faa60
            bind(c.a,suijaFall);
        } else landed();
        return Visit::Continue;
    }
    case suijaFall:case suijaBurst:case suijaSpin:consumeHold(c.o,c.a);landed();return Visit::Continue;
    case suijaRise:
        if(ended(c)){c.a.flags244|=0x80000;queue(c,0x212 + int(c.a.callbacks260[3]));bind(c.a,suijaTop);}
        else updateAirLanding(c.o,c.a); //173880
        return Visit::Continue;
    case suijaTop:
        if(ended(c)){queue(c,0x215);bind(c.a,suijaLand);c.a.flags244&=~0x80000u;}
        return Visit::Continue;
    case suijaLand: {
        if(!ended(c))return Visit::Continue;
        // 14ff80(18c, 0, n) by the first held feature; none requests 0/0x20.
        const auto& h=c.input.sampledFeatures;
        const int state=h[0x39]?0x14:h[0x37]?0x15:h[0x38]?0x13:h[0x40]?0x22:h[0x3e]?0x21:0x20;
        c.a.pendingTable=0;c.a.pendingIndex=int16_t(state);
        return Visit::Continue;
    }
    case suijaDive: // 1fab90
        if(c.o.timeline.clock().flags104&0x80000) {
            const unsigned n=c.a.callbacks260[3];
            if(n>3)throw std::runtime_error("1fab90 reads outside its landing table");
            static constexpr int acts[4]{0x231,0x232,0x233,0}; // 58f6f0
            queue(c,acts[n]);recoverLater(c.a,1);
        } else landed();
        return Visit::Continue;
    case suijaLeap:
        consumeHold(c.o,c.a);
        if(c.o.timeline.clock().flags104&0xc0000){queue(c,armedPair(c,0x24b));bind(c.a,suijaBounce);}
        else if(ended(c)){queue(c,armedPair(c,0x24f));recoverLater(c.a,1);}
        setBody104(c,0x2000);
        return Visit::Continue;
    case suijaBounce:
        consumeHold(c.o,c.a);
        if(ended(c)){queue(c,armedPair(c,0x24f));recoverLater(c.a,1);}
        setBody104(c,0x2000);
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

bool siegerEntry(Ctx& c,uint32_t selector) {
    if(selector!=0xe)return false;
    c.a.callbacks260[3]=0;face(c);markBattle4(c);queue(c,armedPair(c,0x241));bind(c.a,siegerRise);
    return true;
}
Visit siegerVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case siegerRise:
        consumeHold(c.o,c.a);markBattle4(c);
        if(ended(c)) { // then over the opponent
            queue(c,armedPair(c,0x242));bind(c.a,siegerFlight);
            c.o.timeline.setPosition(c.f.weaponLock->opponentBody.timeline.motion().x,c.o.timeline.motion().y);
        }
        return Visit::Continue;
    case siegerFlight: {
        const int dir=leverDirection(c);markBattle4(c);
        if(c.o.timeline.clock().flags104&0xc0000){queue(c,armedPair(c,0x244));bind(c.a,siegerBounce);return Visit::Continue;}
        if(landingReady(c.o,c.a.queuedActionA3c)){queue(c,armedPair(c,0x243));recoverLater(c.a,1);return Visit::Continue;}
        auto m=c.o.timeline.motion();
        if(dir!=2) { // 6645a4 = 0.9 decay; |vx| <= 6645a8 (10485.76) stops
            m.vx=ScalarFloat::integer(m.vx).mul(ScalarFloat{std::bit_cast<uint32_t>(0.9f)}).truncate();m.ax=0;
            const float v=float(m.vx<0?-m.vx:m.vx);
            if(v<=10485.76f)m.vx=0;
        } else { // 6645a0 = -10485.76 added to the acceleration; vx clamped to +-0x66666 (6645ac/6645b0)
            m.ax=ScalarFloat::integer(m.ax).add(ScalarFloat{std::bit_cast<uint32_t>(-10485.76f)}).truncate();
            if(419430.4f<float(m.vx))m.vx=0x66666;
            if(float(m.vx)< -419430.4f)m.vx=int32_t(0xfff9999au);
        }
        c.o.timeline.setMotion(m);
        return Visit::Continue;
    }
    case siegerBounce:
        consumeHold(c.o,c.a);
        if(touchedGround(c.o,c.a.queuedActionA3c)){stopAtGround(c.o);queue(c,armedPair(c,0x243));recoverLater(c.a,1);} //1737d8
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Genjuro (7): 1f1fb8 selectors 15..17 -> 1f2130 (cards); 21..23 -> 1f2678 ----
constexpr uint32_t genjuroThrow=0x1f21b0,genjuroSecond=0x1f26e8,genjuroThird=0x1f2750,genjuroFourth=0x1f2838;
bool genjuroEntry(Ctx& c,uint32_t selector) {
    if(selector-15u<3) {
        const unsigned n=selector-15;
        c.a.callbacks260[3]=n;face(c);c.a.bodyLatch12c=1; // body+12c: the button is still held
        queue(c,int(0x23d + n));bind(c.a,genjuroThrow);
        return true;
    }
    if(selector-21u<3) {
        const unsigned n=selector-21;
        c.a.callbacks260[3]=n;face(c);queue(c,int(0x22c + n));bind(c.a,genjuroSecond);
        return true;
    }
    return false;
}
// 16c408(cb, act, 0, 0) moved onto the opponent's body.
void effectOnOpponent(Ctx& c,unsigned act) {
    auto& e=ownEffect(c,act);
    const auto m=c.f.weaponLock->opponentBody.timeline.motion();
    e[0x40/4]=std::bit_cast<uint32_t>(m.x);e[0x44/4]=std::bit_cast<uint32_t>(m.y);
}
Visit genjuroVisit(Ctx& c) {
    const unsigned n=c.a.callbacks260[3];
    switch(c.a.callbacks260[0]) {
    case genjuroThrow:
        if(c.a.bodyLatch12c&&!c.input.sampledFeatures[0x5b+n])c.a.bodyLatch12c=0;
        if(consumeHold(c.o,c.a)) { //1f2238
            auto& o=ownProjectile(c,0x1f2290,0x240+n);o[0x128/4]=0;o[0xd0/4]=0x10;o[0x12c/4]=c.a.bodyLatch12c;
            recoverLater(c.a,1);
        }
        return Visit::Continue;
    case genjuroSecond:
        if(ended(c)){queue(c,0x22f);bind(c.a,genjuroThird);}
        return Visit::Continue;
    case genjuroThird:
        if(c.o.timeline.clock().flags104&0x40000){stopAtGround(c.o);queue(c,0x230);effectOnOpponent(c,0x231);bind(c.a,genjuroFourth);}
        else if(ended(c))return Visit::Recover;
        return Visit::Continue;
    case genjuroFourth:
        if(c.o.timeline.clock().flags104&0x40000){effectOnOpponent(c,0x232);recoverLater(c.a,1);}
        else if(ended(c))return Visit::Recover;
        return Visit::Continue;
    default:return Visit::NotMine;
    }
}

// ---- Enja (20) / Suija (21): 1f6f28 -> 1f6fb0 (shared; 20 selector 8) ----
constexpr uint32_t flameHold=0x1f6fb0;
bool flameStart(Ctx& c) { // 1f6f28(cb, strength)
    face(c);c.a.callbacks260[3]=strength(c.a);
    queue(c,c.a.character==20?0x237:0x289);bind(c.a,flameHold);
    return true;
}
bool enjaEntry(Ctx& c,uint32_t selector){return selector==8&&flameStart(c);}
Visit flameVisit(Ctx& c) {
    if(c.a.callbacks260[0]!=flameHold)return Visit::NotMine;
    consumeHold(c.o,c.a);
    const bool release=ended(c)||((c.o.timeline.clock().flags108&0x40)&&c.input.sampledFeatures[44]);
    if(release) {
        // 140d78(seat, n, 6): every own kind-6 object is hidden.
        if(!c.f.pools)throw std::runtime_error("1f6fb0 requires the live object pools");
        for(auto t:c.f.ownObjectTasks)if(t) {
            auto& o=c.f.pools->objects.at(c.f.pools->tasks.at(t-1)[7]-1);
            if(o[0xcc/4]==6)o[0x108/4]|=0x1000;
        }
        if(c.a.character==20)queue(c,0x238);
        else { // 16c4e0(cb, 0x28c, 0, 0)
            queue(c,0x28a);
            auto& w=*c.f.weaponLock;
            const auto h=w.objects.create(*c.f.pools,c.f.ownObjectTasks,c.context.player,c.a.flags23c,c.o.childParentWords(),0x1392 + c.context.player,6,0);
            if(!h)throw std::runtime_error("Original 16c4e0 writes through a null object");
            auto& o=c.f.pools->objects.at(h-1);w.objects.request(o,0x28c,false,true);o[0x108/4]|=0x1a000;
        }
        recoverLater(c.a,1);
    }
    setBody104(c,0x2000);
    return Visit::Continue;
}

// ---- Makai Gaoh (43, arcade boss): the stub 208830 sends selector 8 to 208978 instead of 169810 ----
constexpr uint32_t mgRush=0x208a08,mgArrive=0x208a90;
bool makaiGaohEntry(Ctx& c,uint32_t s) {
    if(s!=8)return false;
    // 208978(cb, 0): face, 1699f8, 26c = 0, 140630(2), 244 |= 0x20000, ACT 0x236, then 208a08.
    face(c);consumeHold(c.o,c.a);c.a.callbacks260[3]=0;markBattle4(c);c.a.flags244|=0x20000;
    queueForced(c,0x236);bind(c.a,mgRush);
    return true;
}
Visit makaiGaohVisit(Ctx& c) {
    switch(c.a.callbacks260[0]) {
    case mgRush: // 208a08: at 60 inside the edge behind, land (y = 0) and continue with ACT 0x237
        consumeHold(c.o,c.a);markBattle4(c);
        if(atEdge(c,-60,true)) {
            c.o.timeline.setPosition(c.o.timeline.motion().x,0.f);
            queueForced(c,0x237);bind(c.a,mgArrive);
        }
        return Visit::Continue;
    case mgArrive: { // 208a90: 200 past the facing edge, snap to that camera edge, camera command (3, 30), ACT 0x238
        consumeHold(c.o,c.a);markBattle4(c);
        if(!atEdge(c,-200,false))return Visit::Continue;
        const auto& cam=c.f.weaponLock->camera;
        c.o.timeline.setPosition(float((c.o.timeline.clock().objectFlags&0x80000)?cam.left:cam.right),c.o.timeline.motion().y);
        if(!c.f.battle)throw std::runtime_error("1414f8 needs the battle camera");
        c.f.battle->camera.appendCommand(3,0x1e);
        queueForced(c,0x238);recoverLater(c.a,1);
        return Visit::Continue;
    }
    default:return Visit::NotMine;
    }
}

struct Branch {unsigned character;bool(*entry)(Ctx&,uint32_t);Visit(*visit)(Ctx&);};
constexpr Branch branches[]{{6,ukyoEntry,ukyoVisit},{7,genjuroEntry,genjuroVisit},{8,basaraEntry,basaraVisit},{12,jubeiEntry,jubeiVisit},{13,zankuroEntry,zankuroVisit},
                            {14,charlotteEntry,charlotteVisit},{15,tamtamEntry,tamtamVisit},{17,sogetsuEntry,sogetsuVisit},{22,yoshitoraEntry,yoshitoraVisit},{23,yunfeiEntry,yunfeiVisit},
                            {25,gedoEntry,gedoVisit},{28,yumejiEntry,yumejiVisit},{29,sankuroEntry,sankuroVisit},
                            {37,siegerEntry,siegerVisit},
                            {20,enjaEntry,flameVisit},{21,suijaEntry,suijaVisit},{5,kyoshiroEntry,kyoshiroVisit},{9,shizumaruEntry,shizumaruVisit},{11,amakusaEntry,amakusaVisit},{27,mizukiEntry,mizukiVisit},{31,irohaEntry,irohaVisit},{35,genanEntry,genanVisit},{39,nicotineEntry,nicotineVisit},{4,galfordEntry,galfordVisit},{16,kazukiEntry,kazukiVisit},{32,karakuriEntry,karakuriVisit},{33,ofudaEntry,ofudaVisit},{19,reraEntry,reraVisit},{46,champleEntry,champleVisit},{44,poppyEntry,poppyVisit},{41,rasetsuGalfordEntry,rasetsuGalfordVisit},{48,kurokoEntry,kurokoVisit},{45,shikuruEntry,shikuruVisit},{43,makaiGaohEntry,makaiGaohVisit}};
const Branch* branchOf(unsigned character) {
    for(const auto& b:branches)if(b.character==character)return &b;
    return nullptr;
}
}
bool isScriptFighterAttack(const FighterTables& tables,unsigned character,uint32_t handler) {
    const auto h=tables.scriptAttack(character); // 4e8fe8, verified common stub
    if(!h)return false;
    if(handler==h||handler==0x163610)return true;
    // Follow-up callbacks of the character branches.
    switch(character) {
    case 6:return handler==ukyoSecond||handler==ukyoThird;
    case 7:return handler==genjuroThrow||handler==genjuroSecond||handler==genjuroThird||handler==genjuroFourth;
    case 8:return handler==basaraShadowWait||handler==basaraShadowMove||handler==basaraLeap||handler==basaraBounce;
    case 12:return handler==jubeiSecond||handler==jubeiThird||handler==jubeiHit||handler==jubeiFollow||handler==jubeiAir;
    case 13:return handler==zanWind||handler==zanCharge1||handler==zanCharge2||handler==zanCharge3;
    case 14:return handler==charlotteHold;
    case 15:return handler==tamtamThrow||handler==tamtamCharge;
    case 17:return handler==sogetsuHold;
    case 19:return handler==reraJumpHold||handler==reraJumpLand||handler==reraLeap||handler==reraLeapAir||handler==reraLeapFall||
                   handler==reraDrop||handler==reraClaw1||handler==reraClaw2||handler==reraBite1||handler==reraBite2||handler==reraBite3||
                   handler==reraRush1||handler==reraRush2||handler==reraCall1||handler==reraCall2||handler==reraMount||handler==reraRide1||
                   handler==reraRide2||handler==reraRide3||handler==reraRide4||handler==reraHowl1||handler==reraHowl2||handler==reraVault1||handler==reraVault2;
    case 45:return handler==skJump||handler==skJumpAir||handler==skJumpFall||handler==skCatch||handler==skMount||handler==skAtk1||handler==skAtk2||handler==skAtk3||handler==skAtkHit||handler==skAtkHold||handler==skAtkEnd||handler==skAtkWall;
    case 48:return handler==kkA1||handler==kkA2||handler==kkFire||handler==kkB1||handler==kkB2||handler==kkShot1||handler==kkShot2||handler==kkShot3||handler==kkThrown;
    case 41:return handler==rgDiveStart||handler==rgDiveFall||handler==rgImitate||handler==rgReplica||handler==rgReplica2||handler==rgReplica3||handler==rgReplica4;
    case 44:return handler==poppyDive||handler==poppyDiveFall||handler==poppyLeap||handler==poppyLeapFall||handler==poppyCall;
    case 46:return handler==champleDash||handler==champleStrike;
    case 33:return handler==ofuStart||handler==ofuLoop||handler==ofuThrow||handler==ofuFollow||handler==ofuArrive;
    case 20:return handler==flameHold;
    case 16:return handler==kazFlameHold||handler==kazRush||handler==kazBurst||handler==kazL1a||handler==kazL1b||
                   handler==kazL2a||handler==kazL2b||handler==kazL2c||handler==kazL3a||handler==kazL3b||handler==kazL3c||
                   handler==kazL3d||handler==kazL4a||handler==kazL4b||handler==kazCharge||handler==kazUpper||
                   handler==kazDive||handler==kazDiveEnd;
    case 4:return handler==galCmd9||handler==galCmd10||handler==galCmd11||handler==galCmd12||handler==galCmd18||
                  handler==galCmd19||handler==galCmd20||handler==galWait23||handler==galHold23||handler==galDive||
                  handler==galDiveFall||handler==galDrop||handler==galDropFall;
    case 39:return handler==nicoRise||handler==nicoFall||handler==nicoThrow||handler==nicoReach||handler==nicoBack;
    case 35:return handler==genanWait||handler==genanRun||handler==genanWall||handler==genanCrouch||handler==genanAir||
                   handler==genanLand||handler==genanThrow||handler==genanReach||handler==genanBack;
    case 27:return handler==mizukiShot||handler==mizukiWarp||handler==mizukiFall||handler==mizukiCurse;
    case 11:return handler==amaRise||handler==amaTop||handler==amaAim||handler==amaLand||handler==amaDrop||
                   handler==amaHold||handler==amaPull||handler==amaCharge;
    case 9:return handler==shizuOpen||handler==shizuGlide||handler==shizuGlideEnd||handler==shizuBounce||handler==shizuHop||handler==shizuThrow;
    case 5:return handler==kyoOpen||handler==kyoDance||handler==kyoClose||handler==kyoEnd;
    case 21:return handler==flameHold||handler==suijaDrop||handler==suijaFall||handler==suijaRise||handler==suijaTop||
                   handler==suijaLand||handler==suijaDive||handler==suijaBurst||handler==suijaLeap||handler==suijaBounce||handler==suijaSpin;
    case 37:return handler==siegerRise||handler==siegerFlight||handler==siegerBounce;
    case 29:return handler==sankuroStart||handler==sankuroRepeat||handler==sankuroEnd;
    case 22:return handler==yoshitoraSecond||handler==yoshitoraThird||handler==yoshitoraLast;
    case 23:return handler==yunfeiDive||handler==yunfeiBounce||handler==yunfeiDrop;
    case 25:return handler==gedoWait;
    case 43:return handler==mgRush||handler==mgArrive;
    case 28:return handler==yumejiFollow;
    default:return false;
    }
}
bool updateScriptFighterAttack(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& frame,
                               StateEntryContext& context,const ScriptEngine& scripts) {
    if(a.callbacks260[0]==0x163610)return scripts.step(o,a,input,frame);
    Ctx c{o,a,input,frame,scripts,context};
    const auto* branch=branchOf(a.character);
    if(branch) {
        const auto v=branch->visit(c);
        if(v!=Visit::NotMine)return v==Visit::Recover;
    }
    // The stub: 163570 lookup, 1696c8 strength, clear 260, then 163590, or
    // for form 2 the character branch, else 169810.
    const uint32_t selector=a.callbacks260[2];
    if(ScriptEngine::scriptId(selector)<0&&branch) {
        a.callbacks260[0]=0;
        if(branch->entry(c,selector))return false;
        return true;
    }
    return scripts.enterAttack(o,a,frame);
}
}
namespace ss6 {
void genanChainLayout(TaggedTaskPools& pools,const PlayerObject& b,const StateEntryActor& a) {
    auto at=[&](uint32_t h)->AuxiliaryObject&{if(!h)throw std::runtime_error("205860 reads a null chain object");return pools.objects.at(h-1);};
    auto& p=at(a.bodyState128);
    const auto words=b.childParentWords();
    const bool left=b.timeline.clock().objectFlags&0x80000;
    const float bx=b.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
    float base,t;
    if(!left){base=eeSub(px,52.0f);t=eeSub(base,eeAdd(bx,50.0f));t=eeAdd(t,16.0f);}
    else{base=eeAdd(px,52.0f);t=eeSub(16.0f,eeSub(base,eeSub(bx,50.0f)));}
    t=eeAdd(eeSub(t,1.0f),18.0f);
    const int32_t K=ScalarFloat{std::bit_cast<uint32_t>(t)}.mul(ScalarFloat{0x3d800000u}).div(ScalarFloat{0x40a00000u}).truncate(); // *0.0625 /5
    const float y=eeAdd(b.timeline.motion().y,30.0f);
    p[0x44/4]=std::bit_cast<uint32_t>(y);
    const float b0=std::bit_cast<float>(words[0xb0/4]);
    p[0xb0/4]=std::bit_cast<uint32_t>(eeSub(b0,2.0f));p[0x104/4]|=0x20000; //11dff8
    int32_t off=int32_t(uint32_t(K)*0x50u);
    const uint32_t links[3]{a.bodyLatch12c,a.bodyCounter130,b.scriptLatch134};
    for(int j=0;j<3;++j) {
        auto& e=at(links[j]);
        float x;
        if(!left) {
            x=eeAdd(base,40.0f);if(j<=K)x=eeSub(x,float(off));
            const float lim=eeAdd(bx,80.0f);if(x<lim)x=lim;
        } else {
            x=eeSub(base,40.0f);if(j<=K)x=eeAdd(x,float(off));
            const float lim=eeSub(bx,80.0f);if(lim<x)x=lim;
        }
        e[0x40/4]=std::bit_cast<uint32_t>(x);e[0x44/4]=std::bit_cast<uint32_t>(y);
        e[0xb0/4]=std::bit_cast<uint32_t>(eeAdd(b0,2.0f));e[0x104/4]|=0x20000;
        off=int32_t(uint32_t(off)-0x50u);
    }
}
void nicotineChainLayout(TaggedTaskPools& pools,const PlayerObject& b,const StateEntryActor& a) {
    auto at=[&](uint32_t h)->AuxiliaryObject&{if(!h)throw std::runtime_error("206db0 reads a null chain object");return pools.objects.at(h-1);};
    auto& p=at(a.bodyState128);
    const auto words=b.childParentWords();
    const bool left=b.timeline.clock().objectFlags&0x80000;
    const float bx=b.timeline.motion().x,px=std::bit_cast<float>(p[0x40/4]);
    float f20,t;
    if(!left){const float f2=eeAdd(bx,62.0f);f20=eeSub(px,30.0f);t=eeAdd(eeSub(f20,f2),8.0f);}
    else{const float f2=eeSub(bx,62.0f);f20=eeAdd(px,30.0f);t=eeSub(8.0f,eeSub(f20,f2));}
    t=eeAdd(eeSub(t,1.0f),16.0f);
    const int32_t n=ScalarFloat{std::bit_cast<uint32_t>(t)}.mul(ScalarFloat{0x3e000000u}).div(ScalarFloat{0x40c00000u}).truncate(); // *0.125 /6
    const float y=eeAdd(b.timeline.motion().y,37.0f);
    p[0x44/4]=std::bit_cast<uint32_t>(y);
    const float b0=std::bit_cast<float>(words[0xb0/4]);
    p[0xb0/4]=std::bit_cast<uint32_t>(eeAdd(b0,1.0f));p[0x104/4]|=0x20000; //11dff8
    const int32_t m=int32_t(uint32_t(n)*48u);
    const uint32_t links[3]{a.bodyLatch12c,a.bodyCounter130,b.scriptLatch134};
    for(int i=0;i<3;++i) {
        auto& e=at(links[i]);
        const float d=float(int32_t(uint32_t(m)-48u*uint32_t(i)));
        float x;
        if(!left) {
            x=eeAdd(f20,24.0f);if(!(n<i))x=eeSub(x,d);
            const float lo=eeAdd(bx,48.0f);if(x<lo)x=lo;
        } else {
            x=eeSub(f20,24.0f);if(!(n<i))x=eeAdd(x,d);
            const float hi=eeSub(bx,48.0f);if(hi<x)x=hi;
        }
        e[0x40/4]=std::bit_cast<uint32_t>(x);e[0x44/4]=std::bit_cast<uint32_t>(y);
        e[0xb0/4]=std::bit_cast<uint32_t>(eeAdd(b0,2.0f));e[0x104/4]|=0x20000;
    }
}
bool isScriptFighterObject(uint32_t h) {
    return h==0x1f5860||h==0x1fe280||h==0x1f5bd0||h==0x1f5d08||h==0x1f5ea0||h==0x1f5f88||h==0x1f7ae0||
           h==0x1f2290||h==0x1f2478||h==0x1f2500||h==0x1f25f0||h==0x16d020||h==0x1faa98||h==0x1f3778||h==0x1f37c8||h==0x1f38d8||h==0x1f4838||h==0x1f48d8||h==0x1681c0||h==0x1fe6f0||h==0x1fe768||h==0x1febb0||h==0x16e9b8||h==0x2029d8||h==0x2091d8||h==0x209240||h==0x2094a8||h==0x208508||h==0x208580;
}
void updateScriptFighterObject(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task,const ScriptObjectOwner& owner) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    const auto f104=o[0x104/4];
    const bool ended=o[0xc0/4]&&!(f104&1);
    // 16c408(cb, act, 0, 0) / 16c5f8(cb, handler, act, 0) for the owner.
    const auto effect=[&](unsigned act)->AuxiliaryObject& {
        const auto h=objects.create(pools,owner.registry,owner.player,owner.actor.flags23c,owner.body,0x1396,6,0);
        if(!h)throw std::runtime_error("Original 16c408 writes through a null object");
        auto& n=pools.objects.at(h-1);objects.request(n,act,false,true);n[0x108/4]|=0x2000;return n;
    };
    const auto projectile=[&](uint32_t handler,unsigned act)->AuxiliaryObject& {
        const auto h=objects.create(pools,owner.registry,owner.player,owner.actor.flags23c,owner.body,0x138e + owner.player,2,handler);
        if(!h)throw std::runtime_error("Original 16c5f8 writes through a null object");
        auto& n=pools.objects.at(h-1);objects.request(n,act,false,true);
        n[0xd0/4]=0xffffffffu;n[0xd4/4]=uint32_t(owner.actor.stateIndex()-64);return n;
    };
    switch(t[0]) {
    case 0x1f5bd0:case 0x1f5ea0: { // Tamtam: on landing, ground effects and the ground object
        if(ScalarFloat{0}.less(ScalarFloat{o[0x44/4]}))return; // y > 0
        const uint32_t x=o[0x40/4];
        const bool first=t[0]==0x1f5bd0;
        for(unsigned act:first?std::initializer_list<unsigned>{0x252,0x254,0x255,0x256,0x257}:std::initializer_list<unsigned>{0x26d,0x26e}){
            auto& e=effect(act);e[0x44/4]=0;e[0x40/4]=x;
        }
        auto& g=projectile(first?0x1f5d08:0x1f5f88,first?0x253:0x26f);
        g[0xd0/4]=first?0x24:0x25;g[0x40/4]=x;g[0x44/4]=0;
        o[0x108/4]|=0x1000;
        break;
    }
    case 0x1f5d08:case 0x1f5f88: // at its end it is deleted
        if(!ended)return;
        o[0x108/4]|=0x1000;
        break;
    case 0x1f2290: { // Genjuro's card: follow-ups by the held button and the contact
        const unsigned n=owner.actor.callbacks260[3];
        if(o[0x12c/4]&&owner.input&&!owner.input->sampledFeatures[0x5b+n])o[0x12c/4]=0;
        const auto end=[&](uint32_t bit){AuxiliaryObjects::stop(o);objects.request(o,0x24c,false,true);o[0x108/4]|=bit;};
        if(ended){end(0x2000);break;}
        if(f104&4){end(0x1000);break;}
        if(f104&0x80000) {
            // 139388 (practice mode) is false in versus: only a held button continues.
            if(!o[0x12c/4]){end(0x2000);break;}
            AuxiliaryObjects::stop(o);objects.request(o,0x243+n,true,false);o[0x104/4]|=0x400000;t[0]=0x1f2500;
            return;
        }
        if((f104&0x240000)||(o[0x100/4]&2)) {
            AuxiliaryObjects::stop(o);objects.request(o,0x246+n,true,false);t[0]=0x1f2478;
        }
        return;
    }
    case 0x208508:case 0x208580: { // Rasetsu Galford's replica (then 208658's window clamp)
        const auto old=f104;o[0x104/4]=old&~0x100u; // addiu -0x101 = ~0x100
        const bool done=o[0xc0/4]&&!(old&1);
        const auto park=[&]{t[0]=0x147540;};
        if(t[0]==0x208508) {
            if(done){objects.request(o,0x270+o[0x128/4],false,false);t[0]=0x208580;}
        } else if(o[0x104/4]&0x400000) {
            objects.request(o,0x272+o[0x128/4],false,false);park();o[0x108/4]|=0x2000;
        } else {
            const auto s194=owner.actor.state194;
            if(done||(s194!=0x00500001&&s194!=0x00510001)){park();objects.request(o,0x274+o[0x128/4],false,false);o[0x108/4]|=0x2000;}
        }
        if(!owner.camera)throw std::runtime_error("208658 reads the camera");
        using F=ScalarFloat;
        const F r=F::integer(34),rh=F::integer(606); // 14adf0(41) = 34; (int)(640.0 - 34.0)
        F lo=F::integer(owner.camera->left).add(r),hi=F::integer(owner.camera->right).sub(r);
        if(lo.less(r))lo=r;
        if(rh.less(hi))hi=rh;
        const F x{o[0x40/4]};
        if(x.less(lo))o[0x40/4]=lo.bits;else if(hi.less(x))o[0x40/4]=hi.bits;
        return;
    }
    case 0x2091d8: // Poppy's puppy drops in (0x301), then follows
        if(!o[0xc0/4]||(f104&1))return;
        objects.request(o,0x302,false,false);o[0x12c/4]=0;o[0x128/4]=0;t[0]=0x209240;
        return;
    case 0x209240: { // 209240: follow the owner in three lanes, or attack (state 3)
        const int32_t s=int32_t(o[0x128/4]),k=int32_t(o[0x130/4]);
        const auto& ob=owner.body;
        using F=ScalarFloat;
        const F ox{o[0x40/4]},bx{ob[0x40/4]};
        if(s==3) {
            if(!owner.opponentBody)throw std::runtime_error("209240 faces the opponent");
            const F px{(*owner.opponentBody)[0x40/4]};
            if(px.less(ox))o[0x38/4]|=0x80000;else if(ox.less(px))o[0x38/4]&=~0x80000u;
            o[0xcc/4]=2;objects.request(o,0x305,false,false);t[0]=0x2094a8;o[0x128/4]=3;o[0x12c/4]=3;
            return;
        }
        if(s==int32_t(o[0x12c/4])) {
            int ns=-1;
            if(!(o[0x38/4]&0x80000)) {
                if(bx.sub(F::integer(k*14)).less(ox))ns=2;
                else if(ox.less(bx.sub(F::integer(128-8*k))))ns=1;
                else if(s==1&&ox.less(bx.sub(F::integer(96-8*k)))){o[0x128/4]=1;return;}
                else{o[0x128/4]=0;return;}
            } else {
                if(ox.less(bx.add(F::integer(k*14))))ns=2;
                else if(bx.add(F::integer(96-8*k)).less(ox))ns=1;
                else{o[0x128/4]=0;return;}
            }
            o[0x134/4]=uint32_t(k*10);o[0x128/4]=uint32_t(ns);
            return;
        }
        if(int32_t(o[0x134/4])>0){o[0x134/4]=o[0x134/4]-1;return;}
        if(s==1)objects.request(o,0x303,false,false);
        else if(s==0){AuxiliaryObjects::stop(o);o[0x38/4]=(o[0x38/4]&~0x80000u)|(ob[0x38/4]&0x80000u);objects.request(o,0x302,false,false);}
        else if(s==2)objects.request(o,0x304,false,false);
        o[0x12c/4]=uint32_t(s);o[0x134/4]=0;
        return;
    }
    case 0x2094a8: // the attack ends: park and delete
        if(!(f104&4))return;
        t[0]=0x147540;o[0x108/4]|=0x1000;
        return;
    case 0x2029d8: { // character 33's projectile: deleted 200 units beyond the edge it travels toward
        o[0x104/4]&=~0x100u;
        if(!owner.camera)throw std::runtime_error("2029d8 reads the camera");
        const float x=std::bit_cast<float>(o[0x40/4]);
        if(o[0x38/4]&0x80000){if(eeSub(x,-200.0f)<float(owner.camera->left))o[0x108/4]|=0x1000;}
        else if(float(owner.camera->right)<eeAdd(x,-200.0f))o[0x108/4]|=0x1000;
        return;
    }
    case 0x16e9b8: // 16e818's curse marker: removed once the opponent's timer 20 is spent
        if(!owner.opponent)throw std::runtime_error("16e9b8 reads the opponent's timer 20");
        if(owner.opponent->timers[20]==0)o[0x108/4]|=0x1000;
        return;
    case 0x1fe6f0: { // Mizuki's shot: at its end it stops and flies as 0x247
        const auto f=f104;o[0x104/4]&=~0x100u;
        if(!o[0xc0/4]||(f&1))return;
        AuxiliaryObjects::stop(o);objects.request(o,0x247,false,false);t[0]=0x1fe768;
        return;
    }
    case 0x1fe768: { // 0x247 until a wall/ground contact (2c0000) or its end, then 0x248
        const bool explode=(f104&0x2c0000)||(o[0xc0/4]&&!(f104&1));
        if(!explode){if(f104&4){o[0x108/4]|=0x1000;t[0]=0x147540;}return;}
        AuxiliaryObjects::stop(o);objects.request(o,0x248,false,false);o[0x108/4]|=0x2000;t[0]=0x147540;
        return;
    }
    case 0x1febb0: // Mizuki's curse on the opponent: removed at its end
        if(!o[0xc0/4]||(f104&1))return;
        AuxiliaryObjects::stop(o);o[0x108/4]|=0x1000;t[0]=0x147540;
        return;
    case 0x1681c0: // victim row 0x27's effect: at its end it shows 0x223 and parks
        if(!o[0xc0/4]||(f104&1))return;
        objects.request(o,0x223,false,false);t[0]=0x147540;
        return;
    case 0x1f4838: { // Amakusa's 0x24a: at its end a 0x24c effect takes over (owner body+130)
        if(!o[0xc0/4]||(f104&1))return;
        auto& e=effect(0x24c);e[0x40/4]=o[0x40/4];e[0x108/4]&=~0x2000u;
        owner.actor.bodyCounter130=uint32_t(&e-pools.objects.data())+1;
        t[0]=0x147540;
        return;
    }
    case 0x1f48d8: { // Amakusa's 0x24e: at its end it removes both catch effects and itself
        if(!o[0xc0/4]||(f104&1))return;
        for(unsigned off:{0x12cu,0x130u})if(const auto h=o[off/4])pools.objects.at(h-1)[0x108/4]|=0x1000;
        t[0]=0x147540;o[0x108/4]|=0x1000;
        return;
    }
    case 0x1f3778: // Shizumaru's umbrella rises until its ACT reports 104:4
        if(!(f104&4))return;
        t[0]=0x1f37c8;AuxiliaryObjects::stop(o);o[0x104/4]|=2;
        return;
    case 0x1f37c8: { // it waits for the owner's throw pose, then falls from the stage top over him
        const auto act=owner.body[0x24/4];const auto rec=std::bit_cast<int32_t>(owner.body[0x28/4]);
        static constexpr int32_t late[5]{17,36,44,44,80}; // 589da8
        bool ok=true;
        if(act==0x27c)ok=true;
        else if((act>=0x268&&act<=0x26c)||(act>=0x272&&act<=0x276))ok=false;
        else if(act>=0x277&&act<=0x27b)ok=rec>=late[act-0x277];
        else if(act>=0x26d&&act<=0x271)ok=rec>=6;
        if(!ok)return;
        if(!owner.camera)throw std::runtime_error("1f37c8 reads the stage top");
        o[0x104/4]&=~2u;t[0]=0x1f38d8;o[0x40/4]=owner.body[0x40/4];o[0x5c/4]=0xfff80000u;
        o[0x44/4]=std::bit_cast<uint32_t>(float(int32_t(owner.camera->top)));
        return;
    }
    case 0x1f38d8: { // caught: Shizumaru is armed again and re-enters a standing state
        const float y=std::bit_cast<float>(o[0x44/4]);
        o[0x40/4]=owner.body[0x40/4];
        if(!(y<=eeAdd(std::bit_cast<float>(owner.body[0x44/4]),16.0f)))return;
        t[0]=0x147540;o[0x104/4]|=2;o[0x108/4]|=0x1000;
        auto& p=owner.actor;p.flags23c|=0x1000;
        if(p.stateTable()!=0||p.stateIndex()>=4)return; //1500a8, 1500d0
        if(!owner.enterStateNow)throw std::runtime_error("1f38d8 re-enters the owner's state");
        p.request18c=1;owner.enterStateNow();
        return;
    }
    case 0x1faa98: // Suija's drops: below the ground they stop, show 0x243 and park
        if(!ScalarFloat{o[0x44/4]}.less(ScalarFloat{0}))return; // y < 0
        AuxiliaryObjects::stop(o);objects.request(o,0x243,false,true);o[0x108/4]|=0x2000;t[0]=0x147540;
        return;
    case 0x16d020: // the 0x11 object: at its end (or record 7) five effects take its place
        if(!ended&&std::bit_cast<int32_t>(o[0x28/4])<7)return;
        t[0]=0x147540;o[0x108/4]|=0x1000;
        for(unsigned k=0;k<5;++k){auto& e=effect(0x28b+k);std::copy_n(o.begin()+0x40/4,12,e.begin()+0x40/4);} //11da98
        return;
    case 0x1f2478:case 0x1f25f0:
        if(!ended)return;
        AuxiliaryObjects::stop(o);objects.request(o,t[0]==0x1f2478?0x24c:0x24d,false,true);o[0x108/4]|=0x2000;
        break;
    case 0x1f2500: {
        const unsigned n=owner.actor.callbacks260[3];
        if(f104&0x40000){AuxiliaryObjects::stop(o);objects.request(o,0x249+n,true,false);t[0]=0x1f25f0;}
        else if(!ScalarFloat{0}.less(ScalarFloat{o[0x44/4]})) { // y <= 0
            AuxiliaryObjects::stop(o);objects.request(o,0x24d,false,true);o[0x108/4]|=0x2000;t[0]=0x147540;
        }
        // 104 bit 0x400000 follows the rising flight (vy > 0).
        if(std::bit_cast<int32_t>(o[0x5c/4])>0)o[0x104/4]|=0x400000;else o[0x104/4]&=~0x400000u;
        return;
    }
    case 0x1f7ae0: // Sogetsu: at its end 0x21a, hold; out of view it is only hidden
        if(ended){AuxiliaryObjects::stop(o);objects.request(o,0x21a,false,true);o[0x108/4]|=0x2000;break;}
        if(f104&4)o[0x108/4]|=0x1000;
        return;
    case 0x1f5860:
        // Charlotte's shot: when it ends or leaves the view it is hidden and
        // deleted; on a contact or when struck it plays impact ACT 0x21a,
        // which stays visible (1f58f4 skips the 0x1000 bit).
        if((o[0xc0/4]&&!(f104&1))||(f104&4))o[0x108/4]|=0x1000;
        else if((f104&0x2c0000)||(o[0x100/4]&2)){objects.request(o,0x21a,false,true);o[0x108/4]|=0x2000;}
        else return;
        break;
    case 0x1fe280:
        // Kusaregedo's object: at the end of its ACT it stops, hides and is deleted.
        if(!o[0xc0/4]||(f104&1))return;
        AuxiliaryObjects::stop(o);o[0x108/4]|=0x1000;
        break;
    default:throw std::logic_error("Not a script fighter object");
    }
    t[0]=0x147540; //147530
}
}
