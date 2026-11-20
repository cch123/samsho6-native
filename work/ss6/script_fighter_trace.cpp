// Per-visit trace of updateScriptFighterAttack (script_fighter.cpp compiled
// with -DupdateScriptFighterAttack=tracedCast); same record as mina_special_trace.cpp.
#include "local_versus.hpp"
#include "script_fighter.hpp"
#include "script_engine.hpp"
#include "ground_state.hpp"
#include <array>
#include <bit>
#include <iostream>
namespace {
unsigned tick;
void w(auto n){std::cout<<' '<<uint32_t(n);}
const ss6::AuxiliaryObject* companion=nullptr;
// The first four slots of this seat's 48-slot registry, any kind (140d78
// scans it, e.g. type 0x24 for the first kind-2 object).
constexpr unsigned registrySlots=48;
std::array<const ss6::AuxiliaryObject*,registrySlots> owned{};
std::array<uint32_t,registrySlots> ownedHandles{};
int companionSlot=-1;
// Basara's body+128 and Kyoshiro's body+128..134 hold object handles: name their registry slots.
uint32_t slotMarker(const ss6::StateEntryActor& a,uint32_t v,bool late=false) {
    // Kyoshiro's words hold handles only once his selector-6 scene made them:
    // 128/12c from 1f10f0 (callback 1f11b8 on), 130/134 from 1f11b8 (1f1370 on).
    // Elsewhere 130 is a script counter whose value can equal a live handle.
    const auto h=a.callbacks260[0];
    const bool kyo=a.character==5&&a.state194==0x460001&&(h==0x1f1370||h==0x1f1450||h==0x1f1520||(!late&&h==0x1f11b8));
    // Gen-an's / Nicotine's chains: handles once the head exists (205558 / 206a90 bind the next callback).
    const bool chain=(a.character==35&&a.state194==0x460001&&(h==0x2056c8||h==0x205750||h==0x169a50))||
                     (a.character==39&&(h==0x206c00||h==0x206c88||
                                        (h==0x169a50&&(a.state194==0x4d0001||a.state194==0x4e0001))));
    if(a.character==8||kyo||chain)for(unsigned s=0;s<registrySlots;++s)if(v&&ownedHandles[s]==v)return 0x80000000u|s;
    return v;
}
constexpr unsigned slotWords[]{0xcc,0xd0,0x24,0x40,0x28,0x38,0x44,0xb0,0xc0,0xc4,0x104,0x108,0xe4,0x128,0x12c,0x130,0x134};
void actor(ss6::PlayerObject& o,ss6::StateEntryActor& a,const ss6::ActorCommandInput& in,const ss6::GroundStateFrame& env) {
    const auto& m=o.timeline.motion();const auto c=o.timeline.clock();
    for(auto n:{a.state194,a.flags23c,a.flags248,uint32_t(a.stateFlags19a),uint32_t(a.request18c),uint32_t(a.queuedActionA3c)})w(n);
    for(auto n:a.callbacks260)w(n);
    for(auto n:a.registry28c)w(n);
    w(o.timeline.action().id());w(c.flags104);w(c.flags108);w(c.objectFlags);w(c.endReached);w(c.endControl);w(slotMarker(a,o.scriptLatch134,true));
    for(auto n:{m.x,m.y,env.opponentX})w(std::bit_cast<uint32_t>(n));
    for(auto n:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})w(n);
    for(auto offset:{0xe0,0xfc,0x160,0x168})w(in.sampledFeatures[offset/4]);
    w(env.weaponLock->opponent.flags23c);w(env.battle->timers.lock);w(env.battle->gauges.focus46a948);w(env.battle->gauges.paletteTones[512]);w(a.pendingTable);w(a.pendingIndex);
    {
        // Basara's body+128 holds an object (event 18, selector 6): name its registry slot.
        w(slotMarker(a,a.bodyState128));
    }
    w(a.timers[17]);w(a.timers[18]);w(env.battle->flags138);
    w(env.weaponLock->camera.left);w(env.weaponLock->camera.right);w(env.weaponLock->camera.top);
    w(std::bit_cast<uint32_t>(env.weaponLock->opponentBody.timeline.motion().x));
    w(std::bit_cast<uint32_t>(env.weaponLock->opponentBody.timeline.motion().y));w(a.flags24c);w(env.weaponLock->opponent.state194); // 164bc8
    for(unsigned off:{0x128,0x12c,0x40,0x44,0x130,0x134,0x24,0xc0,0xc4,0x104,0x38,0xfc})w(companion?(*companion)[off/4]:0);w(a.flags244);
    // Life request and rage/sword words written by entry event 28 (165580).
    for(auto n:{a.pendingDamageA38,a.rageState120,a.rageAmount124,a.rageDecay128,a.swordCurrent134,a.swordMaximum138})w(n);
    w(env.config?env.config->system:0); // actor+10c: the spirit whose parameters 14efb8 reads
    w(a.fieldA30); // 165580 caps the self-drain at the current life
    for(unsigned s=0;s<registrySlots;++s){const auto* x=owned[s];w(int(s)==companionSlot?2:x!=nullptr);for(unsigned off:slotWords)w(x?(*x)[off/4]:0);}
    w(slotMarker(a,a.bodyLatch12c)); // body+12c (Yumeji's chosen follow-up)
    for(unsigned n=6;n<=10;++n)w(in.sampledFeatures[n]); // actor+2dc..2ec button features
    for(unsigned n=0x5b;n<=0x5d;++n)w(in.sampledFeatures[n]); // held buttons 0..2 (178dc8)
    w(a.timerDelta);w(a.timers[22]);w(a.timers[23]);w(in.sampledFeatures[62]);w(in.sampledFeatures[64]);w(slotMarker(a,a.bodyCounter130,true)); // charge/mash moves
    w(in.sampledFeatures[55]);w(in.sampledFeatures[57]); // 1fa7c0 lever features
    w(a.characterBytesF14[4]); // f18 (Shizumaru's umbrella charge)
    w(a.characterBytesF14[1]);w(a.characterBytesF14[2]); // f15/f16 (Kazuki's fire levels)
    for(unsigned off:{0x14c,0x150,0x158,0x15c})w(in.sampledFeatures[off/4]); // 174330 diagonals
    w(in.sampledFeatures[3]);w(in.sampledFeatures[45]); // Amakusa's 1f44e0/1f4588
    {const auto words=o.childParentWords();w(words[0xb0/4]);w(words[0x30/4]);} // chain depth base, effect clock
    w(a.jumpDirectionA44); // 200cd8 jumps by a44
    w(env.random?uint32_t(env.random->mode):0);w(env.random?env.random->gameSeed:0); // 443150 / 3d2e80 (112300)
    w(env.random?uint32_t(env.random->librarySeed):0);w(env.random?uint32_t(env.random->librarySeed>>32):0); // _impure_ptr+a8 (316b90)
    w(in.sampledFeatures[24]); // 1638e8 type 0x3c: button hold (actor+324)
    w(std::bit_cast<uint32_t>(env.weaponLock->camera.width)); // stage+c (script events 56/57)
    {const auto& oa=env.weaponLock->opponent; // opponent body latches 128..134 (row 0x3f pinning, event 63)
     w(oa.bodyState128);w(oa.bodyLatch12c);w(oa.bodyCounter130);w(env.weaponLock->opponentBody.scriptLatch134);}
    w(o.timeline.clock().step); // body+28: the record step row 0x3f pins by
    w(env.weaponLock->opponent.character); // opponent a10 (168ea0 anchors in row 0x3f)
    w(uint32_t(o.timeline.attachedEffect()[1]));w(uint32_t(o.timeline.attachedEffect()[2])); // body+110/114 (16fae0)
}
}
namespace ss6 {
bool tracedCast(PlayerObject&,StateEntryActor&,const ActorCommandInput&,const GroundStateFrame&,StateEntryContext&,const ScriptEngine&);
bool updateScriptFighterAttack(PlayerObject& o,StateEntryActor& a,const ActorCommandInput& in,const GroundStateFrame& env,StateEntryContext& c,const ScriptEngine& e) {
    companion=a.auxiliaryObject04?&c.tasks.objects.at(a.auxiliaryObject04-1):nullptr;
    const auto find=[&]{
        owned={};ownedHandles={};companionSlot=-1;
        if(env.pools)for(unsigned s=0;s<registrySlots&&s<env.ownObjectTasks.size();++s)
            if(const auto t=env.ownObjectTasks[s]){
                ownedHandles[s]=env.pools->tasks.at(t-1)[7];owned[s]=&env.pools->objects.at(ownedHandles[s]-1);
                // The companion (actor+4) is compared through its own block; its registry slot reports presence 2.
                if(owned[s]==companion){owned[s]=nullptr;ownedHandles[s]=0;companionSlot=int(s);}
            }
    };
    find();
    std::cout<<"C";w(tick);w(o.ownerCC);actor(o,a,in,env);
    bool finish=tracedCast(o,a,in,env,c,e);
    find(); // the visit may create the object (Charlotte's 1f5828)
    w(finish);actor(o,a,in,env);std::cout<<'\n';return finish;
}
}
int main(int argc,char** argv){try {
    // Optional argv[3] = p1/p2/both: CPU control after the public selection.
    const auto seats=argc>3?ss6::versusCpuSeats(argv[3]):std::array<bool,2>{};
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},ss6::VersusEntry::CharacterSelect,seats);
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
