#include "round_control.hpp"
#include "fighter_roster.hpp"
#include "battle_clock.hpp"
#include "ending_playback.hpp"
#include "round_rules.hpp"
#include "sound_selection.hpp"
#include "object_frame.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
bool skipPressed(const RoundPlayerRef& p) {return p.input.sampledFeatures[0x2c/4]!=0;}
StageEventPlayers stagePlayers(const std::array<RoundPlayerRef,2>& players) {
    return {players[0].body.timeline.motion().x,players[1].body.timeline.motion().x,
        bool(players[0].body.timeline.clock().objectFlags&0x80000)};
}
void keepBodies(const std::array<RoundPlayerRef,2>& players) {
    for(const auto& p:players) {
        const auto clock=p.body.timeline.clock();
        p.body.setFlags(clock.flags104|0x400000,clock.flags108);
        GroundStateRuntime::captureBody(p.body,p.actor);
    }
}
}
void RoundControl::enterRound(BattleRoundInitialization& initialize,GroundStateRuntime& ground,
        BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,BattleEffects& effects,const StageEventRules& events) {
    b.paletteState[0].fill(0xffffffffu);b.paletteState[1].fill(0);b.paletteState[2].fill(0);
    initialize.begin(ground,players,b,effects);
    resetStage(b,players,events);
    b.requestedState=1;enterIntroduction(b,events);
    //The entry publishes the state AFTER its nested requests. Subsequent
    //rounds must not expose transient state0 or run introduction's update
    //during this visit;149918/body commit still belong to the later phase.
    b.currentState=b.requestedState;b.field08=0;b.timers.set(1,0);
}
void RoundControl::resetStage(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,const StageEventRules& events) {
    events.placeRound(b.stageEvent);
    events.request(b.stageEvent,2,true,stagePlayers(players));
}
void RoundControl::enterIntroduction(BattleRoundState& b,const StageEventRules& events) {
    b.camera.commands.clear();b.camera.appendCommand(0,0);
    //Event0 has no positional predicate; later rounds preserve the state
    //requested by the outer reset rather than repeating the first greeting.
    if(b.match.roundIndex==0)events.request(b.stageEvent,0,true,{});
}
void RoundControl::enterOpening(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,
                                const StageEventRules& events,ScheduledOpening& opening,SoundSelection* sound) {
    if(b.match.roundIndex<0)throw std::runtime_error("Opening needs a nonnegative round index");
    const auto label=b.match.openingLabel();
    events.request(b.stageEvent,2,true,stagePlayers(players));
    b.openingOwner30=opening.start(label,b.entry.tasks,b.effectResidency,b.paletteState);
    if(b.match.roundIndex==0) {
        // Jingle 23 in 213ff0 plays resident BVOICE1[49][12] with the music
        // setting, immediately after the spoken prologue. Zero skips key-on.
        const int volume=std::bit_cast<int32_t>(b.audio.streamParameter5a9e78);
        if(sound&&volume!=0)sound->residentJingle(12,volume/512);
        b.voiceGate5850e0=0;
    }
}
void RoundControl::opening(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,const StageEventRules& events) {
    if(!b.entry.tasks.ownerActive(b.openingOwner30)) {
        b.entry.tasks.freeOwner(b.openingOwner30);b.openingOwner30=0;b.requestedState=4;
    }
    //This is an exact fixed-point timer equality, including when the
    //owner just ended. A skipped timer value must not trigger it late.
    if(b.timers.values[1]==(b.match.roundIndex==0?0x8600:0x3900))
        events.request(b.stageEvent,1,true,stagePlayers(players));
}
void RoundControl::combatStageEvent(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,const StageEventRules& events) {
    const auto positions=stagePlayers(players);
    for(unsigned i=0;i<2;++i) {
        auto& a=players[i].actor;const auto& stats=b.match.players[i];
        if((a.flags23c&0x2000)&&a.timers[14]==0) {
            events.request(b.stageEvent,13+int(i),true,positions);
            //The trigger is consumed even if the announcer's active/pending
            //event refuses the request. Retrying next visit changes priority.
            a.flags23c&=~0x2000u;return;
        }
        if(a.fieldA30<stats.previousLife10) {
            events.request(b.stageEvent,(stats.field18?6:4)+int(i),true,positions);return;
        }
    }
    for(unsigned i=0;i<2;++i)if(b.match.players[i].previousPosture14!=int((players[i].actor.flags23c>>3)&1)) {
        events.request(b.stageEvent,2,true,positions);return;
    }
    const bool both=(players[0].actor.flags23c&8)&&(players[1].actor.flags23c&8);
    events.request(b.stageEvent,both?3:2,false,positions);
}
void RoundControl::startStageMusic(BattleRoundState& b,SoundSelection* sound) {
    auto& audio=b.audio;
    audio.streamStart1553b5c=1;
    audio.streamWord1553a40=audio.streamParameter5a9e78;
    audio.requests.push_back({0x170000,audio.streamParameter5a9e78});
    audio.musicActive123a174=1;
    if(sound)sound->startMusic(int(audio.streamParameter5a9e78));
}
void RoundControl::enterCombat(BattleRoundState& b,SoundSelection* sound) {
    BattleGauges::start(b);
    // 143430 supplies the round owner to 13aaf8, which releases the
    // preloaded stream on the first round. Issen forces that same request.
    if(b.match.roundIndex==0)startStageMusic(b,sound);
    b.camera.commands.clear();b.timers.set(3,0);
}
void RoundControl::combat(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,const StageEventRules& events) {
    //13a850 is an actual constant-zero function in this executable.
    //140788 only recognizes exact zero, and only when time is enabled and
    //battle+8 is not exactly1. A timeout returns BEFORE announcer/items.
    if(b.timeExpired()){b.requestedState=5;return;}
    if(b.survival())throw std::runtime_error("Combat control does not support survival");
    for(const auto& p:players)if(p.actor.flags23c&0x80)b.requestedState=5;
    combatStageEvent(b,players,events);
    if(const auto drop=events.items.next(b,stagePlayers(players)))
        b.stageItems.start(drop->kind,drop->targetX,drop->fromRight,b.camera);
}
void RoundControl::snapshotPlayers(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    for(unsigned i=0;i<2;++i) {
        auto& stats=b.match.players[i];stats.previousLife10=players[i].actor.fieldA30;
        stats.previousPosture14=int((players[i].actor.flags23c>>3)&1);
    }
}
void RoundControl::enterEnding(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,
                               ScheduledOpening& captions,const MatchEndingRules& results,SoundSelection* sound) {
    // 123a168 is the network result reporter (sub-mode 6).
    if(b.survival()||b.matchEnd.profileActive123a168)
        throw std::runtime_error("Round end does not support survival or network reporting");
    for(const auto& p:players)if(!playableFighter(p.actor.character)||(p.config.system>5&&p.config.system!=8))
        throw std::runtime_error("Round end requires a supported fighter and spirit");
    BattleGauges::stop(b,players);
    b.match.recordRound({players[0].actor.fieldA30,players[1].actor.fieldA30},
                        {players[0].actor.maximumLifeA34,players[1].actor.maximumLifeA34});
    auto ui=b.match.result.ui;const bool knockout=ui==15||ui==18;
    if(b.match.complete()) {
        results.recordFinal(b,players);
        // A round win keeps the stage track running. The deciding round
        // reaches 143e44 and stops it at KO or timeout, before the victory pose.
        b.matchEnd.continue2c=1;
        if(sound)sound->stopMusic();
        if(ui==15)ui=16;
        if(uint32_t(b.matchEnd.submodeA0)-4>=2)b.matchEnd.endFlagA4=1;
    }
    if(knockout) {
        b.pause.request(ui==16?60:40,2);
        //After11e600,11f450(256,-1) is256 unless globally paused. The
        //original timer5/6 wrapper divides by8 only on that paused branch.
        const int divisor=b.gauges.paused46a940?8:1;
        if(ui==16)b.timers.set(6,30,divisor);
        b.timers.set(5,30,divisor);
    }
    b.paletteState[0].fill(0xffffffffu);b.paletteState[1].fill(0);b.paletteState[2].fill(0);
    b.match.result.ui=ui;b.openingOwner30=captions.startEnding(unsigned(ui),b.entry.tasks,b.effectResidency);
}
void RoundControl::ending(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,ScheduledOpening& captions) {
    if(b.openingOwner30&&!b.entry.tasks.ownerActive(b.openingOwner30)) {
        b.entry.tasks.freeOwner(b.openingOwner30);b.openingOwner30=0;
        const bool complete=b.match.complete();
        unsigned next=0;
        if(b.match.result.result==3&&!complete){b.match.result.result=1;next=17;}
        else if(complete&&b.match.result.result!=0){b.match.result.result=0;next=16;}
        if(next) {
            b.openingOwner30=captions.startEnding(next,b.entry.tasks,b.effectResidency);
            return; //New caption chains defer BOTH actor checks until next visit.
        }
    }
    unsigned ready=0;
    for(unsigned i=0;i<2;++i) {
        const auto& p=players[i];auto& a=p.actor;const auto c=p.body.timeline.clock();
        const bool ended=c.endReached&&!(c.flags104&1);
        if(a.flags23c&0x80) {
            //149488 additionally requires no queued actor action. The
            //living normal52 check in145240 does not test that queue.
            if(!(a.flags23c&0x10)&&ended&&a.queuedActionA3c==-1)++ready;
        } else {
            const bool condition=(a.conditions15c[1]&0x70)||(a.conditionWord17c&0x40000000);
            const auto decision=victoryRequest(a.flags23c,a.flags244,
                std::bit_cast<int16_t>(uint16_t(a.state194)),std::bit_cast<int16_t>(uint16_t(a.state194>>16)),ended,condition);
            if(decision==VictoryRequest::Ready)++ready;
            else if(decision==VictoryRequest::Dismount) {
                // 1452b8 releases the rider before the victory request can succeed.
                p.body.timeline.stopMotion();a.pendingTable=0;a.pendingIndex=32;
            }
            else if(decision==VictoryRequest::Ride){a.pendingTable=1;a.pendingIndex=0x46;a.request18c=1;}
            else if(decision==VictoryRequest::Queue) {
                GroundStateRuntime::captureBody(p.body,a);a.opponentX=players[1-i].body.timeline.motion().x;
                a.faceOpponent();p.body.timeline.setObjectFlags(a.bodyFlags38,c.flags104,c.flags108);
                a.pendingTable=0;a.pendingIndex=52;
            }
        }
    }
    if(!b.openingOwner30&&ready==2)b.requestedState=7;
}
void RoundControl::enterVictory(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,
                                const StageEventRules& events,SoundSelection* sound) {
    const int winner=b.match.result.winner;
    if((!b.match.result.draw&&(winner<0||winner>1))||winner < -1||winner>1)
        throw std::runtime_error("Invalid victory result");
    for(unsigned i=0;i<2;++i)if(int(i)==winner) {
        players[i].actor.pendingTable=0;players[i].actor.pendingIndex=41;
    }
    //The perfect announcement compares literal200, not maximumHP. The
    //ordinary branch draws exactly once even when audio output is disabled.
    const int event=b.match.result.draw?((players[0].actor.flags23c&0x80)?11:12):
        players[unsigned(winner)].actor.fieldA30==200?10:(b.random.bounded(2)?9:8);
    events.request(b.stageEvent,event,true,stagePlayers(players));
    if(b.match.complete()) {
        b.finalSoundPending3d2e78=1;
        // 1e7ce8 sets a global gate and starts track 24 without waiting
        // for the announcer. The next scene transition tests this same gate.
        if(sound) {
            b.voiceGate5850e0=1;
            sound->playMusic(24,int(b.audio.streamParameter5a9e78));
        }
    }
    for(const auto& p:players)p.actor.flags244&=~0x200000u;
}
void RoundControl::introduction(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    bool skipped=false;
    if(b.match.roundIndex==0) {
        for(const auto& p:players)skipped|=skipPressed(p);
        if(!skipped)for(const auto& p:players)if(!(p.actor.flags244&0x40000000))return;
    }
    for(const auto& p:players) {
        ActorTimers timers{p.actor.timerDelta,p.actor.timers};
        EndingPlayback::releaseIntroduction(p.body,timers);p.actor.timers=timers.values;
        //14ff80 only queues normal0; preserve18c and the old body until
        //the later actor visit. Neither release nor skip starts idle here.
        p.actor.pendingTable=0;p.actor.pendingIndex=0;
        GroundStateRuntime::captureBody(p.body,p.actor);
    }
    b.camera.commands.clear();
    if(skipped) {
        b.timers.set(4,4);b.flags138|=8;b.timers.set(2,4);b.requestedState=2;
    } else {b.timers.set(2,30);b.requestedState=3;}
}
void RoundControl::skippedIntroduction(BattleRoundState& b) {
    b.timers.set(2,26);b.requestedState=3;
}
void RoundControl::enterVictoryCamera(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    const auto winner=b.match.result.winner;
    if(winner < -1 || winner > 1)throw std::runtime_error("Invalid round winner");
    for(const auto& p:players)if(!playableFighter(p.actor.character)||p.body.timeline.action().id()>=0x500)
        throw std::runtime_error("Unsupported victory camera action");
    beginVictoryCamera(b.camera,winner,b.match.result.draw,{players[0].actor.flags23c,players[1].actor.flags23c});
    for(unsigned i=0;i<2;++i) {
        auto& a=players[i].actor;
        if(a.flags23c&0x80) {
            //169050 only matches resource-specific actions at0x500+;
            //none of the admitted ordinary body actions request its flip.
            a.pendingTable=2;a.pendingIndex=15;a.request18c=1;
        } else if(int(i)!=winner) {
            a.pendingTable=0;a.pendingIndex=b.match.result.draw?42:43;
        }
    }
}
void RoundControl::victoryCamera(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    keepBodies(players);
    for(const auto& p:players)p.actor.flags244|=0x20000;
    if(b.camera.commandsComplete())b.requestedState=8;
}
void RoundControl::victory(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,int submode) {
    keepBodies(players);
    bool skipped=false;
    for(unsigned i=0;i<2;++i)if(skipPressed(players[i])) {
        const auto mode=b.gameMode;
        skipped|=((mode==1||mode==11)&&i==0)||((mode==2||mode==12)&&i==1)||
                 (mode==3&&int(i)==b.match.result.winner);
    }
    for(const auto& p:players) {
        p.actor.flags244|=0x20000;
        //Original stops at the FIRST unfinished actor. Without a permitted
        //skip, player1 must not receive its flag early while player0 waits.
        if(!(p.actor.flags244&0x40000000)&&!skipped)return;
    }
    b.match.roundIndex=std::bit_cast<int32_t>(uint32_t(b.match.roundIndex)+1);
    const auto next=b.match.transition(b.gameMode,submode);
    b.requestedState=next.state;b.timers.set(2,next.delay);
}
void RoundControl::advanceBattleClock(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    auto& timers=b.timers;
    b.gauges.focus46a948=-2; // 1421e8 resets the drawing selector even on the final locked tick.
    timers.decrease(4);
    b.flags138&=~0x70u;

    // These body animations borrow the opponent's object clock (1691c0).
    // The flag also applies while playing a character-specific hurt state.
    static constexpr std::array<int,17> borrowedActions{133,134,137,138,162,163,232,233,234,235,238,404,405,406,407,430,431};
    for(unsigned i=0;i<2;++i) {
        auto& a=players[i].actor;
        auto& body=players[i].body;
        const auto c=body.timeline.clock();
        const bool fixed=(a.flags23c&0x10000000)&&!(a.flags244&0x1000);
        body.setFlags((c.flags104&~0x01000000u)|(fixed?0x01000000u:0),c.flags108);
        const bool specialOpponent=a.stateTable()!=2 && players[1-i].actor.character==12 &&
                                   (players[1-i].actor.flags248&0x4000);
        if(specialOpponent||(a.stateTable()==2&&a.stateIndex()>=80)||
           std::binary_search(borrowedActions.begin(),borrowedActions.end(),int(body.timeline.action().id())))
            a.flags23c|=0x80000000u;
        b.gauges.words910[6+i]=0;
        const bool independent=StateCallbacks::hasSystemEffect(players[i].config)&&a.systemState13c==3&&!specialOpponent;
        b.gauges.words910[10+i]=(a.flags23c&0x80000000u)&&!independent;
    }
    bool keepPalette=false;
    if(timers.locked()) {
        timers.decreaseLock();
        b.field140=3;
        for(unsigned i=0;i<2;++i)if(players[i].actor.flags23c&0x08000000) {
            if(!(players[i].actor.flags248&0x800))b.gauges.focus46a948=int32_t(i);
            auto& body=players[i].body;
            const auto c=body.timeline.clock();
            body.setFlags(c.flags104|0x01000000u,c.flags108);
            b.gauges.words910[6+i]=1;keepPalette=true;
        }
    } else {
        // 14242c checks the OLD count. Timer 5 starts running only on
        // the update after timer 6 expires, using the previous time delta.
        if(timers.decrease(6)>0)b.field140=2;
        else if(timers.decrease(5)>0)b.field140=1;
        else b.field140=0;
    }
    if(!keepPalette)for(auto& tone:std::span(b.gauges.paletteTones).subspan(512))tone&=~uint16_t(4);
    timers.rawDelta=battleSpeedDelta(b.field140);
    b.gauges.scale1239d88=timers.rawDelta;
    timers.delta=int32_t(resolveObjectDelta(timers.rawDelta,2,b.gauges));
    if(b.currentState==4&&b.field08!=1&&!roundClockStopped(b.currentState,players[0].actor,players[1].actor))timers.decrease(0);
}
void RoundControl::inputLocks(const BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    //battle+c is the round interaction state, NOT battleTimers.lock.
    for(const auto& p:players)p.actor.flags24c=roundInputFlags(p.actor.flags24c,b.currentState,b.field0c);
}
}
