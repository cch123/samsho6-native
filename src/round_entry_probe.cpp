#include "contact_trial.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv) {
 try {
  if(argc!=2)throw std::runtime_error("Expected asset directory");
  ss6::ContactTrial trial(argv[1]);unsigned player,action,first;
  while(std::cin>>player>>action>>first) {
   trial.reset();auto& a=const_cast<ss6::TrialActor&>(trial.actor(player));
   std::cin>>a.table>>a.state>>a.life.flags23c>>a.flags240>>a.reaction.flags244>>a.damage.flags248;
   uint32_t flags38,flags104,flags108;std::cin>>flags38>>flags104>>flags108>>a.object.pendingFlags;
   std::cin>>a.damage.rageState>>a.damage.rageAmount>>a.damage.rageDecay>>a.damage.swordWait>>a.damage.swordCurrent>>a.damage.swordMaximum;
   std::cin>>a.timers.delta;for(auto& t:a.timers.values)std::cin>>t;
   if(!std::cin)throw std::runtime_error("Invalid round-entry fixture");
   const auto pending=a.object.pendingFlags;a.object.pendingFlags=0;
   a.object.request(action,true);a.object.commitRequested();a.object.pendingFlags=pending;
   a.object.timeline.setObjectFlags(flags38,flags104,flags108);
   trial.resetActorForRound(player,first!=0);
   const auto& c=a.object.timeline.clock();const auto& m=a.object.timeline.motion();
   std::cout<<a.life.life<<' '<<a.life.maximum<<' '<<a.life.pendingDamage<<' '
     <<a.life.flags23c<<' '<<a.flags240<<' '<<a.reaction.flags244<<' '<<a.damage.flags248<<' '
     <<unsigned(a.reaction.flags24c)<<' '<<a.table<<' '<<a.state<<' '<<unsigned(a.stateFlags)<<' '
     <<a.life.conditions<<' '<<a.life.queuedAction<<' '
     <<a.damage.rageState<<' '<<a.damage.rageAmount<<' '<<a.damage.rageDecay<<' '
     <<a.damage.swordWait<<' '<<a.damage.swordCurrent<<' '<<a.damage.swordMaximum<<' '<<a.timers.delta;
   for(auto t:a.timers.values)std::cout<<' '<<t;
   std::cout<<' '<<a.object.timeline.action().id()<<' '<<c.step<<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '<<a.object.pendingFlags;
   for(auto v:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})std::cout<<' '<<v;
   std::cout<<' '<<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<' '<<unsigned(a.history.fraction);
   for(const auto& h:a.history.samples)std::cout<<' '<<h.flags<<' '<<h.action<<' '<<h.step<<' '<<std::bit_cast<uint32_t>(h.x)<<' '<<std::bit_cast<uint32_t>(h.y);
   std::cout<<'\n';
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
