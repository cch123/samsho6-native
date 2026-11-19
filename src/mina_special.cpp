#include "mina_special.hpp"
#include "battle_round.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include "nakoruru_capture.hpp"
#include <bit>

// Resource-24 attack callbacks. Addresses refer to SLPS_255.59; see
// docs/mina-callbacks.txt sections 3, 4 and 7.
namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
// 1696c8: strength from the effective attack flags (4 heavy, 2 medium).
unsigned strength(const StateEntryActor& a) {
    const auto f=a.effectiveFlags();
    return (f&4)?2:(f&2)?1:0;
}
// Mina's continuations pass table word 0 to 1522a0, unlike the 163610 binding.
void bind(StateEntryActor& a,uint32_t pc) {a.callbacks260[0]=pc;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;}
void recoverLater(StateEntryActor& a) {bind(a,0x169a50);a.callbacks260[5]=0;}
AuxiliaryObject& chample(StateEntryActor& a,StateEntryContext& context) {
    if(!a.auxiliaryObject04)throw std::runtime_error("Mina's attack requires Chample");
    return context.tasks.objects.at(a.auxiliaryObject04-1);
}
// "free(aux)": Chample may be commanded unless riding (14) or hidden (19).
bool commandable(const AuxiliaryObject& c) {const int s=int32_t(c[0x12c/4]);return s!=14&&s!=19;}
void face(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) {
    GroundStateRuntime::captureBody(b,a);a.opponentX=f.opponentX;a.faceOpponent();GroundStateRuntime::restoreBody(b,a);
}
// 1699f8
bool consumeHold(PlayerObject& b,const StateEntryActor& a) {
    const auto c=b.timeline.clock();
    const bool done=actionEnded(b,a.queuedActionA3c)||(c.flags104&0x100);
    b.setFlags(c.flags104&~0x100u,c.flags108);
    return done;
}
// 16c5f8(cb,handler,act,0): an own kind-2 object, forced ACT request.
void throwWeapon(PlayerObject& b,StateEntryActor& a,StateEntryContext& context,const GroundStateFrame& f,
                 uint32_t handler,unsigned act) {
    if(!f.weaponLock||!f.battle)throw std::runtime_error("Mina's weapon throw requires live objects and camera");
    auto& world=*f.weaponLock;
    const auto handle=world.objects.create(context.tasks,world.objectTasks,context.player,a.flags23c,
                                           b.childParentWords(),0x138e + context.player,2,handler);
    if(handle) {
        auto& o=context.tasks.objects.at(handle-1);
        world.objects.request(o,act,false,true);
        o[0xd0/4]=0xffffffffu;o[0xd4/4]=uint32_t(a.stateIndex()-64);
    }
    f.battle->camera.appendCommand(5,60); // 1414f8(5,60)
}
}

