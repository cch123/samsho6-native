#include "actor_history.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>
int main() {
 try {
  ss6::ActorHistory history;auto images=ss6::makeActorAfterimages();std::string op;
  while(std::cin>>op) {
   ss6::ActorHistorySample s;uint32_t x,y;int32_t delta;int table;
   std::cin>>s.flags>>s.action>>s.step>>x>>y>>delta>>table;
   s.x=std::bit_cast<float>(x);s.y=std::bit_cast<float>(y);
   if(!std::cin)throw std::runtime_error("Invalid history fixture");
   if(op=="reset")history.reset(s);else if(op=="tick")history.update(s,delta);
   else throw std::runtime_error("Unknown history operation");
   std::cout<<unsigned(history.fraction);
   auto print=[](const auto& s) {std::cout<<' '<<s.flags<<' '<<s.action<<' '<<s.step<<' '
      <<std::bit_cast<uint32_t>(s.x)<<' '<<std::bit_cast<uint32_t>(s.y);};
   for(const auto& sample:history.samples)print(sample);
   for(auto& im:images) {
    im.update(history,table);print(im.sample);
    std::cout<<' '<<im.color<<' '<<im.flags104<<' '<<std::bit_cast<uint32_t>(im.depth);
   }
   std::cout<<'\n';
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
