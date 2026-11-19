#include "auxiliary_objects.hpp"
#include "haohmaru_flask.hpp"
#include "sound_selection.hpp"
#include "scheduled_opening.hpp"
#include "effect_snapshot.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>

namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete object frame fixture");return v;}
uint64_t digest(const auto& values) {uint64_t h=14695981039346656037ull;for(uint32_t v:values){h^=v;h*=1099511628211ull;}return h;}
uint64_t rows(const auto& values) {uint64_t h=14695981039346656037ull;for(const auto& row:values)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
void emit(auto value){std::cout<<+value<<' ';}
}
int main(int argc,char** argv){try {
    if(argc<2||argc>3)throw std::runtime_error("Expected assets directory and optional --mixed");
    const bool mixed=argc==3&&std::string(argv[2])=="--mixed";
    ss6::ScheduledOpening effects(argv[1]);ss6::EffectBank drawBank(argv[1]);
    ss6::EffectResidency residency;ss6::EffectPalettes palettes{};
    ss6::AuxiliaryObjects runtime(argv[1],{0,0,51});ss6::SoundSelection sound(argv[1]);
    ss6::TaggedTaskPools pools;ss6::GaugeState gauges;ss6::GameRandom random;
    std::array<ss6::AuxiliaryObject,2> parents{};std::array<ss6::AuxiliaryOwner,2> owners{};
    std::array<std::array<uint32_t,48>,2> players{};std::array<uint32_t,64> common{};
    ss6::ObjectDrawQueue queue;uint32_t jump=0,result=0;int32_t speed=0,stage=0;
    runtime.setSoundObserver([&](int16_t command,const ss6::AuxiliaryObject&){
        //Source345188=0 disables playback after1e83c0 selection. Selection
        //still executes and shares random/history with all other objects.
        sound.resolve(uint16_t(command)&0xfff,stage,random);return 0;
    });
    auto registry=[&](unsigned which)->std::span<uint32_t>{if(which==2)return common;return players.at(which);};
    auto frame=[&]{return ss6::AuxiliaryFrame{gauges,jump,speed,owners};};
    auto callbacks=[&](unsigned which){runtime.visitRegistry(pools,registry(which),[&](uint32_t task){
        const auto handler=pools.tasks.at(task-1)[0];
        if(handler==0x16def0) {
            if(pools.objects.at(pools.tasks.at(task-1)[7]-1)[0xd0/4]==1)ss6::updateHaohmaruFlask(runtime,pools,task);
            else runtime.updateWhirlwind(pools,task);
        }
        else if(handler==0x1701c0)runtime.landWeapon(pools,task);
        else if(handler==0x147540)runtime.releaseHold(pools,task);
        else throw std::runtime_error("Unknown object frame callback");
    });};
    std::string op;
    while(std::cin>>op) {
        if(op=="reset") {
            const auto seed=word();stage=std::bit_cast<int32_t>(word());
            pools={};if(mixed)pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();gauges={};random={};
            random.mode=3;random.gameSeed=seed;random.librarySeed=42;sound.reset();
            parents={};owners={};players={};common={};jump=result=0;speed=0;queue={};
            if(mixed) {
                for(unsigned i=0;i<512;++i)queue.order[i]=0xabc000+seed+i*13;
                for(unsigned i=0;i<32;++i)residency.slots[i]=i+1;
                for(unsigned i=0;i<44;++i)residency.references[i]=(seed+i)%4;
                for(unsigned i=0;i<72;++i)palettes[i/24][i%24]=seed+i*17;
            }
            for(unsigned i=0;i<511;++i)for(unsigned j=0;j<82;++j)queue.slots[i][j]=seed+i*997+j*17;
            for(unsigned i=0;i<2;++i) {
                auto& o=parents[i];o[0xc/4]=o[0xcc/4]=i;o[0x30/4]=256;o[0xc8/4]=1;
                o[0x38/4]=0x10000000|(i<<19);o[0x70/4]=0x3f800000;
                o[0x40/4]=ss6::ScalarFloat::integer(280+80*i).bits;o[0x8c/4]=0xffffffff;
                owners[i]={&o,0x1000,0,0};
            }
        }else if(op=="parent") {const auto i=word(),offset=word();parents.at(i).at(offset/4)=word();}
        else if(op=="actor") {const auto i=word();owners.at(i).flags23c=word();owners[i].postureA2c=word();owners[i].effectiveTable=std::bit_cast<int32_t>(word());}
        else if(op=="gauge") {const auto i=word(),value=word();if(i==0)gauges.paused46a940=value;else if(i==1)gauges.delta46a908=value;else gauges.words910.at(i-2)=value;}
        else if(op=="speed")speed=std::bit_cast<int32_t>(word());
        else if(op=="jump")jump=word();
        else if(op=="whirlwind") {
            const auto player=word(),strength=word();
            result=runtime.spawnWhirlwind(pools,players.at(player),player,owners.at(player).flags23c,parents.at(player),strength);
        }else if(op=="flask") {
            const auto player=word();
            result=ss6::spawnHaohmaruFlask(runtime,pools,players.at(player),player,owners.at(player).flags23c,parents.at(player));
        }else if(op=="reflect") {
            const auto object=word(),team=word();
            runtime.reflectProjectile(pools.objects.at(object-1),team);
        }else if(op=="rising-trail") {
            const auto player=word(),state=word();
            result=runtime.spawnRisingSlashTrail(pools,players.at(player),player,owners.at(player).flags23c,parents.at(player),state);
        }else if(op=="slash-effect") {
            const auto player=word();
            result=runtime.spawnSlashEffect(pools,players.at(player),player,owners.at(player).flags23c,parents.at(player),593);
        }else if(op=="actor-attachment") {
            const auto player=word();const auto& parent=parents.at(player);
            result=runtime.spawnActAttachment(pools,players.at(player),common,player,owners.at(player).flags23c,
                                              parent,parent,parent[0x10c/4],false);
        }else if(op=="projectile-pause") {
            const auto object=word(),first=word(),second=word();
            runtime.pauseWhirlwind(pools.objects.at(object-1),first,second);
        }else if(op=="spawn") {
            const auto kind=word(),player=word();
            if(kind==7)result=runtime.createCommonEffect(pools,common,&parents[0],0x1396,0);
            else if(kind==4)result=runtime.dropAfterLock(pools,players.at(player),random,player,0,owners.at(player).flags23c,parents.at(player));
            else throw std::runtime_error("Unsupported fixture spawn");
        }else if(op=="object") {const auto h=word(),offset=word();pools.objects.at(h-1).at(offset/4)=word();}
        else if(op=="task") {const auto h=word(),offset=word();pools.tasks.at(h-1).at(offset/4)=word();}
        else if(op=="registry") {const auto which=word(),index=word();registry(which)[index]=word();}
        else if(op=="request") {const auto h=word(),action=word(),flags=word();runtime.request(pools.objects.at(h-1),action,flags&1,flags&2);}
        else if(op=="animate")runtime.animate(pools.objects.at(word()-1),gauges,jump);
        else if(op=="move")runtime.move(pools.objects.at(word()-1),gauges);
        else if(op=="delta") {const auto base=word(),selector=word();result=ss6::resolveObjectDelta(base,selector,gauges);}
        else if(op=="update")runtime.updateRegistry(pools,registry(word()),frame());
        else if(op=="visit")callbacks(word());
        else if(op=="draw")runtime.drawRegistry(pools,registry(word()),frame(),queue);
        else if(op=="world") {
            const auto id=word(),flags=word(),slot=word();
            const float x=std::bit_cast<float>(word()),y=std::bit_cast<float>(word()),z=std::bit_cast<float>(word()),scale=std::bit_cast<float>(word());
            effects.startWorld(id,flags,slot,x,y,z,scale,pools,residency,random);
        }else if(op=="opening")result=effects.start(word(),pools,residency,palettes);
        else if(op=="ending")result=effects.startEnding(word(),pools,residency);
        else if(op=="effects") {
            ss6::TaskDispatch dispatch;dispatch.call=[&](uint32_t handler,uint32_t task) {
                if(handler!=0x124898)throw std::runtime_error("Unknown mixed effect task");
                effects.task(task,pools,residency,palettes,queue,gauges);
            };pools.dispatchTasks(dispatch);
        }else if(op=="repeat-draw") {
            const auto which=word(),times=word();
            for(unsigned i=0;i<times;++i)runtime.drawRegistry(pools,registry(which),frame(),queue);
        }else if(op=="sort")queue.sort();
        else if(op=="begin")queue.beginFrame();
        else if(op=="draw-count")queue.count=word();
        else if(op=="tick") {
            queue.beginFrame();for(unsigned i=0;i<3;++i)runtime.updateRegistry(pools,registry(i),frame());
            for(unsigned i=0;i<3;++i)callbacks(i);
            for(unsigned i=0;i<3;++i)runtime.drawRegistry(pools,registry(i),frame(),queue);
        }else if(op!="snapshot")throw std::runtime_error("Unknown object frame operation");
        //Only snapshot emits: input changes remain cheap, while each phase
        //under test can independently request a complete allocator/draw check.
        if(op=="snapshot") {
            emit(result);emit(jump);emit(pools.freeTaskHead);emit(pools.freeObjectHead);emit(pools.freeObjectCount);
            emit(rows(pools.tasks));emit(rows(pools.objects));emit(rows(parents));emit(rows(players));emit(digest(common));
            emit(queue.count);emit(rows(queue.slots));emit(random.gameSeed);emit(random.librarySeed);
            for(auto value:sound.previous)emit(value);
            for(const auto& own:owners){emit(own.flags23c);emit(own.postureA2c);emit(own.effectiveTable);}
            for(unsigned i=252;i<256;++i)for(auto value:pools.objects[i])emit(value);
            if(mixed) {
                std::array<std::array<uint32_t,2>,256> headers;
                for(unsigned i=0;i<256;++i){const auto& h=pools.stacks.at(i+1);headers[i]={h.flags,h.value};}
                emit(rows(headers));emit(pools.freedStacks);emit(pools.ownerGlobal3688);emit(pools.currentTask);emit(pools.activeCount);
                emit(digest(pools.priorityHeads));emit(digest(pools.activeTags));emit(rows(palettes));
                emit(digest(residency.slots));emit(digest(residency.references));emit(digest(queue.order));
                std::vector<uint32_t> decoded;
                for(const auto& row:queue.active())if(row[0x144/4]) {
                    const auto d=ss6::decodeEffectDraw(row,drawBank);for(auto v:d.record.fields)decoded.push_back(v);
                    const auto& state=d.state;
                    for(auto v:{state.step,state.time,state.speed,state.flags})decoded.push_back(v);
                    for(auto v:{state.x,state.y,state.z,state.baseScale})decoded.push_back(std::bit_cast<uint32_t>(v));
                    for(auto v:state.motion)decoded.push_back(v);
                    for(auto v:{state.scale.bits,state.scaleVelocity.bits,state.scaleAcceleration.bits,state.color})decoded.push_back(v);
                    for(auto v:state.colorMotion)decoded.push_back(uint32_t(v));
                }
                emit(decoded.size()/56);emit(digest(decoded));
            }
            std::cout<<'\n';
        }
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
