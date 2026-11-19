#include "nakoruru_eagle_attack.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include "round_control.hpp"
#include <bit>

namespace ss6 {
namespace {
ScalarFloat number(float f) {return {std::bit_cast<uint32_t>(f)};}

void bind(StateEntryActor& a,uint32_t handler,unsigned table=1) {
    a.callbacks260[0]=handler;a.callbacks260[1]=table;a.callbacks260[2]=0xffffffffu;
}

void queue(StateEntryActor& a,int action) {
    a.queuedActionA3c=action;a.flags248&=~0x800u;
}

bool recordSignal(PlayerObject& body,const StateEntryActor& a) {
    const auto c=body.timeline.clock();
    body.setFlags(c.flags104&~0x100u,c.flags108);
    return actionEnded(body,a.queuedActionA3c)||(c.flags104&0x100);
}

void face(PlayerObject& body,StateEntryActor& a,float target) {
    a.opponentX=target;a.faceOpponent();GroundStateRuntime::restoreBody(body,a);
}

bool command(PlayerObject& body,StateEntryActor& a,const ActorCommandInput& input,
             AuxiliaryObject& bird,const GroundStateFrame& frame) {
    auto& r=a.registry28c;
    const bool throwBird=a.stateIndex()!=77;
    if(a.callbacks260[0]==0x1ec2f0) {
        const unsigned strength=a.stateFlags19a&4?2u:unsigned(bool(a.stateFlags19a&2));
        r[0]=r[1]=0;r[2]=0xffffffff;r[3]=strength;
        r[11]=throwBird?0x4df308:0x4df254;
        a.callbacks260[3]=strength;
        if(!throwBird)face(body,a,frame.opponentX);
        a.flags23c&=~0x02000000u;
        queue(a,throwBird?670+int(strength)*2+!(a.flags23c&0x1000):681);
        r[6]=body.timeline.motion().y>0;body.scriptLatch134=0;
        bind(a,0x163610);
        return false;
    }
    // 164804 accepts the ACT's 0x100 marker before testing the last record.
    // The next phase's 164d58 sends the bird. Interrupting the earlier
    // wind-up therefore does not produce a dive from the independent task.
    if(throwBird&&r[0]==0) {
        if(recordSignal(body,a)) {
            ++r[0];r[1]=r[0];
            bird[0x128/4]=6;bird[0x130/4]=a.callbacks260[3];
            a.flags23c&=~0x02000000u;body.scriptLatch134=0;
        }
        r[6]=body.timeline.motion().y>0;
        return false;
    }
    if(!actionEnded(body,a.queuedActionA3c)) {
        recordSignal(body,a);r[6]=body.timeline.motion().y>0;
        return false;
    }
    r.fill(0);r[2]=0xffffffff;
    if(input.sampledFeatures[0xfc/4])a.flags23c|=8;else a.flags23c&=~8u;
    return true;
}
}

bool approachNakoruruEagle(PlayerObject& body,const AuxiliaryObject& bird) {
    const auto c=body.timeline.clock();auto m=body.timeline.motion();
    const bool mirrored=c.objectFlags&0x80000;
    const auto x=number(m.x),y=number(m.y);
    const ScalarFloat eagleX{bird[0x40/4]},eagleY{bird[0x44/4]};
    const auto offset=number(-6);auto dx=(mirrored?eagleX.sub(offset):eagleX.add(offset)).sub(x);
    dx.bits&=0x7fffffffu;
    const auto dy=eagleY.sub(number(30)).sub(y);
    if(dx.mul(dx).add(dy.mul(dy)).sqrt().less(number(10)))return true;
    // 1ece48 compares the unshifted eagle X to set local velocity direction,
    // even when the six-pixel grip offset lies on the other side of the body.
    const ScalarFloat gain{0x45f5c28f};
    m.ax=m.ay=0;m.vx=dx.mul(gain).truncate();m.vy=dy.mul(gain).truncate();
    if(mirrored?x.less(eagleX):eagleX.less(x))m.vx=-m.vx;
    body.timeline.setMotion(m);
    return false;
}

bool nakoruruEagleAttackSupports(int state) {return (state>=74&&state<=77)||state==90;}

bool updateNakoruruEagleAttack(PlayerObject& body,StateEntryActor& a,const ActorCommandInput& input,
                               StateEntryContext& context,const GroundStateFrame& frame) {
    auto& bird=context.tasks.objects.at(a.auxiliaryObject04-1);
    if(a.stateIndex()!=90)return command(body,a,input,bird,frame);
    const auto cb=a.callbacks260[0];const int unarmed=!(a.flags23c&0x1000);
    const auto set=[&](int action,uint32_t handler) {queue(a,action);bind(a,handler);};
    const auto finish=[&](int action) {queue(a,action);bind(a,0x169a50,0);a.callbacks260[5]=0;};
    if(cb==0x1ec2f0) {
        face(body,a,frame.opponentX);set(691,0x1ecfe0);a.flags23c|=0x01000000u;
        return false;
    }
    bool recover=false;
    switch(cb) {
    case 0x1ecfe0:
        if(actionEnded(body,a.queuedActionA3c)) {
            set(693+unarmed,0x1ed050);
            // 168c18 finds these two ACTs in Nakoruru's lock table. The
            // preceding 691 startup plays before the 64-count freeze.
            auto& b=*frame.battle;b.timers.lock=64;b.gauges.focus46a948=int32_t(body.ownerCC);
            for(auto& tone:std::span(b.gauges.paletteTones).subspan(512))tone|=4;
            a.flags23c|=0x08000000u;frame.weaponLock->opponent.flags23c&=~0x08000000u;
        }
        break;
    case 0x1ed050:
        if(approachNakoruruEagle(body,bird)){stopAtGround(body);set(695+unarmed,0x1ed0c8);}
        break;
    case 0x1ed0c8: {
        // The contact resolver writes distinct hit and guard bits. Both
        // take precedence over landing on that update, with hit checked first.
        const auto flags=body.timeline.clock().flags104;
        if(flags&0x40000)set(701+unarmed,0x1ed1c0);
        else if(flags&0x80000)set(698+unarmed,0x1ed300);
        else if(touchedGround(body,a.queuedActionA3c))finish(697);
        break;
    }
    case 0x1ed1c0:
        if(landingReady(body,a.queuedActionA3c)){a.flags23c&=~0x01000000u;set(703+unarmed,0x1ed248);}
        break;
    case 0x1ed248:
        if(recordSignal(body,a)){bird[0x128/4]=7;bind(a,0x1ed2b0);}
        break;
    case 0x1ed2b0:
        recover=actionEnded(body,a.queuedActionA3c);
        break;
    case 0x1ed300:
        if(landingReady(body,a.queuedActionA3c))finish(700);
        break;
    case 0x169a50:
        recordSignal(body,a);
        recover=actionEnded(body,a.queuedActionA3c);
        if(recover)a.request18c=1;
        return recover;
    default:throw UnportedFighterState(a.character,1,a.stateIndex());
    }
    // 168a80 clears this gate before each attack callback. 1ed0xx restores
    // it after checking its branch to keep control over terminal ACT jumps.
    const auto c=body.timeline.clock();body.setFlags(c.flags104|0x2000,c.flags108);
    return recover;
}
}
