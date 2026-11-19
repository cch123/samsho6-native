#include "input_bindings.hpp"
#include "input_features.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::InputBindings bindings(argv[1]);ss6::CommandInput commands(argv[1]);
    ss6::ActorCommandInput actor;ss6::InputSampler sampler;ss6::InputMapping mapping;
    std::string op;
    while(std::cin>>op) {
        if(op=="init") {
            ss6::InputSystemConfig c;std::array<uint8_t,16> d;
            std::cin>>c.system>>c.character;
            for(auto& v:d){unsigned n;std::cin>>n;v=uint8_t(n);}if(c.system==6)c.descriptor=d;
            for(auto* array:{&mapping.normal,&mapping.mode6})for(auto& v:*array)std::cin>>v;
            actor={};sampler={};bindings.initialize(actor,&c);
        } else if(op=="tick") {
            unsigned player;bool age;ss6::NormalizedPadSample pad;ss6::InputSamplingContext c;
            std::cin>>player>>pad.held>>pad.pressed>>c.facing>>c.actualFacing>>c.reverseDirections>>age;
            actor.sampleAndAdvance(commands,sampler,player,pad,mapping,c,age);
            for(auto v:actor.sampledFeatures)std::cout<<v<<' ';
            for(const auto& l:sampler.pressLatches)for(auto v:l)std::cout<<unsigned(v)<<' ';
            for(unsigned kind=0;kind<2;++kind)for(unsigned i=0;i<(kind?32:31);++i) {
                const auto& s=kind?actor.special[i]:actor.normal[i];
                std::cout<<s.definition<<' '<<s.recognized<<' '<<s.cancelAllowed<<' '<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered)<<' ';
            }
            std::cout<<'\n';
        } else throw std::runtime_error("Unknown input stream operation");
        if(!std::cin)throw std::runtime_error("Incomplete input stream fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
