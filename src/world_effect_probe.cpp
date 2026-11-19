#include "scheduled_opening.hpp"
#include "player_object.hpp"
#include <memory>
#include <bit>
#include <iostream>
#include <stdexcept>
namespace {
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete world-effect fixture");return v;}
void emit(auto v){std::cout<<+v<<' ';}
uint64_t hash(const auto& rows){uint64_t h=14695981039346656037ull;for(const auto& row:rows)for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
uint64_t flatHash(const auto& row){uint64_t h=14695981039346656037ull;for(uint32_t v:row){h^=v;h*=1099511628211ull;}return h;}
}
int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ScheduledOpening runtime(argv[1]);ss6::TaggedTaskPools pools;
    ss6::EffectResidency residency;ss6::EffectPalettes palettes{};ss6::GameRandom random;
    ss6::ActionBank bank(argv[1],true);std::unique_ptr<ss6::PlayerObject> body;
    std::vector<ss6::EffectDraw> draws;std::string op;
    while(std::cin>>op) {
        if(op=="fixture") {
            const auto seed=word();pools={};residency={};draws.clear();body.reset();
            pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
            for(unsigned i=0;i<32;++i)residency.slots[i]=i+1;
            for(unsigned i=0;i<44;++i)residency.references[i]=(seed+i)%4;
            for(unsigned i=0;i<72;++i)palettes[i/24][i%24]=seed+i*17;
            random.mode=std::bit_cast<int32_t>(word());random.gameSeed=word();std::cin>>random.librarySeed;
            continue;
        }
        if(op=="player") {
            body=std::make_unique<ss6::PlayerObject>(bank,0);body->resourceSlot0c=body->ownerCC=word();
            body->setFlags(body->timeline.clock().flags104|0x200,body->timeline.clock().flags108);
            body->timeline.setEffectObserver([&](unsigned id,uint32_t flags,float x,float y) {
                //120d10 passes the pinned5df3c8/5df3cc constants(-10,1),
                //rather than inheriting the character's Z or scale.
                runtime.startWorld(id,flags,body->resourceSlot0c,x,y,-10,1,pools,residency,random);
            });
        } else if(op=="request") {const auto action=word(),force=word();body->request(action,force);}
        else if(op=="commit")body->commitRequested();
        else if(op=="animate")body->animate(word());
        else if(op=="move")body->move(word());
        else if(op=="flags") {const auto a=word(),b=word(),c=word();body->timeline.setObjectFlags(a,b,c);}
        else if(op=="pending")body->pendingFlags=uint16_t(word());
        else if(op=="motion") {
            ss6::MotionState m;
            m.dx=std::bit_cast<int32_t>(word());m.vx=std::bit_cast<int32_t>(word());m.ax=std::bit_cast<int32_t>(word());
            m.dy=std::bit_cast<int32_t>(word());m.vy=std::bit_cast<int32_t>(word());m.ay=std::bit_cast<int32_t>(word());
            m.x=std::bit_cast<float>(word());m.y=std::bit_cast<float>(word());body->timeline.setMotion(m);
        } else if(op=="release")body->setFlags(body->timeline.clock().flags104&~0x100u,body->timeline.clock().flags108);
        else if(op=="world") {
            const auto id=word(),flags=word(),slot=word();
            const float x=std::bit_cast<float>(word()),y=std::bit_cast<float>(word()),z=std::bit_cast<float>(word()),scale=std::bit_cast<float>(word());
            runtime.startWorld(id,flags,slot,x,y,z,scale,pools,residency,random);
        } else if(op=="opening")runtime.start(word(),pools,residency,palettes);
        else if(op=="ending")runtime.startEnding(word(),pools,residency);
        else if(op=="tick") {
            const bool paused=word()!=0;draws.clear();ss6::TaskDispatch handlers;
            handlers.call=[&](uint32_t handler,uint32_t task){
                if(handler!=0x124898)throw std::runtime_error("Unknown shared effect callback");
                runtime.task(task,pools,residency,palettes,draws,paused);
            };
            pools.dispatchTasks(handlers);
        } else if(op=="cancel") {const auto tag=word();pools.cancelTasks(tag);pools.cancelObjects(tag);}
        else throw std::runtime_error("Unknown world-effect command");
        emit(pools.freedStacks);emit(pools.ownerGlobal3688);emit(pools.freeTaskHead);emit(pools.freeObjectHead);emit(pools.freeObjectCount);
        emit(pools.currentTask);emit(pools.activeCount);emit(hash(pools.tasks));emit(hash(pools.objects));
        emit(flatHash(pools.priorityHeads));emit(flatHash(pools.activeTags));
        std::array<std::array<uint32_t,2>,256> owners;
        for(unsigned i=0;i<256;++i){const auto h=pools.stacks.at(i+1);owners[i]={h.flags,h.value};}
        emit(hash(owners));emit(hash(palettes));emit(flatHash(residency.slots));emit(flatHash(residency.references));
        emit(random.mode);emit(random.gameSeed);emit(random.librarySeed);emit(draws.size());
        for(const auto& draw:draws) {
            for(auto v:draw.record.fields)emit(v);
            const auto& s=draw.state;emit(s.step);emit(s.time);emit(s.speed);emit(s.flags);
            for(float v:{s.x,s.y,s.z,s.baseScale})emit(std::bit_cast<uint32_t>(v));
            for(auto v:s.motion)emit(v);
            emit(s.scale.bits);emit(s.scaleVelocity.bits);emit(s.scaleAcceleration.bits);emit(s.color);
            for(auto v:s.colorMotion)emit(uint32_t(v));
        }
        if(body) {
            const auto& c=body->timeline.clock();const auto& m=body->timeline.motion();
            for(uint32_t v:{body->timeline.action().id(),c.step,c.fractionalTime,c.endReached,c.endControl,c.objectFlags,c.flags104,c.flags108,uint32_t(c.chainedAction),
                           uint32_t(m.dx),uint32_t(m.vx),uint32_t(m.ax),uint32_t(m.dy),uint32_t(m.vy),uint32_t(m.ay),
                           std::bit_cast<uint32_t>(m.x),std::bit_cast<uint32_t>(m.y),uint32_t(body->pendingFlags)})emit(v);
            for(auto v:body->timeline.attachedEffect())emit(uint32_t(v));
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
