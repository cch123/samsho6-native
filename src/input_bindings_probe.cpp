#include "input_bindings.hpp"
#include <iostream>
#include <stdexcept>

int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::InputBindings bindings(argv[1]);unsigned seed,present;
    while(std::cin>>seed>>present) {
        ss6::InputSystemConfig c;std::array<uint8_t,16> d;
        std::cin>>c.system>>c.character;
        for(auto& v:d){unsigned n;std::cin>>n;v=uint8_t(n);}if(c.system==6)c.descriptor=d;
        ss6::ActorCommandInput a;a.sampledFeatures.fill(seed);
        for(unsigned i=0;i<32;++i) {
            a.specialPriority[i]=uint8_t(i+100);
            auto& s=a.special[i];s.definition=123;s.alternateDirections=i%2;s.recognized=s.cancelAllowed=seed;s.progress={3,4,52,10};
            if(i<31)a.normal[i]=s;
        }
        a.specialCount=32;a.specialStart=4;a.enabled=true;
        bindings.initialize(a,present?&c:nullptr);
        std::cout<<a.enabled<<' '<<a.specialCount<<' '<<a.specialStart<<' ';
        for(auto v:a.sampledFeatures)std::cout<<v<<' ';
        for(unsigned kind=0;kind<2;++kind)for(unsigned i=0;i<(kind?32:31);++i) {
            const auto& s=kind?a.special[i]:a.normal[i];
            std::cout<<s.definition<<' '<<s.alternateDirections<<' '<<s.recognized<<' ';
            if(kind)std::cout<<s.cancelAllowed<<' ';
            std::cout<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered)<<' ';
        }
        for(auto v:a.specialPriority)std::cout<<unsigned(v)<<' ';std::cout<<'\n';
        if(!std::cin)throw std::runtime_error("Incomplete input binding fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
