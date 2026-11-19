#include "actor_state.hpp"
#include "damage.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char** argv) {
 try {
  if(argc!=2)throw std::runtime_error("Usage: ss6-round-reset-probe ASSETS");
  ss6::DamageTables damage(argv[1]);std::string op;
  while(std::cin>>op) {
   if(op=="timers") {
    ss6::ActorTimers t;std::cin>>t.delta;for(auto& v:t.values)std::cin>>v;t.resetRound();
    std::cout<<t.delta;for(auto v:t.values)std::cout<<' '<<v;std::cout<<'\n';
   } else if(op=="flags") {
    ss6::RoundActorFlags f;unsigned byte;
    std::cin>>f.flags23c>>f.flags240>>f.flags244>>f.flags248>>byte;f.flags24c=uint8_t(byte);f.resetRound();
    std::cout<<f.flags23c<<' '<<f.flags240<<' '<<f.flags244<<' '<<f.flags248<<' '<<unsigned(f.flags24c)<<'\n';
   } else if(op=="meters") {
    ss6::DamageActor a;
    std::cin>>a.rageState>>a.rageAmount>>a.rageDecay>>a.swordWait>>a.swordCurrent>>a.swordMaximum;
    damage.resetOrdinaryRoundMeters(a);
    std::cout<<a.rageState<<' '<<a.rageAmount<<' '<<a.rageDecay<<' '<<a.swordWait<<' '<<a.swordCurrent<<' '<<a.swordMaximum<<'\n';
   } else throw std::runtime_error("Unknown reset operation");
   if(!std::cin)throw std::runtime_error("Invalid reset input");
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
