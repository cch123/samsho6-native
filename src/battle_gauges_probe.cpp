#include "round_control.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete gauge fixture");return v;}
int32_t signedWord(){return std::bit_cast<int32_t>(word());}
void emit(auto v){std::cout<<+v<<' ';}
uint64_t hash(const auto& rows){uint64_t h=14695981039346656037ull;for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
uint64_t flatHash(const auto& row){uint64_t h=14695981039346656037ull;for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
}
int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ActionBank bank(argv[1],true);ss6::BattleGauges gauges(argv[1]);ss6::BattleRoundState b;
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
    char code;
    while(std::cin>>code) {
        auto& p=b.entry.tasks;auto& g=b.gauges;uint32_t result=0;
        if(code=='P') {
            const auto seed=word();b={};actors={};p.initializeOwners();p.initializeTasks();p.initializeObjects();
            for(unsigned i=0;i<12;++i)g.words910[i]=seed+i*17;
            for(unsigned i=0;i<1024;++i)g.paletteTones[i]=uint16_t(seed+i*19);
            continue;
        }
        if(code=='F') {
            b.requestedState=signedWord();b.currentState=signedWord();b.field08=signedWord();b.timers.lock=signedWord();
            g.paused46a940=word();g.scale1239d84=word();g.scale1239d88=word();g.delta46a908=word();
            for(auto& v:g.bonusLimits)v=uint8_t(word());
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];a.rageState120=signedWord();a.rageAmount124=signedWord();a.rageDecay128=signedWord();
                a.swordWait130=signedWord();a.swordCurrent134=signedWord();a.swordMaximum138=signedWord();
                a.state194=word();a.stateFlags19a=uint8_t(word());a.flags23c=word();
                a.bonusState14c=signedWord();a.bonusTime150=signedWord();a.bonusRate154=signedWord();a.systemMeter158=signedWord();
                const auto f104=word(),f108=word();bodies[i]->setFlags(f104,f108);
                ss6::GroundStateRuntime::captureBody(*bodies[i],a);
            }
            continue;
        }
        if(code=='R') {
            b.match.roundIndex=signedWord();b.audio.streamParameter5a9e78=word();b.audio.streamStart1553b5c=word();
            b.audio.streamWord1553a40=word();b.audio.musicActive123a174=word();
            b.camera.commands.clear();b.camera.appendCommand(3,17);b.timers.set(3,91);continue;
        }
        if(code=='a')result=gauges.start(b);
        else if(code=='x')gauges.stop(b,players);
        else if(code=='u')gauges.task(b,players);
        else if(code=='e')ss6::RoundControl::enterCombat(b);
        else if(code=='d') {
            ss6::TaskDispatch h;
            h.call=[&](uint32_t handler,uint32_t){if(handler!=0x11e708)throw std::runtime_error("Unexpected gauge task");gauges.task(b,players);};
            p.dispatchTasks(h);
        } else throw std::runtime_error("Unknown gauge command");
        emit(result);emit(b.requestedState);emit(b.currentState);emit(b.field08);emit(b.timers.lock);
        emit(g.paused46a940);emit(g.scale1239d84);emit(g.scale1239d88);emit(g.delta46a908);
        for(auto v:g.bonusLimits)emit(v);
        for(auto v:g.words910)emit(v);emit(flatHash(g.paletteTones));
        for(unsigned i=0;i<2;++i) {
            const auto& a=actors[i];const auto c=bodies[i]->timeline.clock();
            for(auto v:{a.rageState120,a.rageAmount124,a.rageDecay128,a.swordWait130,a.swordCurrent134,a.swordMaximum138})emit(v);
            emit(a.state194);emit(a.stateFlags19a);emit(a.flags23c);
            for(auto v:{a.bonusState14c,a.bonusTime150,a.bonusRate154,a.systemMeter158})emit(v);
            emit(c.flags104);emit(c.flags108);
            if(a.bodyFlags104!=c.flags104||a.bodyFlags108!=c.flags108)throw std::runtime_error("Stale gauge body view");
        }
        emit(p.freeTaskHead);emit(p.currentTask);emit(p.activeCount);emit(hash(p.tasks));emit(hash(p.objects));
        emit(flatHash(p.priorityHeads));emit(flatHash(p.activeTags));emit(p.freedStacks);
        emit(b.match.roundIndex);emit(b.audio.streamParameter5a9e78);emit(b.audio.streamStart1553b5c);
        emit(b.audio.streamWord1553a40);emit(b.audio.musicActive123a174);emit(b.audio.requests.size());
        for(auto r:b.audio.requests){emit(r.command);emit(r.parameter);}
        emit(b.camera.commands.size());for(auto c:b.camera.commands){emit(c.kind);emit(c.parameter);}
        emit(b.timers.values[3]);
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
