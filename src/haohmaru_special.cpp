#include "haohmaru_special.hpp"
#include "nakoruru_strikes.hpp"
#include "ground_state.hpp"
#include "knockout.hpp"
#include "round_control.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
enum class PhaseEnd { Clip, Falling, Ground };
struct Phase {
    int action;
    bool addStrength;
    bool turn;
    PhaseEnd end;
    bool weaponPair=false;
};
struct Script {
    // Identity stored in actor+2b8. It is compared as a resource ID only.
    uint32_t resourceAddress;
    Phase first, last;
    unsigned count;
};
// Selected rows of the 20-byte phase table reached through ELF 4e2788[0].
// For -1 the original keeps playing the current ACT across the phase boundary.
constexpr Phase none{-1,false,false,PhaseEnd::Clip};
constexpr Script whirlwind{0x4df060,{529,true,true,PhaseEnd::Clip},none,1};
constexpr Script feint{0x4df074,{539,false,true,PhaseEnd::Clip},none,1};
constexpr Script rising{0x4df088,{549,true,true,PhaseEnd::Falling},{552,true,false,PhaseEnd::Clip},2};
// 71..73 use the same recovery phase as the standing rising slash.
constexpr Script runningRising{0x4df0b0,{568,true,true,PhaseEnd::Falling},rising.last,2};
constexpr Script leaping{0x4df0d8,{584,true,true,PhaseEnd::Ground},none,2};

constexpr Script flask{0x4df100,{598,false,true,PhaseEnd::Clip,true},none,1};
constexpr Script weaponBreaker{0x4df114,{625,false,true,PhaseEnd::Clip},none,1};
constexpr Script secret{0x4df128,{612,false,true,PhaseEnd::Falling},{613,false,false,PhaseEnd::Clip},2};

// 1/80 uses the fixed ACT even though the command combines two slashes.
constexpr Script heavySlash{0x4df150,{592,false,true,PhaseEnd::Clip},none,1};

// Nakoruru selects the common 163610 interpreter through her own
// 1ec2f0 dispatcher. Her script identities and ACTs belong to bank 01.
constexpr Script nakoruruSpin{0x4df1dc,{554,true,true,PhaseEnd::Clip},none,1};
constexpr Script nakoruruThrust{0x4df1f0,{557,false,false,PhaseEnd::Clip,true},none,1};
constexpr Script nakoruruRush{0x4df240,{715,false,false,PhaseEnd::Clip,true},none,1};
const Script& scriptFor(unsigned character,int state) {
    if(character==1) {
        if(state>=71&&state<=73)return nakoruruSpin;
        if(state==70)return nakoruruThrust;
        if(state==91)return nakoruruRush;
        throw UnportedFighterState(character,1,state);
    }
    if(state>=64&&state<=66)return whirlwind;
    if(state==67)return feint;
    if(state>=68&&state<=70)return rising;
    if(state>=71&&state<=73)return runningRising;
    if(state>=74&&state<=76)return leaping;
    if(state==77)return flask;
    if(state==78)return weaponBreaker;
    if(state==79)return secret;
    if(state==80)return heavySlash;
    throw UnportedFighterState(character,1,state);
}

void enterPhase(PlayerObject& body,StateEntryActor& actor,const GroundStateFrame& frame,const Phase& phase) {
    auto& registry=actor.registry28c;
    if(phase.turn) {
        actor.opponentX=frame.opponentX;
        actor.faceOpponent();
        GroundStateRuntime::restoreBody(body,actor);
    }
    // 163488 clears the stance bit on phase entry. ACT attachments are
    // consumed later, after the new body record has been committed.
    actor.flags23c&=~0x02000000u;
    if(phase.action>=0) {
        actor.queuedActionA3c=phase.action+(phase.addStrength?int(registry[3]):0);
        // Phase flag 4 indexes armed/unarmed ACT pairs separately for each
        // strength. The flask command normally supplies strength zero.
        if(phase.weaponPair)actor.queuedActionA3c+=2*int(registry[3])+!(actor.flags23c&0x1000);
        actor.flags248&=~0x800u;
        // 1493c0 selects the freeze from the character's own ACT table.
        const int lockTicks=actor.character==1?(phase.action==715?16:0):
                            phase.action==625?64:phase.action==612?16:0;
        if(lockTicks) {
            auto& battle=*frame.battle;
            battle.timers.lock=lockTicks;battle.gauges.focus46a948=int32_t(body.ownerCC);
            for(auto& tone:std::span(battle.gauges.paletteTones).subspan(512))tone|=4;
            actor.flags23c|=0x08000000u;
            frame.weaponLock->opponent.flags23c&=~0x08000000u;
        }
    }
    registry[1]=registry[0];
    registry[2]=0xffffffff;
    registry[6]=body.timeline.motion().y>0;
    body.scriptLatch134=0;
}

