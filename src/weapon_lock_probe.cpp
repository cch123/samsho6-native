#include "round_dispatcher.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete weapon-lock fixture");return v;}
int32_t integer(){return std::bit_cast<int32_t>(word());}
void emit(auto v){std::cout<<+v<<' ';}
uint64_t hash(const auto& rows){uint64_t h=14695981039346656037ull;for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
uint64_t flatHash(const auto& row){uint64_t h=14695981039346656037ull;for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
}
int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ActionBank bank(argv[1],true);ss6::WeaponLock lock(argv[1]);ss6::BattleRoundState b;
    ss6::GroundStateRuntime ground(argv[1]);ss6::BattleRoundInitialization initialize(argv[1]);
    ss6::BattleEffects effects(argv[1]);ss6::StageEventRules events(argv[1]);
    ss6::ScheduledOpening captions(argv[1]);ss6::MatchEndingRules results(argv[1]);
    ss6::RoundDispatcher dispatcher({initialize,ground,effects,events,captions,results,lock});
    ss6::AuxiliaryObjects common(argv[1],{0,0,51});
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> contexts;
    std::array<std::unique_ptr<ss6::PlayerObject>,2> bodies;
    for(auto& body:bodies)body=std::make_unique<ss6::PlayerObject>(bank,189);
    const std::array<ss6::RoundPlayerRef,2> players{{
        {*bodies[0],actors[0],inputs[0],configs[0],storage[0],contexts[0]},
        {*bodies[1],actors[1],inputs[1],configs[1],storage[1],contexts[1]}}};
    const auto features=[&](unsigned player,uint32_t mask){
        for(unsigned j=0;j<3;++j)inputs[player].sampledFeatures[6+j]=(mask&(1u<<j))?0x80000001u:0;
    };
    std::string op;
    while(std::cin>>op) {
        auto& pools=b.entry.tasks;uint32_t result=0;
        if(op=="fixture") {
            const auto seed=word();b={};actors={};inputs={};
            pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
            b.random.mode=integer();b.random.gameSeed=word();std::cin>>b.random.librarySeed;
            b.requestedState=b.currentState=4;b.field08=integer();b.field0c=integer();b.flags138=word();
            b.timers.values[2]=256; //step fixtures stop the state callback, not interaction.
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];auto& input=inputs[i];auto& stats=b.match.players[i];
                a.weaponLockPhaseA54=integer();a.weaponLockResultA58=integer();stats.weaponLockPresses30=integer();
                for(unsigned j=0;j<35;++j)a.timers[j]=std::bit_cast<int32_t>(seed+i*31+j*17);
                a.timers[13]=integer();a.controlKindA20=word();a.controlFieldF4=integer();
                for(unsigned j=0;j<171;++j)input.sampledFeatures[j]=seed+i*37+j*19;
                features(i,word());
                auto motion=bodies[i]->timeline.motion();motion.x=std::bit_cast<float>(word());motion.y=std::bit_cast<float>(word());
                bodies[i]->timeline.setMotion(motion);
                const auto f38=word(),f104=word(),f108=word();bodies[i]->timeline.setObjectFlags(f38,f104,f108);
                a.fieldA30=integer();stats.previousLife10=integer();stats.previousPosture14=integer();
                a.request18c=word();a.pendingTable=int16_t(word());a.pendingIndex=int16_t(word());
                a.state194=word();a.flags23c=word();a.flags244=word();
                for(unsigned type=0;type<2;++type) {
                    auto slots=type?std::span<ss6::CommandSlot>(input.special):std::span<ss6::CommandSlot>(input.normal);
                    for(unsigned j=0;j<slots.size();++j) {
                        auto& s=slots[j];s.definition=int16_t(j+17);s.alternateDirections=j%2;
                        s.recognized=seed+j*13;s.cancelAllowed=type?seed+j*7:0;
                        s.progress={uint8_t(j%14),uint8_t(seed+j),uint16_t(seed+j*3),uint8_t(seed+j*5)};
                    }
                }
                ss6::GroundStateRuntime::captureBody(*bodies[i],a);
            }
            continue;
        }
        if(op=="phase") {const auto i=word();actors.at(i).weaponLockPhaseA54=integer();continue;}
        if(op=="timer") {const auto i=word();actors.at(i).timers[13]=integer();continue;}
        if(op=="features") {const auto i=word();features(i,word());continue;}
        if(op=="move") {
            const auto i=word();auto m=bodies.at(i)->timeline.motion();m.x=std::bit_cast<float>(word());m.y=std::bit_cast<float>(word());
            bodies[i]->timeline.setMotion(m);ss6::GroundStateRuntime::captureBody(*bodies[i],actors[i]);continue;
        }
        if(op=="populate") {
            const auto count=word();
            for(unsigned i=0;i<count;++i) {
                const auto task=pools.registerObjectTask(b.objectTasks,0x777,0);auto& o=pools.objects.at(pools.tasks[task-1][7]-1);
                o[1]=task;o[0xcc/4]=i%3?7:6;o[0xc4/4]=i%4?135:134;o[0x104/4]=0x100;
            }
            continue;
        }
        if(op=="alias") {const auto to=word(),from=word();b.objectTasks.at(to)=b.objectTasks.at(from);continue;}
        if(op=="enter")lock.enter(b,players);
        else if(op=="update")lock.update(b,players);
        else if(op=="interaction")dispatcher.interaction(b,players);
        else if(op=="step")dispatcher.step(b,players);
        else if(op=="ai")result=lock.aiPress(actors.at(word()),b.random);
        else if(op=="callbacks") {
            //Object-phase callback slice only, not112838 task scheduling.
            for(auto handle:b.objectTasks)if(handle) {
                const auto handler=pools.tasks.at(handle-1)[0];
                if(handler==0x145e30)lock.task(b,players,handle);
                else if(handler==0x147540)ss6::AuxiliaryObjects::releaseHold(pools,handle);
                else throw std::runtime_error("Unknown weapon-lock object callback");
            }
        } else if(op=="commit") {
            for(auto handle:b.objectTasks)if(handle) {
                auto& o=pools.objects.at(pools.tasks.at(handle-1)[7]-1);
                if(o[0xcc/4]==7)common.commitRequested(o);
            }
        } else if(op!="snapshot")throw std::runtime_error("Unknown weapon-lock operation");
        emit(result);emit(b.requestedState);emit(b.currentState);emit(b.field08);emit(b.field0c);emit(b.flags138);
        for(auto t:b.timers.values)emit(t);
        emit(b.random.mode);emit(b.random.gameSeed);emit(b.random.librarySeed);
        for(unsigned i=0;i<2;++i) {
            const auto& a=actors[i];const auto& s=b.match.players[i];const auto& input=inputs[i];
            emit(a.weaponLockPhaseA54);emit(a.weaponLockResultA58);emit(s.weaponLockPresses30);
            emit(a.controlKindA20);emit(a.controlFieldF4);emit(a.fieldA30);emit(s.previousLife10);emit(s.previousPosture14);
            emit(a.request18c);emit(a.pendingTable);emit(a.pendingIndex);emit(a.state194);emit(a.flags23c);emit(a.flags244);
            for(auto t:a.timers)emit(t);
            const auto c=bodies[i]->timeline.clock();const auto m=bodies[i]->timeline.motion();
            emit(c.objectFlags);emit(c.flags104);emit(c.flags108);emit(std::bit_cast<uint32_t>(m.x));emit(std::bit_cast<uint32_t>(m.y));
            if(a.bodyFlags38!=c.objectFlags||a.bodyFlags104!=c.flags104||a.bodyFlags108!=c.flags108)
                throw std::runtime_error("Stale actor body view after weapon lock");
            emit(flatHash(input.sampledFeatures));
            std::vector<uint32_t> commands;
            for(const auto slots:{std::span<const ss6::CommandSlot>(input.normal),std::span<const ss6::CommandSlot>(input.special)})for(const auto& slot:slots)
                for(uint32_t v:{uint32_t(slot.definition),uint32_t(slot.alternateDirections),slot.recognized,slot.cancelAllowed,
                                uint32_t(slot.progress.step),uint32_t(slot.progress.elapsed),uint32_t(slot.progress.charge),uint32_t(slot.progress.buffered)})commands.push_back(v);
            emit(flatHash(commands));
        }
        emit(pools.freeTaskHead);emit(pools.freeObjectHead);emit(pools.freeObjectCount);emit(hash(pools.tasks));emit(hash(pools.objects));
        emit(flatHash(b.objectTasks));
        //The full hashes catch unrelated changes; expose each registered
        //object as well so a mismatch identifies its exact field.
        for(auto h:b.objectTasks)if(h){emit(h);for(auto v:pools.objects.at(pools.tasks.at(h-1)[7]-1))emit(v);}
        emit(0);std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
