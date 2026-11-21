// Records every native descriptor-projectile callback in a selected match.
// Built with projectile_engine.cpp compiled under -DupdateDescriptorProjectile=tracedProjectile.
#include "local_versus.hpp"
#include "projectile_engine.hpp"
#include "state_entry.hpp"
#include "script_engine.hpp"
#include "script_fighter.hpp"
#include "auxiliary_objects.hpp"
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
    const auto& a=owner.actor;
    // Trailing owner words (group 8 homes on the body and arms the actor):
    // body 38/40/44, actor 194/a3c/260/264/274/18c before; 23c/a3c/260/264/274/18c after.
    // Then the opponent (group 15 homes on it; 142120 reads its spirit): body 40/44, actor 10c/13c.
    const ActorCommandInput* in=nullptr; // descriptor projectiles never read the owner's buttons
    const uint32_t ownerBefore[20]{owner.body[0x38/4],owner.body[0x40/4],owner.body[0x44/4],a.state194,uint32_t(a.queuedActionA3c),
                                  a.callbacks260[0],a.callbacks260[1],a.callbacks260[5],uint32_t(a.request18c),
                                  owner.opponentBody[0x40/4],owner.opponentBody[0x44/4],
                                  owner.opponentConfig?owner.opponentConfig->system:0u,
                                  owner.opponentActor?uint32_t(owner.opponentActor->systemState13c):0u,a.flags244,
                                  a.callbacks260[3],in?in->sampledFeatures[0x5b]:0u,in?in->sampledFeatures[0x5c]:0u,in?in->sampledFeatures[0x5d]:0u,
                                  owner.opponentActor?uint32_t(owner.opponentActor->timers[20]):0u,
                                  uint32_t(uint16_t(a.pendingTable))|uint32_t(uint16_t(a.pendingIndex))<<16}; // 190/192 for 1491e0
    tracedProjectile(table,owner,task);
    w(t[0]);for(auto x:o)w(x);w(owner.actor.characterBytesF14[3]);
    w(owner.companion?(*owner.companion)[0x128/4]:0);w(owner.companion?(*owner.companion)[0x12c/4]:0);
    w(owner.companion?(*owner.companion)[0x40/4]:0);w(owner.companion?(*owner.companion)[0x44/4]:0);
    for(auto x:ownerBefore)w(x);
    for(auto x:{a.flags23c,uint32_t(a.queuedActionA3c),a.callbacks260[0],a.callbacks260[1],a.callbacks260[5],uint32_t(a.request18c),a.flags244})w(x);
    std::cout<<'\n';
}
}
namespace ss6 {
// Character projectile callbacks ported in script_fighter.cpp (compiled with
// -DupdateScriptFighterObject=tracedFighterObject); same record as above, without owner words.
void tracedFighterObject(AuxiliaryObjects&,TaggedTaskPools&,uint32_t,const ScriptObjectOwner&);
void updateScriptFighterObject(AuxiliaryObjects& objects,TaggedTaskPools& pools,uint32_t task,const ScriptObjectOwner& owner) {
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    const auto& a=owner.actor;const auto* in=owner.input;
    std::cout<<"P";w(tick);w(o[0x118/4]-1);w(t[0]);for(auto x:o)w(x);
    w(a.flags23c);w(0); // f17
    if(owner.camera){w(uint32_t(owner.camera->left));w(uint32_t(owner.camera->right));w(uint32_t(owner.camera->top));}else{w(0);w(0);w(0);}
    w(0);
    const uint32_t before[19]{owner.body[0x38/4],owner.body[0x40/4],owner.body[0x44/4],a.state194,uint32_t(a.queuedActionA3c),
        a.callbacks260[0],a.callbacks260[1],a.callbacks260[5],uint32_t(a.request18c),
        owner.opponentBody?(*owner.opponentBody)[0x40/4]:0u,owner.opponentBody?(*owner.opponentBody)[0x44/4]:0u,0,0,a.flags244, // 209240 faces the opponent
        a.callbacks260[3],in?in->sampledFeatures[0x5b]:0u,in?in->sampledFeatures[0x5c]:0u,in?in->sampledFeatures[0x5d]:0u,
        owner.opponent?uint32_t(owner.opponent->timers[20]):0u}; // 16e9b8 reads the opponent's timer 20
    tracedFighterObject(objects,pools,task,owner);
    w(t[0]);for(auto x:o)w(x);for(int i=0;i<5;++i)w(0);
    for(auto x:before)w(x);
    for(auto x:{a.flags23c,uint32_t(a.queuedActionA3c),a.callbacks260[0],a.callbacks260[1],a.callbacks260[5],uint32_t(a.request18c),a.flags244})w(x);
    std::cout<<'\n';
}
}
int main(int argc,char** argv) {try {
    // Optional argv[2] = p1/p2/both: CPU control after the public selection.
    const auto seats=argc>2?ss6::versusCpuSeats(argv[2]):std::array<bool,2>{};
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},ss6::VersusEntry::CharacterSelect,seats);
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
