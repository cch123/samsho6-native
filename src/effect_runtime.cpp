#include "effect_runtime.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
namespace {
uint32_t le(const std::vector<uint8_t>& data,size_t pos,unsigned size) {
    if (pos+size>data.size()) throw std::runtime_error("Truncated effect bank");
    uint32_t value=0;
    for(unsigned i=0;i<size;++i)value|=uint32_t(data[pos+i])<<(8*i);
    return value;
}
int32_t signed32(uint32_t v) { return std::bit_cast<int32_t>(v); }
uint32_t scaledWord(uint32_t v,uint32_t speed) {
    // EE MULT returns a wrapped word before the arithmetic shift, not a
    // widened fixed-point product. This matters for large effect velocities.
    return uint32_t(signed32(v*speed)>>8);
}
ScalarFloat sf(float v) { return {std::bit_cast<uint32_t>(v)}; }
float value(ScalarFloat v) { return std::bit_cast<float>(v.bits); }
}
const std::vector<EffectRecord>& EffectBank::action(unsigned bank,unsigned actionId) {
    const auto key=std::make_pair(bank,actionId);
    if(auto i=clips_.find(key);i!=clips_.end())return i->second;
    // Admit original landing, round/fight UI, and ending UI descriptors.
    // Parsing another bank does not by itself prove its runtime side effects.
    if (!((bank==1&&(actionId<=19||actionId==21))||(bank==2&&actionId<=9)||(bank==3&&actionId>=6&&actionId<=25)||(bank==5&&actionId<32)||(bank==6&&actionId<6)||
          (bank==4&&actionId<=18)||(bank==7&&(actionId<=17||(actionId>=24&&actionId<=26)))))
        throw std::runtime_error("Effect action outside admitted battle subset");
    constexpr const char* files[]={"","01HitFlash.bin","02Guard.bin","03etc.bin","04tenso.bin","Display.bin","Display2.bin","Display3.bin"};
    const auto path=assets_/files[bank];
    std::ifstream in(path,std::ios::binary);
    if(!in)throw std::runtime_error("Cannot open "+path.string());
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)),{});
    if(bytes.size()!=0x3da0)throw std::runtime_error("Invalid effect bank size");
    const auto first=le(bytes,0x100+actionId*4,4),count=le(bytes,0x180+actionId,1);
    if(!count||uint64_t(first+uint64_t(count))*60+0x1a0>bytes.size())
        throw std::runtime_error("Invalid effect action range");
    std::vector<EffectRecord> records(count);
    for(unsigned r=0;r<count;++r)for(unsigned f=0;f<30;++f)
        records[r].fields[f]=uint16_t(le(bytes,0x1a0+(first+r)*60+f*2,2));
    return clips_.emplace(key,std::move(records)).first->second;
}
EffectInstance::EffectInstance(const std::vector<EffectRecord>& clip,uint32_t flags,
                              float x,float y,float z,float scale):clip_(&clip) {
    state.flags=flags;state.x=x;state.y=y;state.z=z;state.baseScale=scale;enterRecord();
}
void EffectInstance::enterRecord() {
    if(!alive())return;
    const auto& r=clip_->at(state.step);const unsigned flags=r.word(0);
    if(flags&2) {
        for(unsigned axis=0;axis<2;++axis)for(unsigned n=0;n<3;++n) {
            const uint32_t shifted=uint32_t(int32_t(r.signedWord(0x10+axis*6+n*2)))<<16;
            uint32_t v=uint32_t(signed32(shifted)/(n==0 ? 1 : n==1 ? 100 : 10000));
            state.motion[axis*3+n]=axis ? 0u-v : v;
        }
    }
    state.scale=flags&4 ? ScalarFloat::integer(r.signedWord(0x1c)).mul({0x3c23d70a}) : ScalarFloat{0x3f800000};
    state.scaleVelocity=flags&4 ? ScalarFloat::integer(r.signedWord(0x1e)).mul({0x38d1b717}) : ScalarFloat{0};
    state.scaleAcceleration=flags&4 ? ScalarFloat::integer(r.signedWord(0x20)).mul({0x38d1b717}) : ScalarFloat{0};
    state.color=0xffffffff;
    if(flags&16) {
        state.color=(r.color()&0xff000000)|0xffffff;
        state.colorMotion[0]=r.signedWord(0x2c);state.colorMotion[1]=r.signedWord(0x2e);
    } else state.colorMotion[0]=0;
    if(flags&32) {
        state.color=(state.color&0xff000000)|(r.color()&0xffffff);
        for(unsigned i=2;i<8;++i)state.colorMotion[i]=r.signedWord(0x2c+i*2);
    } else state.colorMotion[2]=state.colorMotion[4]=state.colorMotion[6]=0;
    // Unflagged records clear velocities only. Original acceleration fields
    // retain their old values, even though 123648 does not integrate them.
}
void EffectInstance::integrate() {
    if(!alive())return;
    const auto flags=clip_->at(state.step).word(0);
    for(unsigned axis=0;axis<2;++axis) {
        auto* m=state.motion.data()+axis*3;
        m[0]+=scaledWord(m[1],state.speed);m[1]+=scaledWord(m[2],state.speed);
    }
    const auto speed=ScalarFloat::integer(signed32(state.speed));
    state.scale=state.scale.add(state.scaleVelocity.mul(speed).mul({0x3b800000}));
    state.scaleVelocity=state.scaleVelocity.add(state.scaleAcceleration.mul(speed).mul({0x3b800000}));
    if(flags&16) {
        uint32_t alpha=(state.color>>24)+scaledWord(uint32_t(state.colorMotion[0]),state.speed);
        // Original SLTIU clamps an underflowed alpha to 255, not to zero.
        // Replacing this with a conventional fade clamp changes the data.
        alpha=std::min(alpha,255u);state.color=(state.color&0xffffff)|(alpha<<24);
    }
    if(flags&32)for(unsigned i=0;i<3;++i) {
        const unsigned shift=16-i*8;
        int32_t c=signed32(((state.color>>shift)&255)+scaledWord(uint32_t(state.colorMotion[2+i*2]),state.speed));
        state.color=(state.color&~(255u<<shift))|(uint32_t(std::clamp(c,0,255))<<shift);
    }
}
void EffectInstance::advanceClock() {
    if(!alive())return;
    const auto duration=std::max(1u,unsigned(clip_->at(state.step).word(2)));
    state.time+=state.speed;
    if(signed32(state.time)<int32_t(duration<<8))return;
    state.time&=255;++state.step;enterRecord();
}
std::optional<EffectDraw> EffectInstance::update(bool effectsPaused) {
    state.speed=effectsPaused ? 0 : 256;
    if(!alive())return std::nullopt;
    integrate();EffectDraw draw{clip_->at(state.step),state};advanceClock();return draw;
}
bool EffectGroup::alive() const {
    return std::any_of(instances.begin(),instances.end(),[](const auto& i){return i.alive();});
}
void EffectGroup::update(std::vector<EffectDraw>& draws,bool paused) {
    for(auto& i:instances)if(auto draw=i.update(paused))draws.push_back(*draw);
}
void RoundIntro::reset() { tasks_.clear();active_=false;label_=0; }
std::vector<unsigned> RoundIntro::descriptors() const {
    std::vector<unsigned> result;for(const auto& t:tasks_)result.push_back(t.descriptor);return result;
}
void RoundIntro::spawn(unsigned descriptor) {
    unsigned bank=5;float z=-60;std::vector<unsigned> actions;
    if(descriptor==1)actions={0,1,2,3,4,5};
    else if(descriptor==2) {actions={6};z=-50;}
    else if(descriptor>=3&&descriptor<=11)actions={descriptor+4,16,17,21,descriptor+19};
    else if(descriptor==12)actions={18,19,20,31};
    else if(descriptor==13) {bank=6;actions={0,1,3,4,5};}
    else if(descriptor==14) {bank=6;actions={2};z=-50;}
    else throw std::runtime_error("Round intro descriptor outside1..14");
    Task task{descriptor,{}};
    for(auto action:actions)task.group.instances.emplace_back(bank_.action(bank,action),0x100000,320,240,z,1);
    tasks_.push_back(std::move(task));
}
void RoundIntro::start(unsigned label) {
    if(active_||!tasks_.empty())throw std::runtime_error("Round intro task already active");
    if(label<1||label>10)throw std::runtime_error("Round label must be1..10");
    label_=label;active_=true;
    if(label==1) {spawn(2);spawn(1);}
    else spawn(label+2);
}
void RoundIntro::update(std::vector<EffectDraw>& draws,bool paused) {
    //112838 builds all scheduler links before visiting callbacks. A task
    // allocated by a completion callback joins the NEXT scheduler visit.
    // Keep final draw snapshots even when their task is removed below.
    std::vector<unsigned> completed;
    for(auto& task:tasks_) {
        task.group.update(draws,paused);
        if(!task.group.alive())completed.push_back(task.descriptor);
    }
    std::erase_if(tasks_,[](const auto& t){return !t.group.alive();});
    for(auto descriptor:completed) {
        if(descriptor==1)spawn(label_+2); //124b48
        else if(descriptor>=3&&descriptor<=12) {spawn(14);spawn(13);} //124bf0
        else if(descriptor==13)active_=false; //124cc0
        //2/14 call124cf0, which deliberately leaves the owner active.
    }
}
void BattleEffects::reset() { knockout_.instances.clear();intro_.reset();world_.clear();draws_.clear(); }
void BattleEffects::update(bool paused) {
    draws_.clear();
    knockout_.update(draws_,paused);
    intro_.update(draws_,paused);
    for(auto& g:world_)g.update(draws_,paused);
    std::erase_if(world_,[](const auto& g){return !g.alive();});
}
void BattleEffects::landing(float x,bool mirror) {
    EffectGroup group;
    group.instances.emplace_back(bank_.action(1,18),0x8000000|(mirror ? 0x80000 : 0),x,0,0,1);
    world_.push_back(std::move(group));
}
void BattleEffects::knockout(bool draw,bool final) {
    if(knockoutActive())throw std::runtime_error("KO effect task already active");
    knockout_.instances.clear();
    // Coordinates are the constants passed by 143eb0..143ee8, not a timer
    // or a centered replacement label generated by the native interface.
    for(unsigned a:draw ? std::vector<unsigned>{12,13,14} : final ?
        std::vector<unsigned>{4,5,6,7,8,24,25,26} : std::vector<unsigned>{0,1,2,3})
        knockout_.instances.emplace_back(bank_.action(7,a),0x100000,320,240,-50,1);
}
EffectQuad projectEffect(const EffectDraw& d,const StageCamera& camera) {
    const auto& s=d.state;const auto& r=d.record;
    unsigned angle=0;
    if(r.word(0)&8)angle=uint32_t(0u-uint32_t(signed32(uint32_t(int32_t(r.signedWord(0x22)))<<16)/360))&0xffff;
    if(s.flags&0x80000)angle=(0u-angle)&0xffff;
    if(s.flags&0x40000)angle=(0u-angle)&0xffff;
    const auto p=(s.flags&0x100000) ? StageProjection{s.x,s.y,1} : camera.project(s.x,s.y,s.z);
    const auto dx=ScalarFloat::integer(signed32(s.motion[0])).mul({0x37800000});
    const auto dy=ScalarFloat::integer(signed32(s.motion[3])).mul({0x37800000});
    const auto x=s.flags&0x80000 ? sf(p.x).sub(dx) : sf(p.x).add(dx);
    const auto y=s.flags&0x40000 ? sf(p.y).sub(dy) : sf(p.y).add(dy);
    const auto scale=sf(p.scale).mul(sf(s.baseScale)).mul(s.scale);
    // Build original vertices before applying the inspection crop. Moving
    // the crop into this arithmetic changes rounding at texel boundaries.
    const auto w=ScalarFloat::integer(r.signedWord(0xc)).mul({0x3f000000}).mul(scale);
    const auto h=ScalarFloat::integer(r.signedWord(0xe)).mul({0x3f000000}).mul(scale);
    EffectQuad result{value(x.sub(w)),value(y.sub(h)),value(x.add(w)),value(y.add(h)),r.signedWord(8),r.signedWord(10),
        r.signedWord(12),r.signedWord(14),r.word(4),r.word(6),
        bool(bool(r.word(0)&0x8000)^bool(s.flags&0x80000)),bool(bool(r.word(0)&0x4000)^bool(s.flags&0x40000)),{},angle!=0};
    // 10b4b8/10b4f8 evaluate the rotation after converting signed ACT degrees
    // and applying both mirrors. Independently truncated angles such as 6 and
    // 354 degrees can land one unit apart. Keep their original results.
    struct Rotation {unsigned angle;uint32_t cosine,sine;};
    static constexpr Rotation rotations[]={
        {20024,0xbeaf12c3,0x3f70919b},{20025,0xbeaf1e95,0x3f708f74},{24576,0xbf3504f3,0x3f3504f3},
        {40960,0xbf3504f4,0xbf3504f3},{45511,0xbeaf1e9b,0xbf708f74},{45512,0xbeaf12cd,0xbf70919a},
        {0,0x3f800000,0x00000000},{1092,0x3f7e992a,0x3dd605b0},{1093,0x3f7e9882,0x3dd637ae},
        {1820,0x3f7c1cd9,0x3e31c5d4},{2002,0x3f7b4c82,0x3e43575f},{2185,0x3f7a6746,0x3e54f246},
        {2730,0x3f774800,0x3e847bd6},{2731,0x3f774660,0x3e8487fa},{3277,0x3f73780e,0x3e9e39de},
        {3640,0x3f70919b,0x3eaf12c5},{4187,0x3f6ba643,0x3ec80da8},{4188,0x3f6ba3ce,0x3ec81939},
        {4370,0x3f69dbbb,0x3ed04a80},{4551,0x3f680415,0x3ed86027},{5461,0x3f5db4e4,0x3efffc5f},
        {5462,0x3f5db1c0,0x3f0003a1},{6371,0x3f51b5f4,0x3f12d30b},{6372,0x3f51b259,0x3f12d831},
        {6554,0x3f4f1a44,0x3f167b21},{7281,0x3f441ea2,0x3f2489fc},{7646,0x3f3e3e2e,0x3f2b4cc4},
        {8192,0x3f3504f3,0x3f3504f4},{8739,0x3f2b4819,0x3f3e4263},{9102,0x3f248ecd,0x3f441a97},
        {9831,0x3f16760b,0x3f4f1df5},{10012,0x3f12d832,0x3f51b259},{10922,0x3f0003a2,0x3f5db1bf},
        {10923,0x3efffc5f,0x3f5db4e4},{11832,0x3ed86b8b,0x3f68016d},{12015,0x3ed03f06,0x3f69de49},
        {12743,0x3eaf1e96,0x3f708f74},{13108,0x3e9e2dea,0x3f7379fe},{13653,0x3e8487fa,0x3f774660},
        {13654,0x3e847bd8,0x3f774800},{14200,0x3e54d9b6,0x3f7a6894},{15292,0x3dd605b2,0x3f7e992a},
        {16384,0xb33bbe2e,0x3f800000},{18205,0xbe31de96,0x3f7c1bc2},{26396,0xbf51b258,0x3f12d833},
        {30038,0xbf774800,0x3e847bda},{35498,0xbf774800,0xbe847bd8},{39140,0xbf51b259,0xbf12d832},
        {47331,0xbe31de9a,0xbf7c1bc1},{49152,0x324cee2e,0xbf800000},{50244,0x3dd6058a,0xbf7e992a},
        {51336,0x3e54d9aa,0xbf7a6895},{51882,0x3e847bd6,0xbf774800},{51883,0x3e8487f8,0xbf774660},
        {52428,0x3e9e2dec,0xbf7379fd},{52793,0x3eaf1e8d,0xbf708f76},{53521,0x3ed03efd,0xbf69de4a},
        {53704,0x3ed86b8d,0xbf68016c},{54613,0x3efffc5e,0xbf5db4e4},{54614,0x3f00039f,0xbf5db1c0},
        {55524,0x3f12d82e,0xbf51b25c},{55705,0x3f16760d,0xbf4f1df3},{56434,0x3f248ecd,0xbf441a97},
        {56797,0x3f2b4816,0xbf3e4264},{57344,0x3f3504f1,0xbf3504f5},{57890,0x3f3e3e2e,0xbf2b4cc5},
        {58255,0x3f441ea3,0xbf2489fb},{58982,0x3f4f1a44,0xbf167b1f},{59164,0x3f51b259,0xbf12d832},
        {59165,0x3f51b5f3,0xbf12d30c},{60074,0x3f5db1be,0xbf0003a3},{60075,0x3f5db4e2,0xbefffc66},
        {60985,0x3f680416,0xbed86025},{61166,0x3f69dbbb,0xbed04a80},{61348,0x3f6ba3cd,0xbec8193d},
        {61349,0x3f6ba641,0xbec80dac},{61896,0x3f70919a,0xbeaf12c8},{62259,0x3f73780e,0xbe9e39d9},
        {62805,0x3f77465f,0xbe848802},{62806,0x3f7747ff,0xbe847bdf},{63351,0x3f7a6745,0xbe54f250},
        {63534,0x3f7b4c82,0xbe435754},{63716,0x3f7c1cd9,0xbe31c5d1},{64443,0x3f7e9882,0xbdd637aa},
        {64444,0x3f7e992a,0xbdd605b1}
    };
    const auto it=std::find_if(std::begin(rotations),std::end(rotations),[angle](Rotation r){return r.angle==angle;});
    if(it==std::end(rotations))throw std::runtime_error("Missing rotation for battle effect record");
    const ScalarFloat c{it->cosine},sn{it->sine};
    for(unsigned i=0;i<4;++i) {
        const auto vx=ScalarFloat::integer(int32_t(r.signedWord(12))*(i&2 ? 1 : -1)).mul({0x3f000000}).mul(scale);
        const auto vy=ScalarFloat::integer(int32_t(r.signedWord(14))*(i&1 ? 1 : -1)).mul({0x3f000000}).mul(scale);
        result.vertices[i]={value(x.add(c.mul(vx).sub(sn.mul(vy)))),value(y.add(sn.mul(vx).add(c.mul(vy))))};
    }
    if(result.rotated) {
        result.left=result.right=result.vertices[0][0];result.top=result.bottom=result.vertices[0][1];
        for(const auto& v:result.vertices) {
            result.left=std::min(result.left,v[0]);result.right=std::max(result.right,v[0]);
            result.top=std::min(result.top,v[1]);result.bottom=std::max(result.bottom,v[1]);
        }
    }
    return result;
}
} // namespace ss6
