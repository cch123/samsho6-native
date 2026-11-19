#include "round_control.hpp"
#include "round_dispatcher.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
void emit(auto value) { std::cout << +value << ' '; }
uint32_t bits(float value) { return std::bit_cast<uint32_t>(value); }
}
int main(int argc,char** argv) { try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ActionBank bank(argv[1],true);
    ss6::StageEventRules events(argv[1]);
    ss6::GroundStateRuntime ground(argv[1]);ss6::BattleRoundInitialization initialize(argv[1]);
    ss6::BattleEffects effects(argv[1]);ss6::ScheduledOpening captions(argv[1]);ss6::MatchEndingRules results(argv[1]);
    ss6::WeaponLock weaponLock(argv[1]);
    ss6::RoundDispatcher dispatcher({initialize,ground,effects,events,captions,results,weaponLock});
    ss6::BattleRoundState battle;
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> callbacks;
    std::array<std::unique_ptr<ss6::PlayerObject>,2> bodies;
    int submode=0;
    int event=0,force=0;
    float placeX=0,placeY=0;
    std::string command;
    while(std::cin>>command) {
        int operation=0;
        if(command=="fixture") {
            uint32_t seed;int draw,queue;
            battle={};actors={};inputs={};storage={};callbacks={};
            std::cin>>seed>>operation>>battle.requestedState>>battle.currentState>>battle.field0c
                >>battle.match.roundIndex>>battle.flags138>>battle.gameMode>>submode
                >>battle.match.result.winner>>draw;
            battle.match.result.draw=draw!=0;
            for(auto& stats:battle.match.players)std::cin>>stats.wins>>stats.requiredWins;
            std::cin>>queue;
            if(queue>=0)battle.camera.appendCommand(unsigned(queue),17);
            for(unsigned j=0;j<7;++j)battle.timers.values[j]=std::bit_cast<int32_t>(seed+j*17);
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];unsigned lock,pending;uint32_t flags104,flags108;
                std::cin>>a.flags23c>>a.flags244>>lock>>a.request18c>>a.pendingTable>>a.pendingIndex
                    >>a.queuedActionA3c>>inputs[i].sampledFeatures[11]>>flags104>>flags108>>pending;
                a.flags24c=uint8_t(lock);a.state194=39u<<16;
                for(unsigned j=0;j<35;++j)a.timers[j]=std::bit_cast<int32_t>(seed+i*43+j*19);
                bodies[i]=std::make_unique<ss6::PlayerObject>(bank,189+i);
                bodies[i]->setFlags(flags104,flags108);bodies[i]->pendingFlags=uint16_t(pending);
                auto motion=bodies[i]->timeline.motion();
                motion.x=280+i*80;motion.y=7;motion.dx=3;motion.vx=-7;motion.ax=11;
                motion.dy=-13;motion.vy=17;motion.ay=-19;bodies[i]->timeline.setMotion(motion);
                ss6::GroundStateRuntime::captureBody(*bodies[i],a);
            }
            if(operation>=6) {
                auto& e=battle.stageEvent;uint32_t x,y,z,target,p0x,p1x,mirror,px,py;
                std::cin>>e.state>>e.request>>e.flags>>e.pending>>e.objectFlags>>x>>y>>z>>target>>e.dx>>e.vx>>e.ax
                    >>battle.random.mode>>battle.random.gameSeed>>battle.random.librarySeed>>battle.finalSoundPending3d2e78
                    >>actors[0].fieldA30>>actors[1].fieldA30>>p0x>>p1x>>mirror>>event>>force>>px>>py;
                e.x=std::bit_cast<float>(x);e.y=std::bit_cast<float>(y);e.z=std::bit_cast<float>(z);e.targetX=std::bit_cast<float>(target);
                placeX=std::bit_cast<float>(px);placeY=std::bit_cast<float>(py);
                for(unsigned i=0;i<2;++i) {
                    auto m=bodies[i]->timeline.motion();m.x=std::bit_cast<float>(i?p1x:p0x);bodies[i]->timeline.setMotion(m);
                    auto c=bodies[i]->timeline.clock();
                    bodies[i]->timeline.setObjectFlags(i?c.objectFlags:(mirror?c.objectFlags|0x80000:c.objectFlags&~0x80000u),c.flags104,c.flags108);
                    ss6::GroundStateRuntime::captureBody(*bodies[i],actors[i]);
                }
            }
            if(operation>=12) {
                std::cin>>battle.field08>>battle.timeOption13c>>battle.stageItemsOption4c3828>>battle.timers.values[0];
                for(unsigned i=0;i<2;++i) {
                    auto& s=battle.match.players[i];
                    std::cin>>actors[i].flags23c>>actors[i].timers[14]>>s.previousLife10>>s.previousPosture14>>s.field18;
                }
            }
            if(operation>=15) {
                int ownerActive;
                std::cin>>battle.requestedState>>battle.currentState>>battle.field08>>battle.field0c
                    >>battle.timers.flags>>battle.timers.lock>>battle.timers.rawDelta>>battle.timers.delta
                    >>battle.timers.values[1]>>battle.timers.values[2]
                    >>battle.matchEnd.profileBusy4452ac>>battle.matchEnd.continue2c>>battle.matchEnd.field18>>ownerActive;
                battle.matchEnd.submodeA0=submode;
                battle.openingOwner30=ownerActive?1:0;
                if(ownerActive)battle.entry.tasks.stacks[1]={1,0};
            }
        } else if(command=="step")std::cin>>operation;
        else throw std::runtime_error("Unknown round-control fixture command");
        if(!std::cin||!bodies[0]||!bodies[1])throw std::runtime_error("Incomplete round-control fixture");
        const std::array<ss6::RoundPlayerRef,2> players{{
            {*bodies[0],actors[0],inputs[0],configs[0],storage[0],callbacks[0]},
            {*bodies[1],actors[1],inputs[1],configs[1],storage[1],callbacks[1]}}};
        const ss6::StageEventPlayers positions{bodies[0]->timeline.motion().x,bodies[1]->timeline.motion().x,
            bool(bodies[0]->timeline.clock().objectFlags&0x80000)};
        bool predicate=false;
        switch(operation) {
        case 0:ss6::RoundControl::introduction(battle,players);break;
        case 1:ss6::RoundControl::skippedIntroduction(battle);break;
        case 2:ss6::RoundControl::enterVictoryCamera(battle,players);break;
        case 3:ss6::RoundControl::victoryCamera(battle,players);break;
        case 4:ss6::RoundControl::victory(battle,players,submode);break;
        case 5:ss6::RoundControl::inputLocks(battle,players);break;
        case 6:ss6::RoundControl::enterIntroduction(battle,events);break;
        case 7:ss6::RoundControl::enterVictory(battle,players,events);break;
        case 8:ss6::RoundControl::resetStage(battle,players,events);break;
        case 9:events.request(battle.stageEvent,event,force!=0,positions);break;
        case 10:events.place(battle.stageEvent,placeX,placeY);break;
        case 11:predicate=events.outsideCenter(battle.stageEvent,positions);break;
        case 12:ss6::RoundControl::combatStageEvent(battle,players,events);break;
        case 13:ss6::RoundControl::combat(battle,players,events);break;
        case 14:ss6::RoundControl::snapshotPlayers(battle,players);break;
        case 15:dispatcher.step(battle,players);break;
        case 16:predicate=dispatcher.enter(battle,players);break;
        case 17:dispatcher.update(battle,players);break;
        case 18:dispatcher.interaction(battle,players);break;
        default:throw std::runtime_error("Unknown round-control operation");
        }
        for(auto v:{battle.requestedState,battle.currentState,battle.field0c,battle.match.roundIndex})emit(v);
        emit(battle.flags138);
        for(auto value:battle.timers.values)emit(value);
        emit(battle.camera.commands.size());
        for(auto c:battle.camera.commands){emit(c.kind);emit(c.parameter);}
        for(unsigned i=0;i<2;++i) {
            const auto& a=actors[i];const auto& o=*bodies[i];const auto c=o.timeline.clock();const auto m=o.timeline.motion();
            emit(a.flags23c);emit(a.flags244);emit(a.flags24c);emit(a.state194);emit(a.request18c);
            emit(a.pendingTable);emit(a.pendingIndex);emit(a.queuedActionA3c);emit(inputs[i].sampledFeatures[11]);
            for(auto timer:a.timers)emit(timer);
            emit(o.timeline.action().id());emit(c.flags104);emit(c.flags108);emit(o.pendingFlags);
            emit(bits(m.x));emit(bits(m.y));
            for(auto value:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})emit(value);
            //The controller must leave the actor's borrowed body view coherent.
            if(a.bodyFlags104!=c.flags104||a.bodyFlags108!=c.flags108||a.bodyPendingFE!=o.pendingFlags)
                throw std::runtime_error("Stale actor body view after round control");
        }
        if(operation>=6) {
            const auto& e=battle.stageEvent;
            emit(e.state);emit(e.request);emit(e.flags);emit(e.pending);emit(e.objectFlags);
            for(auto value:{e.x,e.y,e.z,e.targetX})emit(bits(value));
            emit(e.dx);emit(e.vx);emit(e.ax);
            emit(battle.random.mode);emit(battle.random.gameSeed);emit(battle.random.librarySeed);emit(battle.finalSoundPending3d2e78);
            emit(actors[0].fieldA30);emit(actors[1].fieldA30);
            emit(bits(positions.x0));emit(bits(positions.x1));emit(positions.mirror0);emit(predicate);
        }
        if(operation>=12) {
            emit(battle.field08);emit(battle.timeOption13c);emit(battle.stageItemsOption4c3828);
            for(const auto& s:battle.match.players){emit(s.previousLife10);emit(s.previousPosture14);emit(s.field18);}
        }
        if(operation>=15) {
            for(auto v:{battle.timers.flags,battle.timers.lock,battle.timers.rawDelta,battle.timers.delta})emit(v);
            emit(battle.matchEnd.profileBusy4452ac);emit(battle.matchEnd.continue2c);emit(battle.matchEnd.field18);
            emit(battle.openingOwner30);emit(battle.match.result.result);
            for(const auto& s:battle.match.players){emit(s.wins);emit(s.requiredWins);}
        }
        std::cout<<'\n';
    }
} catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;} }
