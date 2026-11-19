#include "nakoruru_capture.hpp"
#include "hanzo_capture.hpp"
#include "knockout.hpp"
#include <algorithm>
#include <bit>

namespace ss6 {
namespace {
void callback(StateEntryActor& a,uint32_t pc,unsigned table,unsigned mode) {
    a.callbacks260[0]=pc;a.callbacks260[1]=table;a.callbacks260[2]=0xffffffff;
    a.callbacks260[5]=mode;
}
void queue(StateEntryActor& a,int act) {
    a.queuedActionA3c=act;a.flags248&=~0x800u;
}
void oppositeFacing(PlayerObject& target,PlayerObject& source) {
    auto s=source.timeline.clock(),t=target.timeline.clock();
    const float x=target.timeline.motion().x,from=source.timeline.motion().x;
    if(x<from)s.objectFlags|=0x80000;else if(x>from)s.objectFlags&=~0x80000u;
    source.timeline.setObjectFlags(s.objectFlags,s.flags104,s.flags108);
    target.timeline.setObjectFlags((t.objectFlags&~0x80000u)|(~s.objectFlags&0x80000u),t.flags104,t.flags108);
}
float shifted(float x,float offset) {
    // EE rounds toward zero after each offset, including the 0.2-unit split.
    return std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(x)}.add({std::bit_cast<uint32_t>(offset)}).bits);
}
void splitAnchor(PlayerObject& target,PlayerObject& source) {
    const auto m=source.timeline.motion();
    const float split=(source.timeline.clock().objectFlags&0x80000)?0.2f:-0.2f;
    source.timeline.setPosition(shifted(m.x,split),m.y);
    target.timeline.setPosition(shifted(m.x,-split),m.y);
    target.timeline.stopMotion();
}
void constrain(PlayerObject& o) {
    const auto c=o.timeline.clock();
    o.setFlags(c.flags104|0x2000,c.flags108);
}
}

