#include "knockdown.hpp"
#include "action_selection.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
void queueBody(PlayerObject& object,unsigned action,int32_t* actorAction) {
    if(actorAction)*actorAction=int32_t(action);
    else object.request(action);
}
}
void KnockdownPlayback::request(DownedState& a,int table,int index,bool force) {
    a.pendingTable=table;a.pendingIndex=index;
    if(force)a.forceState=true; //14ff80 itself leaves18c untouched.
}
namespace {
// 4e8c50: 12-byte rows (type, armed ACT, lands on back) for damage states
// 62..73 (rows 0..11) and 59/60 (rows 12/13). extract_script_tables.py checks
// this transcription against the ELF. The unarmed ACT is the next one.
struct FallRow {int type;unsigned act;bool back;};
constexpr FallRow fallRows[14]{{0,380,false},{0,382,false},{0,384,false},{0,386,true},{0,388,false},{3,390,true},
    {2,394,false},{1,396,true},{1,398,true},{4,0xffff,false},{0,438,false},{0,440,false},{0,400,false},{0,402,true}};
int fallRow(int state){return state>=62&&state<=73?state-62:state==59||state==60?state-47:-1;}
}
int KnockdownPlayback::fallType(int state) {const int r=fallRow(state);return r<0?-1:fallRows[r].type;}
std::pair<uint32_t,uint32_t> KnockdownPlayback::landingCallbacks(int state) {
    switch(fallType(state)) {
    case 0:return {0x1715b0,0x171640};
    case 1:return {0x1717a0,0x171838};
    case 2:return {0x1719a8,0x171a38};
    case 3:return {0x171c80,0x171d60};
    case 4:return {0x171eb0,0x171f58};
    default:throw std::runtime_error("Unsupported knockdown state");
    }
}
bool KnockdownPlayback::supportsFall(int state) {return fallType(state)>=0;}
bool KnockdownPlayback::backwardFall(int state) {return fallType(state)==1;}
bool KnockdownPlayback::landsOnBack(int state) {
    // The trajectory and the direction on the ground are separate fields:
    // row 13 runs the forward landing callbacks, then the backward get-up.
    const int r=fallRow(state);return r>=0&&fallRows[r].back;
}
unsigned KnockdownPlayback::fallVariant(int state) {
    const int r=fallRow(state);
    if(r<0)throw std::runtime_error("Unsupported knockdown state");
    return unsigned(r);
}
unsigned KnockdownPlayback::fallAction(int state,bool armed) {
    const int r=fallRow(state);
    if(r<0)throw std::runtime_error("Unsupported knockdown state");
    // Type 4 (171eb0) queues its own launch ACT; its row ACT is -1.
    return (fallRows[r].type==4?1294u:fallRows[r].act)+!armed;
}
void KnockdownPlayback::beginHeavy(PlayerObject& o,DownedState& a,ActorTimers& timers,int32_t* actorAction) {
    const auto action=fallAction(a.index,a.flags23c&0x1000);
    a.recoveryA4c=0;stopAtGround(o);timers.set(2,60);
    if(landsOnBack(a.index))a.flags244|=0x8000u;
    else a.flags244&=~0x8000u;
    queueBody(o,action,actorAction);
    const bool wall=fallType(a.index)==3;
    phase=wall?DownedPhase::WallApproach:DownedPhase::FirstLanding;
    if(wall)a.flags244&=~0x20000u; // 171ae8 restores ordinary stage clamping.

}
void KnockdownPlayback::beginDown(PlayerObject& o,DownedState& a,int32_t* actorAction) {
    a.opponentFlagsB8|=2;
    queueBody(o,((a.flags244&0x8000)?50:48)+!(a.flags23c&0x1000),actorAction);phase=DownedPhase::DownWait;
}
void KnockdownPlayback::beginRise() {phase=DownedPhase::RiseQueued;}
void KnockdownPlayback::chooseRecovery(const PlayerObject& o,DownedState& a,const DownedInput& input,GameRandom& random) {
    const auto& m=o.timeline.motion();
    //1720b0 accepts Y==20, but requires strictly negative vertical speed.
    //Once latched, a direction survives subsequent input release until landing.
    if((a.flags23c&0x80)||(a.flags244&0x10)||m.y>20||m.vy>=0||a.recoveryA4c)return;
    if(input.specialInputs&&input.character==19&&input.specialReady){a.recoveryA4c=3;return;}
    if(input.training&&input.controlKind==1&&!(a.flags248&0x20000000)) {
        if(input.trainingAction!=36&&input.trainingAction!=37) {
            int choice=input.trainingRecovery;
            if(choice==3){const int n=random.bounded(100);choice=n<34?3:n<67?2:1;}
            if(choice==1||choice==2)a.recoveryA4c=choice;
        }
        a.flags248|=0x20000000;
    }
    //The manual input check follows training selection and can override it.
    //Actor3c4 is the unmerged BACK predicate at input+100. Calling it
    //forward hides the reversed54/55 choice when connected to real pads.
    if(input.pressRecovery)a.recoveryA4c=input.back100?2:1;
}
bool KnockdownPlayback::requestRecovery(PlayerObject& o,DownedState& a,const DownedInput& input) {
    const int choice=a.recoveryA4c;a.recoveryA4c=0;
    if(choice==1||choice==2) {
        SelectionActor view;view.flags23c=a.flags23c;view.flags248=a.flags248;view.flags24c=a.flags24c;
        view.state194=uint32_t(a.table)|(uint32_t(a.index)<<16);
        const auto c=o.timeline.clock();view.bodyFlags38=c.objectFlags;
        view.x=o.timeline.motion().x;view.opponentX=input.opponentX;view.faceOpponent();
        o.timeline.setObjectFlags(view.bodyFlags38,c.flags104,c.flags108);
        request(a,0,choice==1?54:55);return true;
    }
    if(choice==3){request(a,1,81,true);return true;}
    return false;
}
void KnockdownPlayback::finishDown(DownedState& a,ActorTimers& timers) {
    timers.set(6,3);
    if(a.flags23c&0x80)phase=DownedPhase::Holding;
    else request(a,2,7,true);
}
void KnockdownPlayback::recoverStanding(PlayerObject& o,DownedState& a,const DownedInput& input) {
    const auto c=o.timeline.clock();const float x=o.timeline.motion().x;
    bool turn=(x<input.opponentX&&(c.objectFlags&0x80000))||(x>input.opponentX&&!(c.objectFlags&0x80000));
    bool crouch=a.flags23c&8;
    if(a.table==0) {
        if(a.index>=56&&a.index<=58)crouch=false;
        if(a.index==35)turn=false;
        if(a.index==54||a.index==55)a.flagsB8|=0x20;
    }
    stopAtGround(o);request(a,0,(crouch?1:0)+(turn?4:0));
}
DownedEvents KnockdownPlayback::update(PlayerObject& o,DownedState& a,ActorTimers& timers,const DownedInput& input,GameRandom& random,int32_t* actorAction) {
    DownedEvents events;
    if(phase==DownedPhase::Inactive)return events;
    auto c=o.timeline.clock();o.setFlags(c.flags104|0x2000,c.flags108);
    switch(phase) {
    case DownedPhase::WallApproach: {
        if(!input.wallBounds)throw std::runtime_error("Wall knockdown requires current camera bounds");
        // 14aad8/146a50 truncate X and test either camera edge inclusively.
        // Resource 00 uses the character radius (34) plus the 2-unit margin.
        const int x=int32_t(o.timeline.motion().x);
        const auto [left,right]=*input.wallBounds;
        if(x<=left+36||x>=right-36) {
            a.landingCount253=(a.landingCount253+1)&15;
            queueBody(o,392+!(a.flags23c&0x1000),actorAction);
            phase=DownedPhase::FirstLanding;
        }
        break;
    }
    case DownedPhase::FirstLanding:
        chooseRecovery(o,a,input,random);
        if(fallType(a.index)==4?touchedGround(o):landingReady(o)) {
            if(fallType(a.index)!=4)stopAtGround(o);
            events.dust=true;a.landingCount253=(a.landingCount253+1)&15;
            if(!requestRecovery(o,a,input)) {
                // 171eb0 gives this launch its own bounce ACT at ground contact.
                if(fallType(a.index)==4){stopAtGround(o);queueBody(o,1296+!(a.flags23c&0x1000),actorAction);}
                phase=DownedPhase::SecondLanding;
            }
        }
        break;
    case DownedPhase::SecondLanding:
        if(landingReady(o)){stopAtGround(o);phase=DownedPhase::Finish;}
        break;
    case DownedPhase::Finish:
        c=o.timeline.clock();o.setFlags(c.flags104&~0x100u,c.flags108);
        if(actionEnded(o)) {
            // 169a50 mode 6 preserves the backward fall into lying/rising.
            // 169050 is false for all these resource 00 fall actions.
            if(landsOnBack(a.index))a.flags244|=0x8000u;
            else a.flags244&=~0x8000u;
            request(a,2,16,true);
        }
        break;
    case DownedPhase::DownWait:
        if(actionEnded(o)) {
            const auto& config=input.system;
            if(config.system==6&&!config.descriptor)throw std::runtime_error("Custom recovery needs system descriptor");
            const bool delay=config.system==8||(config.system==6&&(*config.descriptor)[11]==38);
            if(delay&&(input.down||(input.controlKind==1&&input.aiStayDown))) {
                a.flags248&=~0x10000000u;timers.set(30,60);timers.set(29,120);phase=DownedPhase::StayDown;
            } else finishDown(a,timers);
        }
        break;
    case DownedPhase::StayDown:
    case DownedPhase::RiseDelay: {
        //170de8/170ef8 rewinds only the displayed record and its clock.
        //Re-requesting the action would reset completion, motion and flags.
        o.rewindFirstRecord();a.opponentFlags248|=0x04000000;
        if(phase==DownedPhase::StayDown) {
            if(!input.down&&!(input.controlKind==1&&input.aiStayDown))phase=DownedPhase::RiseDelay;
            else if(!timers.decrease(29)){a.flags248|=0x10000000;phase=DownedPhase::RiseDelay;}
        } else if(!timers.decrease(30)) {
            if(a.flags248&0x10000000)events.lifeAdjustment=-10; //14a8d0 health-change request; caller owns mode/handicap gates and healing effect.
            finishDown(a,timers);
        }
        break;
    }
    case DownedPhase::RiseQueued:
        a.opponentFlagsB8|=2;queueBody(o,((a.flags244&0x8000)?54:52)+!(a.flags23c&0x1000),actorAction);
        phase=DownedPhase::Rising;break;
    case DownedPhase::Rising:
        if(actionEnded(o)){recoverStanding(o,a,input);timers.clear(2);}break;
    case DownedPhase::Holding:
        c=o.timeline.clock();o.setFlags(c.flags104&~0x100u,c.flags108);break;
    default:break;
    }
    return events;
}
}
