// Isolate P2's submitted body during the same match input used by
// record_jump_light.py. Nothing in the live fighters or their queue is edited.
#include "native_match.hpp"
#include "native_scene.hpp"
#include <algorithm>
#include <bit>
#include <iostream>
#include <memory>
#include <string>

namespace {
constexpr std::array<uint8_t,4> background{235,233,224,255};
void draw(ss6::NativeScene& scene,const ss6::NativeMatch& match,const ss6::ObjectDrawQueue::Record& body,
          unsigned tick,unsigned index) {
    ss6::ObjectDrawQueue queue;
    queue.slots[0]=body;
    // The body wrapper's 0x200000 bit suppresses only its projected ground
    // shadow. It never changes the pose's visible PIL parts or palette.
    queue.slots[0][0x38/4]|=0x200000;
    queue.count=1;queue.sort();
    ss6::StageCamera camera;
    camera.projectionX=std::bit_cast<float>(body[0x40/4]);
    camera.depthOffset=std::bit_cast<float>(body[0x48/4]); // Unit scale for every column.
    const auto& battle=match.battle();
    const auto& gauges=battle.gauges;
    std::vector<uint8_t> image(640*448*4);
    for(size_t i=0;i<image.size();i+=4)std::copy(background.begin(),background.end(),image.begin()+i);
    scene.paint(queue,{camera,{gauges.words910[2],gauges.words910[3]}},battle.paletteState,gauges.paletteTones,image,{});
    const std::array<uint32_t,4> header={index,tick,body[0x24/4],body[0x28/4]};
    std::cout.write(reinterpret_cast<const char*>(header.data()),sizeof(header));
    std::cout.write(reinterpret_cast<const char*>(image.data()),image.size());
}
}
int main(int argc,char** argv) {
    if(argc!=3)return 2;
    const bool crouch=std::stoi(argv[2])!=0;
    const unsigned reaction=crouch?350:356,neutral=crouch?4:0,contact=crouch?44:42;
    auto match=std::make_unique<ss6::NativeMatch>(argv[1],60,ss6::VersusMode::Console);
    auto scene=std::make_unique<ss6::NativeScene>(argv[1]);
    for(int i=0;i<500;++i)match->tick({});
    std::array<uint32_t,2> last{};
    std::array<unsigned,3> counts{};
    bool recovered=false;
    for(unsigned i=0,l,r;std::cin>>l>>r;++i) {
        const std::array<uint32_t,2> held{l,r};
        std::array<ss6::NormalizedPadSample,2> pads;
        for(unsigned s=0;s<2;++s)pads[s]={held[s],held[s]&~last[s]};
        match->tick(pads);last=held;
        const auto rows=match->objectDraws().active();
        const auto body=std::find_if(rows.begin(),rows.end(),[&](const auto& row){
            return row[0x144/4]==0 && row[0xc/4]==1 && row[0x20/4]==1 &&
                   row[0x24/4]==match->fighter(1).body.timeline.action().id();
        });
        if(body==rows.end())throw std::runtime_error("P2's original costume/body is missing");
        const unsigned action=(*body)[0x24/4],step=(*body)[0x28/4];
        if(i+1==15+contact) {
            if(action!=neutral||match->fighter(1).actor.fieldA30!=200)throw std::runtime_error("Expected neutral pre-impact record");
            draw(*scene,*match,*body,i,0);
        }
        if(action==reaction) {
            if(match->fighter(1).actor.fieldA30!=191)throw std::runtime_error("Expected the original jump-light damage");
            if(counts.at(step)++==0)draw(*scene,*match,*body,i,step+1);
        }
        if(counts[2] && !recovered && action==neutral) {
            draw(*scene,*match,*body,i,4);recovered=true;
        }
    }
    if(!recovered || counts!=(crouch?std::array{9u,3u,4u}:std::array{5u,2u,3u}))
        throw std::runtime_error("Unexpected visible hurt duration");
}
