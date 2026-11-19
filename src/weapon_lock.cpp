#include "weapon_lock.hpp"
#include "sound_selection.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
WeaponLock::WeaponLock(const std::filesystem::path& assets):objects_(assets,{0,0,51}) {
    std::ifstream in(assets/"weapon_lock.bin",std::ios::binary);
    std::array<uint8_t,20> raw{};
    if(!in.read(reinterpret_cast<char*>(raw.data()),raw.size())||in.peek()!=EOF)
        throw std::runtime_error("Invalid weapon-lock tables");
    const auto word=[&](unsigned index){uint32_t value=0;for(unsigned j=0;j<4;++j)value|=uint32_t(raw[index*4+j])<<(8*j);return value;};
    if(word(0)!=51)throw std::runtime_error("Unsupported common resource binding");
    for(unsigned i=0;i<4;++i)constants_[i].bits=word(i+1);
}
void WeaponLock::enter(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p,SoundSelection* sound) {
    b.flags138|=2;
    for(unsigned i=0;i<2;++i) {
        auto& a=p[i].actor;
        a.timers[13]=0;a.pendingTable=0;a.pendingIndex=31;
        a.weaponLockPhaseA54=0;a.weaponLockResultA58=-1;b.match.players[i].weaponLockPresses30=0;
    }
    if(sound)sound->sample(-1,22);
    const auto parent=p[0].body.childParentWords();
    const auto handle=objects_.createCommonEffect(b.entry.tasks,b.objectTasks,&parent,0x1396,0);
    if(!handle)throw std::runtime_error("Weapon-lock effect needs a free battle registry slot");
    auto& o=b.entry.tasks.objects.at(handle-1);
    objects_.request(o,135,false,true);
    o[0x108/4]&=~0x2000u;o[0x38/4]&=~0x80000u;
    const auto x0=ScalarFloat{std::bit_cast<uint32_t>(p[0].body.timeline.motion().x)};
    const auto x1=ScalarFloat{std::bit_cast<uint32_t>(p[1].body.timeline.motion().x)};
    o[0x40/4]=x0.add(x1).mul(constants_[1]).bits;o[0x44/4]=constants_[0].bits;
    b.entry.tasks.tasks.at(o[1]-1)[0]=0x145e30;
}
bool WeaponLock::aiPress(StateEntryActor& a,GameRandom& random) {
    //158ac8 receives actor+8, so its+ec field is actor+f4. The EE shift
    //wraps BEFORE signed division; using a wider expression changes RNG.
    const int32_t doubled=std::bit_cast<int32_t>(uint32_t(a.controlFieldF4)<<1);
    const auto bound=std::bit_cast<int32_t>(uint32_t(doubled/3)+7u);
    return random.bounded(bound)==0;
}
void WeaponLock::update(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p,SoundSelection* sound) {
    bool enough=false;
    for(unsigned i=0;i<2;++i) {
        auto& a=p[i].actor;auto& count=b.match.players[i].weaponLockPresses30;
        const int elapsed=a.timers[13]/256;
        if(sound&&i==0&&a.weaponLockPhaseA54!=0&&elapsed<120&&elapsed%96==0)sound->sample(-1,62);
        //Negative phase words are outside this UNSIGNED range, too.
        if(uint32_t(a.weaponLockPhaseA54)<2) {
            const auto& f=p[i].input.sampledFeatures;
            const bool press=a.controlKindA20?aiPress(a,b.random):(f[6]||f[7]||f[8]);
            //Several attack edges in one visit contribute only one point.
            if(press)count=std::bit_cast<int32_t>(uint32_t(count)+1u);
            if(count>=10)enough=true;
        }
        const auto c=p[i].body.timeline.clock();p[i].body.setFlags(c.flags104|0x400000,c.flags108);
        GroundStateRuntime::captureBody(p[i].body,a);
    }
    bool finished=false;
    const int32_t elapsed=p[0].actor.timers[13];
    if(enough&&elapsed>=0x5000) {
        finished=p[0].actor.weaponLockPhaseA54==1&&p[1].actor.weaponLockPhaseA54==1;
    } else if(elapsed>0xb3ff) {
        //This timeout is an ELSE branch, not an unconditional deadline.
        //With enough presses and an unready phase, the first branch waits.
        enough=finished=true;
    }
    if(enough&&(p[0].actor.weaponLockResultA58==-1||p[1].actor.weaponLockResultA58==-1)) {
        const auto c0=b.match.players[0].weaponLockPresses30,c1=b.match.players[1].weaponLockPresses30;
        p[0].actor.weaponLockResultA58=c0>c1?2:3;
        p[1].actor.weaponLockResultA58=c1>c0?2:3;
    }
    if(!finished)return;
    b.field08=0;
    for(const auto& player:p) {
        player.actor.weaponLockPhaseA54=player.actor.weaponLockResultA58;
        player.input.clearBuffers(); //1797a8 preserves partial command progress/results.
    }
    //Walk registrations, preserving holes and aliases. Completion changes
    //callbacks and visibility, not allocation or the pending action word.
    for(const auto handle:b.objectTasks)if(handle) {
        auto& task=b.entry.tasks.tasks.at(handle-1);
        auto& o=b.entry.tasks.objects.at(task[7]-1);
        if(o[0xcc/4]==7&&o[0xc4/4]==135) {
            b.entry.tasks.tasks.at(o[1]-1)[0]=0x147540;
            o[0x108/4]|=0x2000;
        }
    }
}
void WeaponLock::task(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p,uint32_t task) const {
    auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(task-1)[7]-1);
    o[0x38/4]&=~0x80000u;
    const auto x0=ScalarFloat{std::bit_cast<uint32_t>(p[0].body.timeline.motion().x)};
    const auto x1=ScalarFloat{std::bit_cast<uint32_t>(p[1].body.timeline.motion().x)};
    o[0x40/4]=x0.add(x1).mul(constants_[2]).bits;o[0x44/4]=constants_[3].bits;
}
}
