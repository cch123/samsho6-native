#include "local_versus.hpp"
#include "mina_special.hpp"
#include "script_engine.hpp"
#include "ground_state.hpp"
#include <bit>
#include <iostream>
namespace {
unsigned tick;
void w(auto n){std::cout<<' '<<uint32_t(n);}
const ss6::AuxiliaryObject* companion=nullptr;
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
    w(a.bodyState128);w(a.timers[17]);w(a.timers[18]);w(env.battle->flags138);
    w(env.weaponLock->camera.left);w(env.weaponLock->camera.right);w(env.weaponLock->camera.top);
    w(std::bit_cast<uint32_t>(env.weaponLock->opponentBody.timeline.motion().x));
    w(std::bit_cast<uint32_t>(env.weaponLock->opponentBody.timeline.motion().y));w(a.flags24c);
    for(unsigned off:{0x128,0x12c,0x40,0x44})w(companion?(*companion)[off/4]:0);w(a.flags244);
}
}
namespace ss6 {
bool tracedCast(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&,StateEntryContext&,const ScriptEngine&);
bool updateMinaAttack(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& in,const GroundStateFrame& env,StateEntryContext& c,const ScriptEngine& e) {
    companion=a.auxiliaryObject04?&c.tasks.objects.at(a.auxiliaryObject04-1):nullptr;
    std::cout<<"C";w(tick);w(o.ownerCC);actor(o,a,in,env);
    bool finish=tracedCast(o,a,in,env,c,e);
    w(finish);actor(o,a,in,env);std::cout<<'\n';return finish;
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
        for(unsigned i=0;i<2;++i){const auto& f=session.match().fighter(i);w(f.body.color8c);w(f.actor.timers[17]);}
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<" at "<<tick<<'\n';return 1;}}
