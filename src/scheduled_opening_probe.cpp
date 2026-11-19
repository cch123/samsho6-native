#include "round_control.hpp"
#include "round_dispatcher.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
uint32_t word() {uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete opening fixture");return v;}
void emit(auto v) {std::cout<<+v<<' ';}
uint64_t hash(const auto& rows) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;
}
uint64_t flatHash(const auto& row) {
    uint64_t h=14695981039346656037ull;
    for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;
}
}
int main(int argc,char** argv) {try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ScheduledOpening opening(argv[1]);ss6::StageEventRules events(argv[1]);ss6::MatchEndingRules results(argv[1]);
    ss6::ActionBank bank(argv[1],true);ss6::BattleRoundState b;
    ss6::GroundStateRuntime ground(argv[1]);ss6::BattleRoundInitialization initialize(argv[1]);ss6::BattleEffects effects(argv[1]);
    ss6::WeaponLock weaponLock(argv[1]);
    ss6::RoundDispatcher dispatcher({initialize,ground,effects,events,opening,results,weaponLock});
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> contexts;
    std::array<std::unique_ptr<ss6::PlayerObject>,2> bodies;
    for(unsigned i=0;i<2;++i) {
        bodies[i]=std::make_unique<ss6::PlayerObject>(bank,189);
        auto m=bodies[i]->timeline.motion();m.x=280+i*80;bodies[i]->timeline.setMotion(m);
    }
    const std::array<ss6::RoundPlayerRef,2> players{{
        {*bodies[0],actors[0],inputs[0],configs[0],storage[0],contexts[0]},
        {*bodies[1],actors[1],inputs[1],configs[1],storage[1],contexts[1]}}};
    std::vector<ss6::EffectDraw> draws;std::string op;bool endingProjection=false,entryProjection=false,dispatchProjection=false;
    while(std::cin>>op) {
        auto& p=b.entry.tasks;uint32_t result=0;
        if(op=="fixture") {
            const auto seed=word();b={};draws.clear();endingProjection=entryProjection=dispatchProjection=false;
            p.initializeOwners();p.initializeTasks();p.initializeObjects();
            b.requestedState=b.currentState=3;b.stageEvent.x=320;b.voiceGate5850e0=seed;
            for(unsigned i=0;i<32;++i)b.effectResidency.slots[i]=i+1;
            for(unsigned i=0;i<44;++i)b.effectResidency.references[i]=(seed+i)%4;
            for(unsigned i=0;i<72;++i)b.paletteState[i/24][i%24]=seed+i*17;
            continue;
        }
        if(op=="dispatch-projection") {dispatchProjection=true;continue;}
        if(op=="entry-config") {
            entryProjection=true;b.requestedState=5;b.currentState=4;
            const auto seed=word();auto& e=b.matchEnd;auto& g=b.gauges;
            e.submodeA0=std::bit_cast<int32_t>(word());g.paused46a940=word();
            e.metadataStage04=word();e.profileFlags1239090=word();
            e.characterVersion43d052=uint8_t(word());
            e.winner08=-1;e.stage28=31;e.result8c=17;e.continue2c=9;e.endFlagA4=13;
            b.endingParameter2c=97;b.pause.remaining=11;b.pause.delay=7;
            for(unsigned i=0;i<7;++i)b.timers.values[i]=std::bit_cast<int32_t>(seed+i*23);
            g.scale1239d84=19;g.scale1239d88=43;g.delta46a908=77;
            for(unsigned i=0;i<12;++i)g.words910[i]=seed+i*17;
            for(unsigned i=0;i<1024;++i)g.paletteTones[i]=uint16_t(seed+i*19);
            for(unsigned i=0;i<2;++i) {
                auto& s=b.match.players[i];auto& a=actors[i];a={};configs[i]={};
                for(auto v:{&s.previousLife10,&s.previousPosture14,&s.field18,&s.outcome1c,&s.outcome20,
                            &s.previous24,&s.wins,&s.requiredWins,&s.rating,&s.score,&s.bonus})*v=std::bit_cast<int32_t>(word());
                for(auto& v:s.history)v=uint8_t(word());
                a.fieldA30=std::bit_cast<int32_t>(word());a.maximumLifeA34=std::bit_cast<int32_t>(word());
            }
            continue;
        }
        if(op=="ending-ready") {
            //Explicit actor-phase boundary fixture, not simulated gameplay.
            //The controller tests below still execute every original callee.
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];const bool dead=a.fieldA30<=0;
                a.flags23c=dead?0x1080:0x1000;a.flags244=0;
                a.state194=dead?(2u|(30u<<16)):(52u<<16);a.queuedActionA3c=-1;
                auto& clock=const_cast<ss6::ActionClock&>(bodies[i]->timeline.clock());
                clock.endReached=1;clock.flags104=0;ss6::GroundStateRuntime::captureBody(*bodies[i],a);
            }
            continue;
        }
        if(op=="ending-config") {
            endingProjection=true;b.requestedState=b.currentState=5;
            b.match.result.result=std::bit_cast<int32_t>(word());
            for(auto& s:b.match.players){s.wins=std::bit_cast<int32_t>(word());s.requiredWins=std::bit_cast<int32_t>(word());}
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];a={};
                a.flags23c=word();a.flags244=word();a.flags248=word();a.flags24c=uint8_t(word());
                a.state194=word();a.state1a4=word();a.request18c=word();
                a.pendingTable=int16_t(word());a.pendingIndex=int16_t(word());a.queuedActionA3c=std::bit_cast<int32_t>(word());
                a.conditions15c[1]=word();a.conditionWord17c=word();
                const auto f38=word(),f104=word(),f108=word(),end=word(),x=word();
                auto& body=*bodies[i];body.timeline.setObjectFlags(f38,f104,f108);
                //Boundary-fixture injection only. This is a mutable object;
                //avoid adding a gameplay API that can fake animation completion.
                const_cast<ss6::ActionClock&>(body.timeline.clock()).endReached=end;
                auto m=body.timeline.motion();m.x=std::bit_cast<float>(x);body.timeline.setMotion(m);
                ss6::GroundStateRuntime::captureBody(body,a);
            }
            continue;
        }
        if(op=="configure") {
            b.match.roundIndex=std::bit_cast<int32_t>(word());
            for(auto& s:b.match.players){s.wins=std::bit_cast<int32_t>(word());s.requiredWins=std::bit_cast<int32_t>(word());}
            continue;
        }
        if(op=="owners") {
            p.freedStacks=word();p.ownerGlobal3688=word();
            for(unsigned i=1;i<=256;++i){auto& h=p.stacks[i];h.flags=word();h.value=word();}
            continue;
        }
        if(op=="populate") {
            const auto count=word();
            for(unsigned i=0;i<count;++i)p.registerObjectTask(b.objectTasks,0x1396,0);
            continue;
        }
        if(op=="start")b.openingOwner30=opening.start(word(),p,b.effectResidency,b.paletteState);
        else if(op=="dispatch-entry")dispatcher.enter(b,players);
        else if(op=="enter-ending")ss6::RoundControl::enterEnding(b,players,opening,results);
        else if(op=="gauge-start")result=ss6::BattleGauges::start(b);
        else if(op=="ending")b.openingOwner30=opening.startEnding(word(),p,b.effectResidency);
        else if(op=="owner-flags")p.stacks.at(b.openingOwner30).flags=word();
        else if(op=="ending-update")ss6::RoundControl::ending(b,players,opening);
        else if(op=="enter")ss6::RoundControl::enterOpening(b,players,events,opening);
        else if(op=="tick") {
            const auto pauseWord=word();const bool paused=pauseWord!=0;
            b.gauges.words910[5]=pauseWord; //Same46a924 fixture used by the original effect task.
            draws.clear();ss6::TaskDispatch handlers;
            handlers.call=[&](uint32_t handler,uint32_t task) {
                if(handler!=0x124898)throw std::runtime_error("Unexpected scheduled callback");
                opening.task(task,p,b.effectResidency,b.paletteState,draws,paused);
            };
            p.dispatchTasks(handlers);
        } else if(op=="update") {
            b.timers.values[1]=std::bit_cast<int32_t>(word());ss6::RoundControl::opening(b,players,events);
        } else if(op=="allocate")result=p.allocateOwner();
        else if(op=="clear-objects")p.clearRegistry(b.objectTasks);
        else if(op=="release")p.freeOwner(word());
        else if(op=="active")result=p.ownerActive(word());
        else if(op=="initialize-owners")p.initializeOwners();
        else if(op=="cancel") {p.cancelTasks(0x1b5b);p.cancelObjects(0x1b5b);}
        else throw std::runtime_error("Unknown opening operation");
        emit(result);emit(b.openingOwner30);emit(b.requestedState);emit(b.currentState);emit(b.match.roundIndex);
        emit(b.voiceGate5850e0);emit(b.timers.values[1]);
        emit(p.freedStacks);emit(p.ownerGlobal3688);emit(p.freeTaskHead);emit(p.freeObjectHead);emit(p.freeObjectCount);
        emit(p.currentTask);emit(p.activeCount);emit(hash(p.tasks));emit(hash(p.objects));
        emit(flatHash(p.priorityHeads));emit(flatHash(p.activeTags));
        std::array<std::array<uint32_t,2>,256> owners;
        for(unsigned i=0;i<256;++i){auto h=p.stacks.at(i+1);owners[i]={h.flags,h.value};}
        emit(hash(owners));emit(hash(b.paletteState));emit(flatHash(b.effectResidency.slots));emit(flatHash(b.effectResidency.references));
        const auto& e=b.stageEvent;emit(e.state);emit(e.request);emit(e.flags);emit(e.pending);emit(e.objectFlags);
        for(float v:{e.x,e.y,e.z,e.targetX})emit(std::bit_cast<uint32_t>(v));
        emit(e.dx);emit(e.vx);emit(e.ax);emit(draws.size());
        for(const auto& draw:draws) {
            for(auto v:draw.record.fields)emit(v);
            const auto& s=draw.state;emit(s.step);emit(s.time);emit(s.speed);emit(s.flags);
            for(float v:{s.x,s.y,s.z,s.baseScale})emit(std::bit_cast<uint32_t>(v));
            for(auto v:s.motion)emit(v);
            emit(s.scale.bits);emit(s.scaleVelocity.bits);emit(s.scaleAcceleration.bits);emit(s.color);
            for(auto v:s.colorMotion)emit(uint32_t(v));
        }
        if(endingProjection) {
            emit(b.match.result.result);
            for(const auto& s:b.match.players){emit(s.wins);emit(s.requiredWins);}
            for(unsigned i=0;i<2;++i) {
                const auto& a=actors[i];const auto& body=*bodies[i];const auto c=body.timeline.clock();
                emit(a.flags23c);emit(a.flags244);emit(a.flags248);emit(a.flags24c);emit(a.state194);emit(a.state1a4);emit(a.request18c);
                emit(uint16_t(a.pendingTable));emit(uint16_t(a.pendingIndex));emit(uint32_t(a.queuedActionA3c));
                emit(a.conditions15c[1]);emit(a.conditionWord17c);
                emit(c.objectFlags);emit(c.flags104);emit(c.flags108);emit(c.endReached);emit(std::bit_cast<uint32_t>(body.timeline.motion().x));
                if(a.bodyFlags38!=c.objectFlags||a.bodyFlags104!=c.flags104||a.bodyFlags108!=c.flags108)
                    throw std::runtime_error("Ending controller left a stale actor body view");
            }
        }
        if(entryProjection) {
            const auto& e=b.matchEnd;const auto& g=b.gauges;
            emit(b.match.result.draw);emit(b.match.result.winner);emit(b.match.result.result);emit(b.endingParameter2c);
            emit(e.winner08);emit(e.stage28);emit(e.result8c);emit(e.submodeA0);emit(e.continue2c);emit(e.endFlagA4);
            emit(e.metadataStage04);emit(e.profileFlags1239090);emit(e.characterVersion43d052);
            emit(b.pause.remaining);emit(b.pause.delay);for(auto t:b.timers.values)emit(t);
            emit(g.paused46a940);emit(g.scale1239d84);emit(g.scale1239d88);emit(g.delta46a908);
            for(auto v:g.words910)emit(v);emit(flatHash(g.paletteTones));
            for(unsigned i=0;i<2;++i) {
                const auto& s=b.match.players[i];const auto& a=actors[i];
                for(auto v:{s.previousLife10,s.previousPosture14,s.field18,s.outcome1c,s.outcome20,s.previous24,
                            s.wins,s.requiredWins,s.rating,s.score,s.bonus})emit(v);
                for(auto v:s.history)emit(v);emit(a.fieldA30);emit(a.maximumLifeA34);
            }
        }
        if(dispatchProjection) {
            emit(b.field08);emit(b.field0c);
            for(auto v:{b.timers.flags,b.timers.lock,b.timers.rawDelta,b.timers.delta})emit(v);
            for(auto v:b.timers.values)emit(v);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