void updateFighterCapture(PlayerObject& body,StateEntryActor& a,StateEntryContext& context,const GroundStateFrame& frame) {
    auto& world=*frame.weaponLock;auto& source=world.opponent;
    auto& sourceBody=world.opponentBody;
    // Rimururu's sole victim row (4e2a40) performs the same weapon operation
    // as Nakoruru row 4. Its final request selects backward fall 69.
    const bool iceBreak=a.callbacks260[0]==0x1edfa0;
    const bool hanzo=a.pendingCharacter254==3;
    const int slot=iceBreak?4:a.stateIndex()-80;
    const bool weaponLoss=hanzo?slot==5:slot==4;
    auto& registry=a.registry28c;
    if(hanzo&&slot!=16&&a.callbacks260[0]==0x165cc0) {
        advanceHanzoThrowPhase(body,a,context,frame);return;
    }
    if(a.callbacks260[0]==0x165cc0) {
        // Row 16 waits independently for each actor's ground contact. Until
        // then 166ce8 anchors the recipient to the attacker's current position.
        const auto& cmd=body.timeline.record().motion;
        if(cmd.kind>=5&&cmd.kind<=8) {
            registry[4]=uint32_t(cmd.values[0])<<16;registry[5]=uint32_t(cmd.values[1])<<16;
        }
        const int dx=std::bit_cast<int32_t>(registry[4])>>16;
        const int dy=std::bit_cast<int32_t>(registry[5])>>16;
        const auto m=sourceBody.timeline.motion();
        body.timeline.setPosition(shifted(m.x,(body.timeline.clock().objectFlags&0x80000)?-dx:dx),shifted(m.y,dy));
        body.timeline.stopMotion();constrain(body);constrain(sourceBody);
        if(!registry[7]&&body.timeline.motion().y<=0){stopAtGround(body);registry[7]=1;}
        if(!registry[8]&&sourceBody.timeline.motion().y<=0){stopAtGround(sourceBody);registry[8]=1;}
        registry[9]=1;
        if(registry[7]&&registry[8]) {
            callback(a,0x169a50,2,5);
            callback(source,0x174158,1,3);
        }
        GroundStateRuntime::captureBody(sourceBody,source);
        return;
    }
    if(slot<0||(slot>(hanzo?7:4)&&slot!=16))throw UnportedFighterState(a.character,2,a.stateIndex());
    const bool paired=hanzo?!weaponLoss:slot==0||slot==16;
    auto requestFallback=[&] {
        a.pendingTable=2;a.pendingIndex=74;a.request18c=1;
    };
    auto loseWeapon=[&] {
        const auto parent=body.childParentWords();
        if(frame.opponentSystem==1)
            world.objects.dropSpecial(context.tasks,world.objectTasks,*frame.random,context.player,a.character,a.flags23c,parent);
        else
            world.objects.drop(context.tasks,world.objectTasks,*frame.random,context.player,a.character,a.flags23c,parent);
        a.flags244&=~0x20000u;
    };

    // 1ec460 clears the entry callback even when a simultaneous grab causes
    // 1657b0 to abandon the row and preserve the existing request.
    a.callbacks260[0]=0;
    auto* child=a.bodyField124?&context.tasks.objects.at(a.bodyField124-1):nullptr;
    bool invalidSource=source.stateTable()==2;
    if(child&&(*child)[0xc/4]!=2) {
        const auto owner=(*child)[0xc/4];
        const auto tasks=owner==context.player?std::span<const uint32_t>(world.objectTasks):frame.opponentObjectTasks;
        const auto kind=(*child)[0xcc/4];
        // 168220 searches the emitter's registry. A freed or reused slot may
        // still contain the old ACT and owner. Its identity and kind must match.
        const bool registered=std::any_of(tasks.begin(),tasks.end(),[&](auto task) {
            return task&&context.tasks.tasks.at(task-1)[7]==a.bodyField124;
        });
        invalidSource=owner>1||!registered||(kind!=2&&kind!=3);
    }
    if(invalidSource)requestFallback();
    if(invalidSource||(a.flags23c&0x10000000)) {
        // 1688c8 runs the row's final weapon operation even when the pair
        // cannot take control. Only the ordinary completion requests 2/71.
        if(weaponLoss)loseWeapon();
        return;
    }

    if(child) {
        if(!weaponLoss&&!((*child)[0x104/4]&0x100000)) {
            auto& flags=(*child)[0x38/4];
            const float x=body.timeline.motion().x,from=std::bit_cast<float>((*child)[0x40/4]);
            if(x<from)flags|=0x80000;else if(x>from)flags&=~0x80000u;
            const auto clock=body.timeline.clock();
            body.timeline.setObjectFlags((clock.objectFlags&~0x80000u)|(~flags&0x80000u),clock.flags104,clock.flags108);
        }
        (*child)[0x104/4]|=0x100000;
    } else if(!weaponLoss&&!(source.flags23c&0x10000000))oppositeFacing(body,sourceBody);
    source.flags23c|=0x10000000u;
    source.flags244&=~0x1000u;
    registry[0]=0;registry[1]=registry[2]=0xffffffff;
    registry[3]=source.effectiveFlags()&4?2:unsigned(bool(source.effectiveFlags()&2));
    registry[7]=registry[8]=registry[9]=0;
    registry[12]=hanzo?hanzoCaptureAddress(slot):iceBreak?0x4e2a40:0x4e29b0+20*(slot==16?5:slot);
    // 168318 runs after registration: a KO invalidates the paired row
    // after facing and the attacker's lock have already been committed.
    if(paired&&(source.stateTable()==2||source.fieldA30<=0||(source.flags23c&0x80))) {
        requestFallback();GroundStateRuntime::captureBody(sourceBody,source);return;
    }
    if(paired) {
        source.callbacks260={};source.override27c={};source.request18c=0;
        source.pendingTable=source.pendingIndex=-1;source.timers[0]=source.timers[1]=0;
    } else source.flags23c&=~0x10000000u;
    if(frame.suppressCaptureObjects)frame.suppressCaptureObjects();
    a.flags244|=0x10;a.callbacks260={};a.override27c={};
    a.bodyState128=a.bodyLatch12c=0;
    a.timers[0]=a.timers[1]=a.timers[23]=source.timers[23]=0;
    body.timeline.stopMotion();
    registry[1]=0;registry[10]=0;
    a.callbacks260[3]=registry[3];
    if(weaponLoss) {
        loseWeapon();
        a.pendingTable=2;a.pendingIndex=hanzo?62:iceBreak?69:71;a.request18c=1;a.flags248|=0x20;
        return;
    }
    const int unarmed=!(a.flags23c&0x1000);
    if(hanzo&&slot!=16) {
        enterHanzoThrowPhase(body,a,context,frame);
        GroundStateRuntime::captureBody(sourceBody,source);return;
    }
    if(paired) {
        splitAnchor(body,sourceBody);registry[4]=registry[5]=0;
        queue(a,(hanzo?1325:slot==16?1310:1307)+unarmed);
        queue(source,slot==16?(hanzo?592:571)+!(source.flags23c&0x1000):682);
        if(slot==16) {
            // 166db0 latches motion kind 5..8 from the queued victim ACT.
            const auto& motion=body.actionRecord(a.queuedActionA3c,0).motion;
            if(motion.kind>=5&&motion.kind<=8){registry[4]=uint32_t(motion.values[0])<<16;registry[5]=uint32_t(motion.values[1])<<16;}
            callback(a,0x165cc0,2,0);
        } else {
            callback(a,0x169a50,2,5);callback(source,0x169a50,0,0);
        }
    } else {
        queue(a,1299+(slot-1)*2+unarmed);
        if(slot==1||slot==2) {
            const float x=sourceBody.timeline.motion().x;
            body.timeline.setPosition(shifted(x,(sourceBody.timeline.clock().objectFlags&0x80000)?-48.f:48.f),body.timeline.motion().y);
        }
        callback(a,0x169a50,slot==3?2:0,slot==3?5:4);
    }
    GroundStateRuntime::captureBody(sourceBody,source);
}

bool updateNakoruruThrowLanding(PlayerObject& body,StateEntryActor& a) {
    if(!touchedGround(body,a.queuedActionA3c))return false;
    auto& count=a.callbacks260[5];
    if(count>0&&!landingReady(body,a.queuedActionA3c))return false;
    if(count>1){--count;return false;}
    if(actionEnded(body,a.queuedActionA3c))return true;
    callback(a,0x169a50,1,0);
    return false;
}
}