bool isMinaAttackCallback(uint32_t h) {
    switch(h) {
    case 0x1fb7a8:case 0x163610:case 0x1fbbc0:case 0x1fbd00:case 0x1fbda0:case 0x1fbe30:
    case 0x1fc078:case 0x1fc138:case 0x1fc1f8:case 0x1fc2c8:case 0x1fc368:case 0x1fc3d0:
        return true;
    default:return false;
    }
}
bool updateMinaAttack(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f,
                      StateEntryContext& context,const ScriptEngine& scripts) {
    const auto pc=a.callbacks260[0];
    const auto queue=[&](int act){scripts.queue(b,a,f,act);};
    switch(pc) {
    case 0x163610:return scripts.step(b,a,input,f);
    case 0x1fb7a8: {
        // 1fb7a8 calls 163570 and 1696c8 before clearing the callback word.
        const uint32_t selector=a.callbacks260[2];
        const int id=ScriptEngine::scriptId(selector);
        const unsigned variant=strength(a);
        a.callbacks260[0]=0;
        if(id>=0){scripts.start(b,a,f,unsigned(id),variant);return false;}
        auto& c=chample(a,context);
        switch(selector) {
        case 0:case 1:case 3: // 1fba08 / 1fba88 / 1fbc40
            queue(selector==0?650:selector==1?651:649);recoverLater(a);
            if(selector==3)c[0x128/4]=15;
            else if(commandable(c))c[0x128/4]=selector==0?16:18;
            return false;
        case 2: { // 1fbb08: turn toward Chample by writing the mirror bit directly
            queue(647);bind(a,0x1fbbc0);c[0x128/4]=13;
            const F bx{std::bit_cast<uint32_t>(b.timeline.motion().x)},cx{c[0x40/4]};
            GroundStateRuntime::captureBody(b,a);
            if(bx.less(cx))a.bodyFlags38&=~mirror;else if(cx.less(bx))a.bodyFlags38|=mirror;
            GroundStateRuntime::restoreBody(b,a);
            return false;
        }
        case 4:face(b,a,f);queue(610);bind(a,0x1fbd00);return false; // 1fbca8
        case 18:queue(635);bind(a,0x1fc078);return false;
        case 19:queue(633);bind(a,0x1fc138);return false;
        case 20:queue(634);bind(a,0x1fc1f8);return false;
        case 28:face(b,a,f);queue(709);bind(a,0x1fc2c8);return false; // 1fc270
        default:return true; // 169810
        }
    }
    case 0x1fbbc0: {
        auto& c=chample(a,context);
        // Exact float equality: Chample state 13 snaps onto her X.
        const F bx{std::bit_cast<uint32_t>(b.timeline.motion().x)},cx{c[0x40/4]};
        if(!bx.less(cx)&&!cx.less(bx)) { // C.EQ.S
            queue(648);recoverLater(a);c[0x128/4]=14;
        }
        return false;
    }
    case 0x1fbd00:
        if(actionEnded(b,a.queuedActionA3c)) {
            queue(611);bind(a,0x1fbda0);a.flags23c&=~0x1000u;
            throwWeapon(b,a,context,f,0x1fbfc8,613);
        }
        return false;
    case 0x1fbda0:
        // 104:4 is the out-of-view mark written by 142f30 before the stage phase.
        if(b.timeline.clock().flags104&4) {
            queue(612);bind(a,0x1fbe30);
            if(!f.weaponLock)throw std::runtime_error("Mina's dive requires the opponent body");
            b.timeline.setPosition(f.weaponLock->opponentBody.timeline.motion().x,b.timeline.motion().y);
        }
        return false;
    case 0x1fbe30: {
        // 174330: screen direction from the held lever, mirrored by facing.
        const auto& s=input.sampledFeatures;
        const bool facingLeft=b.timeline.clock().objectFlags&mirror;
        int dir=0;
        if(s[0x168/4]||s[0x14c/4]||s[0x150/4])dir=facingLeft?2:1;
        else if(s[0x160/4]||s[0x15c/4]||s[0x158/4])dir=facingLeft?1:2;
        if(landingReady(b,a.queuedActionA3c)){recoverLater(a);return false;}
        auto m=b.timeline.motion();
        const F step{std::bit_cast<uint32_t>(dir==1?10485.76f:dir==2?-10485.76f:0.0f)};
        if(!dir) {
            m.ax=0;
            const int v=F::integer(m.vx).mul({std::bit_cast<uint32_t>(0.9f)}).truncate();m.vx=v;
            F mag=F::integer(v<0?-v:v);
            if(!F{std::bit_cast<uint32_t>(10485.76f)}.less(mag))m.vx=0;
        } else {
            const int old=m.vx;
            m.ax=F::integer(m.ax).add(step).truncate();
            if(F{std::bit_cast<uint32_t>(419430.4f)}.less(F::integer(old)))m.vx=0x66666;
            else if(F::integer(old).less({std::bit_cast<uint32_t>(-419430.4f)}))m.vx=int32_t(0xfff9999a);
        }
        b.timeline.setMotion(m);
        return false;
    }
    case 0x1fc078:case 0x1fc138:case 0x1fc1f8:
        if(consumeHold(b,a)) {
            auto& c=chample(a,context);
            if(commandable(c))c[0x128/4]=pc==0x1fc078?20:pc==0x1fc138?23:30;
            recoverLater(a);
        }
        return false;
    case 0x1fc2c8:
        if(actionEnded(b,a.queuedActionA3c)) {
            queue(710);bind(a,0x1fc368);a.flags23c&=~0x1000u;
            throwWeapon(b,a,context,f,0x1fc420,712);
        }
        return false;
    case 0x1fc368:if(actionEnded(b,a.queuedActionA3c)){queue(711);bind(a,0x1fc3d0);}return false;
    case 0x1fc3d0:if(landingReady(b,a.queuedActionA3c))recoverLater(a);return false;
    default:throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());
    }
}

