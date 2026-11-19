#include "local_versus.hpp"
#include "nakoruru_eagle_attack.hpp"
#include <bit>
#include <iostream>

namespace {
unsigned tick;
void word(auto v) {std::cout<<' '<<uint32_t(v);}
void snapshot(ss6::PlayerObject& o,ss6::StateEntryActor& a,const ss6::ActorCommandInput& in,
              const ss6::StateEntryContext& cx,const ss6::GroundStateFrame& env) {
    const auto& m=o.timeline.motion();const auto& c=o.timeline.clock();const auto& bird=cx.tasks.objects.at(a.auxiliaryObject04-1);
    word(a.state194);word(a.flags23c);word(a.flags244);word(a.flags248);word(a.flags24c);word(a.stateFlags19a);
    word(a.request18c);word(a.queuedActionA3c);word(in.sampledFeatures[0xfc/4]);
    for(auto v:a.callbacks260)word(v);for(auto v:a.registry28c)word(v);
    word(o.timeline.action().id());word(c.flags104);word(c.flags108);word(c.objectFlags);word(c.endReached);word(c.endControl);word(o.scriptLatch134);
    for(auto v:{m.x,m.y,env.opponentX})word(std::bit_cast<uint32_t>(v));
    for(auto v:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})word(v);
    for(auto off:{0x40,0x44,0x128,0x12c,0x130})word(bird[off/4]);
    word(env.weaponLock->opponent.flags23c);word(env.battle->timers.lock);word(env.battle->gauges.focus46a948);
    word(env.battle->gauges.paletteTones[512]);word(a.pendingTable);word(a.pendingIndex);
}
}
namespace ss6 {
// Only the test build renames the production entry. Snapshot both sides of
// each real visit so the unmodified EE callback can be run with identical
// external inputs, even during hitstop or as a contact changes the victim.
bool tracedEagleImplementation(PlayerObject&,StateEntryActor&,const ActorCommandInput&,StateEntryContext&,const GroundStateFrame&);
bool updateNakoruruEagleAttack(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& in,
                                StateEntryContext& cx,const GroundStateFrame& env) {
    std::cout<<"C "<<tick<<' '<<o.ownerCC;snapshot(o,a,in,cx,env);
    bool recover=tracedEagleImplementation(o,a,in,cx,env);
    word(recover);snapshot(o,a,in,cx,env);std::cout<<'\n';return recover;
}
}
int main(int argc,char** argv) {try{
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},true);
    std::array<uint32_t,2> last{},held{};std::array<ss6::NormalizedPadSample,2> p;
    for(tick=1;std::cin>>held[0]>>held[1];++tick) {
        for(unsigned i=0;i<2;++i)p[i]={held[i],held[i]&~last[i]};last=held;session.tick(p);
        if(tick<unsigned(std::stoul(argv[2])))continue;
        const auto& m=session.match();std::cout<<"F "<<tick;
        for(unsigned i=0;i<2;++i) {
            const auto& f=m.fighter(i);word(f.config.character);word(f.config.system);word(f.actor.stateTable());word(f.actor.stateIndex());
            word(f.body.timeline.action().id());word(f.body.timeline.clock().step);word(f.actor.fieldA30);
            word(f.hits);word(f.guards);word(f.actor.flags23c);word(f.actor.rageState120);
            if(f.actor.auxiliaryObject04){const auto& bird=m.battle().entry.tasks.objects.at(f.actor.auxiliaryObject04-1);for(auto off:{0x24,0x28,0x128,0x130})word(bird[off/4]);}
            else for(int j=0;j<4;++j)word(0);
        }
        word(m.battle().match.roundIndex);
        for(const auto& seat:m.battle().match.players)word(seat.wins);
        for(unsigned i=0;i<2;++i) {
            const auto& f=m.fighter(i);
            if(!f.actor.auxiliaryObject04)continue;
            const auto& eagle=m.battle().entry.tasks.objects.at(f.actor.auxiliaryObject04-1);
            for(auto value:eagle)word(value);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<" at "<<tick<<'\n';return 1;}}
