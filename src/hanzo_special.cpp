#include "hanzo_special.hpp"
#include "battle_round.hpp"
#include "ground_state.hpp"
#include "jump_motion.hpp"
#include "knockout.hpp"
#include "scalar_float.hpp"
#include <bit>

namespace ss6 {
namespace {
// 4e2788[3]. One script has two phase rows, so the script ID alone
// cannot be multiplied by the row size to recover its original identity.
struct Script { unsigned address; int act; bool weaponPair,turn; };
constexpr std::array<Script,9> scripts{{
    {0x4df478,529,true,false},{0x4df48c,546,true,false},{0x4df4a0,730,true,false},
    {0x4df4b4,716,true,false},{0x4df4dc,723,false,false},{0x4df4f0,617,true,true},
    {0x4df504,642,true,true},{0x4df518,664,true,true},{0x4df52c,568,true,true}
}};
float offset(float position,int units) {
    // A teleport can cross a power-of-two boundary while the opponent has
    // a fractional jump or recoil position. EE ADD.S truncates that bit.
    return std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(position)}.add(ScalarFloat::integer(units)).bits);
}
void bind(StateEntryActor& a,uint32_t pc) {
    a.callbacks260[0]=pc;a.callbacks260[1]=1;a.callbacks260[2]=0xffffffff;
}
void turn(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f) {
    GroundStateRuntime::captureBody(b,a);
    a.opponentX=f.opponentX;a.faceOpponent();GroundStateRuntime::restoreBody(b,a);
}
void queue(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,int action) {
    a.queuedActionA3c=action;a.flags248&=~0x800u;
    // 168c18(3,ACT) has precisely three positive entries in bank 03.
    const int lock=action==723?64:action==664||action==665?16:0;
    if(!lock)return;
    auto& battle=*f.battle;
    battle.timers.lock=lock;battle.gauges.focus46a948=int32_t(b.ownerCC);
    for(auto& tone:std::span(battle.gauges.paletteTones).subspan(512))tone|=4;
    a.flags23c|=0x08000000u;f.weaponLock->opponent.flags23c&=~0x08000000u;
}
void enter(PlayerObject& b,StateEntryActor& a,const GroundStateFrame& f,const Script& s) {
    auto& r=a.registry28c;
    if(s.turn)turn(b,a,f);
    a.flags23c&=~0x02000000u;
    if(r[0]==0)queue(b,a,f,s.act+(s.weaponPair?2*int(r[3])+!(a.flags23c&0x1000):0));
    else {
        // Invisibility starts on the marker in ACT 716/717; the current
        // ACT continues through the second phase without restarting it.
        a.timers[17]=540<<8;a.timers[18]=16<<8;
    }
    r[1]=r[0];r[2]=0xffffffff;r[6]=b.timeline.motion().y>0;
    b.scriptLatch134=0;
}
void clearMarker(PlayerObject& b) {
    auto c=b.timeline.clock();b.setFlags(c.flags104&~0x100u,c.flags108);
}
bool stepScript(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& frame) {
    auto& r=a.registry28c;
    // Row 8 clamps both sides during the close-range strike, including its final visit.
    if(r[11]==scripts[8].address) {
        const auto c=b.timeline.clock();b.setFlags(c.flags104|0x2000,c.flags108);
    }
    const bool firstHide=r[11]==scripts[3].address&&r[0]==0;
    const bool ended=actionEnded(b,a.queuedActionA3c);
    const bool marker=b.timeline.clock().flags104&0x100;
    if(firstHide)clearMarker(b);
    if(firstHide&&(marker||ended)) {++r[0];enter(b,a,frame,scripts[3]);return false;}
    if(!ended){clearMarker(b);r[6]=b.timeline.motion().y>0;return false;}
    if(input.sampledFeatures[0xfc/4])a.flags23c|=8;else a.flags23c&=~8u;
    r.fill(0);r[2]=0xffffffff;return true;
}
}
bool isHanzoSpecialCallback(uint32_t pc) {
    return pc==0x1ee4a0||pc==0x163610||pc==0x1ee748||pc==0x1ee858||
           pc==0x1ee998||pc==0x1eeb80||pc==0x1eec90||pc==0x1eed40||pc==0x1eee08;
}
bool updateHanzoSpecial(PlayerObject& b,StateEntryActor& a,const ActorCommandInput& input,const GroundStateFrame& f) {
    const auto pc=a.callbacks260[0];
    const int unarmed=!(a.flags23c&0x1000);
    if(pc==0x163610)return stepScript(b,a,input,f);
    if(pc==0x1ee4a0) {
        const unsigned selector=a.callbacks260[2];
        if(selector>=0x80&&selector<0x80+scripts.size()) {
            const auto& s=scripts[selector-0x80];auto& r=a.registry28c;
            r[0]=0;r[1]=r[2]=0xffffffff;
            r[3]=a.effectiveFlags()&4?2:unsigned(bool(a.effectiveFlags()&2));
            r[11]=s.address;a.callbacks260[3]=r[3];
            enter(b,a,f,s);bind(a,0x163610);return false;
        }
        turn(b,a,f);
        int act=0;unsigned next=0;
        switch(selector) {
        case 3:act=682+unarmed;next=0x1ee748;break;
        case 4:act=702+unarmed;next=0x1ee998;break;
        case 22:act=692+unarmed;next=0x1ee748;break;
        case 23:act=692;next=0x1ee998;break;
        case 18:case 19:case 20:case 21:
            a.bodyState128=selector>=20;
            act=575+unarmed;next=selector&1?0x1eed40:0x1eeb80;break;
        default:throw UnportedFighterState(3,1,a.stateIndex());
        }
        queue(b,a,f,act);bind(a,next);return false;
    }
    const bool ended=actionEnded(b,a.queuedActionA3c);
    if(pc==0x1ee858) {
        const bool landed=jumpReachedGround(b,a.queuedActionA3c);
        if(!landed&&!(b.timeline.clock().flags104&0xc0000))return false;
        queue(b,a,f,(landed?688:686)+unarmed);bind(a,0x169a50);a.callbacks260[5]=0;return false;
    }
    if(pc==0x1eec90||pc==0x1eee08) {
        clearMarker(b);f.battle->flags138|=4;
        if(ended&&pc==0x1eec90){a.pendingTable=0;a.pendingIndex=32;}
        return ended&&pc==0x1eee08;
    }
    if(!ended)return false;
    auto& world=*f.weaponLock;
    auto m=b.timeline.motion();
    const int mirror=(b.timeline.clock().objectFlags&0x80000)?1:-1;
    if(pc==0x1ee748) {
        // 1efc98 stops all accumulated motion, then installs the descent.
        // The body anchor is relative to the opponent even if he is jumping.
        auto c=b.timeline.clock();b.setFlags(c.flags104&~0x140u,c.flags108);
        m={0,0,0,0,-65536,-40960,offset(f.opponentX,mirror*10),offset(world.opponentBody.timeline.motion().y,100)};
        b.timeline.setMotion(m);a.flags23c|=0x30;
        queue(b,a,f,684+unarmed);bind(a,0x1ee858);
    } else if(pc==0x1ee998) {
        b.timeline.setPosition(offset(f.opponentX,mirror*40),m.y);
        queue(b,a,f,704+unarmed);bind(a,0x169a50);a.callbacks260[5]=0;
    } else if(pc==0x1eeb80||pc==0x1eed40) {
        const bool air=pc==0x1eeb80;
        b.timeline.setPosition(a.bodyState128?float(world.camera.right-48):float(world.camera.left+48),
                               air?float(world.camera.top-96):m.y);
        if(air)a.flags23c|=0x10;
        turn(b,a,f);queue(b,a,f,(air?579:577)+unarmed);
        bind(a,air?0x1eec90:0x1eee08);f.battle->flags138|=4;
    } else throw UnportedFighterState(3,1,a.stateIndex());
    return false;
}
}
