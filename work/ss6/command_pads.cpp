// Synthesizes a pad sequence for every original command template (input_commands.bin) from the
// native feature producer, then proves each sequence with the native recognizer.
// Usage: command_pads <assets> [facing 0|1] -> "id ok|fail pad,pad,..." per template.
// Pads use the battle mapping (button k = bit 8+k; 0x10 up, 0x20 down, 0x40 left, 0x80 right).
#include "command_input.hpp"
#include "input_features.hpp"
#include <cstdlib>
#include <iostream>
#include <map>
#include <set>
#include <vector>
using namespace ss6;
namespace {
InputMapping mapping() {InputMapping m;for(unsigned k=0;k<8;++k)m.normal[k]=m.mode6[k]=1u<<(8+k);return m;}
// Features raised while 'pad' is held (after neutral), at its first or any later tick.
std::set<unsigned> raised(uint32_t pad,const InputSamplingContext& c) {
    InputSampler s;const auto m=mapping();uint32_t last=0;std::set<unsigned> out;
    for(int t=0;t<8;++t){NormalizedPadSample p{0,0};s.advance(0,p,m,c);last=0;}
    std::set<unsigned> base;for(unsigned i=0;i<171;++i)if(s.features[i])base.insert(i);
    for(int t=0;t<4;++t) {
        NormalizedPadSample p{pad,pad&~last};last=pad;s.advance(0,p,m,c);
        for(unsigned i=0;i<171;++i)if(s.features[i]&&!base.count(i))out.insert(i);
    }
    return out;
}
const uint32_t dirs[9]{0,0x10,0x90,0x80,0xa0,0x20,0x60,0x40,0x50}; // 5,8,9,6,3,2,1,4,7 (facing right)
}
int main(int argc,char** argv) {
    CommandInput commands(argv[1]);
    InputSamplingContext c;c.facing=c.actualFacing=argc>2&&argv[2][0]=='1';
    // token -> cheapest pad (fewest bits) that raises it
    std::map<unsigned,uint32_t> best;
    for(auto d:dirs)for(uint32_t b=0;b<32;++b) {
        const uint32_t pad=d|(b<<8);
        for(auto f:raised(pad,c)) {
            auto it=best.find(f);
            if(it==best.end()||__builtin_popcount(pad)<__builtin_popcount(it->second))best[f]=pad;
        }
    }
    if(std::getenv("SS6_FEATURES")){for(auto [f,pad]:best)std::cout<<"feature "<<f<<' '<<pad<<'\n';return 0;}
    const auto m=mapping();
    for(unsigned id=0;id<CommandInput::Count;++id) {
        const auto& def=commands.definition(id);
        std::vector<uint32_t> pads(6,0);bool unknown=false;uint32_t dir=0;
        for(unsigned k=0;k<def.tokens.size()&&def.tokens[k]!=255;++k) {
            const unsigned t=def.tokens[k];
            if(t==48){for(int i=0;i<60;++i)pads.push_back(dir);continue;} // charge marker: keep holding
            if(t==49){for(int i=0;i<3;++i)pads.push_back(0);dir=0;continue;} // neutral
            auto it=best.find(t);
            if(it==best.end()){unknown=true;break;}
            const uint32_t pad=it->second;
            if((pad&0xff00)&&!(pad&0xf0)&&dir){pads.push_back(dir|pad);pads.push_back(dir|pad);pads.push_back(0);dir=0;continue;}
            for(int i=0;i<3;++i)pads.push_back(pad);
            dir=pad&0xf0;
            if(pad&0xff00){pads.push_back(0);dir=0;}
        }
        for(int i=0;i<4;++i)pads.push_back(0);
        bool ok=false;
        if(!unknown) {
            InputSampler s;CommandProgress prog;uint32_t last=0;
            for(auto p:pads) {
                s.advance(0,NormalizedPadSample{p,p&~last},m,c);last=p;
                if(commands.evaluate(id,prog,s.features,false)){ok=true;break;}
            }
        }
        std::cout<<id<<' '<<(unknown?"unknown":ok?"ok":"fail");
        for(size_t i=0;i<pads.size();++i)std::cout<<(i?',':' ')<<pads[i];
        std::cout<<'\n';
    }
}
