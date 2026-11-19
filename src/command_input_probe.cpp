#include "command_input.hpp"
#include "input_features.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
namespace {
void read(ss6::CommandProgress& p) {
    unsigned step,elapsed,charge,buffer;std::cin>>step>>elapsed>>charge>>buffer;
    p={uint8_t(step),uint8_t(elapsed),uint16_t(charge),uint8_t(buffer)};
}
void print(const ss6::CommandProgress& p) {
    std::cout<<' '<<unsigned(p.step)<<' '<<unsigned(p.elapsed)<<' '<<p.charge<<' '<<unsigned(p.buffered);
}
ss6::InputFeatures features() {
    ss6::InputFeatures f{};unsigned count;std::cin>>count;
    for(unsigned n=0;n<count;++n){unsigned index,value;std::cin>>index>>value;f.at(index)=value;}
    return f;
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::CommandInput input(argv[1]);std::string op;
    while(std::cin>>op) {
        if(op=="eval") {
            unsigned id;bool alternate;ss6::CommandProgress p;
            std::cin>>id>>alternate;read(p);auto f=features();
            std::cout<<input.evaluate(id,p,f,alternate);print(p);std::cout<<'\n';
        } else if(op=="charge") {
            unsigned token;bool alternate;std::cin>>token>>alternate;auto f=features();
            std::cout<<input.chargeHeld(token,f,alternate)<<'\n';
        } else if(op=="group"||op=="pipeline") {
            ss6::ActorCommandInput a;bool age;
            std::cin>>a.enabled>>a.specialCount>>age;
            for(auto* slots:{&a.normal[0],&a.special[0]}) {
                const unsigned count=slots==&a.normal[0]?31:32;
                for(unsigned i=0;i<count;++i) {
                    auto& s=slots[i];std::cin>>s.definition>>s.alternateDirections>>s.recognized>>s.cancelAllowed;read(s.progress);
                }
            }
            ss6::InputSampler sampler;ss6::InputSamplingContext c;
            if(op=="pipeline") {
                unsigned player;ss6::NormalizedPadSample pad;ss6::InputMapping mapping;
                std::cin>>player>>pad.held>>pad.pressed>>c.facing>>c.actualFacing>>c.reverseDirections>>c.playback>>c.replayIndex>>c.gameMode;
                for(auto* array:{&mapping.normal,&mapping.mode6})for(auto& v:*array)std::cin>>v;
                sampler.features=features();a.sampledFeatures=features();
                for(auto& l:sampler.pressLatches)for(auto& v:l){unsigned n;std::cin>>n;v=uint8_t(n);}
                unsigned h,p;std::cin>>h>>p;
                if(uint32_t(c.replayIndex)<600){sampler.replayHeld[c.replayIndex]=uint16_t(h);sampler.replayPressed[c.replayIndex]=uint16_t(p);}
                a.sampleAndAdvance(input,sampler,player,pad,mapping,c,age);
            } else {auto f=features();a.advance(input,f,age);}
            for(auto* slots:{&a.normal[0],&a.special[0]}) {
                const unsigned count=slots==&a.normal[0]?31:32;
                for(unsigned i=0;i<count;++i){auto& s=slots[i];std::cout<<s.recognized<<' '<<s.cancelAllowed;print(s.progress);std::cout<<' ';}
            }
            if(op=="pipeline") {
                for(auto v:sampler.features)std::cout<<v<<' ';
                for(auto v:a.sampledFeatures)std::cout<<v<<' ';
                for(const auto& l:sampler.pressLatches)for(auto v:l)std::cout<<unsigned(v)<<' ';
                if(uint32_t(c.replayIndex)<600)std::cout<<sampler.replayHeld[c.replayIndex]<<' '<<sampler.replayPressed[c.replayIndex];
                else std::cout<<"0 0";
            }
            std::cout<<'\n';
        } else throw std::runtime_error("Unknown command-input probe operation");
        if(!std::cin)throw std::runtime_error("Incomplete command-input fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
