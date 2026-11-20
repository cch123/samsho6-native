// Per-call trace of updateVictimScript (victim_script.cpp compiled with
// -DupdateVictimScript=tracedVictim) in publicly selected matches, for
// validate_victim_visits.py. Each record holds both fighters' actor/body
// words and the battle words the table-B engine touches, before and after.
#include "local_versus.hpp"
#include "victim_script.hpp"
#include "battle_round.hpp"
#include <bit>
#include <iostream>
namespace {
unsigned tick;
void w(auto n){std::cout<<' '<<uint32_t(n);}
// Genjuro's rows keep an object in the victim's body+134 (0x1e): name it.
const ss6::PlayerObject* keptBody=nullptr;bool keptObject=false;
void fighter(const ss6::PlayerObject& o,const ss6::StateEntryActor& a) {
    for(auto n:{a.state194,a.flags23c,a.flags244,a.flags248,uint32_t(a.stateFlags19a),uint32_t(a.request18c),
                uint32_t(uint16_t(a.pendingTable)),uint32_t(uint16_t(a.pendingIndex)),uint32_t(a.queuedActionA3c),
                uint32_t(a.fieldA30),uint32_t(a.pendingDamageA38),uint32_t(a.pendingCharacter254)})w(n);
    for(auto n:a.callbacks260)w(n);
    for(auto n:a.override27c)w(n);
    for(auto n:a.registry28c)w(n);
    for(auto n:a.timers)w(n);
    w(a.timerDelta);
    for(auto n:{a.rageState120,a.rageAmount124,a.rageDecay128,a.swordCurrent134,a.swordMaximum138})w(n); // 1413d8 meters
    w(a.characterBytesF14[8]);w(a.characterBytesF14[9]); // f1c/f1d (Andrew's rounds)
    w(a.characterBytesF14[1]);w(a.characterBytesF14[2]); // f15/f16 (Kazuki's fire levels)
    w(a.fieldA50); // a50: the defense adjustment read by 1a41b8
    const auto c=o.timeline.clock();const auto& m=o.timeline.motion();
    for(auto n:{uint32_t(o.timeline.action().id()),c.step,c.objectFlags,c.flags104,c.flags108,c.endReached,c.endControl,
                uint32_t(o.pendingFlags),a.bodyField124,a.bodyState128,a.bodyLatch12c,a.bodyCounter130,
                (keptObject&&&o==keptBody&&o.scriptLatch134)?0x80000000u:o.scriptLatch134})w(n);
    for(auto n:{m.x,m.y})w(std::bit_cast<uint32_t>(n));
    for(auto n:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})w(n);
    for(auto n:{o.historyOffsetEc,o.historyOffsetF0})w(std::bit_cast<uint32_t>(n)); // body+ec/f0 (16e788 anchors)
    {const auto words=o.childParentWords();w(words[0xb0/4]);w(words[0x30/4]);} // depth base (chain layouts) and the clock copied into new effects
}
void battle(const ss6::BattleRoundState& b) {
    w(b.timers.values[5]);w(b.timers.values[6]);w(b.pause.remaining);w(b.pause.delay);
    w(b.camera.shakeX44);w(b.camera.shakeY48);w(b.camera.commands.size());
    for(unsigned i=0;i<4;++i){const bool has=i<b.camera.commands.size();w(has?b.camera.commands[i].kind:0);w(has?uint32_t(b.camera.commands[i].parameter):0);}
    w(b.timers.values[0]);w(b.timeOption13c);w(b.field08); // 14a8d0's time-out test
}
// The attacker's button features 58..61 (actor+3ac..3b8) read by 1f3db8.
// The delivering object (victim body +124): presence, owner-registry
// membership and the words 168220/1657b0/165a78 read or write.
constexpr unsigned childWords[]{0x0c,0xcc,0x38,0x40,0x44,0x104,0x108,0xdc,0xe4,0xe8,0xc0,0x24,0x28,0x14};
// The visit's child: an end op may detach it (body +124 = 0) while the
// object itself lives on, so its words are still compared after the visit.
uint32_t visitChild=0;
void child(const ss6::StateEntryActor& v,const ss6::StateEntryContext& c,const ss6::GroundStateFrame& f) {
    const auto handle=v.bodyField124?v.bodyField124:visitChild;
    const auto* o=handle?&c.tasks.objects.at(handle-1):nullptr;
    bool registered=false;
    if(o)for(auto list:{std::span<const uint32_t>(f.weaponLock->objectTasks),std::span<const uint32_t>(f.opponentObjectTasks)})
        for(auto t:list)if(t&&c.tasks.tasks.at(t-1)[7]==handle)registered=true;
    w(v.bodyField124!=0);w(registered);for(auto off:childWords)w(o?(*o)[off/4]:0);
    w(o&&(*o)[1]?c.tasks.tasks.at((*o)[1]-1)[0]:0); // its task callback (147530 parks it on 147540); 0 once freed
    const auto* k=(keptObject&&keptBody&&keptBody->scriptLatch134)?&c.tasks.objects.at(keptBody->scriptLatch134-1):nullptr;
    for(unsigned off:{0x24u,0xc4u,0x108u})w(k?(*k)[off/4]:0);
}
// Kyoshiro's scene (source 5): body+128..134 of both fighters hold object
// handles; their words are snapshot so the validator can build fixture objects.
constexpr unsigned sceneWords[]{0x24,0x28,0x38,0x40,0x44,0xb0,0xc0,0xc4,0x104,0x108,0x8c,0x30};
void scene(const ss6::PlayerObject& b0,const ss6::StateEntryActor& a0,const ss6::PlayerObject& b1,const ss6::StateEntryActor& a1,
           const ss6::StateEntryContext& c,const ss6::GroundStateFrame& f) {
    const auto scene=[](unsigned c){return c==5||c==11||c==31||c==33||c==35||c==39;};
    const bool on=scene(a0.character)||scene(a1.character);
    for(auto [b,a]:{std::pair{&b0,&a0},std::pair{&b1,&a1}})
        for(uint32_t h:{a->bodyState128,a->bodyLatch12c,a->bodyCounter130,b->scriptLatch134})
        {
            for(auto off:sceneWords)w(on&&h&&h<=c.tasks.objects.size()?c.tasks.objects[h-1][off/4]:0);
            bool registered=false; // in the attacker's (any fighter's) registry: 168400 freezes it
            if(on&&h)for(auto l:{std::span<const uint32_t>(f.weaponLock->objectTasks),std::span<const uint32_t>(f.opponentObjectTasks)})
                for(auto t:l)if(t&&c.tasks.tasks.at(t-1)[7]==h)registered=true;
            w(registered);
        }
}
void features(const ss6::GroundStateFrame& f) {
    for(unsigned n=58;n<=61;++n)w(f.opponentInput?f.opponentInput->sampledFeatures[n]:0);
    w(f.weaponLock->camera.left);w(f.weaponLock->camera.right); // stage+10/14 read by 146a50
    w(std::bit_cast<uint32_t>(f.weaponLock->camera.x)); // stage+4 (row type 0x50)
    w(f.config?f.config->system:0);w(f.opponentSystem); // actor+10c spirits read by 1413d8/14efb8
    for(unsigned n=6;n<=8;++n)w(f.opponentInput?f.opponentInput->special[n].recognized:0); // 604/608/60c: character 32's lock
    for(unsigned n:{10u,63u,64u})w(f.ownInput?f.ownInput->sampledFeatures[n]:0); // the victim's recovery inputs (1720b0 / 172008)
    w(f.opponentInput?f.opponentInput->special[18].recognized:0); // 634: Kuroko's repeat (20b648 / 20b930)
}
}
namespace ss6 {
bool tracedVictim(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&,const VictimTables&,const ScriptEngine&);
bool tracedLanding(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
void tracedLifeHold(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
// The source's own 166e10 visit (end op 9), recorded like the landing.
void updateLifeHold(PlayerObject& body,StateEntryActor& v,StateEntryContext& c,const GroundStateFrame& f) {
    auto& world=*f.weaponLock;visitChild=v.bodyField124;
    std::cout<<"L";w(tick);w(c.player);w(v.callbacks260[0]);
    fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    tracedLifeHold(body,v,c,f);
    w(0);fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    std::cout<<'\n';
}
// The attacker's own 174158 visit, recorded in the victim role (cb[0] = the visiting actor).
bool updateLanding174158(PlayerObject& body,StateEntryActor& v,StateEntryContext& c,const GroundStateFrame& f) {
    auto& world=*f.weaponLock;visitChild=v.bodyField124;
    std::cout<<"L";w(tick);w(c.player);w(v.callbacks260[0]);
    fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    const bool recover=tracedLanding(body,v,c,f);
    w(recover);fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    std::cout<<'\n';return recover;
}
bool updateVictimScript(PlayerObject& body,StateEntryActor& v,StateEntryContext& c,const GroundStateFrame& f,const VictimTables& t,const ScriptEngine& e) {
    auto& world=*f.weaponLock;
    std::cout<<"V";w(tick);w(c.player);w(v.callbacks260[0]);
    visitChild=v.bodyField124;keptBody=&body;keptObject=world.opponent.character==7;
    // Galford's rows 0x19/0x1a adopt his companion (attacker actor+4) as the child.
    if(!visitChild&&world.opponent.character==4)visitChild=world.opponent.auxiliaryObject04;
    fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    const bool recover=tracedVictim(body,v,c,f,t,e);
    w(recover);fighter(body,v);fighter(world.opponentBody,world.opponent);battle(*f.battle);features(f);child(v,c,f);scene(body,v,world.opponentBody,world.opponent,c,f);
    std::cout<<'\n';return recover;
}
}
int main(int argc,char** argv){try {
    const auto seats=argc>2?ss6::versusCpuSeats(argv[2]):std::array<bool,2>{};
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},ss6::VersusEntry::CharacterSelect,seats);
    std::array<uint32_t,2> last{},held{};
    for(tick=1;std::cin>>held[0]>>held[1];++tick) {
        std::array<ss6::NormalizedPadSample,2> p;
        for(unsigned i=0;i<2;++i)p[i]={held[i],held[i]&~last[i]};last=held;session.tick(p);
    }
}catch(const std::exception& e){std::cerr<<e.what()<<" at "<<tick<<'\n';return 1;}}
