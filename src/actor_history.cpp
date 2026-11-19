#include "actor_history.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>

namespace ss6 {
ActorHistorySample ActorHistory::capture(const PlayerObject& object,float ox,float oy) {
    const auto& t=object.timeline;const auto& c=t.clock();
    const ScalarFloat x{std::bit_cast<uint32_t>(t.motion().x)},y{std::bit_cast<uint32_t>(t.motion().y)};
    const ScalarFloat dx{std::bit_cast<uint32_t>(ox)},dy{std::bit_cast<uint32_t>(oy)};
    return {c.objectFlags,t.action().id(),c.step,
        std::bit_cast<float>((c.objectFlags&0x80000 ? x.sub(dx) : x.add(dx)).bits),
        std::bit_cast<float>(y.add(dy).bits)};
}
void ActorHistory::reset(const ActorHistorySample& sample) { fraction=0;samples.fill(sample); }
void ActorHistory::update(const ActorHistorySample& sample,int32_t delta) {
    const int32_t sum=std::bit_cast<int32_t>(uint32_t(fraction)+uint32_t(delta));
    fraction=uint8_t(sum%256);
    if(sum<256)return;
    std::move_backward(samples.begin(),samples.end()-1,samples.end());samples[0]=sample;
}
std::array<ActorAfterimage,3> makeActorAfterimages() {
    std::array<ActorAfterimage,3> images;
    for(unsigned i=0;i<images.size();++i) {
        images[i].lag=(i+1)*5;images[i].alpha=144-i*48;images[i].depthOffset=i+1;
    }
    return images;
}
void ActorAfterimage::update(const ActorHistory& history,int table,float actorDepth,unsigned character) {
    sample=history.samples.at(lag);
    sample.flags=(sample.flags&~uint32_t(0x800000))|0x40208000;
    color=(alpha<<24)+0x808080;
    depth=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(actorDepth)}.add(ScalarFloat::integer(int32_t(depthOffset))).bits);
    flags104=(flags104&~uint32_t(0x140))|0x400300; //11d990 then147c20
    const unsigned action=sample.action;
    // 147b60 checks the shared pursuit exception before the source
    // 169138 table, which indexes special trails by character and ACT.
    const bool eligible=action==264 || (character==0&&((action>=549&&action<=551)||(action>=568&&action<=570)||action==612)) ||
        (character==1&&(action==715||action==716)) || (character==2&&(action==634||action==635)) || (character==3&&action>=664&&action<=671);
    if(table==2||!eligible)flags104|=2;else flags104&=~uint32_t(2);
}
}
