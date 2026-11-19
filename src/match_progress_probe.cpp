#include "match_progress.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
void read(ss6::PlayerMatchStats& p) {
    std::cin>>p.outcome1c>>p.outcome20>>p.previous24>>p.wins>>p.requiredWins>>p.rating>>p.score>>p.bonus;
    for(auto& h:p.history){unsigned v;std::cin>>v;h=uint8_t(v);}
}
void write(const ss6::PlayerMatchStats& p) {
    std::cout<<p.outcome1c<<' '<<p.outcome20<<' '<<p.previous24<<' '<<p.wins<<' '<<p.requiredWins
             <<' '<<p.rating<<' '<<p.score<<' '<<p.bonus;
    for(auto h:p.history)std::cout<<' '<<unsigned(h);
}
}
int main() {
 try {
  std::string kind;
  while(std::cin>>kind) {
   if(kind=="record"||kind=="init"||kind=="reset") {
    ss6::PlayerMatchStats p;read(p);
    if(kind=="record") {int result,perfect,other,draw;std::cin>>result>>perfect>>other>>draw;p.record(result,perfect,other,draw);}
    if(kind=="init") {int selected,source;std::cin>>selected>>source;p.initialize(selected,source);}
    if(kind=="reset")p.resetRound();
    write(p);std::cout<<' '<<p.complete()<<'\n';
   } else if(kind=="round") {
    ss6::MatchProgress m;for(auto& p:m.players)read(p);
    std::array<int32_t,2> life,maximum;for(auto& v:life)std::cin>>v;for(auto& v:maximum)std::cin>>v;
    m.recordRound(life,maximum);
    std::cout<<m.result.winner<<' '<<m.result.result<<' '<<m.result.ui<<' '<<m.result.draw;
    for(const auto& p:m.players){std::cout<<' ';write(p);}std::cout<<' '<<m.complete()<<'\n';
   } else if(kind=="transition") {
    ss6::MatchProgress m;int mode,submode;
    std::cin>>mode>>submode>>m.result.winner>>m.result.draw;
    for(auto& p:m.players)std::cin>>p.wins>>p.requiredWins;
    auto t=m.transition(mode,submode);std::cout<<t.state<<' '<<t.delay<<'\n';
   } else if(kind=="timer") {
    ss6::BattleTimers t;int op;unsigned index;int32_t ticks,divisor;
    std::cin>>op>>index>>ticks>>divisor>>t.lock>>t.delta;
    for(auto& v:t.values)std::cin>>v;
    int32_t returned=0;
    if(op==0)t=ss6::BattleTimers{};
    else if(op==1)t.set(index,ticks,divisor);
    else if(op==2)t.clear(index);
    else if(op==3)returned=t.decrease(index);
    else if(op==4)returned=t.increase(index);
    else if(op==5)t.decreaseLock();
    else throw std::runtime_error("Unknown timer operation");
    std::cout<<returned<<' '<<t.lock<<' '<<t.delta;
    for(auto v:t.values)std::cout<<' '<<v;std::cout<<' '<<t.locked()<<'\n';
   } else throw std::runtime_error("Unknown match operation");
   if(!std::cin)throw std::runtime_error("Invalid match probe input");
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
