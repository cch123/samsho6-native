#include "effect_runtime.hpp"
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv) {
 try {
  if(argc!=2)throw std::runtime_error("Usage: ss6-round-intro-probe ASSETS");
  ss6::EffectBank bank(argv[1]);unsigned label,visits,pauseMode;
  while(std::cin>>label>>visits>>pauseMode) {
   ss6::RoundIntro intro(bank);intro.start(label);
   for(unsigned visit=0;visit<=visits;++visit) {
    std::vector<ss6::EffectDraw> draws;
    if(visit)intro.update(draws,pauseMode==1||(pauseMode==2&&visit%3==1));
    const auto tasks=intro.descriptors();std::cout<<intro.active()<<' '<<tasks.size();
    for(auto id:tasks)std::cout<<' '<<id;
    std::cout<<' '<<draws.size();
    for(const auto& d:draws) {
     for(auto v:d.record.fields)std::cout<<' '<<v;
     const auto& s=d.state;
     std::cout<<' '<<s.step<<' '<<s.time<<' '<<s.speed;
     for(auto v:s.motion)std::cout<<' '<<v;
     std::cout<<' '<<s.scale.bits<<' '<<s.scaleVelocity.bits<<' '<<s.scaleAcceleration.bits<<' '<<s.color;
     for(auto v:s.colorMotion)std::cout<<' '<<uint32_t(v);
    }
    std::cout<<'\n';
   }
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
