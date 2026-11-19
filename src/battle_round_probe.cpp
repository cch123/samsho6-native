#include "battle_round.hpp"
#include "human_input.hpp"
#include "sound_selection.hpp"
#include "round_control.hpp"
#include "round_dispatcher.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>

namespace {
uint64_t digest(const auto& values) {
    uint64_t h=14695981039346656037ull;
    for(auto v:values){h^=uint32_t(v);h*=1099511628211ull;}return h;
}
uint64_t rows(const auto& values) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:values)for(auto v:row){h^=v;h*=1099511628211ull;}return h;
}
uint32_t bits(float v){return std::bit_cast<uint32_t>(v);}
void emit(auto v){std::cout<<+v<<' ';}
void array(const auto& a){for(auto v:a)emit(+v);}
}
int main(int argc,char** argv) {try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ActionBank bank(argv[1],true);ss6::GroundStateRuntime ground(argv[1]);
    ss6::BattleRoundInitialization initialize(argv[1]);ss6::HumanInputPipeline human(argv[1]);
    ss6::SoundSelection sounds(argv[1]);ss6::BattleEffects effects(argv[1]);ss6::BattleRoundState b;
    ss6::StageEventRules stageEvents(argv[1]);
    ss6::ScheduledOpening captions(argv[1]);ss6::MatchEndingRules results(argv[1]);
    ss6::WeaponLock weaponLock(argv[1]);
    ss6::RoundDispatcher dispatcher({initialize,ground,effects,stageEvents,captions,results,weaponLock});
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> callbacks;
    std::array<std::unique_ptr<ss6::PlayerObject>,2> bodies;
    std::string op;
    while(std::cin>>op) {
        if(op=="reset") {
            b={};actors={};inputs={};storage={};callbacks={};sounds.reset();effects.reset();
            b.entry.tasks.initializeTasks();b.entry.tasks.initializeObjects();
            for(unsigned i=0;i<2;++i) {
                bodies[i]=std::make_unique<ss6::PlayerObject>(bank,189+i);
                bodies[i]->ownerCC=i;
                bodies[i]->timeline.setObjectFlags(0x10000000|(i?0x80000:0),0x40000200,0);
                bodies[i]->timeline.setPosition(280+i*80,0);
                bodies[i]->timeline.stopMotion();
                bodies[i]->timeline.setSoundObserver([&](int16_t command,const ss6::ActionClock& clock){sounds.record(command,clock,0,b.random);});
                auto& a=actors[i];a.flags23c=0x1000;a.state194=41u<<16;a.state1a4=0xffffffff;
                a.fieldA30=100;a.maximumLifeA34=200;
                human.initialize(inputs[i],configs[i]);
                ground.captureBody(*bodies[i],a);
            }
            continue;
        }
        if(op=="seed") {
            uint32_t seed;std::cin>>seed>>b.match.roundIndex>>b.requestedState>>b.flags138>>b.random.mode;
            b.currentState=8;b.field08=17;b.field0c=19;b.phase130=9;b.field140=23;
            b.lastItemSecond=29;b.stageItems.start(7,320,0,b.camera);
            b.entry.attackMarker12d2300=43;b.random.gameSeed=seed;b.random.librarySeed=uint64_t(seed)*0x100000001ull;
            b.stageEvent={int32_t(seed%15),7,seed%3==0?14:0,seed%2?0x100u:0x40u,0x12345678u,400,70,-5,27,1,3,5};
            b.finalSoundPending3d2e78=seed;
            for(unsigned i=0;i<3;++i)for(unsigned j=0;j<24;++j)b.paletteState[i][j]=seed+(i*24+j)*5;
            b.camera.delta=64;b.camera.x=440;b.camera.y=200;b.camera.width=400;
            b.camera.commands.clear();
            b.camera.appendCommand(3,17);b.camera.appendCommand(0,0);
            b.timers.flags=7;b.timers.lock=99;b.timers.rawDelta=128;b.timers.delta=512;b.timers.values.fill(61);
            for(unsigned j=0;j<171;++j)b.sampler.features[j]=seed+j*13;
            for(unsigned i=0;i<2;++i)for(unsigned j=0;j<6;++j)b.sampler.pressLatches[i][j]=uint8_t(seed+i+j);
            for(unsigned j=0;j<600;++j){b.sampler.replayHeld[j]=uint16_t(seed+j*13);b.sampler.replayPressed[j]=uint16_t(seed*3+j*7);}
            for(unsigned i=0;i<2;++i) {
                auto& a=actors[i];auto& input=inputs[i];
                a.rageState120=(seed+i)%4;a.rageAmount124=501+i;a.rageDecay128=17+i;a.swordWait130=5+i;
                a.swordCurrent134=123+i;a.swordMaximum138=456+i;a.flags240=0xabcdef01;a.fieldA50=43;
                a.controlFlagsB4=61;a.flagsB8=67;a.controlCounterC0=71;a.controlModeC8=i?38:4;
                a.controlTimers0c.fill(79);a.controlMotion38.fill(83);a.characterBytesF14.fill(0xff);a.characterBytesF22.fill(0x5a);
                for(unsigned j=0;j<35;++j)a.timers[j]=int32_t(seed+j*19);
                for(unsigned j=0;j<171;++j)input.sampledFeatures[j]=seed+i*7+j*13;
                for(auto slots:{std::span<ss6::CommandSlot>(input.normal),std::span<ss6::CommandSlot>(input.special)})for(unsigned j=0;j<slots.size();++j) {
                    auto& s=slots[j];s.recognized=seed+j;s.cancelAllowed=slots.size()==32?j+1:0;
                    s.progress={uint8_t(j%3),uint8_t(j+2),uint16_t(seed+j),uint8_t(j%7)};
                }
                auto& stats=b.match.players[i];stats.outcome1c=5;stats.outcome20=7;stats.previous24=11;
                stats.wins=i;stats.requiredWins=2;stats.rating=13;stats.score=17;stats.bonus=19;stats.history={1,2,3,4,5};
            }
            continue;
        }
        if(op=="allocate") {
            unsigned owner,count;std::cin>>owner>>count;
            auto registry=owner==2?std::span<uint32_t>(b.objectTasks):std::span<uint32_t>(storage.at(owner).objectTasks);
            for(unsigned i=0;i<count;++i)b.entry.tasks.registerObjectTask(registry,0x1396+owner,0);
        } else if(op=="dispatch-round") {
            dispatcher.enter(b,{{{*bodies[0],actors[0],inputs[0],configs[0],storage[0],callbacks[0]},
                                 {*bodies[1],actors[1],inputs[1],configs[1],storage[1],callbacks[1]}}});
        } else if(op=="entry-round") {
            ss6::RoundControl::enterRound(initialize,ground,b,
                {{{*bodies[0],actors[0],inputs[0],configs[0],storage[0],callbacks[0]},
                  {*bodies[1],actors[1],inputs[1],configs[1],storage[1],callbacks[1]}}},effects,stageEvents);
        } else if(op=="round") {
            initialize.begin(ground,{{{*bodies[0],actors[0],inputs[0],configs[0],storage[0],callbacks[0]},
                                      {*bodies[1],actors[1],inputs[1],configs[1],storage[1],callbacks[1]}}},b,effects);
        } else if(op=="dispatch")b.entry.tasks.dispatchTasks();
        else if(op=="commit") {
            for(unsigned i=0;i<2;++i){ground.commitAction(*bodies[i],actors[i]);bodies[i]->commitRequested();ground.captureBody(*bodies[i],actors[i]);}
        } else if(op!="snapshot")throw std::runtime_error("Unknown battle-round operation");
        if(!std::cin)throw std::runtime_error("Incomplete battle-round fixture");
        for(auto v:{b.requestedState,b.currentState,b.field08,b.field0c,b.match.roundIndex})emit(v);
        for(auto v:{b.flags138,b.field140,b.phase130,uint32_t(b.lastItemSecond)})emit(v);
        emit(b.stageItems.itemIndex());emit(b.stageItems.itemCallback());emit(b.stageItems.busy());emit(b.entry.attackMarker12d2300);
        emit(b.random.mode);emit(b.random.gameSeed);emit(b.random.librarySeed);array(sounds.previous);
        const auto& c=b.camera;emit(c.delta);
        for(float v:{c.x,c.y,c.width})emit(bits(v));emit(c.left);emit(c.right);emit(c.top);
        for(float v:{c.targetX,c.targetY,c.targetWidth})emit(bits(v));emit(c.vx);emit(c.vy);emit(c.vwidth);
        for(float v:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})emit(bits(v));
        emit(c.commands.size());for(auto cmd:c.commands){emit(unsigned(cmd.kind));emit(cmd.parameter);}
        emit(b.timers.flags);emit(b.timers.lock);emit(b.timers.rawDelta);emit(b.timers.delta);array(b.timers.values);
        emit(digest(b.sampler.features));for(const auto& l:b.sampler.pressLatches)array(l);
        emit(digest(b.sampler.replayHeld));emit(digest(b.sampler.replayPressed));
        for(unsigned i=0;i<2;++i) {
            const auto& a=actors[i];const auto& o=*bodies[i];const auto clock=o.timeline.clock();const auto motion=o.timeline.motion();
            const auto& stats=b.match.players[i];
            for(auto v:{stats.outcome1c,stats.outcome20,stats.previous24,stats.wins,stats.requiredWins,stats.rating,stats.score,stats.bonus})emit(v);
            array(stats.history);
            for(auto v:{a.state194,a.request18c,uint32_t(a.pendingTable),uint32_t(a.pendingIndex),uint32_t(a.stateCharacter198),uint32_t(a.stateFlags19a),
                a.flags23c,a.flags240,a.flags244,a.flags248,uint32_t(a.flags24c),a.state1a4,a.controlFlagsB4,a.flagsB8,a.controlCounterC0,a.controlModeC8,
                a.control88,a.control8c,a.controlFlagsBC,a.controlC4,a.controlCC,a.controlD8,a.controlE4,a.controlE8,a.fieldA2c,a.fieldA50})emit(v);
            array(a.controlTimers0c);array(a.controlMotion38);array(a.characterBytesF14);array(a.characterBytesF22);
            for(auto v:{a.fieldA30,a.maximumLifeA34,a.pendingDamageA38,a.rageState120,a.rageAmount124,a.rageDecay128,a.swordWait130,a.swordCurrent134,a.swordMaximum138,
                        a.queuedActionA3c,a.timerDelta})emit(v);
            array(a.timers);array(a.conditions15c);array(a.callbacks260);array(a.override27c);array(a.registry28c);
            for(auto v:{uint32_t(o.timeline.action().id()),clock.step,clock.fractionalTime,clock.endReached,clock.objectFlags,clock.flags104,clock.flags108,
                        uint32_t(o.pendingFlags),o.color8c,o.field20,bits(motion.x),bits(motion.y)})emit(v);
            for(auto v:{motion.dx,motion.vx,motion.ax,motion.dy,motion.vy,motion.ay,clock.chainedAction})emit(v);
            emit(storage[i].history.fraction);for(auto s:storage[i].history.samples){emit(s.flags);emit(s.action);emit(s.step);emit(bits(s.x));emit(bits(s.y));}
            array(storage[i].objectTasks);array(storage[i].afterimageObjects);
            const auto& input=inputs[i];emit(digest(input.sampledFeatures));emit(input.specialCount);emit(input.specialStart);emit(input.enabled);array(input.specialPriority);
            for(auto slots:{std::span<const ss6::CommandSlot>(input.normal),std::span<const ss6::CommandSlot>(input.special)})for(const auto& s:slots) {
                emit(s.definition);emit(s.alternateDirections);emit(s.recognized);emit(s.cancelAllowed);
                emit(unsigned(s.progress.step));emit(unsigned(s.progress.elapsed));emit(s.progress.charge);emit(unsigned(s.progress.buffered));
            }
        }
        array(b.objectTasks);emit(b.entry.tasks.freeTaskHead);emit(b.entry.tasks.freeObjectHead);emit(b.entry.tasks.freeObjectCount);
        emit(rows(b.entry.tasks.tasks));emit(rows(b.entry.tasks.objects));emit(b.entry.tasks.currentTask);emit(b.entry.tasks.activeCount);
        emit(digest(b.entry.tasks.priorityHeads));emit(digest(b.entry.tasks.activeTags));
        const auto& e=b.stageEvent;emit(e.state);emit(e.request);emit(e.flags);emit(e.pending);emit(e.objectFlags);
        for(auto v:{e.x,e.y,e.z,e.targetX})emit(bits(v));emit(e.dx);emit(e.vx);emit(e.ax);
        emit(b.finalSoundPending3d2e78);for(const auto& a:b.paletteState)array(a);
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