void updateMinaWeapon(TaggedTaskPools& pools,uint32_t task,const AuxiliaryObject& body,StateEntryActor& owner) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    if(!o[0xc0/4]||(o[0x104/4]&1))return;
    const auto release=[&]{t[0]=0x147540;o[0x108/4]|=0x1000;owner.flags23c|=0x1000;};
    if(t[0]==0x1fbfc8){release();return;}
    // 1fc420: home on the owner's body + (0, 12).
    const F twelve=F::integer(12),zero{0};
    const F tx=(body[0x38/4]&mirror)?F{body[0x40/4]}:F{body[0x40/4]}.add(zero);
    const F ty=F{body[0x44/4]}.add(twelve);
    const F ox{o[0x40/4]};
    F dx=tx.sub(ox);const F dy=ty.sub({o[0x44/4]});
    if(dx.less(zero))dx.bits^=0x80000000u;
    // MULA.S / MADD.S accumulate dx*dx + dy*dy before SQRT.S.
    const F distance=dx.mul(dx).add(dy.mul(dy)).sqrt();
    if(!twelve.less(distance)){release();return;}
    const F k=F::integer(100).div(distance);
    const F scale{std::bit_cast<uint32_t>(0.08f)},fixed=F::integer(65536);
    const F vy=F::integer(dy.mul(k).mul(scale).mul(fixed).truncate());
    F vx=F::integer(dx.mul(k).mul(scale).mul(fixed).truncate());
    const bool flipped=o[0x38/4]&mirror;
    if(!flipped&&tx.less(ox))vx.bits^=0x80000000u;
    if(flipped&&ox.less(tx))vx.bits^=0x80000000u;
    if(!o[0x128/4]) {
        AuxiliaryObjects::stop(o);
        o[0x50/4]=uint32_t(vx.truncate());o[0x5c/4]=uint32_t(vy.truncate());o[0x128/4]=1;
    } else {
        // libgcc soft double (310be0/310fa0/311390/310ee0/311440): IEEE double,
        // round to nearest, then truncation toward zero.
        const auto blend=[](F fresh,uint32_t old) {
            const double v=double(std::bit_cast<float>(fresh.bits))*0.6+double(int32_t(old))*0.4;
            return uint32_t(int32_t(v));
        };
        o[0x50/4]=blend(vx,o[0x50/4]);
        o[0x5c/4]=blend(vy,o[0x5c/4]);
    }
}
}