bool finishedPhase(PlayerObject& body,StateEntryActor& actor,PhaseEnd end) {
    const auto clock=body.timeline.clock();
    const auto& m=body.timeline.motion();
    const bool ended=actionEnded(body,actor.queuedActionA3c);
    if(end==PhaseEnd::Falling&&actor.registry28c[6]) {
        if(m.vy<0)return true;
    } else if(end==PhaseEnd::Ground) {
        // 1737d8 checks the ACT landing sentinel first. At y==0 the
        // start of a jump still has velocity and must not count as a landing.
        if((clock.endControl&0x100)||m.y<0||
           ((ended||(clock.flags104&0x100))&&m.y==0&&m.vy==0&&m.ay==0)) {
            stopAtGround(body);
            return true;
        }
    } else if(ended)return true;

    // 16472c calls 1699f8 for its side effect even while waiting. Keep
    // the previous airborne flag until after evaluating the descent gate.
    body.setFlags(clock.flags104&~0x100u,clock.flags108);
    actor.registry28c[6]=m.y>0;
    return false;
}
}

bool haohmaruSpecialSupports(int state) {
    return state>=64&&state<=80;
}

bool updateHaohmaruSpecial(PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input,
                           const GroundStateFrame& frame) {
    if(actor.character==1&&actor.stateIndex()>=64&&actor.stateIndex()<=69)
        return updateNakoruruStrike(body,actor,input,frame);
    const auto& script=scriptFor(actor.character,actor.stateIndex());
    auto& registry=actor.registry28c;
    if(actor.callbacks260[0]==(actor.character==1?0x1ec2f0u:0x1ec1d8u)) {
        const unsigned strength=(actor.stateFlags19a&4)?2u:(actor.stateFlags19a&2)?1u:0u;
        // 163488 retains unused fields. A wholesale reset here would erase
        // the registry's object identity before state entry can release it.
        registry[0]=0;
        registry[1]=registry[2]=0xffffffff;
        registry[3]=strength;
        registry[11]=script.resourceAddress;
        actor.callbacks260[3]=strength;
        enterPhase(body,actor,frame,script.first);
        actor.callbacks260[0]=0x163610;
        actor.callbacks260[1]=1;
        actor.callbacks260[2]=0xffffffff;
        return false;
    }
    if(actor.callbacks260[0]!=0x163610||registry[11]!=script.resourceAddress||registry[0]>=script.count)
        throw std::runtime_error("Invalid Haohmaru special phase");
    const auto& phase=registry[0]==0?script.first:script.last;
    if(!finishedPhase(body,actor,phase.end))return false;
    if(registry[0]+1<script.count) {
        ++registry[0];
        GroundStateRuntime::captureBody(body,actor);
        enterPhase(body,actor,frame,script.last);
        return false;
    }
    // 169918 reads the current pad state at recovery, independently of
    // whether the motion that started the attack included down.
    if(input.sampledFeatures[0xfc/4])actor.flags23c|=8;
    else actor.flags23c&=~8u;
    registry.fill(0);
    registry[2]=0xffffffff;
    return true;
}
namespace {
// 4e2858, 4e28bc, 4e2920. The three victim scripts share phase actions
// and gates, but have different ascent times and original landing damage.
constexpr std::array<int,3> whirlwindLiftTimes{13,19,31};
constexpr std::array<int,3> whirlwindLandingDamage{12,16,18};
void bindWhirlwindAnchor(PlayerObject& body,AuxiliaryObject& child) {
    const float x=std::bit_cast<float>(child[0x40/4]);
    const float y=std::bit_cast<float>(child[0x44/4]);
    const float separation=(child[0x38/4]&0x80000)?0.2f:-0.2f;
    // 166c28 separates the two anchors even when their coordinates began
    // identical. Rounding each new coordinate independently is observable.
    child[0x40/4]=std::bit_cast<uint32_t>(x+separation);
    body.timeline.setPosition(x-separation,y);
    body.timeline.stopMotion();
}
void setWhirlwindPhase(PlayerObject& body,StateEntryActor& a,StateEntryActor& opponent,
                       AuxiliaryObject* child,AuxiliaryObjects& objects,unsigned phase) {
    auto& r=a.registry28c;
    r[0]=r[1]=phase;r[7]=r[8]=r[9]=0;
    a.timers[23]=opponent.timers[23]=0;
    if(phase<=1) {
        bindWhirlwindAnchor(body,*child);r[4]=r[5]=0;
    }
    if(phase<3) {
        a.queuedActionA3c=int32_t(1280+phase*2+!(a.flags23c&0x1000));
        a.flags248&=~0x800u;
        objects.request(*child,535+phase,false,false);
        if(phase==2)body.pendingFlags|=1;
    }
}
void restrictScriptJump(PlayerObject& body) {
    const auto c=body.timeline.clock();body.setFlags(c.flags104|0x2000,c.flags108);
}
}
void updateWhirlwindVictim(PlayerObject& body,StateEntryActor& a,const ActorCommandInput&,
                           StateEntryContext& context,const GroundStateFrame& frame) {
    if(!frame.weaponLock)throw std::runtime_error("Whirlwind victim requires live opponent and auxiliary pool");
    auto& world=*frame.weaponLock;
    auto& r=a.registry28c;
    const auto strength=unsigned(a.stateIndex()-80);
    if(strength>=3)throw std::runtime_error("Invalid whirlwind victim state");
    if(a.callbacks260[0]==0x174158) {
        // 174158 mode 5 releases the grounded ACT hold before changing to
        // the common finish callback. The bounce itself comes from ACT 1284.
        if(landingReady(body,a.queuedActionA3c)) {
            a.callbacks260[0]=0x169a50;a.callbacks260[5]=5;
            if(actionEnded(body,a.queuedActionA3c)){a.flags244&=~0x8000u;a.pendingTable=2;a.pendingIndex=16;a.request18c=1;}
        }
        return;
    }
    AuxiliaryObject* child=a.bodyField124?&context.tasks.objects.at(a.bodyField124-1):nullptr;
    if(a.callbacks260[0]==0x1ec248) {
        if(!child||(*child)[0xcc/4]!=2||(*child)[0x14/4]!=0||!(*child)[1]) {
            // 168220 falls back to common air damage when its source has
            // already gone away before the captured reaction can take over.
            a.callbacks260[0]=0;a.pendingTable=2;a.pendingIndex=74;a.request18c=1;return;
        }
        auto& source=*child;
        if(!(source[0x104/4]&0x100000)) {
            const float x=body.timeline.motion().x,otherX=std::bit_cast<float>(source[0x40/4]);
            if(x<otherX)source[0x38/4]|=0x80000;
            else if(x>otherX)source[0x38/4]&=~0x80000u;
            const auto c=body.timeline.clock();
            body.timeline.setObjectFlags((c.objectFlags&~0x80000u)|((~source[0x38/4])&0x80000),c.flags104,c.flags108);
            source[0x104/4]|=0x100000;
        }
        world.opponent.flags23c&=~0x10000000u;world.opponent.flags244|=0x1000;
        a.flags244|=0x10;source[0xdc/4]=source[0xe4/4]=source[0xe8/4]=0;
        context.tasks.tasks.at(source[1]-1)[0]=0x147540;
        source[0x108/4]&=~0x7000u;
        a.callbacks260={0x165cc0,2,0xffffffffu,(world.opponent.stateFlags19a&4)?2u:unsigned(bool(world.opponent.stateFlags19a&2)),0,0,0};
        a.override27c={};r[12]=0x4e2858u+strength*100;r[10]=a.bodyField124;r[3]=a.callbacks260[3];
        r[2]=0xffffffff;r[7]=r[8]=r[9]=0;a.timers[0]=a.timers[1]=0;
        setWhirlwindPhase(body,a,world.opponent,child,world.objects,0);return;
    }
    const auto phase=r[0];
    restrictScriptJump(body);restrictScriptJump(world.opponentBody);
    if(child)(*child)[0x104/4]|=0x2000;
    if(phase==0) {
        const auto& motion=body.timeline.record().motion;
        if(motion.kind>=5&&motion.kind<=8) {
            r[4]=uint32_t(motion.values[0])<<16;r[5]=uint32_t(motion.values[1])<<16;
        }
        const auto dx=std::bit_cast<int32_t>(r[4])>>16,dy=std::bit_cast<int32_t>(r[5])>>16;
        body.timeline.setPosition(std::bit_cast<float>((*child)[0x40/4])+((body.timeline.clock().objectFlags&0x80000)?-dx:dx),
                                  std::bit_cast<float>((*child)[0x44/4])+dy);
        body.timeline.stopMotion();r[7]=r[8]=1;
        if(!(*child)[0xc0/4]||((*child)[0x104/4]&1))return;
    } else if(phase==1) {
        r[8]=r[9]=1;const auto previous=a.timers[23];
        a.timers[23]=std::min(0x173400,previous+a.timerDelta);
        if(previous<whirlwindLiftTimes[strength]*256)return;
    } else if(phase==2) {
        // The third row has no wait. Its completion instruction gives the
        // projectile back to its own cleanup pass after ACT 537 finishes.
        (*child)[0x108/4]|=0x2000;a.bodyField124=r[10]=0;child=nullptr;
    } else if(phase==3) {
        r[8]=r[9]=1;
        if(!landingReady(body,a.queuedActionA3c))return;
        stopAtGround(body);
        setWhirlwindPhase(body,a,world.opponent,nullptr,world.objects,4);
        frame.captureDamage(whirlwindLandingDamage[strength]);
        a.callbacks260[0]=0x174158;a.callbacks260[5]=5;return;
    } else throw std::runtime_error("Invalid whirlwind victim phase");
    setWhirlwindPhase(body,a,world.opponent,child,world.objects,phase+1);
}
}
