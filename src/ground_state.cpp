#include "ground_state.hpp"
#include <execinfo.h>
#include <algorithm>
#include <cstdlib>
#include "fighter_roster.hpp"
#include "poppy.hpp"
#include "damage.hpp"
#include "battle_round.hpp"
#include "dash_motion.hpp"
#include "ground_throw.hpp"
#include "weapon_handling.hpp"
#include "weapon_deflection.hpp"
#include "weapon_pickup.hpp"
#include "pursuit_attack.hpp"
#include "combined_slash.hpp"
#include "stage_item_contact.hpp"
#include "throw_victim.hpp"
#include "sound_selection.hpp"
#include "jump_motion.hpp"
#include "haohmaru_special.hpp"
#include "rimururu_special.hpp"
#include "hanzo_special.hpp"
#include "script_fighter.hpp"
#include "mina_special.hpp"
#include "chample.hpp"
#include "nakoruru_eagle_attack.hpp"
#include "nakoruru_riding.hpp"
#include "nakoruru_capture.hpp"
#include "ten_explosion.hpp"
#include "knockout.hpp"
#include "ordinary_rules.hpp"
#include "state_callbacks.hpp"
#include "actor_state.hpp"
#include "round_rules.hpp"
#include "ending_playback.hpp"
#include "actor_color.hpp"
#include "ten_chain.hpp"
#include "contact_presentation.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
struct StateEntryActor;struct GroundStateFrame;
void launchPakuPaku(const StateEntryActor&,const GroundStateFrame&);
namespace {
bool unsupportedForm(const StateEntryActor& a) {
    uint32_t mask=(a.character==1||a.character==45)?0x500000u:0xf00000u; // 1 and 45 ride (0x200000)
    if(a.character==11)mask&=~0x400000u; // Amakusa's alternate stance (script events 21/22, 14bba8)
    if(a.character==19)mask&=~0x800000u; // Rera riding Shikuru (1f8f10 / 1f94c0)
    return (a.flags23c&mask)!=0;
}
}
std::optional<WhirlwindRows> GroundStateRuntime::whirlwindRows(const StateEntryActor& v) const {
    if(v.stateTable()!=2)return std::nullopt;
    const int k=v.stateIndex()-80;const unsigned source=v.pendingCharacter254;
    if(k<0||k>2||source>=51)return std::nullopt;
    const auto address=victimTables_.find(source,unsigned(k));
    if(!address)return std::nullopt;
    const auto& row=victimTables_.row(address);
    if(!(row.flags&0x40)||row.childAct!=0x217)return std::nullopt;
    return WhirlwindRows{source,victimTables_.fighters().damageSource(source),address,victimTables_.row(address+40).type==0x08};
}
void UnportedFighterState::traceOrigin() {
    if(!std::getenv("SS6_DEBUG_HANDLER"))return;
    void* frames[8];const int n=backtrace(frames,8);backtrace_symbols_fd(frames,n,2);
}
bool GroundStateRuntime::supports(int table,int index) {
    if(table==0)return (index>=0&&index<=60)||index==62||index==63;
    if(table==1)return (index>=0&&index<=24)||index==26||index==29||index==31||index==33||(index>=35&&index<=54)||(index>=64&&index<96);
    return table==2&&((index>=0&&index<=7)||(index>=10&&index<=16)||(index>=20&&index<=26)||
        index==30||index==31||(index>=32&&index<=49)||(index>=52&&index<=58)||KnockdownPlayback::supportsFall(index)||index==61||index==74||index==75||(index>=80&&index<=87)||index==96);
}
void GroundStateRuntime::prepareInput(StateEntryActor& a,const PermissionActor& opponent,
        const ActorCommandInput& input,CallbackContext& objects,int32_t distance) const {
    if(!playableFighter(a.character)||!playableFighter(opponent.character)||unsupportedForm(a))
        throw std::runtime_error("Ground input phases require a supported ordinary fighter");
    a.flags244=ordinaryStateGates(a.flags244,a.flags23c,a.stateTable(),a.stateIndex(),
        a.effectiveFlags(),a.bodyFlags108,a.timers[5],ordinary_.far(distance,a.flags23c&0x1000,opponent.flags23c&0x1000,a.character,opponent.character));
    // 151b00 table-1 branch: Rasetsu Galford with the replica out (244:2000).
    if(a.character==41&&a.stateTable()==1&&(a.flags244&0x2000))a.flags244=((a.flags244|1)&~2u&~4u)&~8u;
    // 151c24: the weaponless fighters 43..47 (169388) are re-armed on every visit.
    if(a.character>=43&&a.character<=47)a.flags23c|=0x1000;
    //151b00 also transfers the one-visit248:04000000 flag and clears24c:4.
    //The opponent41 forced-direction branch is excluded by the resource check.
    a.flags248=(a.flags248&0x04000000)?a.flags248|0x08000000:a.flags248&~0x08000000u;
    a.flags248&=~0x04000000u;a.flags24c&=uint8_t(~4u);
    ActorTimers timers{a.timerDelta,a.timers};
    if(timers.advanceActor({a.state194,a.stateTable(),bool(a.flags23c&0x10),
            bool(input.sampledFeatures[0xd8/4]),bool(input.sampledFeatures[0x100/4])}))objects.releaseAttackGates();
    a.timers=timers.values;
}
void GroundStateRuntime::enterStateNow(PlayerObject& o,StateEntryActor& a,ActorCommandInput& input,const InputSystemConfig& config,
                                       StateEntryContext& context,unsigned player,uint32_t& opponentFlagsB8) const {
    const unsigned saved=context.player;const auto flags=context.opponentFlagsB8;
    context.player=player;context.opponentFlagsB8=opponentFlagsB8;
    captureBody(o,a);entries_.transition(a,input,config,context);restoreBody(o,a);
    opponentFlagsB8=context.opponentFlagsB8;context.player=saved;context.opponentFlagsB8=flags;
}
void GroundStateRuntime::seizeOpponent(StateEntryActor& a,StateEntryContext& context,const GroundStateFrame& frame) const {
    if(!frame.weaponLock||!frame.opponentInput)throw std::runtime_error("Seizing the opponent requires its live controls");
    auto& world=*frame.weaponLock;auto& victim=world.opponent;
    victim.pendingCharacter254=uint8_t(a.character);victim.bodyField124=0;
    victim.pendingTable=2;victim.pendingIndex=96;victim.request18c=1;
    // 1491e0 runs immediately on the other seat. The victim registers its
    // callback on its own actor turn, even if it ran first.
    const unsigned player=context.player;const auto flags=context.opponentFlagsB8;
    context.player=1-player;context.opponentFlagsB8=a.flagsB8;
    InputSystemConfig opponent{frame.opponentSystem,victim.character,{}};
    captureBody(world.opponentBody,victim);
    entries_.transition(victim,*frame.opponentInput,opponent,context);restoreBody(world.opponentBody,victim);
    a.flagsB8=context.opponentFlagsB8;context.player=player;context.opponentFlagsB8=flags;
}
void GroundStateRuntime::captureBody(const PlayerObject& o,StateEntryActor& a) {
    const auto c=o.timeline.clock();const auto m=o.timeline.motion();
    a.bodyFlags38=c.objectFlags;a.bodyFlags104=c.flags104;a.bodyFlags108=c.flags108;
    a.bodyPendingFE=o.pendingFlags;a.bodyAction24=int(o.timeline.action().id());
    a.bodyColor8c=o.color8c;a.bodyField20=o.field20;
    a.x=m.x;a.y=m.y;a.offsetX4c=m.dx;a.velocityX50=m.vx;a.accelerationX54=m.ax;
    a.offsetY58=m.dy;a.velocityY5c=m.vy;a.accelerationY60=m.ay;
}
void GroundStateRuntime::afterContacts(PlayerObject& o,StateEntryActor& a,ActorCommandInput& input,
        const InputSystemConfig& config,StateEntryContext& context) const {
    captureBody(o,a);entries_.transition(a,input,config,context);restoreBody(o,a);
    if(a.stateTable()!=3&&a.timers[0]>0) {
        const auto c=o.timeline.clock();
        //1522d0 preserves word1: the shake counter continues across visits.
        a.override27c[0]=0x143108;a.override27c[2]=c.flags104;a.override27c[3]=c.flags108;
        o.setFlags(c.flags104|0x30,c.flags108);o.pendingFlags|=6;a.flags23c|=0x100;
    }
    captureBody(o,a);
}
void GroundStateRuntime::contactPause(PlayerObject& o,StateEntryActor& a) {
    if(a.override27c[0]!=0x143108)throw std::runtime_error("Unknown temporary actor callback");
    //168ab8 ->168b68.143108 itself is empty; the type3 prefix and tail
    //own shaking, clock gates and the final restore on timer0 expiry.
    a.bodyFieldE4=0;
    if((a.stateTable()==2||(a.flags23c&0x04000000))&&a.timers[0]>0) {
        const auto old=a.override27c[1];a.override27c[1]=old+1;
        const int32_t phase=std::bit_cast<int32_t>(old+2)/2;
        a.bodyFieldE4=(uint32_t(phase)&1)?uint32_t(-2):2;
    }
    const auto c=o.timeline.clock();o.setFlags(c.flags104|0x2000,c.flags108);
    if(a.timers[0]<=0) {
        o.setFlags(a.override27c[2]&~0x30u,a.override27c[3]);o.pendingFlags&=uint16_t(~6u);
        a.override27c[0]=0;a.bodyFieldE4=a.bodyFieldE8=0;a.flags23c&=~0x04000100u;
    }
}
unsigned GroundStateRuntime::beforeCallbacks(PlayerObject& o,StateEntryActor& a) {
    if(unsupportedForm(a))throw std::runtime_error("Recovery guard requires ordinary actor state");
    unsigned diagnostics=0;
    ActorTimers timers{a.timerDelta,a.timers};
    const int32_t old=timers.increase(15);
    const auto requestKo=[&] {a.pendingTable=2;a.pendingIndex=31;a.request18c=1;++diagnostics;};
    if(old>0x257ff) {
        //The watchdog compares RAW194 against these five states, not the
        //pending request. It resets the timer even for a living ground actor.
        const uint32_t state=a.state194;
        const bool protectedState=state==0x000f0002||state==0x001e0002||state==0x001f0002||
                                  state==0x00100002||state==0x003d0002;
        if(a.flags23c&0x80) {if(!protectedState)requestKo();}
        else if(a.flags23c&0x10) {
            ++diagnostics;o.timeline.setPosition(o.timeline.motion().x,0);a.y=0;
            a.pendingTable=0;a.pendingIndex=0; //14ff80 leaves18c unchanged.
        }
        timers.clear(15);
    }
    //This remains a second check: a timed-out dead normal/attack actor
    //emits both diagnostics and queues31 twice, without committing it here.
    if((a.flags23c&0x80)&&(a.stateTable()==0||a.stateTable()==1))requestKo();
    a.timers=timers.values;return diagnostics;
}
void GroundStateRuntime::restoreBody(PlayerObject& o,const StateEntryActor& a) {
    o.timeline.setObjectFlags(a.bodyFlags38,a.bodyFlags104,a.bodyFlags108);o.pendingFlags=a.bodyPendingFE;
    o.color8c=a.bodyColor8c;o.field20=a.bodyField20;
    o.timeline.setMotion({a.offsetX4c,a.velocityX50,a.accelerationX54,a.offsetY58,a.velocityY5c,a.accelerationY60,a.x,a.y});
}
void GroundStateRuntime::begin(PlayerObject& o,StateEntryActor& a,const InputSystemConfig& config,StateEntryContext& context,const GroundStateFrame& frame) {
    const int state=a.stateIndex();const bool armed=a.flags23c&0x1000;
    a.callbacks260[0]=0; //1743c0 clears its entry handler, even for idle/walk.
    if(state>=32&&state<=34) {
        if(a.character==1)beginNakoruruDismount(a);
        else {
            // 173c78(cb, dir): the falling clip resumes directly and preserves the
            // current height. Several fighters fall through their own clips,
            // which carry the descent motion (Suija's hover ends in 0x216..0x218).
            const int dir=state-32;a.jumpDirectionA44=dir;
            auto pair=[&](int d0,int d1,int d2){a.queuedActionA3c=(dir==1?d1:dir==2?d2:d0)+!armed;a.flags248&=~0x800u;};
            uint32_t handler=0x173b18;
            switch(a.character) {
            case 0x13:pair(0x2cd,0x2cf,0x2d1);break;
            case 0x15:a.queuedActionA3c=dir==1?0x217:dir==2?0x218:0x216;a.flags248&=~0x800u;break; // 1493c0, not a pair
            case 8:pair(0x242,0x240,0x244);break;
            case 0x20:break; // the current clip continues
            case 0x1f:handler=0x173a68;break; // the ascending callback, current clip
            case 0x2d:pair(0x246,0x247,0x248);break;
            default:
                if(a.character==0x17&&(a.flags244&0x100000)){a.flags244&=~0x100000u;pair(0x250,0x252,0x254);break;}
                if(a.character==0x23&&dir==1){pair(0x23c,0x23c,0x23c);break;}
                // 4e9888: 16, 20, 24 by direction.
                a.queuedActionA3c=16+4*dir+!armed;a.flags248&=~0x800u;
            }
            a.callbacks260[0]=handler;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        }
        return;
    }
    if(state>=17&&state<=22){beginJump(o,a);return;}
    if(state==8||state==16||state==38){beginAirGuard(o,a);return;}
    if(state==23||state==24||state==36){beginDash(o,a,ordinary_.movementFlags(a.character));return;}
    if(state==54||state==55){beginRecoveryRoll(o,a);return;}
    if(state==37){beginGroundThrow(o,a,context,frame);return;}
    if(state==49||state==50){beginWeaponHandling(a);return;}
    if(state==51){beginWeaponPickup(o,a,context.tasks,frame.weaponLock->objectTasks,frame.opponentX);return;}
    if(state==31){weaponLockCallback(o,a,context,frame,true);return;}
    if(state==39||(state>=41&&state<=43)){endingCallback(o,a,context,frame,true);return;}
    unsigned action=0;
    switch(state) {
    case 0:stopAtGround(o);captureBody(o,a);action=standingIdleAction(a.fieldA30,a.rageState120,armed,frame.remainingSeconds,frame.training,frame.trainingRage);break;
    case 1:action=4+!armed;break;
    case 2:action=10+!armed;break;
    case 3:action=12+!armed;break;
    case 4:case 5:
        a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
        action=(state==4?44:46)+!armed;break;
    case 6:case 7:a.controlCounterC0=2;action=(state==6?286:290)+!armed;break;
    case 9:case 10:action=(state==9?6:8)+!armed;break;
    case 15:action=0x22a+!armed;break; // 1745b0 (Rera landing on her wolf): 169a50 mode 1
    case 11:case 13:a.controlCounterC0=1;action=(state==11?278:282)+!armed;break;
    case 12:case 14:a.controlCounterC0=4;action=(state==12?280:284)+!armed;break;
    case 25:case 26:case 27:case 28:case 29:case 30: {
        a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
        stopAtGround(o);captureBody(o,a);
        const int strength=(state-25)%3;
        // 169c28 gives the Ten chain opener its own recoil even on a clash.
        // For a blocked slash it reads the near/far variant at recoil entry.
        const int variant=(a.flags23c&0x200000)?a.aliasCharacter1a8:a.stateCharacter198;
        if(a.flags23c&0x40000)action=307;
        else if(a.flags23c&0x20000)action=141+strength;
        else action=(variant<2?294:300)+(state>=28?3:0)+strength;
        a.flags248&=~0x800u;
        break;
    }
    case 35:action=74+!armed;break;
    case 40:action=318+!armed;break;
    case 44:action=312+!armed;break;
    case 45:action=72+!armed;break;
    case 46:
        a.queuedActionA3c=156+!armed;a.flags248&=~0x800u;
        a.callbacks260[0]=0x16a298;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        return;
    case 47: {
        a.queuedActionA3c=314+!armed;a.flags248&=~0x800u;
        a.callbacks260[0]=0x173500;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        ActorTimers timers{a.timerDelta,a.timers};timers.set(10,10);a.timers=timers.values;
        DamageTables::spendKenGuard(a);
        return;
    }
    case 53: {
        // Success applies reaction row 8's retreat to the fighter but
        // remains in the normal-state table, allowing another perfect guard.
        auto motion=o.timeline.motion();auto flags=o.timeline.clock().flags108;
        reactions_.startRetreat(8,motion,flags,frame.opponentAuxiliary);
        o.timeline.setMotion(motion);o.setFlags(o.timeline.clock().flags104,flags);captureBody(o,a);
        a.flags23c|=0x04000000u;a.flags244|=0x02000000u;
        a.queuedActionA3c=316+!armed;a.flags248&=~0x800u;
        a.callbacks260[0]=0x170c20;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffff;
        return;
    }
    case 48:
        // The unarmed input falls through to Shin's ordinary E evasion.
        // The armed doll changes hurt boxes with its four body records.
        if(!armed)throw std::logic_error("Haohmaru doll requires his sword");
        action=164;
        if(a.characterBytesF22[2]<99)++a.characterBytesF22[2];
        break;
    case 62:
        a.queuedActionA3c=144+!armed;a.flags248&=~0x800u;
        a.callbacks260[0]=0x16a458;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        return;
    case 63:action=162+!armed;break; // 174b20, newly full Shin gauge.
    case 56:case 57:case 58:
        // The prone and rolling actions face the opponent before ACT applies
        // local velocity. The same clip therefore moves in opposite world
        // directions for the two starting sides.
        a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
        stopAtGround(o);captureBody(o,a);
        if((config.system==5||config.system==8)&&(state==56||state==58)) { // 14f9b8: systems 5 and 8
            action=(state==56?92:84)+!armed;
            a.flags248&=~0x800u;
            frame.spawnMikiri(action+2);
            if(state==58)a.flags23c&=~8u; // The neutral slide rises from the roll descriptor's crouch pose.
        } else action=60+2*(state-56)+!armed;
        break;
    case 59:case 60: {
        // The forward dive fixes facing at takeoff. Low evasion keeps the
        // current facing. Both release their held animation record on landing.
        if(state==59){a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);}
        const bool lowSlide=state==60&&(config.system==5||config.system==8);
        if(lowSlide)frame.spawnMikiri(102+!armed);
        stopAtGround(o);captureBody(o,a);
        a.queuedActionA3c=(lowSlide?100:state==59?68:66)+!armed;a.flags248&=~0x800u;
        a.callbacks260[0]=(state==59?0x174030:0x174100);a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        return;
    }
    case 52:
        a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
        o.pendingFlags|=1;action=493+!armed;break;
    default:throw std::runtime_error("Unimplemented ordinary ground entry");
    }
    a.queuedActionA3c=int(action); //1493c0 queues actorA3c, not bodyC4 yet.
    if(state>=4) {
        a.callbacks260[0]=0x169a50;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
        a.callbacks260[5]=(state==6||state==7||state==52)?4:(state==11||state==13)?2:state==15?1:0;
    }
}
void GroundStateRuntime::recoverStanding(PlayerObject& o,StateEntryActor& a,float opponentX) {
    GroundStateFrame frame;frame.opponentX=opponentX;recover(o,a,frame);
}
void GroundStateRuntime::recover(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& frame) {
    const auto c=o.timeline.clock();const float x=o.timeline.motion().x;
    // The turn check is suppressed by 169894 on the wraparound step.
    // A cross switches sides before the follow-up normal selector refaces.
    const bool turn=a.state194!=0x230000&&((x<frame.opponentX&&(c.objectFlags&0x80000))||(x>frame.opponentX&&!(c.objectFlags&0x80000)));
    if(a.stateTable()==0&&(a.stateIndex()==54||a.stateIndex()==55))a.flagsB8|=0x20;
    stopAtGround(o);captureBody(o,a);
    // 169810 returns prone/forward roll/back roll to standing or turning
    // even while their outgoing posture descriptor still says crouch.
    const bool rollOrProne=a.stateTable()==0&&a.stateIndex()>=56&&a.stateIndex()<=58;
    a.pendingTable=0;a.pendingIndex=int16_t(((a.flags23c&8)&&!rollOrProne?1:0)+(turn?4:0));
}
void GroundStateRuntime::recoverGuard(PlayerObject& o,StateEntryActor& a) {
    a.controlCounterC0=2;
    if(!(a.flags23c&0x10)){stopAtGround(o);captureBody(o,a);}
    a.pendingTable=0;a.pendingIndex=(a.flags23c&0x10)?8:(a.flags23c&8)?7:6; //169988
}
void GroundStateRuntime::beginDamage(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& input,
        const InputSystemConfig& config,StateEntryContext& context,const GroundStateFrame& frame) {
    int state=a.stateIndex();a.callbacks260[0]=0;
    if(a.flags23c&0x80) {
        if(a.effectiveFlags()&0x40)state=30;
        if(a.effectiveFlags()&0x80)state=31;
        //174fe0 commits only the raw request. Re-running full state entry
        //would incorrectly replace the saved hurt metadata/conditions here.
        a.pendingTable=2;a.pendingIndex=int16_t(state);a.request18c=1;
        commitStateRequest(a);a.request18c=0;
    }
    auto motion=o.timeline.motion();auto flags=o.timeline.clock().flags108;
    reactions_.startRetreat(unsigned(state),motion,flags,frame.opponentAuxiliary);
    o.timeline.setMotion(motion);o.setFlags(o.timeline.clock().flags104,flags);captureBody(o,a);
    if((state>=10&&state<=12)||state==14){beginDeflectedWeapon(o,a,frame);return;}
    if(state==13){beginThrowVictim(o,a,frame.weaponLock->opponentBody);return;}
    if(state==61) {
        stopAtGround(o);
        a.queuedActionA3c=int(reactions_.ordinaryAction(61,a.flags23c&0x1000,a.flags244&0x8000));
        a.flags248&=~0x800u;
        a.callbacks260[0]=0x1709d8;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(state==58){beginIssenVictim(o,a,frame);return;}
    if(state>=24&&state<=26) { // 172580(cb, k): launched 64 back, 48 up, ACT 0x1aa/0x1ab
        const unsigned k=unsigned(state-24);
        a.bodyState128=k; // body+128
        if(frame.battle)frame.battle->flags138|=4;
        a.flags244&=~0x20000u;
        a.flags244&=~0x10u; // 13a858 (byte 43d05e) is 0 under console VS
        auto m=o.timeline.motion();
        const ScalarFloat x{std::bit_cast<uint32_t>(m.x)},d=ScalarFloat::integer(64);
        m.x=std::bit_cast<float>(((o.timeline.clock().objectFlags&0x80000)?x.add(d):x.sub(d)).bits);
        m.y=48.0f;
        m.vx=int32_t(k==0?0xfffb0000u:k==1?0xfff80000u:0xfff50000u);m.ax=0;m.ay=-0x3d70;m.vy=0x80000;
        o.timeline.setMotion(m);o.pendingFlags|=8;
        a.queuedActionA3c=0x1aa+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x1726b0;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(state==22) { // 172408: ACT 0x1ac/0x1ad, landing as state 20
        a.queuedActionA3c=0x1ac+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x172288;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(state==23) { // 172458: ACT 0x186/0x187 until a wall, then state 21's 0x1aa
        if(frame.battle)frame.battle->flags138|=4;
        a.queuedActionA3c=0x186+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x1724c8;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        a.flags244&=~0x20000u;
        return;
    }
    if(state==21) { // 1722e0: blown back toward a wall, ACT 0x1aa/0x1ab
        if(frame.battle)frame.battle->flags138|=4; // 140630(2)
        a.flags244&=~0x20000u;
        a.queuedActionA3c=0x1aa+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x172350;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(state==20) { // 172238: thrown into the air (Enja's flame), ACT 0x1a8/0x1a9
        a.queuedActionA3c=0x1a8+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x172288;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(state==74||state==75){beginAirHurt(o,a);return;}
    if(state==6){beginAirBlockReaction(o,a);return;}
    if(state==15) {
        a.flags23c|=0x80;endingCallback(o,a,context,frame,true);return;
    } else if(state==30||state==31) {
        knockoutCallback(o,a,frame,true);return;
    } else if(state==7||state==16||KnockdownPlayback::supportsFall(state)) {
        downedCallback(o,a,input,config,context,frame,true);return;
    } else if(state<6) {
        a.controlCounterC0=3;a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
        a.queuedActionA3c=(state<3?288:292)+!(a.flags23c&0x1000);
        a.callbacks260[0]=0x170640;
    } else {
        if(frame.opponentFlags23c&0x20)a.timers[6]=3*256;
        a.queuedActionA3c=int(reactions_.ordinaryAction(unsigned(state),a.flags23c&0x1000));
        a.callbacks260[0]=0x170890;
        // From state 50 onward, each reaction has one fixed ACT row (bomb
        // recoil uses rows 8 and 9), instead of three strengths per row.
        a.callbacks260[3]=state>=50?0:unsigned(state-32)%3;
        a.callbacks260[6]=state>=50?unsigned(state-50)+6:unsigned(state-32)/3;
    }
    a.callbacks260[1]=2;a.callbacks260[2]=0xffffffff;
}
DownedEvents GroundStateRuntime::downedCallback(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& input,
        const InputSystemConfig& config,StateEntryContext& context,const GroundStateFrame& frame,bool entering) {
    //The actor's callback words are authoritative. Reconstruct the playback
    //view each visit so a new hurt/KO cannot leave a second, stale downed phase.
    DownedState down;
    down.flags23c=a.flags23c;down.flags244=a.flags244;down.flags248=a.flags248;down.flags24c=a.flags24c;
    down.flagsB8=a.flagsB8;down.opponentFlagsB8=context.opponentFlagsB8;
    down.landingCount253=a.landingCount253;down.recoveryA4c=a.recoveryA4c;
    down.table=a.stateTable();down.index=a.stateIndex();
    ActorTimers timers{a.timerDelta,a.timers};KnockdownPlayback playback;DownedEvents events;
    if(entering) {
        if(KnockdownPlayback::supportsFall(down.index)) {
            if(down.index==70&&a.fieldA30>0&&!(a.flags23c&0x80)&&frame.sound)
                frame.sound->act(155,context.player,voiceCharacter(a),a.flags23c,3,0,*frame.random);
            if(KnockdownPlayback::fallType(down.index)==3)frame.battle->flags138|=4;
            playback.beginHeavy(o,down,timers,&a.queuedActionA3c);a.callbacks260[6]=KnockdownPlayback::fallVariant(down.index);
        } else if(down.index==16)playback.beginDown(o,down,&a.queuedActionA3c);
        else playback.beginRise();
    } else {
        switch(a.callbacks260[0]) {
        case 0x171b98:playback.phase=DownedPhase::WallApproach;break;
        case 0x171eb0:case 0x171c80:case 0x1715b0:case 0x1717a0:case 0x1719a8:playback.phase=DownedPhase::FirstLanding;break;
        case 0x171f58:case 0x171d60:case 0x171640:case 0x171838:case 0x171a38:playback.phase=DownedPhase::SecondLanding;break;
        case 0x169a50:
            if(a.callbacks260[5]!=5&&a.callbacks260[5]!=6)throw std::runtime_error("Unsupported downed finish mode");
            playback.phase=DownedPhase::Finish;break;
        case 0x170cd8:playback.phase=DownedPhase::DownWait;break;
        case 0x170de8:playback.phase=DownedPhase::StayDown;break; // system 8 (and custom 6) hold-down
        case 0x170ef8:playback.phase=DownedPhase::RiseDelay;break;
        case 0x1706c0:playback.phase=DownedPhase::RiseQueued;break;
        case 0x170758:playback.phase=DownedPhase::Rising;break;
        default:throw std::runtime_error("Unsupported downed callback");
        }
        DownedInput controls;controls.system=config;controls.character=a.character;
        controls.controlKind=a.controlKindA20;controls.opponentX=frame.opponentX;
        // 1720b0 reads the published features for either control type. A CPU
        // recovery uses its command from this actor visit, including BACK.
        controls.pressRecovery=input.sampledFeatures[0x28/4];
        controls.back100=input.sampledFeatures[0x100/4];controls.down=input.sampledFeatures[0xfc/4];
        const auto previous=playback.phase;
        if(previous==DownedPhase::WallApproach) {
            frame.battle->flags138|=4;
            controls.wallBounds={{frame.battle->camera.left,frame.battle->camera.right}};
        }
        events=playback.update(o,down,timers,controls,*frame.random,&a.queuedActionA3c);
        if(KnockdownPlayback::fallType(down.index)==3) {
            bool impact=false;
            if(previous==DownedPhase::WallApproach&&playback.phase==DownedPhase::FirstLanding) {
                a.bodyState128=0;
                // 171c20 replaces the previous camera script on wall contact.
                frame.battle->camera.commands.clear();
                frame.battle->camera.appendCommand(3,20);
                impact=true;
            } else if(previous==DownedPhase::FirstLanding&&playback.phase==DownedPhase::SecondLanding) {
                impact=true;
            } else if(previous==DownedPhase::SecondLanding&&playback.phase==DownedPhase::Finish) {
                impact=true;
            }
            if(impact&&frame.sound)frame.sound->act(31,context.player,voiceCharacter(a),a.flags23c,3,0,*frame.random);
            if(previous==DownedPhase::FirstLanding&&!events.dust&&o.timeline.clock().step==2&&!a.bodyState128) {
                a.bodyState128=1;
                if(frame.sound&&a.fieldA30>0&&!(a.flags23c&0x80))
                    frame.sound->act(155,context.player,voiceCharacter(a),a.flags23c,3,0,*frame.random);
            }
        }
        if(down.index==70&&frame.sound&&((previous==DownedPhase::FirstLanding&&playback.phase==DownedPhase::SecondLanding)||
            (previous==DownedPhase::SecondLanding&&playback.phase==DownedPhase::Finish)))
            frame.sound->act(31,context.player,voiceCharacter(a),a.flags23c,3,0,*frame.random);
    }
    uint32_t handler=0;
    switch(playback.phase) {
    case DownedPhase::WallApproach:handler=0x171b98;break;
    case DownedPhase::FirstLanding:handler=KnockdownPlayback::landingCallbacks(down.index).first;break;
    case DownedPhase::SecondLanding:handler=KnockdownPlayback::landingCallbacks(down.index).second;break;
    case DownedPhase::Finish:handler=0x169a50;a.callbacks260[5]=KnockdownPlayback::landsOnBack(down.index)?6:5;break;
    case DownedPhase::DownWait:handler=0x170cd8;break;
    case DownedPhase::StayDown:handler=0x170de8;break;
    case DownedPhase::RiseDelay:handler=0x170ef8;break;
    case DownedPhase::RiseQueued:handler=0x1706c0;break;
    case DownedPhase::Rising:handler=0x170758;break;
    case DownedPhase::Holding:handler=0x169a50;a.callbacks260[5]=7;break;
    default:throw std::runtime_error("Downed continuation outside ordinary system0");
    }
    a.callbacks260[0]=handler;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffff;
    a.flags23c=down.flags23c;a.flags244=down.flags244;a.flags248=down.flags248;a.flags24c=down.flags24c;
    a.flagsB8=down.flagsB8;context.opponentFlagsB8=down.opponentFlagsB8;
    a.landingCount253=down.landingCount253;a.recoveryA4c=down.recoveryA4c;a.timers=timers.values;
    if(down.pendingTable!=-1){a.pendingTable=int16_t(down.pendingTable);a.pendingIndex=int16_t(down.pendingIndex);}
    if(down.forceState)a.request18c=1;
    if(events.dust)frame.effects->landing(o.timeline.motion().x,o.timeline.clock().objectFlags&0x80000);
    // 14a8d0(-10): the system-8 delayed rise heals through the pending-damage queue (game-mode,
    // time-out (140788) and opponent-KO gates as in queueLifeChange).
    if(events.lifeAdjustment) {
        if(!frame.battle)throw std::runtime_error("The delayed-rise heal needs the battle");
        frame.battle->queueLifeChange(a,frame.opponentFlags23c,events.lifeAdjustment);
    }
    return events;
}
DownedEvents GroundStateRuntime::knockoutCallback(PlayerObject& o,StateEntryActor& a,
        const GroundStateFrame& frame,bool entering) {
    KnockoutPlayback playback;DownedEvents events;
    if(entering)playback.begin(o,a.flags23c,a.stateIndex()==31?2:bool(a.flags244&0x8000),&a.queuedActionA3c);
    else {
        switch(a.callbacks260[0]) {
        case 0x172be8:playback.phase=KnockoutPhase::FirstLanding;break;
        case 0x172c50:playback.phase=KnockoutPhase::SecondLanding;break;
        case 0x172cb0:playback.phase=KnockoutPhase::Finishing;break;
        default:throw std::runtime_error("Unsupported KO continuation");
        }
        events.dust=playback.update(o);
    }
    uint32_t handler=0;
    switch(playback.phase) {
    case KnockoutPhase::FirstLanding:handler=0x172be8;break;
    case KnockoutPhase::SecondLanding:handler=0x172c50;break;
    case KnockoutPhase::Finishing:handler=0x172cb0;break;
    case KnockoutPhase::Complete:handler=0x169a50;a.callbacks260[5]=7;break;
    default:throw std::runtime_error("Unsupported KO phase");
    }
    a.callbacks260[0]=handler;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffff;
    if(events.dust)frame.effects->landing(o.timeline.motion().x,o.timeline.clock().objectFlags&0x80000);
    return events;
}
void GroundStateRuntime::beginAttack(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& frame) {
    const int state=a.stateIndex();
    if(isJumpAttack(state)&&state==16&&a.character==32&&o.timeline.motion().y>0) {
        // 16aec8 -> 200c50: the puppet joins the air kick (aux 7), ACT 0xd9/0xda, then 173880.
        if(!a.auxiliaryObject04||!frame.pools)throw std::runtime_error("200c50 commands the puppet");
        frame.pools->objects.at(a.auxiliaryObject04-1)[0x128/4]=7;
        a.flags244|=0x400;
        a.queuedActionA3c=0xd9+!(a.flags23c&0x1000);a.flags248&=~0x800u;
        a.callbacks260[0]=0x200cc0;a.callbacks260[1]=1;a.callbacks260[2]=0xffffffffu;
        return;
    }
    if(isJumpAttack(state)){beginJumpAttack(o,a);launchPakuPaku(a,frame);return;}
    const bool armed=a.flags23c&0x1000;
    if(state==22) {
        // 4e5420 bits 2 (armed) and 3 (unarmed) both enable the aerial
        // command normal for Rimururu. It keeps its ACT across touchdown.
        const bool aerial=ordinary_.movementFlags(a.character)&(armed?4:8);
        a.opponentX=frame.opponentX;
        a.faceOpponent();
        restoreBody(o,a);
        stopAtGround(o);
        captureBody(o,a);
        a.queuedActionA3c=armed?239:240;
        a.flags248&=~0x800u;
        StateEntryRules::pose(a,aerial?7:3);
        restoreBody(o,a);
        a.callbacks260[0]=aerial?0x16b2b8:0x16b318;
        a.callbacks260[1]=1;
        a.callbacks260[2]=0xffffffff;
        return;
    }
    const bool runningAttack=state>=17;
    // 16ad88 keeps the current facing for a running attack carrying the
    // 00800000 flag. Ordinary standing and crouching attacks face the opponent.
    if(!runningAttack||!(a.flags23c&0x00800000)) {
        a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
    }
    unsigned parameter=0;
    if(runningAttack) {
        constexpr unsigned parameters[]={1,3,5,0};
        parameter=parameters[state-17];
        a.queuedActionA3c=armed?219+state-17:223+(state==20);
    } else if(state>=12) {
        a.queuedActionA3c=(armed?197:205)+state-12;
    } else {
        const int strength=state/4;
        parameter=1+2*strength;
        // The near/far flag was computed before input and before turning.
        a.queuedActionA3c=armed?((state&1)?191:185)+2*strength+bool(a.flags244&0x4000):
            ((state&1)?203:201)+bool(strength);
    }
    a.flags248&=~0x800u;
    a.callbacks260[0]=0x16ae60;a.callbacks260[1]=1;a.callbacks260[2]=0xffffffff;
    a.callbacks260[4]=armed?parameter:0;
    //16f948 (PakuPaku only) launches its 0xa8 object; 16b1e8 is an empty function.
    launchPakuPaku(a,frame);
}
// 16f948: tail of the attack entries 16ad88 / 16afcc / 16b288. Only PakuPaku (47) in attack
// states < 64 launches its first own kind-6 object of descriptor 0xa8 as a kind-2 projectile
// with the velocities of the 0x4e8808 row (each float * 65536.0, truncated).
void launchPakuPaku(const StateEntryActor& a,const GroundStateFrame& frame) {
    if(a.character!=47||a.stateTable()!=1||a.stateIndex()>=64)return;
    static constexpr uint32_t rows[][4]{
        {0x3fcccccdu,0x0u,0x0u,0x0u},
        {0x3fe66666u,0x0u,0x404ccccdu,0xbda3d70au},
        {0x3f99999au,0xbc23d70au,0x3f99999au,0xbe4ccccdu},
        {0x3fcccccdu,0x3ca3d70au,0x3f99999au,0xbe4ccccdu},
        {0x4019999au,0x0u,0x0u,0x0u},
        {0x402ccccdu,0x0u,0x4099999au,0xbdf5c28fu},
        {0x4019999au,0xbd23d70au,0xc019999au,0x3ca3d70au},
        {0x3fe66666u,0x3ca3d70au,0xc019999au,0x3ca3d70au},
        {0x404ccccdu,0x0u,0x0u,0x0u},
        {0x40666666u,0x0u,0x40cccccdu,0xbe75c28fu},
        {0x4099999au,0xbd23d70au,0xc04ccccdu,0x0u},
        {0x4099999au,0x0u,0xc04ccccdu,0xbdcccccdu},
        {0x3fcccccdu,0x0u,0x3fcccccdu,0x0u},
        {0x40b33333u,0xbd75c28fu,0x404ccccdu,0xbdcccccdu},
        {0x3f800000u,0x3d4ccccdu,0x0u,0x3dcccccdu},
        {0xbf4ccccdu,0x3dcccccdu,0x0u,0x3ca3d70au},
        {0xbf19999au,0x3e4ccccdu,0xbe4ccccdu,0xbdcccccdu},
        {0xbf19999au,0x3e4ccccdu,0x0u,0x3d23d70au},
        {0xbf99999au,0x3ecccccdu,0x3f99999au,0xbd23d70au},
        {0xbfe66666u,0x3f4ccccdu,0x0u,0x0u},
        {0x40800000u,0x3ecccccdu,0x3f4ccccdu,0x3da3d70au},
        {0x0u,0x0u,0x0u,0x0u},
        {0x40000000u,0xbca3d70au,0x41000000u,0xbe8f5c29u}
    };
    const int idx=a.stateIndex();
    if(idx<0||idx>=int(std::size(rows)))return; // rows 23..63 are all zero
    const auto& row=rows[idx];
    if(!(row[0]&0x7fffffffu)&&!(row[1]&0x7fffffffu)&&!(row[2]&0x7fffffffu))return;
    if(!frame.pools||!frame.weaponLock)throw std::runtime_error("16f948 scans the own registry");
    for(auto task:frame.ownObjectTasks) {
        if(!task)continue;
        auto& o=frame.pools->objects.at(frame.pools->tasks.at(task-1)[7]-1);
        if(o[0xcc/4]!=6||o[0xd0/4]!=0xa8)continue;
        o[0xcc/4]=2;frame.pools->tasks.at(task-1)[0]=0x16def0;
        frame.weaponLock->objects.request(o,0x250,false,false);
        o[0x38/4]=(o[0x38/4]&~0x80000u)|(a.bodyFlags38&0x80000u); //11dbb8
        const auto v=[&](unsigned k){return uint32_t(ScalarFloat{row[k]}.mul(ScalarFloat{0x47800000u}).truncate());};
        o[0x50/4]=v(0);o[0x54/4]=v(1);o[0x5c/4]=v(2);o[0xfc/4]|=8u<<16;o[0x60/4]=v(3);
        return;
    }
}
// 20a9a0 "TAKE LOSER": a referee object (Kuroko's kind 6, ACT 0x20a) enters 80 beyond the camera edge
// on the loser's side; native_match drives its tasks 20aac0..20ad70 and the carried body 20ad78.
void GroundStateRuntime::takeLoser(PlayerObject& o,StateEntryActor& a,StateEntryContext& context,const GroundStateFrame& frame) {
    if(!frame.weaponLock||!frame.pools)throw std::runtime_error("20a9a0 needs the opponent and pools");
    auto& w=*frame.weaponLock;
    if(!(w.opponent.flags23c&0x80))return; // only a KO'd loser
    const auto h=w.objects.create(*frame.pools,frame.ownObjectTasks,context.player,a.flags23c,o.childParentWords(),0x1396,6,0);
    if(!h)throw std::runtime_error("Original 16c408 writes through a null object");
    auto& r=frame.pools->objects.at(h-1);
    w.objects.request(r,0x20a,false,true);r[0x108/4]|=0x2000;
    using F=ScalarFloat;
    if(F{std::bit_cast<uint32_t>(w.opponentBody.timeline.motion().x)}.less(F{r[0x40/4]})) {
        r[0x38/4]|=0x80000;r[0x40/4]=F::integer(w.camera.right).add(F::integer(80)).bits;
    } else {
        r[0x38/4]&=~0x80000u;r[0x40/4]=F::integer(w.camera.left).sub(F::integer(80)).bits;
    }
    frame.pools->tasks.at(r[1]-1)[0]=0x20aac0;r[0x108/4]&=~0x2000u;
}
void GroundStateRuntime::endingCallback(PlayerObject& o,StateEntryActor& a,StateEntryContext& context,
        const GroundStateFrame& frame,bool entering) {
    EndingPlayback playback;
    auto* companion=a.auxiliaryObject04?&context.tasks.objects.at(a.auxiliaryObject04-1):nullptr;
    if(entering) {
        if(companion&&(a.stateTable()==2||a.stateIndex()!=39)) {
            // All four dispatchers clear readiness before their character switch.
            // Konru keeps hovering; only Mamahaha receives a new command.
            (*companion)[0x108/4]&=~0x100000u;
            if(a.character==1||a.character==45)(*companion)[0x128/4]=a.stateTable()==2?11u:a.stateIndex()==41?9u:a.stateIndex()==42?10u:12u;
        }
        // 14e000 tests 1fde18 before its tail 1a3400 commands Chample state 34.
        const bool champleBusy=a.character==24&&companion&&!champleAvailable(*companion);
        // 1a3400 (win 34), 1a34c0 (draw 35), 1a3580 (loss 36), 1a3640 (surviving loser 37).
        if(a.character==24&&companion&&(a.stateTable()==2||a.stateIndex()!=39))
            commandChamplePresentation(*companion,a.stateTable()==2?36u:a.stateIndex()==41?34u:a.stateIndex()==42?35u:37u);
        // Poppy: 1a3400 win 0x2f, 1a34c0 draw 0x30, 1a3580 loss 0x31, 1a3640 surviving loser 0x32.
        if(a.character==4&&companion&&(a.stateTable()==2||a.stateIndex()!=39))
            commandPoppy(*companion,a.stateTable()==2?0x31u:a.stateIndex()==41?0x2fu:a.stateIndex()==42?0x30u:0x32u);
        // Chamcham's pet: win 0x14, draw 0x15, loss 0x16, surviving loser 0x17.
        if((a.character==34||a.character==19)&&companion&&(a.stateTable()==2||a.stateIndex()!=39))
            commandPoppy(*companion,a.stateTable()==2?0x16u:a.stateIndex()==41?0x14u:a.stateIndex()==42?0x15u:0x17u);
        if(a.stateTable()==2)playback.beginLoser(o,a.flags23c,a.flags244,&a.queuedActionA3c);
        else if(a.stateIndex()==39) {
            playback.beginIntroduction(o,a.flags244,context.player,&a.queuedActionA3c,
                selectedCharacter(a)==(frame.opponentSelected>=0?frame.opponentSelected:int(frame.opponentCharacter)));a.flags248|=0x1000;
        } else {
            a.opponentX=frame.opponentX;a.faceOpponent();restoreBody(o,a);
            if(a.stateIndex()==41&&champleBusy) {
                // Same non-forced 1494c0 request as the generic winner clips.
                a.queuedActionA3c=508+!(a.flags23c&0x1000);
                a.flags244&=~0x40000000u;playback.phase=EndingPhase::Playing;
            } else if(a.stateIndex()==41) {
                const bool final=frame.matchStats->complete();
                playback.beginWinner(o,a.flags23c,a.flags244,a.fieldA30,final,&a.queuedActionA3c);
                if(a.character==48&&final) {
                    // 14e000: Kuroko's full-life final pose 0x201 + 2 * GameRandom(4), then 20a9a0 before the queue.
                    if(a.fieldA30>=100) {
                        if(!frame.random)throw std::runtime_error("14e000 draws the game RNG");
                        a.queuedActionA3c=0x201+2*frame.random->bounded(4)+!(a.flags23c&0x1000);
                    }
                    takeLoser(o,a,context,frame);
                }
            }
            else {
                // A surviving loser and a draw each have a separate clip.
                // Both signal readiness through the same 14e320 callback.
                a.queuedActionA3c=(a.stateIndex()==42?503:505)+!(a.flags23c&0x1000);
                a.flags244&=~0x40000000u;
                playback.phase=EndingPhase::Playing;
            }
        }
    } else {
        //14e320 is authoritative; no persistent parallel EndingPhase may
        //survive a new hit or a round-controller state request.
        playback.phase=EndingPhase::Playing;ActorTimers timers{a.timerDelta,a.timers};
        playback.update(o,a.flags244,&timers,context.player,&a.queuedActionA3c,(a.character!=1&&a.character!=4&&a.character!=19&&a.character!=24&&a.character!=34&&a.character!=45)||!companion||((*companion)[0x108/4]&0x100000));a.timers=timers.values;
        //Only timer34's expiry queues a clip here;1493c0 explicitly forces492.
        if(a.queuedActionA3c!=-1)a.flags248|=0x1000;
    }
    a.callbacks260[0]=playback.phase==EndingPhase::Holding?0x169a50:0x14e320;
    // 14e000 holds Mina's ordinary win clips in 14e470 until Chample is ready.
    const int win=a.queuedActionA3c;
    if(entering&&a.character==24&&a.stateTable()==0&&a.stateIndex()==41&&(win==495||win==496||win==499||win==501))
        a.callbacks260[0]=0x14e470;
    a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
    if(playback.phase==EndingPhase::Holding)a.callbacks260[5]=4;
}
void GroundStateRuntime::minaWinnerHold(PlayerObject& o,StateEntryActor& a,StateEntryContext& context) {
    // 14e470: wait for 1a3930 readiness, then for 1699f8 on the clip.
    auto& companion=context.tasks.objects.at(a.auxiliaryObject04-1);
    if(!(companion[0x108/4]&0x100000))return;
    const auto c=o.timeline.clock();
    const bool done=actionEnded(o,a.queuedActionA3c)||(c.flags104&0x100);
    o.setFlags(c.flags104&~0x100u,c.flags108);
    if(!done)return;
    const auto act=o.timeline.action().id();
    if(act==499||act==501)companion[0x104/4]|=2;
    a.callbacks260[0]=0x14e320;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
}
void GroundStateRuntime::weaponLockCallback(PlayerObject& o,StateEntryActor& a,StateEntryContext& entry,
        const GroundStateFrame& frame,bool entering) {
    auto& lock=*frame.weaponLock;
    const auto registerNext=[&](uint32_t handler) {
        //1522a0 changes only the first three words; continuation arguments
        //survive registration unless the original callback clears them.
        a.callbacks260[0]=handler;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
    };
    const auto request=[&](int action){a.queuedActionA3c=action;a.flags248&=~0x800u;};
    if(entering) {
        a.weaponLockPhaseA54=0;
        a.opponentX=lock.opponentBody.timeline.motion().x;a.faceOpponent();restoreBody(o,a);
        stopAtGround(o);captureBody(o,a);request(137);o.pendingFlags|=1;
        registerNext(0x1523e8);return;
    }
    switch(a.callbacks260[0]) {
    case 0x1523e8:
        //Do not recompute from the bodies:147f08 reads the cached stage
        //distance even if an earlier actor callback already moved a body.
        if(lock.cachedDistance<49)registerNext(0x152440);
        break;
    case 0x152440: {
        StateEntryRules::pose(a,21);restoreBody(o,a);
        a.weaponLockPhaseA54=1;a.timers[13]=0;
        captureBody(lock.opponentBody,lock.opponent);
        const auto stageActor=[&](const StateEntryActor& actor) {
            return StageActor{actor.x,actor.y,actor.flags23c,actor.flags244,actor.bodyFlags38,actor.flags24c,
                int16_t(actor.stateTable()),int16_t(actor.stateIndex()),
                actor.stateTable()==2&&unsigned(actor.stateIndex())<80?uint8_t(reactions_.descriptor(actor.stateIndex()).flags):uint8_t(0)};
        };
        std::array<StageActor,2> actors{stageActor(a),stageActor(lock.opponent)};
        separateActorAnchors(actors,lock.camera,80);
        o.timeline.setPosition(actors[0].x,actors[0].y);
        lock.opponentBody.timeline.setPosition(actors[1].x,actors[1].y);
        captureBody(lock.opponentBody,lock.opponent);
        stopAtGround(o);captureBody(o,a);request(138);registerNext(0x1524e0);break;
    }
    case 0x1524e0: {
        ActorTimers timers{a.timerDelta,a.timers};timers.increase(13);a.timers=timers.values;
        if(a.weaponLockPhaseA54!=1)registerNext(a.weaponLockPhaseA54==2?0x152560:0x1525b8);
        break;
    }
    case 0x152560:request(139);registerNext(0x169a50);a.callbacks260[5]=0;break;
    case 0x1525b8:request(140);registerNext(0x152600);break;
    case 0x152600: {
        const auto c=o.timeline.clock();
        const bool ready=actionEnded(o,a.queuedActionA3c)||(c.flags104&0x100);
        o.setFlags(c.flags104&~0x100u,c.flags108);
        //1699f8 returns the OLD hold bit. This drops at140 record2 and
        //releases the remaining animation; waiting for clip end deadlocks.
        if(ready) {
            lock.objects.dropAfterLock(entry.tasks,lock.objectTasks,*frame.random,entry.player,
                a.character,a.flags23c,o.childParentWords());
            registerNext(0x169a50);a.callbacks260[5]=0;
        }
        break;
    }
    default:throw std::runtime_error("Unknown weapon-lock actor callback");
    }
}
void GroundStateRuntime::callback(PlayerObject& o,StateEntryActor& a,const GroundStateFrame& frame) {
    //169a50 calls1699f8 every visit, including a zero-duration hold.
    auto c=o.timeline.clock();
    if(actionEnded(o,a.queuedActionA3c)||(c.flags104&0x100))o.setFlags(c.flags104&~0x100u,c.flags108);
    if(!actionEnded(o,a.queuedActionA3c))return;
    const auto mode=a.callbacks260[5];
    if(mode==0) {recover(o,a,frame);a.request18c=1;}
    else if(mode==1) { // 169918: the crouch bit follows held down (feature 63), then 169810
        if(!frame.ownInput)throw std::runtime_error("169918 reads the actor's held down");
        if(frame.ownInput->sampledFeatures[63])a.flags23c|=8;else a.flags23c&=~8u;
        recover(o,a,frame);a.request18c=1;
    }
    else if(mode==2)recoverGuard(o,a);
    else if(mode==4) {
        //Corpse15 shares this hold with normal victory/guard states. Only
        //normal/attack tables may restart KO; otherwise the corpse rises again.
        if((a.flags23c&0x80)&&unsigned(a.stateTable())<2){a.pendingTable=2;a.pendingIndex=30;a.request18c=1;}
    } else if(mode!=7)throw std::runtime_error("Unimplemented ordinary ground continuation");
}
DownedEvents GroundStateRuntime::visit(PlayerObject& o,StateEntryActor& a,ActorCommandInput& input,
        const InputSystemConfig& config,StateEntryContext& context,const GroundStateFrame& frame) {
    DownedEvents events;
    if(!playableFighter(a.character)||a.character!=config.character||(config.system>5&&config.system!=8))
        throw std::runtime_error("Invalid ground fighter or spirit");
    if(unsupportedForm(a))throw std::runtime_error("Transformed ground callbacks require their own dispatcher");
    // 1493c0 runs 14d788 on every queued ACT: a form (Amakusa's 23c 0x400000)
    // substitutes its own ACT. Native code queues by assignment, so the
    // outermost visit applies the substitution to every ACT it queued, for
    // both fighters (victim scripts queue the attacker too).
    struct FormQueue {
        const FighterTables& tables;StateEntryActor* actors[2];int32_t before[2];int& depth;const GroundStateFrame& frame;
        ~FormQueue() {
            if(--depth)return;
            for(unsigned k=0;k<2;++k)if(actors[k]&&actors[k]->queuedActionA3c!=before[k]&&actors[k]->queuedActionA3c>=0) {
                auto& x=*actors[k];
                int companion=-1;
                const int mapped=tables.formAction(x.character,x.flags23c,x.queuedActionA3c,&companion);
                if(mapped!=-1)x.queuedActionA3c=mapped;
                // 14e6d8: riding Rera's ACT also gives the wolf its companion ACT, 11d908(wolf, act, 0, 0).
                if(companion!=-1&&x.auxiliaryObject04&&frame.pools&&frame.weaponLock)
                    frame.weaponLock->objects.request(frame.pools->objects.at(x.auxiliaryObject04-1),unsigned(companion),false,false);
            }
        }
    };
    StateEntryActor* opponentActor=frame.weaponLock?&frame.weaponLock->opponent:nullptr;
    ++formQueueDepth_;
    FormQueue formQueue{victimTables_.fighters(),{&a,opponentActor},{a.queuedActionA3c,opponentActor?opponentActor->queuedActionA3c:-1},formQueueDepth_,frame};
    const int table=a.pendingTable==-1?a.stateTable():a.pendingTable;
    const int state=a.pendingIndex==-1?a.stateIndex():a.pendingIndex;
    const bool pendingRide=(a.character==1||a.character==45)&&(a.flags23c&0x200000)&&a.aliasPendingTable>=0&&a.pendingTable==-1;
    // 1fb970 handles every captured state 80..111 of a Mina victim, recovering
    // through 169810 where 4e3a80 has no row (e.g. the shared throw type 45).
    // The plain table-B stubs (victim_script.cpp) behave the same way.
    const bool minaVictim=table==2&&state>=80&&state<=111&&(a.pendingCharacter254==24||victimTables_.handler(a.pendingCharacter254));
    if(!pendingRide&&!minaVictim&&!supports(table,state))throw UnportedFighterState(a.character,table,state);
    if(table==1&&(!frame.objects||(a.character==0&&state>=64&&state!=77&&!(a.flags23c&0x1000))))
        throw std::runtime_error("Ground attacks require armed actor and explicit object context");
    if(((table==2&&state==13)||(table==1&&state==31))&&!frame.weaponLock)
        throw std::runtime_error("Ground throw requires both fighters");
    if(table==2&&((state>=10&&state<=12)||state==14)&&(!frame.weaponLock||!frame.random))
        throw std::runtime_error("Weapon deflection requires both fighters and the weapon registry");
    if(table==0&&(state==50||state==51)&&!frame.weaponLock)
        throw std::runtime_error("Weapon handling needs the player's live object registry");
    if(table==0&&state==31&&(!frame.weaponLock||!frame.random||!playableFighter(frame.weaponLock->opponent.character)||
            frame.weaponLock->objectTasks.size()!=48))
        throw std::runtime_error("Weapon-lock actors require live opponent, stage,48-slot registry and shared random context");
    if(table==1&&state==35&&(!frame.battle||!frame.weaponLock))
        throw std::runtime_error("Item pickup requires the stage and both fighters' live objects");
    if(table==0&&state==41&&!frame.matchStats)
        throw std::runtime_error("Victory requires explicit match statistics");
    if(table==0&&state==39&&!playableFighter(frame.opponentCharacter))
        throw std::runtime_error("Cross-character introduction needs its voice-delay selection");
    if(table==2&&state==67&&!frame.battle)
        throw std::runtime_error("Wall knockdown requires the live battle camera");
    if(table==1&&(state==36||state==37||(state==38&&a.systemState13c==3&&StateCallbacks::hasSystemEffect(config)))&&!frame.battle)
        throw std::runtime_error("Spirit burst actions require the live battle clocks");
    if(((table==1&&(state==78||state==79))||(table==2&&state==83))&&
       (!frame.battle||!frame.weaponLock||!frame.random))
        throw std::runtime_error("Haohmaru's weapon and secret techniques require the live battle clock and both fighters");
    if(table==2&&((a.flags248&0x400)||(state>=32&&a.contactKind252))&&
            (a.contactKind252>8||!frame.battle||!frame.weaponLock))
        throw std::runtime_error("Elemental damage requires its full callback path");
    if(table==2&&((a.flags23c&0x80)||state==7||state==16||state==30||state==31||KnockdownPlayback::supportsFall(state))&&
            (!frame.effects||!frame.random||frame.training))
        throw std::runtime_error("Ordinary downed/KO callbacks require battle effects and random state");
    captureBody(o,a);a.flags248&=~0x20u;
    entries_.transition(a,input,config,context);
    entries_.transitionAlias(a,input,config,context);restoreBody(o,a);
    if(a.request18c||a.aliasRequest19c) {
        entries_.updateMetadata(a,context);
        // 149e9c interrupts a retained ACT voice before this character
        // enters a special. Ordinary attacks keep the retained channel.
        if(frame.sound&&a.stateTable()==1&&a.stateIndex()>=64)
            frame.sound->stop(o.sound34);
        if(!a.request18c) {
            StateCallbacks::registerAlias(a);a.aliasRequest19c=0;
            if(a.stateTable()==1)context.opponentFlagsB8|=2;
        } else if(a.stateTable()==0)StateCallbacks::registerNormal(a);
        else if(a.stateTable()==1) {callbacks_.registerAttack(a,config,*frame.objects);context.opponentFlagsB8|=2;}
        else {
            callbacks_.registerOrdinaryDamage(a,config);
            const int damage=a.stateIndex();
            // 1731d4 and 173240 terminate an active concentration on a throw,
            // blade catch or character-specific capture. Ordinary hitstun does
            // not interrupt it.
            if((damage==13||damage==14||damage>=80)&&a.systemState13c==3&&StateCallbacks::hasSystemEffect(config)) {
                if(!frame.battle)throw std::runtime_error("Concentration capture requires the live battle clock");
                BattleGauges::endConcentration(*frame.battle,a,context.player);
            }
            if(damage<32&&(damage<18||damage>=24)) {a.fieldA2c=0;a.contactKind252=0;}
            // 14a088 overrides the incoming JDG element for the defense-down item.
            if(a.flags248&0x400)a.contactKind252=6;
            // 14b0a8 turns a fighter struck during the cross-behind ACT toward
            // the attacker. Other backwards hit descriptors retain their recoil.
            if(a.bodyAction24==74||a.bodyAction24==75) {
                a.opponentX=frame.opponentX;
                if(a.faceOpponent(true))restoreBody(o,a); // 16e2c8 copies the updated body facing.
            }
            else if((a.flags24c&2)&&(a.stateFlags19a&0x10))a.bodyFlags108|=0x200;
            a.fieldA2c=a.contactKind252;
            if(a.contactKind252) {
                // 14b120 assigns the new generation before registering the
                // attached effect. Landing or another attachment expires it.
                a.landingCount253=(a.landingCount253+1)&15;
                spawnElementHurt(frame.weaponLock->objects,*frame.battle,context.player,o,a);
            }
        }
        a.request18c=0;
        a.flags248=(a.flags248|0x1000)&~0x400u;
        const int index=a.stateIndex();
        //169760 retains only persistent hurts32+ and18..23. In particular,
        //down16 and rise7 reset landing count and repeated-heavy history.
        if(a.stateTable()!=2||(index<32&&(index<18||index>23))) {
            a.clearContacts();
            // 149f00 ends the opponent's combo when this recipient leaves
            // the set of hit reactions that preserve contact history.
            if(frame.opponentStats)frame.opponentStats->hitCount0c=0;
        }
        restoreBody(o,a);
    }
    const auto handler=a.callbacks260[0];
    if(a.override27c[0])contactPause(o,a);
    else if(handler) {
        //168a68/168a80: attacks allow terminal ACT jumps (e.g. crouch4),
        //whereas normal transitions retain control until their callback ends.
        const auto c=o.timeline.clock();
        o.setFlags(a.callbacks260[1]==1?c.flags104&~0x2000u:c.flags104|0x2000,c.flags108);captureBody(o,a);
        if(isNakoruruRidingCallback(a)) {
            if(updateNakoruruRiding(o,a,input,context,frame))recover(o,a,frame);
        } else if(handler==0x1743c0)begin(o,a,config,context,frame);
        else if(isDashCallback(a)){if(updateDash(o,a,input))recover(o,a,frame);}
        else if(handler==0x173a68||handler==0x173b18||handler==0x173bb8)
            updateJump(o,a,input,frame.weaponLock?&frame.weaponLock->camera:nullptr,ordinary_.movementFlags(a.character));
        else if(handler==0x173500) {
            ActorTimers timers{a.timerDelta,a.timers};
            if(!timers.decrease(10)){a.pendingTable=0;a.pendingIndex=40;}
            a.timers[10]=timers.values[10];
        } else if(handler==0x170c20) {
            if(actionEnded(o,a.queuedActionA3c)) {
                if(input.sampledFeatures[0xfc/4])a.flags23c|=8u;else a.flags23c&=~8u;
                recover(o,a,frame);
            }
        }
        else if(handler==0x173880)updateAirLanding(o,a);
        else if(handler==0x173438||handler==0x170b60)updateAirGuard(o,a);
        else if(handler==0x16a298&&actionEnded(o,a.queuedActionA3c)) {
            if(a.rageState120>0)recover(o,a,frame);
            else {
                a.queuedActionA3c=158+!(a.flags23c&0x1000);a.flags248&=~0x800u;
                // 14f1b0 seeds the accelerating charge; the priority-5 meter
                // task reads it before the player's next input/callback pass.
                a.rageCharge12c=40;a.flags23c|=0x10000u;
                a.callbacks260[0]=0x16a398;
            }
        } else if(handler==0x16a398||handler==0x16a298) {
            if(handler==0x16a398&&a.rageState120>=1)recover(o,a,frame);
        }
        else if(handler==0x16a458) {
            if(actionEnded(o,a.queuedActionA3c)) {
                a.queuedActionA3c=146+!(a.flags23c&0x1000);a.flags248&=~0x800u;
                // Conversion starts after the entire kneeling animation.
                // Releasing either button ends meditation in the input selector.
                a.flags23c|=0x8000u;a.callbacks260[0]=0x16a4d0;
            }
        }
        else if(handler==0x16a4d0) {
            if(a.rageState120>0||a.rageAmount124<=0||a.systemAmount140>=0xc800)recover(o,a,frame);
        }
        else if(handler==0x174030||handler==0x174100) {
            if(landingReady(o,a.queuedActionA3c)) {
                stopAtGround(o);
                a.callbacks260[0]=0x169a50;a.callbacks260[1]=0;a.callbacks260[2]=0xffffffff;
                a.callbacks260[5]=0;
            }
        }
        else if(handler==0x200cc0)updateAirLanding(o,a); // character 32's air kick: 173880
        else if(handler==0x16afd8||handler==0x16b050||handler==0x16b0c0) {
            if(updateJumpAttack(o,a))recover(o,a,frame);
        } else if(a.stateTable()==1&&((a.character==1&&a.stateIndex()==79)||(a.character==3&&a.stateIndex()==78))&&handler==0x174158) {
            if(updateNakoruruThrowLanding(o,a))recover(o,a,frame);
        } else if(a.character==1&&a.stateTable()==1&&a.stateIndex()==78&&handler!=0x169a50) {
            if(handler==0x1ec2f0) {
                a.queuedActionA3c=564+!(a.flags23c&0x1000);a.flags248&=~0x800u;
                a.callbacks260[0]=0x1ecbb0;a.callbacks260[1]=1;a.callbacks260[2]=0xffffffff;
            } else if(handler==0x1ecbb0) {
                const auto clock=o.timeline.clock();
                o.setFlags(clock.flags104&~0x100u,clock.flags108);
                if((clock.flags104&0x100)||actionEnded(o,a.queuedActionA3c))a.callbacks260[0]=0x1ecc00;
            } else if(handler==0x1ecc00&&(touchedGround(o,a.queuedActionA3c)||actionEnded(o,a.queuedActionA3c))) {
                a.pendingTable=0;a.pendingIndex=22;
            }
        } else if(a.stateTable()==1&&((a.character==1&&a.stateIndex()==79&&handler==0x1ec2f0)||
                  (a.character==3&&a.stateIndex()==78&&handler==0x1ee4a0))) {
            a.callbacks260[0]=0;
            seizeOpponent(a,context,frame); // 1ecc58
        } else if(a.character==1&&a.stateTable()==1&&nakoruruEagleAttackSupports(a.stateIndex())&&handler!=0x169a50) {
            if(updateNakoruruEagleAttack(o,a,input,context,frame))recover(o,a,frame);
        } else if(a.character==24&&a.stateTable()==1&&isMinaAttackCallback(handler)) {
            if(updateMinaAttack(o,a,input,frame,context,scripts_))recover(o,a,frame);
        } else if(a.stateTable()==1&&handler==0x174158&&a.callbacks260[5]==0&&victimTables_.handler(a.character)) {
            // End op 11 of the victim's table-B script: 174158 mode 0 waits
            // for the landing, then 169a50 (table kept) or 169810.
            if(updateGroundThrow(o,a,frame))recover(o,a,frame);
        } else if(handler==0x166e10&&victimTables_.handler(a.character)) {
            updateLifeHold(o,a,context,frame);
        } else if(a.stateTable()==1&&handler==0x174158&&victimTables_.handler(a.character)) {
            // Other modes from end ops 12..22 on the attacker's slot.
            if(updateLanding174158(o,a,context,frame))recover(o,a,frame);
        } else if(a.stateTable()==1&&isScriptFighterAttack(victimTables_.fighters(),a.character,handler)) {
            if(updateScriptFighterAttack(o,a,input,frame,context,scripts_))recover(o,a,frame);
        } else if(a.character==3&&a.stateTable()==1&&isHanzoSpecialCallback(handler)) {
            if(updateHanzoSpecial(o,a,input,frame))recover(o,a,frame);
        } else if(a.character==2&&(handler==0x1edf30||handler==0x163610)) {
            if(updateRimururuSpecial(o,a,input,frame))recover(o,a,frame);
        } else if(handler==0x1ec1d8||handler==0x1ec2f0||handler==0x163610) {
            if(updateHaohmaruSpecial(o,a,input,frame))recover(o,a,frame);
        }
        else if(handler==0x169a50&&a.callbacks260[5]!=5&&a.callbacks260[5]!=6)callback(o,a,frame);
        else if(handler==0x16b5b8||handler==0x16b6b8||handler==0x16b7d8||handler==0x16b8c8) {
            if(updatePursuitAttack(o,a,frame.opponentX))recover(o,a,frame);
        }
        else if(handler==0x16bb88||handler==0x16c2b0) {
            if(updateStageItemPickup(o,a,context,frame))recover(o,a,frame);
        }
        else if(handler==0x1709d8)updatePursuitVictim(o,a);
        else if(handler==0x171208||handler==0x171268||handler==0x1713c0)updateDeflectedWeapon(o,a,context,frame);
        else if(handler==0x16a610)updateWeaponDiscard(o,a,context,frame);
        else if(handler==0x1523e8||handler==0x152440||handler==0x1524e0||handler==0x152560||handler==0x1525b8||handler==0x152600)
            weaponLockCallback(o,a,context,frame);
        else if(handler==0x174b40) {
            const auto state=a.stateIndex();
            if(state>=39&&state<=54)beginTenChain(o,a,frame.opponentX);
            else if(state==23||state==24||state==29)beginWeaponDeflection(o,a,frame);
            else if(state==21)beginCombinedSlash(a);
            else if(state==33)beginPursuitAttack(a);
            else if(state==35)beginStageItemPickup(o,a);
            else if(state>=36&&state<=38)beginSpiritBurst(o,a,config,frame);
            else if(a.stateIndex()==26||a.stateIndex()==31)beginGroundThrow(o,a,context,frame);
            else beginAttack(o,a,frame);
        } else if(handler==0x16b9a8||handler==0x16ba08||handler==0x16bf00||handler==0x16bfc0||
                  handler==0x16c028||handler==0x172a18||handler==0x172a90) {
            if(updateTenExplosion(o,a,frame))recover(o,a,frame);
        } else if(handler==0x16bc68) {
            if(updateTenChain(o,a,input,config,callbacks_))recover(o,a,frame);
        } else if(handler==0x16c1d0)updateCombinedSlash(o,a);
        else if(isGroundThrowCallback(a)){if(updateGroundThrow(o,a,frame))recover(o,a,frame);}
        else if(handler==0x171090) {
            auto& other=*frame.weaponLock;
            updateThrowVictim(o,a,other.opponentBody);
            captureBody(other.opponentBody,other.opponent);
        }
        else if(handler==0x16b2b8) {
            if(jumpReachedGround(o,a.queuedActionA3c)) {
                captureBody(o,a);StateEntryRules::pose(a,3);restoreBody(o,a);
                // The next actor visit releases the held landing record.
                a.callbacks260[0]=0x16b318;
                a.callbacks260[1]=1;a.callbacks260[2]=0xffffffff;
            }
        }
        else if(handler==0x16b318||handler==0x16b368) {
            // Both continuations poll 1699f8 on separate actor visits. The
            // terminal pose persists while these callbacks hand control back.
            const auto c=o.timeline.clock();
            if(actionEnded(o,a.queuedActionA3c)||(c.flags104&0x100)) {
                o.setFlags(c.flags104&~0x100u,c.flags108);
                a.callbacks260[0]=handler==0x16b318?0x16b368:0x169a50;
                a.callbacks260[1]=1;
                a.callbacks260[2]=0xffffffff;
                if(handler==0x16b368)a.callbacks260[5]=0;
            }
        }
        else if(handler==0x16ae60) {if(actionEnded(o,a.queuedActionA3c))recover(o,a,frame);}
        else if(handler==0x1fb970) {
            if(updateMinaVictim(o,a,context,frame,scripts_))recover(o,a,frame);
            if(a.flags248&0x20)return visit(o,a,input,config,context,frame);
        }
        else if(a.stateTable()==2&&victimTables_.handler(a.pendingCharacter254)&&!whirlwindRows(a)&&
                (handler==victimTables_.handler(a.pendingCharacter254)||handler==0x165cc0||handler==0x174158||
                 (victimTables_.fighters().victimK4Routine(a.pendingCharacter254)&&
                  (handler==0x1f3db8||handler==0x1f4010||handler==0x1f4098||handler==0x1f7c30||handler==0x2064a8||handler==0x206548||
                   handler==0x1f3a70||handler==0x1fedc8||handler==0x1fee40||handler==0x1fef00||handler==0x207150||handler==0x2015e0||handler==0x20b4d0||handler==0x20b588||handler==0x20b648||handler==0x20b7b8||handler==0x20b870||handler==0x20b930||handler==0x20baa0||handler==0x202b28||handler==0x202ca8||handler==0x202d98||handler==0x202f50||handler==0x2030a0||handler==0x203130||handler==0x203408||handler==0x2034f0||handler==0x201708||handler==0x201818||handler==0x201928||handler==0x201a20||handler==0x207620||handler==0x207880||handler==0x2078f8||handler==0x2079b0||handler==0x207a20||handler==0x207b70||handler==0x205c18||handler==0x200228||handler==0x2003d0||handler==0x200560||handler==0x200710||(handler>=0x1f1890&&handler<=0x1f1c88&&(handler==0x1f1890||handler==0x1f1900||handler==0x1f1b90||handler==0x1f1c88)))))) {
            if(updateVictimScript(o,a,context,frame,victimTables_,scripts_))recover(o,a,frame);
            if(a.flags248&0x20)return visit(o,a,input,config,context,frame);
        }
        else if(handler==0x1ec420||handler==0x1edfa0||handler==0x1ee658||
                (a.stateTable()==2&&(a.pendingCharacter254==1||a.pendingCharacter254==3)&&handler==0x165cc0)) {
            updateFighterCapture(o,a,context,frame);
            if(a.flags248&0x20)return visit(o,a,input,config,context,frame);
        }
        else if(handler==0x1ec248&&a.stateIndex()==83) {
            auto& world=*frame.weaponLock;
            world.opponent.flags23c&=~0x10000000u;
            a.bodyState128=0;a.timers[0]=a.timers[1]=a.timers[23]=world.opponent.timers[23]=0;
            // 168750 selects by the attacker: Shin shatters the weapon,
            // while Zan leaves the intact sword available once it lands.
            const auto parent=o.childParentWords();
            if(frame.opponentSystem==1)
                world.objects.dropSpecial(context.tasks,world.objectTasks,*frame.random,context.player,a.character,a.flags23c,parent);
            else
                world.objects.drop(context.tasks,world.objectTasks,*frame.random,context.player,a.character,a.flags23c,parent);
            a.flags244=(a.flags244&~0x20000u)|0x10;
            if(a.fieldA30>0) {
                const int divisor=frame.battle->gauges.paused46a940?8:1;
                frame.battle->timers.set(6,12,divisor);
                frame.battle->timers.set(5,6,divisor);
            }
            // 16690c requests the launch; 149f90 immediately visits it.
            // Weapon ownership must already be clear when the launch selects its ACT.
            a.pendingTable=2;a.pendingIndex=71;a.request18c=1;a.flags248|=0x20;
            return visit(o,a,input,config,context,frame);
        }
        else if(const auto rows=whirlwindRows(a);rows&&(handler==rows->entry||handler==0x165cc0||handler==0x174158))
            updateWhirlwindVictim(o,a,input,context,frame,*rows);
        else if(handler==0x174fe0)beginDamage(o,a,input,config,context,frame);
        else if(handler==0x14e320)endingCallback(o,a,context,frame);
        else if(handler==0x14e470&&a.character==24)minaWinnerHold(o,a,context);
        else if(handler==0x170640) {a.controlCounterC0=3;if(actionEnded(o,a.queuedActionA3c))recoverGuard(o,a);}
        else if(handler==0x172350||handler==0x1724c8||handler==0x1726b0) {
            if(frame.battle)frame.battle->flags138|=4;
            // 14aad8(a,(int)(14adf0+2.0),0,0): either camera edge, X truncated.
            if(!frame.battle)throw std::runtime_error("Damage state 21 needs the live camera");
            auto& camera=frame.battle->camera;
            const int m=(a.character==46?8:a.character==47?16:34)+2;
            const int x=int(o.timeline.motion().x);
            const auto hold=[&]{ // 1699f8 clears the hold bit and returns the old one or the clip end
                const auto c=o.timeline.clock();const bool done=actionEnded(o,a.queuedActionA3c)||(c.flags104&0x100);
                o.setFlags(c.flags104&~0x100u,c.flags108);return done;};
            if((x>=camera.right-m||x<=camera.left+m)&&hold()) {
                if(handler==0x1726b0) { // 1726b0: the rebound speed follows 172580's k
                    auto m=o.timeline.motion();const auto k=a.bodyState128;
                    m.vx=k==0?0x19999:k==1?0x33333:0x4cccc;o.timeline.setMotion(m);
                }
                if(handler==0x1724c8) { // 1724c8: the wall turns it into state 21's reel
                    a.queuedActionA3c=0x1aa+!(a.flags23c&0x1000);a.flags248&=~0x800u;
                    a.callbacks260[0]=0x172350;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
                } else {
                camera.commands.clear();camera.appendCommand(3,0x14); // 1414b8, 1414f8(3,0x14)
                a.callbacks260[0]=0x172288;a.callbacks260[1]=2;a.callbacks260[2]=0xffffffffu;
                }
            }
        }
        else if(handler==0x172288) { // on the ground: crouching recovery, then 1727f8's voice
            if(touchedGround(o,a.queuedActionA3c)) {
                a.flags23c|=8;recover(o,a,frame);
                constexpr unsigned quiet[]{10,13,25,32,36,37,38,40}; // 1727a0
                const bool loud=std::find(std::begin(quiet),std::end(quiet),a.character)==std::end(quiet);
                if(frame.sound&&frame.random)frame.sound->act(loud?0x9c:0x9d,int(context.player),voiceCharacter(a),a.flags23c,3,0,*frame.random);
            }
        }
        else if(handler==0x170890) {if(updateGroundReaction(o))recover(o,a,frame);}
        else if(handler==0x172be8||handler==0x172c50||handler==0x172cb0)
            events=knockoutCallback(o,a,frame);
        else if(handler==0x171eb0||handler==0x171f58||handler==0x171b98||handler==0x171c80||handler==0x171d60||handler==0x1715b0||handler==0x171640||handler==0x1717a0||handler==0x171838||handler==0x1719a8||handler==0x171a38||handler==0x169a50||handler==0x170cd8||handler==0x170de8||handler==0x170ef8||handler==0x1706c0||handler==0x170758)
            events=downedCallback(o,a,input,config,context,frame);
        else {if(getenv("SS6_DEBUG_HANDLER"))fprintf(stderr,"handler %x\n",handler);throw UnportedFighterState(a.character,a.stateTable(),a.stateIndex());}
    }
    //The tail can commit a new logical state while the displayed body and
    //saved descriptor still belong to the completed transition for one visit.
    captureBody(o,a);entries_.transition(a,input,config,context);restoreBody(o,a);
    //149f78 runs after the tail state transition but before149918 commits
    //a queued body. Fade classification must still observe the old action.
    uint32_t* kind4=nullptr; // 140d78(seat, 0, 4)
    if(a.character==11&&frame.pools)for(auto t:frame.ownObjectTasks)if(t) {
        auto& obj=frame.pools->objects.at(frame.pools->tasks.at(t-1)[7]-1);
        if(obj[0xcc/4]==4){kind4=&obj[0x38/4];break;}
    }
    updateActorColor(a,config,kind4);restoreBody(o,a);
    a.flags244&=~0x40000u;
    captureBody(o,a);
    return events;
}
void GroundStateRuntime::commitAction(PlayerObject& o,StateEntryActor& a) {
    if(a.queuedActionA3c==-1)return;
    //Even a same-action refusal drains the actor queue and force bit. The
    //body's current clip changes only in the later11d8e0 object pass.
    o.request(unsigned(a.queuedActionA3c),a.flags248&0x1000);
    a.queuedActionA3c=-1;a.flags248&=~0x1000u;captureBody(o,a);
}
}
