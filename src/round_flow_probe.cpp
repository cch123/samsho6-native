#include "contact_trial.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>

namespace {
void snapshot(const ss6::ContactTrial& t) {
    const auto& c=t.camera;
    std::cout<<t.match.roundIndex;
    for(float v:{c.x,c.y,c.width})std::cout<<' '<<std::bit_cast<uint32_t>(v);
    std::cout<<' '<<c.left<<' '<<c.right;
    const auto& timers=t.battleTimers;
    std::cout<<' '<<timers.flags<<' '<<timers.lock<<' '<<timers.rawDelta<<' '<<timers.delta;
    for(auto v:timers.values)std::cout<<' '<<v;
    for(unsigned i=0;i<2;++i) {
        const auto& p=t.match.players[i];const auto& a=t.actor(i);const auto& d=a.damage;
        for(auto v:{p.outcome1c,p.outcome20,p.previous24,p.wins,p.requiredWins,p.rating,p.score,p.bonus})std::cout<<' '<<v;
        for(auto h:p.history)std::cout<<' '<<unsigned(h);
        for(auto v:{a.life.life,a.life.maximum,d.rageState,d.rageAmount,d.rageDecay,d.swordWait,d.swordCurrent,d.swordMaximum,a.timers.values[19]})std::cout<<' '<<v;
    }
    std::cout<<' '<<t.pendingRoundState<<' '<<t.roundState<<'\n';
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected asset directory");
    ss6::ContactTrial trial(argv[1]);std::string op;
    while(std::cin>>op) {
        trial.reset();std::cin>>trial.match.roundIndex;
        if(op=="label") {
            for(auto& p:trial.match.players)std::cin>>p.wins>>p.requiredWins;
            std::cout<<trial.match.openingLabel()<<'\n';continue;
        }
        if(op!="reset")throw std::runtime_error("Unknown round flow fixture");
        trial.firstRoundIntroduction=trial.match.roundIndex==0;
        for(unsigned i=0;i<2;++i) {
            auto& p=trial.match.players[i];auto& a=const_cast<ss6::TrialActor&>(trial.actor(i));auto& d=a.damage;
            std::cin>>p.outcome1c>>p.outcome20>>p.previous24>>p.wins>>p.requiredWins>>p.rating>>p.score>>p.bonus;
            for(auto& h:p.history){unsigned v;std::cin>>v;h=uint8_t(v);}
            std::cin>>d.rageState>>d.rageAmount>>d.rageDecay>>d.swordWait>>a.timers.values[19];
            a.object.request(i?48:495,true);a.object.commitRequested();
            a.object.setFlags(0x400200,0);a.table=i?2:0;a.state=i?15:41;
            a.life.life=i?0:100;a.life.flags23c=0x1000|(i?0x80:0);
        }
        if(!std::cin)throw std::runtime_error("Invalid round flow fixture");
        trial.roundState=8;trial.pendingRoundState=0;
        trial.camera.x=440;trial.camera.y=200;trial.camera.width=400;
        // Drive the real integration entry, rather than independently
        // rebuilding the desired state in this comparison executable.
        trial.tick();snapshot(trial);
        for(unsigned tick=0;tick<31;++tick){trial.tick();snapshot(trial);}
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