namespace ss6 {
bool updateMinaVictim(PlayerObject& body,StateEntryActor& v,StateEntryContext& context,const GroundStateFrame& f,const ScriptEngine& scripts) {
    // 1fb970 for a victim of Mina. Rows (4e3a80) exist for k = 1..4; see
    // docs/victim-script-engine.txt sections 3, 4 and 10.
    if(!f.weaponLock)throw std::runtime_error("Mina's victim script requires both fighters");
    const int k=v.stateIndex()-80;
    if(k==2||k==4){updateFighterCapture(body,v,context,f);return false;}
    if(k==3)throw UnportedFighterState(v.character,2,v.stateIndex());
    auto& world=*f.weaponLock;auto& mina=world.opponent;auto& minaBody=world.opponentBody;
    const unsigned str=strength(mina);
    v.callbacks260[0]=0;
    // 1657b0 / 168220: the delivering object must still be registered.
    auto* child=v.bodyField124?&context.tasks.objects.at(v.bodyField124-1):nullptr;
    const auto fallback=[&]{v.pendingTable=2;v.pendingIndex=74;v.request18c=1;};
    bool invalid=false;
    if(!child||(*child)[0xc/4]==2) {
        if(mina.stateTable()==2){fallback();invalid=true;}
    } else {
        const auto owner=(*child)[0xc/4];
        const auto tasks=owner==context.player?std::span<const uint32_t>(world.objectTasks):f.opponentObjectTasks;
        bool found=false;
        for(auto task:tasks)if(task&&context.tasks.tasks.at(task-1)[7]==v.bodyField124) {
            const auto kind=(*child)[0xcc/4];found=kind==2||kind==3;break;
        }
        if(owner>1||!found){fallback();invalid=true;}
    }
    // 1688c8 drops the weapon only for rows whose first row has flag 80.
    if(invalid||(v.flags23c&0x10000000))return false;
    const bool noFacing=k==1||k==2; // 168f48(24,k)
    if(!child) {
        if(!(mina.flags23c&0x10000000)&&!noFacing) {
            auto s=minaBody.timeline.clock(),t=body.timeline.clock();
            const float x=body.timeline.motion().x,from=minaBody.timeline.motion().x;
            if(x<from)s.objectFlags|=0x80000;else if(x>from)s.objectFlags&=~0x80000u;
            minaBody.timeline.setObjectFlags(s.objectFlags,s.flags104,s.flags108);
            body.timeline.setObjectFlags((t.objectFlags&~0x80000u)|(~s.objectFlags&0x80000u),t.flags104,t.flags108);
        }
    } else if(!((*child)[0x104/4]&0x100000)) {
        if(!noFacing) {
            auto& flags=(*child)[0x38/4];
            const float x=body.timeline.motion().x,from=std::bit_cast<float>((*child)[0x40/4]);
            if(x<from)flags|=0x80000;else if(from<x)flags&=~0x80000u;
            const auto c=body.timeline.clock();
            body.timeline.setObjectFlags((c.objectFlags&~0x80000u)|(~flags&0x80000u),c.flags104,c.flags108);
        }
        (*child)[0x104/4]|=0x100000;
    }
    mina.flags23c|=0x10000000u;mina.flags244&=~0x1000u; // 168690(24,k) is false
    if(k!=1)return true; // no row: 169810
    // 165a78, row 1 (4e3a80): paired, last row without waits.
    auto& r=v.registry28c;
    r[12]=0x4e3a80;r[3]=str;r[2]=0xffffffffu;r[0]=0;r[1]=0xffffffffu;r[7]=r[8]=r[9]=0;
    if(mina.stateTable()==2||mina.fieldA30<=0||(mina.flags23c&0x80)){fallback();return false;} // 168318
    v.callbacks260={};v.override27c={};v.callbacks260[3]=str;v.bodyState128=v.bodyLatch12c=0;
    mina.callbacks260={};mina.override27c={};mina.request18c=0;mina.pendingTable=mina.pendingIndex=-1;
    mina.timers[0]=mina.timers[1]=0;
    r[10]=0;
    // 168400: freeze both registries and the common one; mark the victim.
    if(f.suppressCaptureObjects)f.suppressCaptureObjects();
    v.flags244|=0x10;
    if(body.timeline.action().id()!=1578)body.timeline.stopMotion();
    // 165f18 row entry: queue2(V,1499,1500); timers23 cleared.
    v.queuedActionA3c=(v.flags23c&0x1000)?1499:1500;v.flags248&=~0x800u;
    r[1]=0;v.timers[23]=0;mina.timers[23]=0;
    // 1667f8: victim op 6 holds the final pose; attacker op 27 starts script 64.
    v.callbacks260[0]=0x169a50;v.callbacks260[1]=0;v.callbacks260[2]=0xffffffffu;v.callbacks260[5]=4;
    mina.registry28c.fill(0);mina.registry28c[2]=0xffffffffu;
    WeaponLockActorContext reverse{body,v,world.camera,world.cachedDistance,world.objects,f.opponentObjectTasks};
    GroundStateFrame minaFrame=f;minaFrame.opponentX=body.timeline.motion().x;minaFrame.weaponLock=&reverse;
    GroundStateRuntime::captureBody(minaBody,mina);
    scripts.start(minaBody,mina,minaFrame,64,0);
    GroundStateRuntime::captureBody(minaBody,mina);
    v.timers[0]=v.timers[1]=0;
    return false;
}
}
