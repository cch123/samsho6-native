#include "asset_files.hpp"
#include "kazuki_fire.hpp"
#include "companion_motion.hpp"
#include "state_entry.hpp"
#include "scalar_float.hpp"
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
F f(float v){return F{std::bit_cast<uint32_t>(v)};}
int32_t& word(AuxiliaryObject& o,unsigned off){return reinterpret_cast<int32_t&>(o[off/4]);}
// 1f7520: step the visible level toward the fire level, two visits per step.
void setLevel(AuxiliaryObjects& objects,AuxiliaryObject& o,const AuxiliaryObject& body,int level) {
    if(word(o,0x128)>0){--word(o,0x128);return;}
    const int old=word(o,0x124);
    if(old==level)return;
    word(o,0x124)=level<old?old-1:old+1;
    const int n=word(o,0x124);
    if(n==0)objects.request(o,0x304,false,false);
    else if(o[0x134/4])objects.request(o,unsigned(n+0x25d),false,false);
    else if(old!=0)objects.request(o,unsigned(n+0x250),false,false);
    else { // appearing from 0
        o[0x40/4]=body[0x40/4];
        o[0x44/4]=F{body[0x44/4]}.add(f(level==1?64.0f:140.0f)).bits;
        objects.request(o,unsigned(n+0x250),false,false);
    }
    word(o,0x128)=2;
}
bool steer(AuxiliaryObject& o,F x,F y,CompanionSteering s) {
    const F dx=x.sub(F{o[0x40/4]}),dy=y.sub(F{o[0x44/4]});
    const F length=dx.mul(dx).add(dy.mul(dy)).sqrt();
    return steerCompanion(o,x,dx,dy,length,s);
}
}
AngleTrig::AngleTrig(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"angle_trig.bin"),std::ios::binary);
    table_.resize(2*0x10000);
    if(!in.read(reinterpret_cast<char*>(table_.data()),std::streamsize(table_.size()*4)))
        throw std::runtime_error("Missing angle_trig.bin");
}
uint32_t spawnKazukiFire(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,unsigned player,
                         uint32_t flags,const AuxiliaryObject& body,unsigned level) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x1f7318);
    if(!handle)throw std::runtime_error("Missing Kazuki fire object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=((body[0x38/4]&mirror)?F{body[0x40/4]}.add(f(100.0f)):F{body[0x40/4]}.sub(f(100.0f))).bits;
    o[0x128/4]=0;o[0x12c/4]=0;o[0x130/4]=0;o[0x134/4]=0;o[0x124/4]=0xffffffffu;
    o[0x44/4]=F{body[0x44/4]}.add(f(80.0f)).bits;
    setLevel(objects,o,body,int(level));
    // 1a3220's shared tail; character 16 alone keeps 108:40000 clear.
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;
    return handle;
}
void updateKazukiFire(AuxiliaryObjects& objects,AuxiliaryObject& o,const KazukiFireWorld& w) {
    const auto& ob=w.body;auto& owner=w.owner;
    const int level=owner.characterBytesF14[1]; // f15
    if(o[0x134/4]) { // 1f76a0
        if(!(o[0x134/4]==1&&level!=0)) {
            if(!o[0xc0/4]||(o[0x104/4]&1))return;
            o[0x128/4]=0;o[0x124/4]=0xffffffffu;o[0x12c/4]=0;o[0x134/4]=0;
            setLevel(objects,o,ob,0);
            owner.characterBytesF14[1]=0;
            return;
        }
        const F x{w.opponentBody[0x40/4]},y=F{w.opponentBody[0x44/4]}.add(f(32.0f));
        steer(o,x,y,{f(0.01f),f(6.0f),f(0.1f),F::integer(65536),f(0.05f),f(0.05f)});
        const int32_t step=word(o,0x30);
        word(o,0x130)-=w.opponentConcentrating?step/4:step;
        if((o[0x104/4]&0x2c0000)||(o[0x100/4]&2)||word(o,0x130)<=0) {
            AuxiliaryObjects::stop(o);o[0x134/4]=2;objects.request(o,0x261,false,false);
            return;
        }
        setLevel(objects,o,ob,level);
        return;
    }
    // 1f7318: orbit around a point 50 behind and 64 above the owner.
    const F x=(ob[0x38/4]&mirror)?F{ob[0x40/4]}.sub(f(-50.0f)):F{ob[0x40/4]}.add(f(-50.0f));
    const F y=w.opponentHoldsOwner?f(64.0f):F{ob[0x44/4]}.add(f(64.0f));
    steer(o,x,y,{f(0.05f),f(30.0f),f(0.1f),F::integer(65536),f(0.5f),f(0.5f)});
    const F K{0x43360b60u}; // 182.04443359375: degrees to 16-bit units
    const int32_t t=word(o,0x12c)-2*level+7;
    word(o,0x12c)=t%36000;
    const int32_t a=((2*word(o,0x12c))/3)%360;
    const uint32_t cu=uint32_t(F::integer(a).mul(K).truncate());
    o[0xec/4]=F::integer(level+1).mul(F{w.trig.cosine(cu)}).bits;
    const int32_t b=word(o,0x12c)%360;
    const uint32_t su=uint32_t(F::integer(b).mul(K).truncate());
    o[0xf0/4]=F::integer(level+3).mul(F{w.trig.sine(su)}).bits;
    setLevel(objects,o,ob,level);
}
}
