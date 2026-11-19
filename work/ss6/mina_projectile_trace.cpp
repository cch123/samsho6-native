// Records every native descriptor-projectile callback in a selected match.
// Built with projectile_engine.cpp compiled under -DupdateDescriptorProjectile=tracedProjectile.
#include "local_versus.hpp"
#include "projectile_engine.hpp"
#include "state_entry.hpp"
#include "script_engine.hpp"
#include <iostream>
namespace {
unsigned tick;
void w(uint32_t n){std::cout<<' '<<n;}
}
namespace ss6 {
void tracedProjectile(const ProjectileTable&,ProjectileOwner&,uint32_t);
uint32_t tracedSpawn(const ProjectileTable&,ProjectileOwner&,const ScriptRow&);
uint32_t spawnScriptProjectile(const ProjectileTable& table,ProjectileOwner& owner,const ScriptRow& row) {
    const auto& a=owner.actor;
    std::cout<<"S";w(tick);w(owner.player);
    for(auto x:{a.state194,a.flags23c,a.flags244,a.flags248,a.callbacks260[3],uint32_t(a.characterBytesF14[3])})w(x);
    for(auto x:a.registry28c)w(x);
    for(auto x:owner.body)w(x);
    w(owner.opponentBody[0x40/4]);w(owner.opponentBody[0x44/4]);
    w(uint32_t(owner.camera.left));w(uint32_t(owner.camera.right));w(uint32_t(owner.camera.top));
    const auto handle=tracedSpawn(table,owner,row);
    w(handle!=0);w(a.characterBytesF14[3]);w(a.flags248);
    if(handle) {
        const auto& o=owner.pools.objects.at(handle-1);
        w(owner.pools.tasks.at(o[1]-1)[0]);for(auto x:o)w(x);
    }
    std::cout<<'\n';
    return handle;
}
void updateDescriptorProjectile(const ProjectileTable& table,ProjectileOwner& owner,uint32_t task) {
    auto& t=owner.pools.tasks.at(task-1);auto& o=owner.pools.objects.at(t[7]-1);
    std::cout<<"P";w(tick);w(owner.player);w(t[0]);for(auto x:o)w(x);
    w(owner.actor.flags23c);w(owner.actor.characterBytesF14[3]);
    w(uint32_t(owner.camera.left));w(uint32_t(owner.camera.right));w(uint32_t(owner.camera.top));
    w(owner.companion?(*owner.companion)[0x128/4]:0);
    tracedProjectile(table,owner,task);
    w(t[0]);for(auto x:o)w(x);w(owner.actor.characterBytesF14[3]);
    w(owner.companion?(*owner.companion)[0x128/4]:0);w(owner.companion?(*owner.companion)[0x12c/4]:0);
    w(owner.companion?(*owner.companion)[0x40/4]:0);w(owner.companion?(*owner.companion)[0x44/4]:0);
    std::cout<<'\n';
}
}
int main(int argc,char** argv) {try {
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},ss6::VersusEntry::CharacterSelect,{});
    std::array<uint32_t,2> last{},held{};
    for(tick=1;std::cin>>held[0]>>held[1];++tick) {
        std::array<ss6::NormalizedPadSample,2> p;
        for(unsigned i=0;i<2;++i)p[i]={held[i],held[i]&~last[i]};last=held;session.tick(p);
        const auto& m=session.match();
        std::cout<<"F";w(tick);
        for(unsigned i=0;i<2;++i) {
            const auto& f=m.fighter(i);
            w(f.actor.stateTable());w(f.actor.stateIndex());w(f.body.timeline.action().id());w(f.actor.fieldA30);w(f.hits);w(f.guards);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<" at "<<tick<<'\n';return 1;}}
