#include "contact_trial.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ss6 {
namespace {
// Keyboard bindings at the software-pad boundary. The selector reads raw
// button edges 0 and 2 plus the current down direction (177310 / 150620).
constexpr uint32_t lightButton=0x100, heavyButton=0x400, downDirection=0x20;
constexpr InputMapping slashMapping{{lightButton,0,heavyButton}};
}
ContactTrial::ContactTrial(const std::filesystem::path& assets):effects(assets),bank_(assets,true),judgments_(assets),
    collisions_(assets),combat_(assets),damage_(assets),reactions_(assets),ordinary_(assets),entries_(assets),selection_(assets) { reset(); }
void ContactTrial::reset() {
    for (unsigned i=0;i<2;++i) {
        actors_[i]=std::make_unique<TrialActor>(bank_);
        auto& a=*actors_[i];
        // 0x149008 spawn coordinates, 0x14f0d0 system-0 sword initialization.
        a.object.timeline.setPosition(i ? 400 : 240,0);
        a.object.timeline.setObjectFlags(0x10000000|(i ? 0x80000 : 0),0x200,0);
        a.damage.swordCurrent=a.damage.swordMaximum=100*256;
        a.expectedMirror=i!=0;
        a.history.reset(ActorHistory::capture(a.object));
        for(auto& im:a.afterimages)im.update(a.history,0);
    }
    camera=StageCamera{};contacts.clear();updates=0;winner=-1;knockoutPreview=false;
    roundState=pendingRoundState=4;roundBodiesReady=roundPresentationReady=roundEndingReady=false;effects.reset();
    battlePause=BattlePause{};
    match=MatchProgress{};
    battleTimers=BattleTimers{};
    random_={};discardAttackPresses();
    continueRounds=matchFinished=firstRoundIntroduction=false;
}
void ContactTrial::enableRoundContinuation() {
    if(updates||knockoutPreview)throw std::runtime_error("Round continuation requires an unstarted battle fixture");
    continueRounds=true;
}
void ContactTrial::startMatch() {
    if(updates||knockoutPreview||effects.openingActive())throw std::runtime_error("Match requires an unstarted battle");
    continueRounds=firstRoundIntroduction=true;
    roundState=-1;pendingRoundState=0;
    for(auto& a:actors_)a->reaction.flags24c=roundInputFlags(a->reaction.flags24c,roundState,0);
}
void ContactTrial::setWinRequirement(unsigned wins) {
    if(updates||wins<1||wins>3)throw std::runtime_error("Win requirement needs an unstarted fixture and1..3wins");
    for(auto& p:match.players)p.requiredWins=int32_t(wins);
}
void ContactTrial::resetActorForRound(unsigned i,bool first) {
    auto& a=*actors_.at(i);auto& t=a.object.timeline;
    a.life.life=a.life.maximum=200;a.life.pendingDamage=0;a.life.y=0;
    RoundActorFlags flags{a.life.flags23c,a.flags240,a.reaction.flags244,a.damage.flags248,a.reaction.flags24c};
    flags.resetRound();a.life.flags23c=flags.flags23c;a.flags240=flags.flags240;
    a.reaction.flags244=flags.flags244;a.reaction.flags24c=flags.flags24c;
    a.damage.flags248=flags.flags248|0x1000; //149db8 force the new state's action
    a.damage.flags23c=a.life.flags23c;a.damage.life=200;a.damage.armed=true;
    damage_.resetOrdinaryRoundMeters(a.damage);a.timers.resetRound();a.delta=256;
    const auto c=t.clock();
    //14b190 also initializes the rage pulse at old timer16==0. The full
    // per-tick color modulation is still outside this muted battle fixture.
    uint32_t presentation=(c.objectFlags&~uint32_t(0x40890000))|(i?0x80000:0);
    if(a.damage.rageState==1){presentation|=0x40010000;a.timers.values[16]=256;}
    t.setObjectFlags(presentation,
        (c.flags104&~uint32_t(0x72|0x20000))|0x2000,c.flags108&~uint32_t(0xe00));
    t.stopMotion();t.setPosition(i?400:240,0);
    a.object.pendingFlags&=~uint16_t(1);
    a.table=0;a.state=first?39:0;a.stateFlags=first?0:0x9e;
    a.reaction.previousReaction=255;a.reaction.secondaryReaction=0;a.reaction.heavyReaction=false;
    a.reaction.pendingTable=a.reaction.pendingState=-1;a.reaction.forceState=false;a.reaction.stateTable=0;
    a.life.conditions=1; //151298, normal0 descriptor's condition-set0
    a.life.queuedAction=first?492:standingIdleAction(a.life.life,a.damage.rageState,true);
    a.roundActionQueued=true;a.queuedStateFlags=-1;
    a.knockout={};a.ending={};a.victoryRequested=false;a.endingStateRequested=-1;slashPresses_[i]=0;
    a.knockdown={};a.downed={};a.downEntryQueued=false;
    a.expectedMirror=i!=0;
    if(first) {
        a.object.markActorActionPending();
        //14df00 suppresses actor1's duplicate voice for equal characters.
        if(i==1){const auto f=t.clock();a.object.setFlags(f.flags104|0x200,f.flags108);}
    }
    //149008 fills history before149918 commits the pending idle action.
    // Keeping the old clip here is intentional; replacing the body loses it.
    a.history.reset(ActorHistory::capture(a.object));a.afterimages=makeActorAfterimages();
}
void ContactTrial::beginNextRound() {
    camera=StageCamera{};battleTimers=BattleTimers{};effects.reset();contacts.clear();
    winner=-1;match.result={};roundBodiesReady=roundPresentationReady=roundEndingReady=false;
    const bool first=firstRoundIntroduction&&match.roundIndex==0;
    for(unsigned i=0;i<2;++i){match.players[i].resetRound();resetActorForRound(i,first);}
    if(first)battleTimers.set(2,60); //13fd80 first-round gate overlaps introduction playback
    //143430 state0 calls13fd80 and143708 in the SAME entry, and publishes
    // the resulting state1. A separate state0 update would add a false tick.
    roundState=pendingRoundState=1;camera.appendCommand(0,0);
}
void ContactTrial::startOpeningFixture(unsigned label) {
    if(updates||knockoutPreview||effects.openingActive())
        throw std::runtime_error("Opening fixture requires an unstarted battle");
    effects.opening(label);
    // Supply the state3 entry boundary explicitly.13fd80/149008 and the
    // first-round character introductions are not replaced by this fixture.
    roundState=pendingRoundState=3;match.roundIndex=int32_t(label)-1;
    discardAttackPresses();
    for(auto& a:actors_) {
        a->reaction.flags24c=roundInputFlags(a->reaction.flags24c,3,0);
    }
}
void ContactTrial::startKnockoutPreview(unsigned player,unsigned action) {
    if (player>1 || (action!=382&&action!=383&&(action<400||action>403)))
        throw std::runtime_error("KO preview admits actions382/383/400..403");
    reset();knockoutPreview=true;
    auto& a=*actors_[player];
    const bool airborne=action==382||action==383;
    a.life.life=0;a.life.flags23c=0x80|((action&1) ? 0 : 0x1000)|(airborne ? 0x10 : 0);
    a.object.timeline.setPosition(a.object.timeline.motion().x,airborne ? 64 : 0);
    enter(player,2,airborne ? 31 : 30,action,false);
    a.knockout.begin(a.object,a.life.flags23c,airborne ? 2 : (action-400)/2);
    a.object.commitRequested();
}
void ContactTrial::place(float left,float right) {
    if (!std::isfinite(left)||!std::isfinite(right)) throw std::runtime_error("Invalid fixture positions");
    actors_[0]->object.timeline.setPosition(left,0);actors_[1]->object.timeline.setPosition(right,0);
    faceOpponent(0);faceOpponent(1);
}
void ContactTrial::setInitialLife(unsigned player,int life) {
    if (player>1||updates||life<1||life>200||knockoutPreview)
        throw std::runtime_error("Initial life requires an unstarted battle fixture, player0/1 and life1..200");
    actors_[player]->life.life=life;
}
void ContactTrial::startHeavyHurtFixture(unsigned player) {
    if(player>1||updates||knockoutPreview||firstRoundIntroduction||effects.openingActive())
        throw std::runtime_error("Heavy-hurt setup requires an unstarted ordinary battle fixture");
    auto& a=*actors_[player];enter(player,2,34,342,true);
    a.life.flags23c=(a.life.flags23c&~0xe0fu)|4;
    a.reaction.previousReaction=34;a.reaction.heavyReaction=true;
    a.object.commitRequested();
}
void ContactTrial::faceOpponent(unsigned i) {
    auto& a=*actors_[i];auto& timeline=a.object.timeline;const auto& c=timeline.clock();
    uint32_t flags=c.objectFlags&~uint32_t(0x80000);
    const float other=actors_[1-i]->object.timeline.motion().x;
    // 0x14a978 retains the old facing at equal X. This direct state-entry
    // helper still does not replace the original turn-animation callbacks.
    if (timeline.motion().x>other||(timeline.motion().x==other&&(c.objectFlags&0x80000))) flags|=0x80000;
    timeline.setObjectFlags(flags,c.flags104,c.flags108);
}
void ContactTrial::command(unsigned i,TrialCommand input) {
    auto& a=*actors_.at(i);
    if (input==TrialCommand::LightSlash) slashPresses_[i]|=lightButton;
    else if (input==TrialCommand::HeavySlash) slashPresses_[i]|=heavyButton;
    else a.command=input;
}
void ContactTrial::enter(unsigned i,int table,int state,unsigned action,bool stop,bool deferAction) {
    auto& a=*actors_[i];
    //A contact can interrupt the gap between recovery-state commit and its
    //next-visit idle action. The old idle must not replace the new hurt/KO.
    a.roundActionQueued=false;a.queuedStateFlags=-1;a.life.queuedAction=-1;
    //A new reaction/KO replaces the old callback. Retaining a downed
    //request would otherwise resurrect its get-up after a fatal interruption.
    a.knockdown={};a.downed.pendingTable=a.downed.pendingIndex=-1;a.downed.forceState=false;
    a.downEntryQueued=table==2&&(state==64||state==16||state==7);
    // 0x149348: only leaving attack table 1 starts this 20-call wait.
    // Staying in table 1 does not continually postpone sword recovery.
    if (a.table==1&&table!=1) a.damage.swordWait=20;
    a.table=int16_t(table);a.state=int16_t(state);
    // 0x14b798 loads byte0 from the selected original state descriptor.
    // Near/far descriptors also carry the attack strength used by damage.
    const bool farAttack=action==186||action==190||action==192||action==196;
    a.stateFlags=table==2 ? uint8_t(reactions_.descriptor(unsigned(state)).flags) :
        table==1 ? entries_.descriptor(1,unsigned(state),0,farAttack?2:0)[0] :
        (state==41||state==52) ? 0 : (state>=25&&state<=30) ? 0x10 : (state==6||state==7) ? 0x9c : 0x9e;
    a.damage.attackStrength=(a.stateFlags&4)?2:(a.stateFlags&2)?1:0;
    a.reaction.stateTable=a.table;
    a.life.flags23c&=~uint32_t(0x40000000|0x100);
    if (table==0&&state!=52&&state!=41) {
        // Ordinary 0x16a8f8 pose18/19 clears the same posture/motion bits.
        a.life.flags23c=(a.life.flags23c&0xfffff1f0)|((state==1||state==7||(state>=28&&state<=30)) ? 8 : 0);
        //149d08 ->152220 clears the contact history for normal-state entry.
        a.reaction.previousReaction=255;a.reaction.heavyReaction=false;
        a.downed.landingCount253=0;
    } else if (table==1) {
        //Original standing/crouching descriptors use pose3/5. Posture must
        //also feed hurt and clash selection; it is not just a visual change.
        const bool crouch=state==1||state==9;
        a.life.flags23c=(a.life.flags23c&0xfffff1f0)|(crouch?9:1);
        a.reaction.previousReaction=255;a.reaction.heavyReaction=false;
        a.downed.landingCount253=0;
    }
    auto& timeline=a.object.timeline;const auto c=timeline.clock();
    timeline.setObjectFlags(c.objectFlags,c.flags104&~uint32_t(0x72|0x20000),c.flags108&~uint32_t(0xe00));
    if (stop) { timeline.stopMotion();timeline.setPosition(timeline.motion().x,std::max(0.0f,timeline.motion().y)); }
    if(table<2) {
        const auto d=entries_.descriptor(unsigned(table),unsigned(state),0,farAttack?2:0);
        StateEntryActor view;StateEntryContext context;view.velocityX50=timeline.motion().vx;
        entries_.conditions(view,context,d[table==1?3:2]);a.life.conditions=view.conditions15c[1];
        actors_[1-i]->downed.flagsB8|=context.opponentFlagsB8;
    }
    if(a.downEntryQueued) {
        //Use the original descriptor pose/conditions. Damage64 has pose2
        //(retain motion until171418), whereas16/7 have pose0 (ground/stop).
        const auto d=entries_.descriptor(2,unsigned(state),0);
        StateEntryActor view;StateEntryContext context;
        view.flags23c=a.life.flags23c;view.bodyFlags104=timeline.clock().flags104;
        auto m=timeline.motion();view.x=m.x;view.y=m.y;
        view.offsetX4c=m.dx;view.velocityX50=m.vx;view.accelerationX54=m.ax;
        view.offsetY58=m.dy;view.velocityY5c=m.vy;view.accelerationY60=m.ay;
        entries_.pose(view,d[10]);entries_.conditions(view,context,d[11]);
        a.life.flags23c=view.flags23c;a.life.conditions=view.conditions15c[1];
        m.dx=view.offsetX4c;m.vx=view.velocityX50;m.ax=view.accelerationX54;
        m.dy=view.offsetY58;m.vy=view.velocityY5c;m.ay=view.accelerationY60;m.y=view.y;
        timeline.setMotion(m);a.object.setFlags(view.bodyFlags104,timeline.clock().flags108);
        actors_[1-i]->downed.flagsB8|=context.opponentFlagsB8;
    }
    //170690 only installs1706c0. Damage7 must keep the old lying clip
    //until that callback runs on the next visit and requests52/54.
    if(!deferAction&&!(table==2&&state==7))a.object.request(action);
    a.timers.clear(3);a.timers.clear(4);a.timers.clear(15);
}
void ContactTrial::downedCallback(unsigned i) {
    auto& a=*actors_[i];auto& other=*actors_[1-i];auto& d=a.downed;
    if(d.pendingTable!=-1) {
        const int table=d.pendingTable,state=d.pendingIndex;
        if(table==2&&(state==16||state==7))
            enter(i,table,state,state==16?48:52,false);
        else if(table==0&&(state==0||state==1)) {
            enter(i,0,state,state==1?4:standingIdleAction(a.life.life,a.damage.rageState,true),true);
            return;
        } else throw std::runtime_error("Recovery turn/roll request outside direct-command trial");
    }
    d.flags23c=a.life.flags23c;d.flags244=a.reaction.flags244;d.flags248=a.damage.flags248;
    d.flags24c=a.reaction.flags24c;d.table=a.table;d.index=a.state;
    d.opponentFlagsB8=other.downed.flagsB8;d.opponentFlags248=other.damage.flags248;
    DownedInput input;input.opponentX=other.object.timeline.motion().x;
    input.down=a.command==TrialCommand::CrouchGuard||a.command==TrialCommand::Crouch;
    //The fixture's command keys are not1720b0's recovery input producer.
    //System0's ordinary automatic get-up is the admitted live path.
    if(a.downEntryQueued) {
        a.downEntryQueued=false;
        //169760 excludes16/7 from persistent damage history;149d08 then
        //calls152220 before dispatching their entry, clearing250..25f.
        if(a.state==16||a.state==7) {
            d.landingCount253=0;a.reaction.previousReaction=255;
            a.reaction.secondaryReaction=0;a.reaction.heavyReaction=false;
        }
        const auto c=a.object.timeline.clock();a.object.setFlags(c.flags104|0x2000,c.flags108);
        if(a.state==64)a.knockdown.beginHeavy(a.object,d,a.timers);
        else if(a.state==16)a.knockdown.beginDown(a.object,d);
        else a.knockdown.beginRise();
    } else {
        const auto events=a.knockdown.update(a.object,d,a.timers,input,random_);
        if(events.dust){++a.landingDustEvents;effects.landing(a.object.timeline.motion().x,a.object.timeline.clock().objectFlags&0x80000);}
        if(events.lifeAdjustment)throw std::runtime_error("Delayed-rise healing outside system0 trial");
    }
    a.life.flags23c=d.flags23c;a.reaction.flags244=d.flags244;a.damage.flags248=d.flags248;
    other.downed.flagsB8=d.opponentFlagsB8;other.damage.flags248=d.opponentFlags248;
    if(d.pendingTable!=-1) {
        //149d08's tail commits the actor state/pose NOW, but registers its
        //new action callback on the NEXT visit. The body keeps its old clip
        //and14b798's old descriptor byte through the intervening frame pass.
        const int table=d.pendingTable,state=d.pendingIndex;
        if(!((table==2&&(state==16||state==7))||(table==0&&(state==0||state==1))))
            throw std::runtime_error("Recovery turn/roll request outside direct-command trial");
        const auto metadata=a.stateFlags;const auto strength=a.damage.attackStrength;
        enter(i,table,state,0,table==0,true);
        a.stateFlags=metadata;a.damage.attackStrength=strength;
        d.pendingTable=table;d.pendingIndex=state;
    }
}
CollisionPlayer ContactTrial::collisionPlayer(unsigned i) const {
    const auto& a=*actors_[i];const auto& t=a.object.timeline;const auto& c=t.clock();
    CollisionPlayer p;
    p.owner=i;p.objectFlags104=c.flags104;p.objectFlags108=c.flags108;p.actorFlags=a.life.flags23c;
    p.stateTable=a.table;p.stateIndex=a.state;
    p.stateFlags=a.stateFlags;
    p.x=t.motion().x;p.y=t.motion().y;p.mirrorX=c.objectFlags&0x80000;
    p.judgmentFlags=t.record().judgmentFlags;p.judgments=judgments_.forRecord(t.record());
    return p;
}
bool ContactTrial::startGroundSlash(unsigned i,uint32_t pressed) {
    auto& a=*actors_[i];
    auto& timeline=a.object.timeline;
    const auto clock=timeline.clock();
    const bool down=a.command==TrialCommand::Crouch||a.command==TrialCommand::CrouchGuard;
    InputSamplingContext context;
    context.facing=a.expectedMirror;
    context.actualFacing=(clock.objectFlags&0x80000)!=0;
    slashSampler_.sampleRaw(i,{down?downDirection:0u,pressed},slashMapping,context);
    // These ground slashes only use the raw edge and down fields. Motion
    // commands and cancel windows need the full persistent input dispatcher.
    ActorCommandInput buttons{};
    buttons.sampledFeatures=slashSampler_.features;
    SelectionActor view;
    view.state194=(uint32_t(a.state)<<16)|uint16_t(a.table);
    view.flags23c=a.life.flags23c;view.flags244=a.reaction.flags244;
    view.flags248=a.damage.flags248;view.flags24c=a.reaction.flags24c;
    view.bodyFlags38=clock.objectFlags;view.x=timeline.motion().x;
    view.opponentX=actors_[1-i]->object.timeline.motion().x;
    if(!selection_.requestAttack(view,buttons))return false;

    const auto state=view.pendingIndex;
    if(state!=0&&state!=1&&state!=8&&state!=9)
        throw std::runtime_error("Unexpected grounded light/heavy slash state");
    timeline.setObjectFlags(view.bodyFlags38,clock.flags104,clock.flags108);
    // 16acf8 uses the near/far flag published before the input callback.
    const unsigned action=(state&1?191:185)+(state>=8?4:0)+bool(view.flags244&0x4000);
    enter(i,1,state,action,true);
    return true;
}
void ContactTrial::callbacks(unsigned i,uint32_t pressed) {
    auto& a=*actors_[i];auto& t=a.object.timeline;
    if(a.roundActionQueued) {
        a.roundActionQueued=false;
        if(a.queuedStateFlags!=-1){a.stateFlags=uint8_t(a.queuedStateFlags);a.queuedStateFlags=-1;}
        //149d08 runs the type0 prefix again after the animation pass,
        //including a freshly queued entry.149008's earlier bit is already
        //cleared by11d730; retaining it here protects the first ACT jump.
        const auto c=t.clock();a.object.setFlags(c.flags104|0x2000,c.flags108);
        if(a.state==39)a.ending.beginIntroduction(a.object,a.reaction.flags244,i);
        else a.object.request(unsigned(a.life.queuedAction),true);
        a.life.queuedAction=-1;a.damage.flags248&=~uint32_t(0x1000);return;
    }
    const bool locked=a.reaction.flags24c&1;
    // 0x14b880 compares the OLD value returned by increasing timer15.
    // Comparing the new value would advance its recovery fallback by a tick.
    const int32_t previousTimer=a.timers.increase(15);
    const int ko=knockoutRequest(a.life.flags23c,a.reaction.flags244,a.table,a.state,previousTimer,locked);
    if (previousTimer>0x257ff) a.timers.clear(15);
    if (ko>=0) {
        enter(i,2,ko,ko==31 ? 382 : 400,false);
        a.knockout.begin(a.object,a.life.flags23c,ko==31 ? 2 : 0);
        return;
    }
    if(a.endingStateRequested!=-1) {
        const int state=a.endingStateRequested;a.endingStateRequested=-1;
        a.knockout.phase=KnockoutPhase::Inactive;
        if(state==15) {
            enter(i,2,15,((a.reaction.flags244&0x8000) ? 50 : 48)+!(a.life.flags23c&0x1000),false);
            a.life.flags23c|=0x80; // 1751d0 damage15 entry.
            a.ending.beginLoser(a.object,a.life.flags23c,a.reaction.flags244);
        } else {
            faceOpponent(i);
            const bool final=match.players[i].complete();
            enter(i,0,41,(a.life.life>=100 ? 495 : 497)+(final?4:0)+!(a.life.flags23c&0x1000),false);
            a.ending.beginWinner(a.object,a.life.flags23c,a.reaction.flags244,a.life.life,final);
        }
        return;
    }
    if(a.ending.phase!=EndingPhase::Inactive) {
        a.ending.update(a.object,a.reaction.flags244,&a.timers,i);
        return;
    }
    if (a.knockout.phase!=KnockoutPhase::Inactive) {
        if (a.knockout.update(a.object)) {
            ++a.landingDustEvents;
            effects.landing(t.motion().x,t.clock().objectFlags&0x80000);
        }
        return;
    }
    if(a.downEntryQueued||a.downed.pendingTable!=-1||a.knockdown.phase!=DownedPhase::Inactive) {
        downedCallback(i);return;
    }
    if (a.victoryRequested) {
        a.victoryRequested=false;faceOpponent(i);
        enter(i,0,52,(a.life.flags23c&0x1000) ? 493 : 494,false);
        a.object.pendingFlags|=1; // 0x174928 restarts the paired action.
        return;
    }
    if (a.table==0&&a.state==52) {
        // 0x169a50 case4 keeps the completed winner pose. Callback type0
        // reasserts2000; returning to idle here would permit a fresh attack.
        auto c=t.clock();a.object.setFlags(c.flags104|0x2000,c.flags108);
        if (actionEnded(a.object)) a.object.setFlags((c.flags104|0x2000)&~uint32_t(0x100),c.flags108);
        return;
    }
    bool ended=t.clock().endReached&&!(t.clock().flags104&1);
    if(a.table==2&&a.state>=32&&a.state<50) {
        //170890 calls1699f8 on EVERY visit. Heavy reaction342 contains a
        //zero-duration record; waiting for endReached would freeze it forever.
        //The type2 prefix also suppresses the crouching clip's ACT jump.
        //Recovery belongs to the actor callback, not a premature body jump.
        ended=updateGroundReaction(a.object);
    }
    if (a.table==1||a.table==2||(a.table==0&&a.state>=25&&a.state<=30)) {
        if (!ended) return;
        faceOpponent(i);
        const bool guard=a.table==2&&a.state<6;
        const bool crouch=a.life.flags23c&8;
        if((a.table==1&&(a.state==1||a.state==9))||(a.table==0&&a.state>=28&&a.state<=30)) {
            //191/192/195/196 first ACT-jump to4.16ae60 sees completion on
            //the following visit;149d08 then commits normal1, while its
            //forced idle request/metadata wait until the next actor visit.
            const auto oldMetadata=a.stateFlags;
            enter(i,0,1,4,true,true);
            a.queuedStateFlags=a.stateFlags;a.stateFlags=oldMetadata;
            a.roundActionQueued=true;a.life.queuedAction=4;return;
        }
        enter(i,0,guard ? (crouch ? 7 : 6) : (crouch ? 1 : 0),
              guard ? (crouch ? 290 : 286) : (crouch ? 4 : standingIdleAction(a.life.life,a.damage.rageState,true)),true);
        return;
    }
    if (locked) return;
    if (a.timers.values[0]>0) return;
    if (pressed&&startGroundSlash(i,pressed)) return;
    const auto cmd=a.command;
    const unsigned action=cmd==TrialCommand::Forward ? 10 : cmd==TrialCommand::Backward ? 12 :
        cmd==TrialCommand::StandGuard ? 286 : cmd==TrialCommand::CrouchGuard ? 290 : cmd==TrialCommand::Crouch ? 4 : standingIdleAction(a.life.life,a.damage.rageState,true);
    const int state=cmd==TrialCommand::Forward ? 2 : cmd==TrialCommand::Backward ? 3 :
        cmd==TrialCommand::StandGuard ? 6 : cmd==TrialCommand::CrouchGuard ? 7 : cmd==TrialCommand::Crouch ? 1 : 0;
    //Normal0 has no continuing action-selection callback. A meter change
    //does not restart an already playing idle;169d10 runs on state entry.
    if (a.state!=state||(state!=0&&t.action().id()!=action)) { faceOpponent(i);enter(i,0,state,action,true); }
}
void ContactTrial::tick() {
    // Each button edge belongs to exactly one simulation update. Recovery,
    // round changes and the global KO pause may all skip the attack callback.
    const auto pressed=std::exchange(slashPresses_,{});
    // Priority5 effects precede priority50 battle. 1235f8 reads46a924;
    // ordinary KO's 11f588(1) sets46a940 but leaves46a924 zero. Thus KO
    // pauses actors while these tasks continue. New tasks draw next visit.
    effects.update();
    if (knockoutPreview) {
        // Explicit isolated fixture: run the verified KO body callbacks and
        // stage projection while the full actor/round transition is ported.
        ++updates;
        for (auto& a:actors_) a->object.animate(256);
        for (auto& a:actors_) a->object.move(256);
        advanceStage();
        for (auto& a:actors_) {
            a->life.y=a->object.timeline.motion().y;commitLife(a->life,a->timers);
            if (a->knockout.update(a->object)) {
                ++a->landingDustEvents;
                const auto& t=a->object.timeline;
                effects.landing(t.motion().x,t.clock().objectFlags&0x80000);
            }
        }
        return;
    }
    ++updates;contacts.clear();
    // The original scheduler visits priorities in ascending order: gauge
    // callback 0x11e708 is priority 5, battle coroutine 0x138f48 is 50.
    // Thus gauges see the previous frame's action/JDG state, before contacts.
    for (auto& a:actors_) {
        // 0x11e760 checks battle+0 (requested state), not current state+4.
        // Therefore recovery stops one visit before state5's entry callback.
        if (!ordinaryMetersActive(pendingRoundState,battlePause.paused)) continue;
        const auto c=a->object.timeline.clock();uint32_t f108=c.flags108;
        a->damage.flags23c=a->life.flags23c;
        damage_.advanceOrdinaryMeters(a->damage,a->table,a->state,c.flags104,f108);
        a->object.setFlags(c.flags104,f108);
    }
    if (battlePause.advance()) return;
    ContactRegistry registry;std::array<ContactMarks,2> marks;
    std::array<int,2> pendingClash{-1,-1};
    std::array<CollisionPlayer,2> snapshots;
    for (unsigned i=0;i<2;++i) {
        auto& a=*actors_[i];const auto& c=a.object.timeline.clock();
        marks[i]={i,c.flags104,c.flags108,0};
        registry.add(i,0,a.object.timeline.action().id(),marks[i]);
        a.object.setFlags(marks[i].flags104,marks[i].flags108);
        snapshots[i]=collisionPlayer(i);
        a.reaction.flags23c=a.life.flags23c;
        a.reaction.pendingTable=a.reaction.pendingState=-1;a.reaction.forceState=false;
        a.damage.life=a.life.life;a.damage.flags23c=a.life.flags23c;
        a.damage.flags248&=~uint32_t(0x40);
    }
    for (auto i:registry.objects()) for (auto j:registry.objects())
        if (i!=j) collectContacts(collisions_,snapshots[i],snapshots[j],uint8_t(i),uint8_t(j),contacts);
    orderContacts(contacts);
    for (const auto& event:contacts) {
        const unsigned i=event.a.player,j=event.b.player;
        auto& a=*actors_[i];auto& b=*actors_[j];
        const auto indices=combat_.consumptionIndices(event.route);
        if (contactConsumed(marks[i],indices[0])||contactConsumed(marks[j],indices[1])) continue;
        if (event.route==11) {
            // 0x154bd0 normal two-player push; exceptional action IDs are not
            // admitted by this fixture. Width is the original intersection.
            auto ma=a.object.timeline.motion(),mb=b.object.timeline.motion();
            PushActor pa{ma.x,ma.y,a.damage.flags248},pb{mb.x,mb.y,b.damage.flags248};
            ordinaryPush(pa,pb,event.width);ma.x=pa.x;mb.x=pb.x;
            a.object.timeline.setMotion(ma);b.object.timeline.setMotion(mb);
            a.damage.flags248=pa.flags248;b.damage.flags248=pb.flags248;
        } else if (event.route==8) {
            // Ordinary raw33/raw33 weapon clash: 0x1555d8 queues 0x14d070
            // for both actors. Spark effect8 and audio remain part of the
            // fixture's explicitly unported contact presentation.
            if (event.a.fields.type!=33||event.b.fields.type!=33)
                throw std::runtime_error("Non-ordinary clash outside fixture");
            for (const unsigned slot:{i,j}) {
                auto& actor=*actors_[slot];
                const unsigned strength=(actor.stateFlags&4)?2:(actor.stateFlags&2)?1:0;
                auto request=queueWeaponClash(actor.life.flags23c,actor.table,actor.state,strength,true);
                if (request.state<25||request.state>30)throw std::runtime_error("Non-grounded clash outside fixture");
                actor.damage.flags23c=request.flags23c;pendingClash[slot]=request.state;
            }
        } else if (event.route==7) {
            DefenseSnapshot defense;defense.actorFlags23c=b.life.flags23c;
            defense.stateTable=b.table;defense.stateIndex=b.state;
            defense.stateFlags=b.stateFlags;
            defense.field3C0=b.command==TrialCommand::CrouchGuard||b.command==TrialCommand::Crouch;
            const auto decision=inspectContactDecision(combat_,event,snapshots[i],defense,marks[i],marks[j]);
            if (decision.kind==DecisionKind::AlreadyConsumed||decision.kind==DecisionKind::SourceBlocked) continue;
            if (event.a.fields.type!=10&&event.a.fields.type!=12) throw std::runtime_error("Trial only admits standing light/heavy contacts");
            if (decision.kind==DecisionKind::HitBranch) {
                b.life.pendingDamage+=damage_.applyOrdinaryContact(event.auxiliary,a.damage,b.damage,false);
                const unsigned part=event.b.fields.type>=1&&event.b.fields.type<=3 ? event.b.fields.type-1 : 0;
                reactions_.applyGroundHit(b.reaction,a.timers,b.timers,event.a.fields.type,part,event.b.fields.low7&1,false,
                                         a.damage.attackStrength,a.damage.flags248);
                marks[j].consumed|=2;marks[i].consumed|=4;++a.hitCount;
            } else if (decision.kind==DecisionKind::GuardBranch) {
                damage_.applyOrdinaryContact(event.auxiliary,a.damage,b.damage,true);
                // 0x155d50: armed target + no source108100 => zero chip.
                // Other chip conditions require their own admitted handler.
                if (marks[i].flags108&0x100) throw std::runtime_error("Chip-damage attack outside fixture");
                unsigned ignored=0;
                reactions_.applyGuard(b.reaction,a.timers,b.timers,decision.defense,unsigned(event.extra),ignored);
                marks[i].consumed|=8;++a.guardCount;
            } else throw std::runtime_error("Unresolved ordinary hit branch");
        } else throw std::runtime_error("Contact route "+std::to_string(event.route)+" outside integration fixture: "+
                                       std::to_string(event.a.fields.type)+" / "+std::to_string(event.b.fields.type));
        markContactConsumed(marks[i],indices[0]);markContactConsumed(marks[j],indices[1]);
    }
    for (unsigned i=0;i<2;++i) {
        auto& a=*actors_[i];auto& t=a.object.timeline;
        a.object.setFlags(marks[i].flags104,marks[i].flags108);
        // 0x153558 post-contact marks. Character-specific hit effects remain
        // outside this integration fixture and are listed in its scope notes.
        uint32_t flags=t.clock().flags104;
        if (marks[i].consumed&0x10) flags|=0x200000;
        else if (marks[i].consumed&4) flags|=0x40000;
        else if (marks[i].consumed&8) flags|=0x80000;
        a.object.setFlags(flags,t.clock().flags108);
        a.life.flags23c=a.damage.flags23c;
        if (pendingClash[i]>=0) {
            // 0x169c28 selects action141 with the weapon-clash flag, faces
            // the opponent, stops motion and waits for 0x169a50 completion.
            //169c28's weapon-clash bit chooses141+strength for BOTH
            //postures; crouch still selects logical states28..30/pose19.
            faceOpponent(i);enter(i,0,pendingClash[i],141+unsigned((pendingClash[i]-25)%3),true);
        } else if (a.reaction.forceState) {
            const unsigned state=unsigned(a.reaction.pendingState);
            unsigned action=state<3 ? 288 : state<6 ? 292 : reactions_.ordinaryAction(state,true);
            if (!action) throw std::runtime_error("Reaction action outside fixture");
            enter(i,2,int(state),action,false);
            auto motion=t.motion();uint32_t f=t.clock().flags108;
            reactions_.startRetreat(state,motion,f,0);t.setMotion(motion);
            a.object.setFlags(t.clock().flags104,f);
        }
        auto f=t.clock().flags104&~uint32_t(0x30);
        a.object.pendingFlags&=~uint16_t(6);
        if (a.timers.values[0]>0) { f|=0x30;a.object.pendingFlags|=6;a.life.flags23c|=0x100; }
        else a.life.flags23c&=~uint32_t(0x100);
        a.object.setFlags(f,t.clock().flags108);
    }
    advanceRoundBodies();
    // Matches the original pass ordering. Individual routines are validated;
    // the complete fixture still needs an original full-frame trace.
    for (auto& a:actors_) a->object.animate(a->delta);
    for (auto& a:actors_) a->object.move(a->delta);
    advanceStage();
    for (unsigned i=0;i<2;++i) {
        auto& a=actors_[i];const auto& other=*actors_[1-i];
        a->reaction.flags244=ordinaryStateGates(a->reaction.flags244,a->life.flags23c,a->table,a->state,
            a->stateFlags,a->object.timeline.clock().flags108,a->timers.values[5],
            ordinary_.far(playerDistance(a->object.timeline.motion().x,other.object.timeline.motion().x),
                          a->life.flags23c&0x1000,other.life.flags23c&0x1000));
        a->delta=a->timers.values[1] ? 128 : 256;
        a->timers.delta=int32_t(a->delta);a->timers.advanceContactTimers();
        a->life.y=a->object.timeline.motion().y;commitLife(a->life,a->timers);
    }
    for (auto& a:actors_) a->reaction.flags24c=roundInputFlags(a->reaction.flags24c,roundState,0);
    for (unsigned i=0;i<2;++i) callbacks(i,pressed[i]);
    for (auto& a:actors_) {
        a->history.update(ActorHistory::capture(a->object),int32_t(a->delta));
        for(auto& im:a->afterimages)im.update(a->history,a->table);
        a->object.commitRequested();
    }
}
void ContactTrial::advanceRoundBodies() {
    //1435d8 advances timer2 before any entry/update. Entry clears timer1;
    // only a regular update increments it. These are battle-clock values,
    // not outer updates (which also include the40-call global KO freeze).
    if(battleTimers.decrease(2)>0)return;
    const bool entry=roundState!=pendingRoundState;
    updateRoundBodies();
    if(entry)battleTimers.clear(1);
    else battleTimers.increase(1);
}
void ContactTrial::updateRoundBodies() {
    // 0x1435d8/143430 enter before update and skip the update on entry.
    // Ordinary two-player KO flow, with optional automatic continuation.
    // Body completion cannot substitute for effect or camera completion.
    if (roundState!=pendingRoundState) {
        roundState=pendingRoundState;
        if(roundState==0) {
            beginNextRound();
        } else if(roundState==2) {
            //1438e8 is empty;1438f0 runs on the following dispatcher visit.
        } else if(roundState==3) {
            effects.opening(match.openingLabel());
        } else if(roundState==4) {
            //143b08 clears the camera queue and timer3. The fixture already
            // owns the gauge updater; its requested-state gate admits the
            // next priority5 visit, before this priority50 entry callback.
            camera.commands.clear();battleTimers.set(3,0);
            //13aaf8's sound/replay setup remains outside this muted fixture.
        } else if(roundState==5) {
            const int a=actors_[0]->life.life,b=actors_[1]->life.life;
            match.recordRound({a,b},{actors_[0]->life.maximum,actors_[1]->life.maximum});
            winner=match.result.draw?2:match.result.winner;
            // 0x143f20 ordinary KO/doubleKO; final-match UI16 requests60.
            const bool final=winner<2&&match.players[winner].complete();
            if(final)match.result.ui=16;
            battlePause.request(final?60:40,2);effects.knockout(winner==2,final);battleTimers.set(5,30);
        } else if(roundState==7) {
            beginVictoryCamera(camera,match.result.winner,match.result.draw,
                {actors_[0]->life.flags23c,actors_[1]->life.flags23c});
            for(auto& a:actors_)if(a->life.flags23c&0x80)a->endingStateRequested=15;
        } else if(roundState==8) {
            if(winner<2)actors_[winner]->endingStateRequested=41;
            for(auto& a:actors_)a->reaction.flags244&=~uint32_t(0x200000); //145dc0
            // 1443f0 also schedules announcer audio. Playback remains muted,
            // as documented for this inspector, rather than fake-timed audio.
        } else if(roundState==10) {
            // Original state10 exits the battle to its surrounding menu.
            // This native fixture exposes the same terminal boundary; its
            // local restart control is not a reconstruction of those menus.
            matchFinished=true;
        } else throw std::runtime_error("Round entry outside the ending fixture");
        return;
    }
    if(roundState==10)return;
    if(roundState==1) {
        //143798 waits for both introduction callbacks only in round0.
        //Subsequent rounds intentionally bypass this readiness check.
        if(match.roundIndex==0&&firstRoundIntroduction)
            for(const auto& a:actors_)if(!(a->reaction.flags244&0x40000000))return;
        for(auto& a:actors_) {
            auto c=a->object.timeline.clock();a->object.setFlags(c.flags104&~uint32_t(0x330),c.flags108);
            a->object.pendingFlags&=~uint16_t(6);a->timers.clear(34);
            a->table=a->state=0;a->stateFlags=0x9e;a->ending={};
            a->life.queuedAction=standingIdleAction(a->life.life,a->damage.rageState,true);a->roundActionQueued=true;
        }
        //1438e4 is the branch delay slot: it supplies3 to1438b8.
        // A subsequent round skips state2 (and its26-tick sound delay).
        camera.commands.clear();battleTimers.set(2,30);pendingRoundState=3;return;
    }
    if(roundState==2) {battleTimers.set(2,26);pendingRoundState=3;return;}
    if(roundState==3) {
        //143a38 waits for the shared owner, including callback-created
        // groups. The draw queued on completion survives this state request.
        if(!effects.openingActive())pendingRoundState=4;
        return;
    }
    if (roundState==4) {
        if ((actors_[0]->life.flags23c|actors_[1]->life.flags23c)&0x80) pendingRoundState=5;
        return;
    }
    if(roundState==7||roundState==8) {
        for(auto& a:actors_) {
            const auto c=a->object.timeline.clock();
            a->object.setFlags(c.flags104|0x400000,c.flags108); //145df8
        }
        if(roundState==7) {
            for(auto& a:actors_)a->reaction.flags244|=0x20000;
            if(camera.commandsComplete())pendingRoundState=8;
        } else {
            // 144570 stops at the first incomplete actor. Do not set player1
            // flags early when player0 is still playing its victory clip.
            roundEndingReady=true;
            for(auto& a:actors_) {
                a->reaction.flags244|=0x20000;
                if(!(a->reaction.flags244&0x40000000)) {roundEndingReady=false;break;}
            }
            if(roundEndingReady&&continueRounds) {
                const auto next=match.transition(3,0); // explicit local two-player configuration
                ++match.roundIndex;pendingRoundState=next.state;battleTimers.set(2,next.delay);
            }
        }
        return;
    }
    bool ready=true;
    for (auto& p:actors_) {
        auto& a=*p;
        if (a.life.flags23c&0x80) ready&=!(a.life.flags23c&16)&&actionEnded(a.object);
        else {
            const auto request=victoryRequest(a.life.flags23c,a.reaction.flags244,a.table,a.state,
                actionEnded(a.object),(a.life.conditions&0x70)!=0);
            a.victoryRequested=request==VictoryRequest::Queue;
            ready&=request==VictoryRequest::Ready;
        }
    }
    roundBodiesReady=ready;
    roundPresentationReady=!effects.knockoutActive();
    if(roundBodiesReady&&roundPresentationReady)pendingRoundState=7;
}
void ContactTrial::advanceStage() {
    // 0x1426d8 uses the PREVIOUS camera bounds, then publishes new bounds.
    // Moving the camera before clamping loses the original wall interaction.
    std::array<StageActor,2> stage;
    for (unsigned i=0;i<2;++i) {
        const auto& a=*actors_[i];const auto& t=a.object.timeline;
        stage[i]={t.motion().x,t.motion().y,a.life.flags23c,a.reaction.flags244,t.clock().objectFlags,
            a.reaction.flags24c,a.table,a.state,a.table==2 ? uint8_t(reactions_.descriptor(unsigned(a.state)).flags) : uint8_t(0),a.expectedMirror};
        if (a.object.pendingFlags&0xc0) throw std::runtime_error("Pending camera effect outside ordinary trial");
    }
    updateOrdinaryStage(stage,camera);
    for (unsigned i=0;i<2;++i) {
        auto& a=*actors_[i];a.object.timeline.setPosition(stage[i].x,stage[i].y);
        a.reaction.flags24c=stage[i].flags24c;a.expectedMirror=stage[i].expectedMirror;
    }
}
}
