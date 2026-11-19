#include "local_versus.hpp"
#include "rimururu_special.hpp"
#include <bit>
#include <iostream>
namespace {
unsigned tick;
void w(auto n){std::cout<<' '<<uint32_t(n);}
void actor(ss6::PlayerObject& o,ss6::StateEntryActor& a,const ss6::ActorCommandInput& in,const ss6::GroundStateFrame& env) {
    const auto& m=o.timeline.motion();const auto c=o.timeline.clock();
    for(auto n:{a.state194,a.flags23c,a.flags248,uint32_t(a.stateFlags19a),uint32_t(a.request18c),uint32_t(a.queuedActionA3c)})w(n);
    for(auto n:a.callbacks260)w(n);
    for(auto n:a.registry28c)w(n);
    w(o.timeline.action().id());w(c.flags104);w(c.flags108);w(c.objectFlags);w(c.endReached);w(c.endControl);w(o.scriptLatch134);
    for(auto n:{m.x,m.y,env.opponentX})w(std::bit_cast<uint32_t>(n));
    for(auto n:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})w(n);
    for(auto offset:{0xe0,0xfc,0x160,0x168})w(in.sampledFeatures[offset/4]);
    w(env.weaponLock->opponent.flags23c);w(env.battle->timers.lock);w(env.battle->gauges.focus46a948);w(env.battle->gauges.paletteTones[512]);w(a.pendingTable);w(a.pendingIndex);
}
constexpr unsigned fields[]={0x20,0x24,0x100,0x104,0x108,0xd0,0xd4,0x11c,0x38,0x40,0x44,0x4c,0x50,0x54,0x58,0x5c,0x60,0x64,0x68,0x6c,0x70,0xc0,0xc4};
void ice(const ss6::AuxiliaryObject& o){for(auto k:fields)w(o[k/4]);}
}
namespace ss6 {
bool tracedCast(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&);
void tracedIce(AuxiliaryObjects&,TaggedTaskPools&,uint32_t,const StageCamera&,unsigned);
bool updateRimururuSpecial(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& in,const GroundStateFrame& env) {
    std::cout<<"C";w(tick);w(o.ownerCC);actor(o,a,in,env);
    const auto& p=env.battle->entry.tasks;AuxiliaryObject platform{};
    for(auto h:env.weaponLock->objectTasks)if(h) {
        const auto& child=p.objects.at(p.tasks.at(h-1)[7]-1);
        if(child[0xcc/4]==2&&child[0xd0/4]==10){platform=child;break;}
    }
    w(platform[0xcc/4]);ice(platform);
    bool finish=tracedCast(o,a,in,env);
    w(finish);actor(o,a,in,env);std::cout<<'\n';return finish;
}
void updateRimururuIce(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t handle,const StageCamera& camera,unsigned action) {
    const auto& task=pools.tasks.at(handle-1);const auto& o=pools.objects.at(task[7]-1);
    std::cout<<"I";w(tick);w(o[0xc/4]);w(action);w(camera.left);w(camera.right);w(task[0]);ice(o);
    tracedIce(objects,pools,handle,camera,action);w(task[0]);ice(o);std::cout<<'\n';
}
}
int main(int argc,char** argv){try {
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},true);
    std::array<uint32_t,2> last{},held{};
    const unsigned start=std::stoul(argv[2]);
    for(tick=1;std::cin>>held[0]>>held[1];++tick) {
        std::array<ss6::NormalizedPadSample,2> p;
        for(unsigned i=0;i<2;++i)p[i]={held[i],held[i]&~last[i]};last=held;session.tick(p);
        if(tick<start)continue;
        std::cout<<"F";w(tick);
        for(unsigned i=0;i<2;++i){
            const auto& f=session.match().fighter(i);
            w(f.config.character);w(f.config.system);w(f.actor.stateTable());w(f.actor.stateIndex());
            w(f.body.timeline.action().id());w(f.body.timeline.clock().step);w(f.actor.fieldA30);w(f.hits);w(f.guards);w(f.actor.flags23c);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<" at "<<tick<<'\n';return 1;}}
