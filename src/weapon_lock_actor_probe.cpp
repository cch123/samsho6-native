#include "weapon_lock.hpp"
#include "scheduled_opening.hpp"
#include "sound_selection.hpp"
#include "effect_snapshot.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>
namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete lock actor fixture");return v;}
int32_t integer(){return std::bit_cast<int32_t>(word());}
float number(){return std::bit_cast<float>(word());}
void emit(auto v){std::cout<<+v<<' ';}
uint64_t hash(const auto& rows){uint64_t h=14695981039346656037ull;for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
uint64_t flatHash(const auto& row){uint64_t h=14695981039346656037ull;for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
}
int main(int argc,char** argv){try {
    if(argc<2||argc>3)throw std::runtime_error("Expected assets directory and optional --objects");
    const bool unified=argc==3&&std::string(argv[2])=="--unified";
    const bool objectFrames=unified||(argc==3&&std::string(argv[2])=="--objects");
    ss6::EffectBank drawBank(argv[1]);
    ss6::ActionBank bank(argv[1],true);ss6::GroundStateRuntime ground(argv[1]);
    ss6::WeaponLock lock(argv[1]);ss6::AuxiliaryObjects auxiliary(argv[1],{0,0,51});
    ss6::ScheduledOpening particles(argv[1]);ss6::BattleRoundState b;ss6::ReactionTables reactions(argv[1]);
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> contexts;
    std::array<std::unique_ptr<ss6::PlayerObject>,2> bodies;
    std::vector<ss6::EffectDraw> draws;int32_t distance=0;
    ss6::ObjectDrawQueue objectDraws;uint32_t jumpFlags=0;ss6::SoundSelection sound(argv[1]);
    auxiliary.setSoundObserver([&](int16_t command,const ss6::AuxiliaryObject&) {
        sound.resolve(uint16_t(command)&0xfff,0,b.random);return 0; //source345188=0, stage0 fixture
    });
    const auto stageActors=[&] {
        std::array<ss6::StageActor,2> stage;
        for(unsigned i=0;i<2;++i) {
            ss6::GroundStateRuntime::captureBody(*bodies[i],actors[i]);const auto& a=actors[i];
            stage[i]={a.x,a.y,a.flags23c,a.flags244,a.bodyFlags38,a.flags24c,int16_t(a.stateTable()),int16_t(a.stateIndex()),
                a.stateTable()==2&&unsigned(a.stateIndex())<80?uint8_t(reactions.descriptor(a.stateIndex()).flags):uint8_t(0)};
        }
        return stage;
    };
    const auto visitActor=[&](unsigned i) {
        auto& a=actors.at(i);auto& other=actors[1-i];
        ss6::WeaponLockActorContext shared{*bodies[1-i],other,b.camera,distance,auxiliary,storage[i].objectTasks};
        ss6::GroundStateFrame frame;frame.opponentX=bodies[1-i]->timeline.motion().x;
        frame.opponentFlags23c=other.flags23c;frame.objects=&contexts[i];frame.random=&b.random;frame.weaponLock=&shared;
        b.entry.player=i;b.entry.opponentFlagsB8=other.flagsB8;
        ground.visit(*bodies[i],a,inputs[i],configs[i],b.entry,frame);other.flagsB8=b.entry.opponentFlagsB8;
    };
    const auto advanceStage=[&] {
        auto stage=stageActors();distance=ss6::updateOrdinaryStage(stage,b.camera)[0];
        for(unsigned i=0;i<2;++i){bodies[i]->timeline.setPosition(stage[i].x,stage[i].y);actors[i].flags24c=stage[i].flags24c;}
    };
    const auto advanceEffects=[&](bool paused) {
        draws.clear();objectDraws.beginFrame();b.gauges.words910[5]=paused;ss6::TaskDispatch handlers;
        handlers.call=[&](uint32_t handler,uint32_t task) {
            if(handler!=0x124898)throw std::runtime_error("Unexpected shared particle task");
            if(unified)particles.task(task,b.entry.tasks,b.effectResidency,b.paletteState,objectDraws,b.gauges);
            else particles.task(task,b.entry.tasks,b.effectResidency,b.paletteState,draws,paused);
        };b.entry.tasks.dispatchTasks(handlers);
    };
    std::string op;
    while(std::cin>>op) {
        auto& pools=b.entry.tasks;
        if(op=="fixture") {
            const auto seed=word();b={};actors={};inputs={};storage={};contexts={};draws.clear();distance=0;objectDraws={};jumpFlags=0;sound.reset();
            b.requestedState=b.currentState=4;b.field08=1;b.field0c=0;
            pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
            b.random.mode=integer();b.random.gameSeed=word();std::cin>>b.random.librarySeed;
            for(unsigned i=0;i<32;++i)b.effectResidency.slots[i]=i+1;
            for(unsigned i=0;i<44;++i)b.effectResidency.references[i]=(seed+i)%4;
            for(unsigned i=0;i<72;++i)b.paletteState[i/24][i%24]=seed+i*17;
            for(unsigned i=0;i<2;++i) {
                bodies[i]=std::make_unique<ss6::PlayerObject>(bank,0);
                auto& o=*bodies[i];auto& a=actors[i];
                o.ownerCC=o.resourceSlot0c=i;
                o.timeline.setObjectFlags(0x10000000|(word()<<19),0x40000200,0x40);
                const float x=number(),y=number();o.timeline.setPosition(x,y);
                o.timeline.setEffectObserver([&,i](unsigned id,uint32_t flags,float x,float y) {
                    particles.startWorld(id,flags,bodies[i]->resourceSlot0c,x,y,-10,1,pools,b.effectResidency,b.random);
                });
                a.flags23c=0x1000;a.fieldA30=200;a.state1a4=0xffffffff;
                a.swordCurrent134=a.swordMaximum138=25600;
                contexts[i].bindTasks(pools,storage[i].objectTasks);
                ss6::GroundStateRuntime::captureBody(o,a);
            }
            continue;
        }
        const std::array<ss6::RoundPlayerRef,2> players{{
            {*bodies[0],actors[0],inputs[0],configs[0],storage[0],contexts[0]},
            {*bodies[1],actors[1],inputs[1],configs[1],storage[1],contexts[1]}}};
        if(op=="object-update"||op=="object-visit"||op=="object-draw") {
            if(!objectFrames)throw std::runtime_error("Object frame protocol needs --objects");
            std::array<ss6::AuxiliaryObject,2> parents;
            ss6::AuxiliaryFrame frame{b.gauges,jumpFlags,int32_t(b.field140),{}};
            for(unsigned i=0;i<2;++i) {
                parents[i]=bodies[i]->childParentWords();parents[i][0x8c/4]=bodies[i]->color8c;
                frame.owners[i]={&parents[i],actors[i].flags23c,actors[i].fieldA2c,actors[i].stateTable()};
            }
            if(op=="object-draw"&&!unified){draws.clear();objectDraws.beginFrame();}
            for(unsigned i=0;i<3;++i) {
                std::span<uint32_t> registry=i==2?std::span<uint32_t>(b.objectTasks):std::span<uint32_t>(storage[i].objectTasks);
                if(op=="object-update")auxiliary.updateRegistry(pools,registry,frame);
                else if(op=="object-draw")auxiliary.drawRegistry(pools,registry,frame,objectDraws);
                else auxiliary.visitRegistry(pools,registry,[&](uint32_t task) {
                    switch(pools.tasks.at(task-1)[0]) {
                    case 0x145e30:lock.task(b,players,task);break;
                    case 0x1701c0:auxiliary.landWeapon(pools,task);break;
                    case 0x147540:auxiliary.releaseHold(pools,task);break;
                    default:throw std::runtime_error("Unexpected combined lock object callback");
                    }
                });
            }
        }else if(op=="enter")lock.enter(b,players);
        else if(op=="update")lock.update(b,players);
        else if(op=="features") {
            const auto i=word(),mask=word();for(unsigned j=0;j<3;++j)inputs.at(i).sampledFeatures[6+j]=(mask>>j)&1;
        } else if(op=="distance")distance=integer();
        else if(op=="bounds") {b.camera.left=integer();b.camera.right=integer();}
        else if(op=="posture") {const auto i=word();actors.at(i).flags23c=word();actors[i].flags244=word();actors[i].state194=word();}
        else if(op=="position") {const auto i=word();const float x=number(),y=number();bodies.at(i)->timeline.setPosition(x,y);}
        else if(op=="callback-words") {const auto i=word();for(unsigned j=3;j<7;++j)actors.at(i).callbacks260[j]=word();}
        else if(op=="phase") {const auto i=word();actors.at(i).weaponLockPhaseA54=integer();}
        else if(op=="timer") {const auto i=word();actors.at(i).timers[13]=integer();}
        else if(op=="delta") {const auto i=word();actors.at(i).timerDelta=integer();}
        else if(op=="queue") {const auto i=word();actors.at(i).queuedActionA3c=integer();}
        else if(op=="body-flags") {const auto i=word(),a=word(),c=word();bodies.at(i)->setFlags(a,c);}
        else if(op=="visit") {visitActor(word());
        } else if(op=="commit-actor") {const auto i=word();ground.commitAction(*bodies.at(i),actors[i]);}
        else if(op=="commit-body")bodies.at(word())->commitRequested();
        else if(op=="animate"||op=="move") {
            const auto i=word(),delta=word();auto& o=*bodies.at(i);o.delta30=delta;
            if(op=="animate")o.animate(delta);else o.move(delta);
        } else if(op=="stage"||op=="separate") {
            auto stage=stageActors();
            if(op=="stage")distance=ss6::updateOrdinaryStage(stage,b.camera)[0];
            else ss6::separateActorAnchors(stage,b.camera,integer());
            for(unsigned i=0;i<2;++i){bodies[i]->timeline.setPosition(stage[i].x,stage[i].y);actors[i].flags24c=stage[i].flags24c;}
        } else if(op=="effects") {advanceEffects(word()!=0);
        } else if(op=="common-commit") {
            for(auto h:b.objectTasks)if(h)auxiliary.commitRequested(pools.objects.at(pools.tasks.at(h-1)[7]-1));
        } else if(op=="step") {
            const auto first=word(),delta=word(),mask0=word(),mask1=word(),paused=word();
            for(unsigned i=0;i<2;++i) {
                auto& o=*bodies[i];o.delta30=delta;o.animate(delta);o.move(delta);actors[i].timerDelta=int32_t(delta);
            }
            advanceStage();visitActor(first);visitActor(1-first);
            for(unsigned i:{first,1-first})ground.commitAction(*bodies[i],actors[i]);
            for(unsigned i:{first,1-first})bodies[i]->commitRequested();
            for(unsigned i=0;i<2;++i)for(unsigned j=0;j<3;++j)inputs[i].sampledFeatures[6+j]=((i?mask1:mask0)>>j)&1;
            if(b.field08==1)lock.update(b,players);
            advanceEffects(paused!=0);
        } else if(op=="drop") {
            const auto i=word();auxiliary.dropAfterLock(pools,storage.at(i).objectTasks,b.random,i,actors[i].character,actors[i].flags23c,bodies[i]->childParentWords());
        } else if(op!="snapshot")throw std::runtime_error("Unknown lock actor operation");
        if(unified) {
            if(op=="object-draw")objectDraws.sort();
            draws.clear();for(const auto& row:objectDraws.active())
                if(row[0x144/4])draws.push_back(ss6::decodeEffectDraw(row,drawBank));
        }
        emit(b.field08);emit(b.field0c);emit(b.flags138);emit(distance);emit(b.entry.attackMarker12d2300);
        for(unsigned i=0;i<2;++i) {
            auto& o=*bodies[i];auto& a=actors[i];ss6::GroundStateRuntime::captureBody(o,a);
            for(uint32_t v:{a.state194,a.request18c,uint32_t(int32_t(a.pendingTable)),uint32_t(int32_t(a.pendingIndex)),
                uint32_t(a.stateCharacter198),uint32_t(a.stateFlags19a),a.flags23c,a.flags244,a.flags248,uint32_t(a.flags24c),
                a.controlCounterC0,a.flagsB8,uint32_t(a.swordWait130),uint32_t(a.queuedActionA3c),
                uint32_t(a.weaponLockPhaseA54),uint32_t(a.weaponLockResultA58),uint32_t(b.match.players[i].weaponLockPresses30),
                a.fieldA28,a.fieldA2c,uint32_t(a.timerDelta)})emit(v);
            for(auto v:a.conditions15c)emit(v);for(auto v:a.callbacks260)emit(v);for(auto v:a.timers)emit(uint32_t(v));
            for(auto v:a.override27c)emit(v);
            for(uint32_t v:std::array<uint32_t,10>{a.field250,a.field251,a.contactKind252,a.landingCount253,a.pendingCharacter254,a.previousReaction,a.secondaryReaction,a.field257,a.heavyReaction,a.extraReaction25c})emit(v);
            emit(flatHash(inputs[i].sampledFeatures));
            const auto c=o.timeline.clock();const auto m=o.timeline.motion();
            for(uint32_t v:{o.timeline.action().id(),c.step,c.fractionalTime,c.endReached,c.endControl,c.objectFlags,c.flags104,c.flags108,uint32_t(c.chainedAction),
                uint32_t(m.dx),uint32_t(m.vx),uint32_t(m.ax),uint32_t(m.dy),uint32_t(m.vy),uint32_t(m.ay),
                std::bit_cast<uint32_t>(m.x),std::bit_cast<uint32_t>(m.y),uint32_t(o.pendingFlags),o.color8c,o.field20,o.delta30})emit(v);
            for(auto v:o.timeline.attachedEffect())emit(uint32_t(v));emit(flatHash(storage[i].objectTasks));
        }
        emit(pools.freedStacks);emit(pools.ownerGlobal3688);emit(pools.freeTaskHead);emit(pools.freeObjectHead);emit(pools.freeObjectCount);
        emit(pools.currentTask);emit(pools.activeCount);emit(hash(pools.tasks));emit(hash(pools.objects));
        emit(flatHash(pools.priorityHeads));emit(flatHash(pools.activeTags));
        std::array<std::array<uint32_t,2>,256> owners;
        for(unsigned i=0;i<256;++i){const auto h=pools.stacks.at(i+1);owners[i]={h.flags,h.value};}emit(hash(owners));
        emit(hash(b.paletteState));emit(flatHash(b.effectResidency.slots));emit(flatHash(b.effectResidency.references));
        emit(b.random.mode);emit(b.random.gameSeed);emit(b.random.librarySeed);emit(flatHash(b.objectTasks));emit(draws.size());
        for(const auto& draw:draws) {
            for(auto v:draw.record.fields)emit(v);const auto& s=draw.state;
            emit(s.step);emit(s.time);emit(s.speed);emit(s.flags);
            for(float v:{s.x,s.y,s.z,s.baseScale})emit(std::bit_cast<uint32_t>(v));
            for(auto v:s.motion)emit(v);emit(s.scale.bits);emit(s.scaleVelocity.bits);emit(s.scaleAcceleration.bits);emit(s.color);
            for(auto v:s.colorMotion)emit(uint32_t(v));
        }
        if(objectFrames){emit(jumpFlags);emit(objectDraws.count);for(const auto& row:objectDraws.active())for(auto v:row)emit(v);}
        if(unified)emit(flatHash(objectDraws.order));
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
