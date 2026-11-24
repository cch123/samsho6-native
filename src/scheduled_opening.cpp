#include "asset_files.hpp"
#include "scheduled_opening.hpp"
#include "effect_snapshot.hpp"
#include "sound_selection.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
unsigned actionCount(const std::array<uint32_t,27>& d,unsigned first=5) {
    unsigned n=0;while(n<8&&std::bit_cast<int32_t>(d[first+n])>=0)++n;return n;
}
int32_t signedWord(uint32_t value) {return std::bit_cast<int32_t>(value);}
uint32_t randomSpeed(GameRandom& random,uint32_t lo,uint32_t hi) {
    //124620 always uses the LIBRARY generator, independent of game mode.
    //The product wraps before its arithmetic shift, then speed scales by10000.
    const uint32_t product=(random.nextLibrary()&0x7fff)*(hi-lo);
    return (lo+uint32_t(signedWord(product)>>15))*10000u;
}
void capacity(const TaggedTaskPools& pools,unsigned objects,unsigned tasks) {
    auto o=pools.freeObjectHead,t=pools.freeTaskHead;
    for(unsigned i=0;i<objects;++i) {
        if(!o)throw std::runtime_error("Opening effect object pool exhausted");
        o=pools.objects.at(o-1)[78];
    }
    for(unsigned i=0;i<tasks;++i) {
        if(!t)throw std::runtime_error("Opening effect task pool exhausted");
        t=pools.tasks.at(t-1)[3];
    }
}
}
ScheduledOpening::ScheduledOpening(const std::filesystem::path& assets,SoundSelection* sound):bank_(assets),sound_(sound) {
    constexpr unsigned size=15*108+4;
    std::ifstream in(resolveAsset(assets/"opening_tasks.bin"),std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=size)throw std::runtime_error("Invalid opening task tables");
    std::array<uint8_t,size> data{};in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(data.data()),size))throw std::runtime_error("Truncated opening task tables");
    auto word=[&](unsigned at){uint32_t v=0;for(unsigned b=0;b<4;++b)v|=uint32_t(data[at+b])<<(b*8);return v;};
    for(unsigned i=0;i<15;++i)for(unsigned j=0;j<27;++j)descriptors_[i][j]=word(i*108+j*4);
    palette_=word(15*108);
    if(palette_>=24)throw std::runtime_error("Invalid opening palette mapping");
    for(unsigned i=1;i<15;++i) {
        const auto& d=descriptors_[i];
        const uint32_t callback=i==1?0x124b48:(i==2||i==14)?0x124cf0:i==13?0x124cc0:0x124bf0;
        if(d[26]!=callback||std::bit_cast<int32_t>(d[13])>=0||!actionCount(d))
            throw std::runtime_error("Opening descriptor outside admitted callbacks/actions");
    }
    std::ifstream ending(resolveAsset(assets/"ending_tasks.bin"),std::ios::binary|std::ios::ate);
    if(!ending||ending.tellg()!=5*108)throw std::runtime_error("Invalid ending task tables");
    std::array<uint8_t,5*108> tail{};ending.seekg(0);
    if(!ending.read(reinterpret_cast<char*>(tail.data()),tail.size()))throw std::runtime_error("Truncated ending task tables");
    for(unsigned i=15;i<20;++i) {
        auto& d=descriptors_[i];
        for(unsigned j=0;j<27;++j)for(unsigned b=0;b<4;++b)d[j]|=uint32_t(tail[(i-15)*108+j*4+b])<<(b*8);
        if(d[26]||std::bit_cast<int32_t>(d[13])>=0||!actionCount(d))
            throw std::runtime_error("Ending descriptor outside admitted callbacks/actions");
    }
    // 124430 (world) and 1242c0 (contact) index the same table at 4a2b30;
    // effect_descriptors.bin holds all 67 entries. An entry is usable when
    // it has actions; only 1 and 4 carry completion callbacks (11ef90/11f1c8).
    std::ifstream effects(resolveAsset(assets/"effect_descriptors.bin"),std::ios::binary|std::ios::ate);
    constexpr auto effectSize=std::tuple_size_v<decltype(effectDescriptors_)>*108;
    if(!effects||effects.tellg()!=effectSize)throw std::runtime_error("Invalid effect descriptor table");
    std::vector<uint8_t> bytes(effectSize);effects.seekg(0);
    if(!effects.read(reinterpret_cast<char*>(bytes.data()),bytes.size()))throw std::runtime_error("Truncated effect descriptor table");
    for(unsigned i=0;i<effectDescriptors_.size();++i) {
        auto& d=effectDescriptors_[i];
        for(unsigned j=0;j<27;++j)for(unsigned b=0;b<4;++b)d[j]|=uint32_t(bytes[i*108+j*4+b])<<(b*8);
        effectUsable_[i]=(actionCount(d)+actionCount(d,13))!=0&&d[26]==(i==4?0x11f1c8u:i==1?0x11ef90u:0u);
    }
}
const std::array<uint32_t,27>& ScheduledOpening::descriptor(unsigned id) const {
    //Native IDs distinguish the two original descriptor tables without
    //retaining source pointers. A world12 task is not the opening12 task.
    if(id>=1&&id<=19)return descriptors_[id];
    if(id>=0x100&&id-0x100<effectDescriptors_.size()&&effectUsable_[id-0x100])return effectDescriptors_[id-0x100];
    throw std::runtime_error("Unsupported scheduled-effect descriptor "+std::to_string(id));
}
void ScheduledOpening::preflight(unsigned descriptor,const TaggedTaskPools& pools,const EffectResidency& residency) {
    const auto& d=this->descriptor(descriptor);
    for(unsigned i=1;i<5&&d[i];++i) {
        const auto asset=d[i];
        if(asset>=residency.slots.size()||asset==10||asset==11||!residency.slots[asset]||
           residency.slots[asset]>=residency.references.size())
            throw std::runtime_error("Opening requires resident effect textures");
    }
    for(unsigned first:{5u,13u})for(unsigned i=0;i<actionCount(d,first);++i)bank_.action(d[0],d[first+i]);
    capacity(pools,actionCount(d)+actionCount(d,13),1);
}
void ScheduledOpening::spawnAt(unsigned descriptor,uint32_t owner,TaggedTaskPools& pools,EffectResidency& residency,
        uint32_t flags,float x,float y,float z,float scale,uint32_t tag,GameRandom* random) {
    preflight(descriptor,pools,residency);
    auto& header=pools.stacks.at(owner);const auto& d=this->descriptor(descriptor);
    if(actionCount(d,13)&&!random)throw std::runtime_error("Random effects require the shared generator");
    for(unsigned i=1;i<5&&d[i];++i)++residency.references[residency.slots[d[i]]];
    uint32_t first=0,previous=0;
    for(unsigned list:{5u,13u})for(unsigned i=0;i<actionCount(d,list);++i) {
        const auto h=pools.allocateObject(tag);auto& o=pools.objects.at(h-1);
        if(previous)pools.objects.at(previous-1)[0]=h;else first=h;
        previous=h;o[0x14/4]=d[0];o[0x24/4]=d[list+i];
        EffectInstance effect(bank_.action(d[0],d[list+i]),flags&0x081c0000,x,y,z,scale);
        if(list==13) {
            const auto vx=randomSpeed(*random,d[21],d[22]);
            const auto vy=randomSpeed(*random,d[23],d[24]);
            effect.state.motion[1]=(flags&0x80000)?0u-vx:vx;
            effect.state.motion[4]=(flags&0x40000)?vy:0u-vy;
            const auto ay=d[25]*100u;
            effect.state.motion[5]=(flags&0x40000)?ay:0u-ay;
        }
        writeEffectState(o,effect.state);
    }
    header.flags|=1;
    const auto h=pools.createTask(5,0x124898,0x10,tag);auto& t=pools.tasks.at(h-1);
    t[6]=owner;t[7]=first;t[8]=descriptor;
}
void ScheduledOpening::spawn(unsigned descriptor,uint32_t owner,TaggedTaskPools& pools,EffectResidency& residency) {
    spawnAt(descriptor,owner,pools,residency,0x100000,320,240,descriptor==2||descriptor>=14?-50:-60,1,0x1b5b,nullptr);
}
uint32_t ScheduledOpening::startWorld(unsigned id,uint32_t flags,unsigned resourceSlot,
        float x,float y,float z,float scale,TaggedTaskPools& pools,EffectResidency& residency,GameRandom& random) {
    const unsigned nativeId=0x100u+id;
    // ACT births and contact sparks index the same Japanese table. The birth
    // keeps the ACT owner tag, mirror and depth even for a shared descriptor.
    preflight(nativeId,pools,residency);
    const auto owner=pools.allocateOwner();
    if(!owner)throw std::runtime_error("World effect owner pool exhausted");
    pools.stacks.at(owner).flags|=2; //124430 explicitly requests owner auto-free.
    const uint32_t tag=((resourceSlot+id*4u)<<16)+0x1b5b;
    spawnAt(nativeId,owner,pools,residency,flags|0x08000000,x,y,z,scale,tag,&random);
    return owner;
}
void ScheduledOpening::startContact(unsigned id,float x,float y,float scale,TaggedTaskPools& pools,EffectResidency& residency,GameRandom& random,
                                    uint32_t facing,float z) {
    if(id>=effectDescriptors_.size()||!effectUsable_[id])throw std::runtime_error("Unsupported contact-effect group "+std::to_string(id));
    const auto nativeId=0x100u+id;
    preflight(nativeId,pools,residency);
    const auto owner=pools.allocateOwner();
    if(!owner)throw std::runtime_error("Contact effect owner pool exhausted");
    pools.stacks.at(owner).flags|=2;
    // 1574f0 and the other callers pass target facing as the integer 0/1.
    // 124620 masks with 081c0000, so it does not mirror the effect image.
    spawnAt(nativeId,owner,pools,residency,0x08000000|facing,x,y,z,scale,0x1b5b,&random);
}
uint32_t ScheduledOpening::start(unsigned label,TaggedTaskPools& pools,EffectResidency& residency,EffectPalettes& palettes) {
    if(label<1||label>10)throw std::runtime_error("Opening label outside1..10");
    preflight(label==1?1:label+2,pools,residency);
    if(label==1) {preflight(2,pools,residency);capacity(pools,7,2);}
    //The original dereferences a null allocation. Reject its undefined
    //exhausted domain without manufacturing a successful presentation.
    const auto owner=pools.allocateOwner();
    if(!owner)throw std::runtime_error("Opening owner pool exhausted");
    palettes[2][palette_]=1;palettes[0][palette_]=0xffffffff;
    pools.stacks.at(owner).value=label;
    if(label==1){spawn(2,owner,pools,residency);spawn(1,owner,pools,residency);}
    else spawn(label+2,owner,pools,residency);
    // 1249c8 starts the prologue for label 1; other labels go directly to
    // their numbered line (table 4a4778, entries 4..12). Both use the NAL queue.
    if(sound_)sound_->voice(49,label==1?55:int(label)+56);
    return owner;
}
uint32_t ScheduledOpening::startEnding(unsigned descriptor,TaggedTaskPools& pools,EffectResidency& residency) {
    if(descriptor<15||descriptor>19)throw std::runtime_error("Ending descriptor outside15..19");
    preflight(descriptor,pools,residency);
    const auto owner=pools.allocateOwner();
    if(!owner)throw std::runtime_error("Ending owner pool exhausted");
    //124548 leaves the freshly allocated value word zero and does not
    //reserve opening palette10.
    spawn(descriptor,owner,pools,residency);
    // 124548 looks up the line immediately after submitting the caption.
    // The owner later finishes on its animation even if the line is still playing.
    constexpr std::array<int,5> endingLines{67,68,71,72,70}; // 4a4778[15..19]
    if(sound_)sound_->voice(49,endingLines[descriptor-15]);
    return owner;
}
void ScheduledOpening::task(uint32_t handle,TaggedTaskPools& pools,EffectResidency& residency,
                            EffectPalettes& palettes,std::vector<EffectDraw>& draws,bool paused) {
    visitTask(handle,pools,residency,palettes,paused,[&](const AuxiliaryObject&,const EffectDraw& draw){draws.push_back(draw);});
}
void ScheduledOpening::task(uint32_t handle,TaggedTaskPools& pools,EffectResidency& residency,
                            EffectPalettes& palettes,ObjectDrawQueue& queue,const GaugeState& clocks) {
    visitTask(handle,pools,residency,palettes,clocks.words910[5]!=0,
        [&](const AuxiliaryObject& snapshot,const EffectDraw&){queue.submit(snapshot,clocks,1);});
}
void ScheduledOpening::visitTask(uint32_t handle,TaggedTaskPools& pools,EffectResidency& residency,
                            EffectPalettes& palettes,bool paused,const DrawEmitter& emit) {
    auto& t=pools.tasks.at(handle-1);
    if(t[0]!=0x124898)throw std::runtime_error("Unsupported scheduled effect task handler");
    const auto owner=t[6];auto& header=pools.stacks.at(owner);const auto& d=descriptor(t[8]);
    bool alive=false;
    for(auto h=t[7];h;h=pools.objects.at(h-1)[0]) {
        auto& o=pools.objects.at(h-1);
        EffectInstance effect(bank_.action(o[0x14/4],o[0x24/4]));effect.state=readEffectState(o);
        if(auto draw=effect.update(paused)) {
            //123800 submits before1239b8 advances the record. Preserve the
            //whole raw object, substituting that saved pre-clock state;
            //copying effect.state here would drop or change the final frame.
            auto snapshot=o;writeEffectState(snapshot,draw->state);emit(snapshot,*draw);
        }
        writeEffectState(o,effect.state);alive|=effect.alive();
    }
    if(alive)return;
    for(auto h=t[7];h;) {const auto next=pools.objects.at(h-1)[0];pools.freeObject(h);h=next;}
    for(unsigned i=1;i<5&&d[i];++i)if(const auto slot=residency.slots.at(d[i])) {
        auto& refs=residency.references.at(slot);
        refs=uint32_t(std::max(std::bit_cast<int32_t>(refs-1),0));
    }
    t[1]=0x12;
    if(!d[26]) {
        //Unlike the non-null (even empty) opening callbacks, the null
        //callback clears active1 but keeps reservation8. Bit2 explicitly
        //requests auto-release; ordinary round-end owners are freed later
        //by144020. Conflating these paths can reuse an owner too early.
        header.flags&=~1u;
        if(header.flags&2)pools.freeOwner(owner);
        return;
    }
    // Ten resumes when the last explosion particle retires, including across pauses.
    if(d[26]==0x11f1c8) {
        if(explosionFinished_)explosionFinished_();
    } else if(d[26]==0x11ef90) {
        // The last light beam starts the slowed battle clock, even if its owner finished the gesture earlier.
        if(concentrationFinished_)concentrationFinished_();
    } else if(d[26]==0x124b48) {
        spawn(header.value+2,owner,pools,residency);
        if(sound_)sound_->voice(49,int(header.value)+56);
    } else if(d[26]==0x124bf0) {
        spawn(14,owner,pools,residency);spawn(13,owner,pools,residency);
        // Start the fight call at the caption transition; pausing the effects
        // or reclaiming this task late must also delay the spoken line.
        if(sound_)sound_->voice(49,56);
    }
    else if(d[26]==0x124cc0){header.flags&=~1u;palettes[2][palette_]=0;}
    //Even the empty2/14 callback clears reservation8 while active1 can
    //remain set. Do not turn this into reference counting or early freeing.
    //112838 reclaims the old TASK only after its callback returns; the
    //controller later frees the OWNER when112550 observes active1 clear.
    header.flags&=~8u;
}
}
