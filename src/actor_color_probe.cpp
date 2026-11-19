#include "actor_color.hpp"
#include <iostream>
#include <stdexcept>

int main(int argc,char** argv) {
    try {
        ss6::StateEntryActor a;ss6::InputSystemConfig config;
        if(argc==2)config.system=std::stoi(argv[1]);
        while(std::cin>>a.fieldA2c>>a.rageState120>>a.state194>>a.bodyAction24
                >>a.bodyFlags38>>a.bodyColor8c>>a.bodyField20>>a.fieldA28>>a.timerDelta) {
            for(auto& value:a.timers)std::cin>>value;
            if(!std::cin)throw std::runtime_error("Incomplete actor color fixture");
            ss6::updateActorColor(a,config);
            std::cout<<a.bodyFlags38<<' '<<a.bodyColor8c<<' '<<a.bodyField20;
            for(auto value:a.timers)std::cout<<' '<<value;
            std::cout<<'\n';
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
