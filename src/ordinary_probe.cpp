#include "ordinary_rules.hpp"
#include "contact_trial.hpp"
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>
int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-ordinary-probe ASSETS");
        ss6::OrdinaryRules rules(argv[1]);std::string op;
        std::cout<<std::setprecision(17);
        while (std::cin>>op) {
            if(op=="idle") {
                int life,rage,armed,remaining,training,setting;
                std::cin>>life>>rage>>armed>>remaining>>training>>setting;
                std::cout<<ss6::standingIdleAction(life,rage,armed,remaining,training,setting)<<'\n';
            } else if(op=="idle-flow") {
                int life,rage,nextLife,nextRage;
                std::cin>>life>>rage>>nextLife>>nextRage;
                ss6::ContactTrial trial(argv[1]);
                auto& a=const_cast<ss6::TrialActor&>(trial.actor(0));
                const auto setFixture=[&](int health,int gauge) {
                    a.life.life=health;a.damage.rageState=gauge;
                    a.damage.rageAmount=25600;a.damage.rageDecay=0;
                };
                const auto frame=[&](ss6::TrialCommand command) {
                    trial.command(0,command);trial.tick();const auto c=a.object.timeline.clock();
                    std::cout<<a.object.timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '<<c.endReached<<' ';
                };
                setFixture(life,rage);frame(ss6::TrialCommand::Forward);frame(ss6::TrialCommand::Idle);
                //Artificial gauge/life mutation isolates entry selection
                //from the already separately verified gauge producer.
                setFixture(nextLife,nextRage);
                for(int tick=0;tick<5;++tick)frame(ss6::TrialCommand::Idle);
                frame(ss6::TrialCommand::Forward);frame(ss6::TrialCommand::Idle);
                std::cout<<'\n';
            } else if(op=="heavy-entry") {
                unsigned player;float distance;std::cin>>player>>distance;
                ss6::ContactTrial trial(argv[1]);trial.place(280,280+distance);
                trial.command(player,ss6::TrialCommand::HeavySlash);trial.tick();
                const auto& a=trial.actor(player);const auto& t=a.object.timeline;const auto c=t.clock();
                std::cout<<a.table<<' '<<a.state<<' '<<unsigned(a.stateFlags)<<' '<<a.life.flags23c<<' '
                         <<unsigned(a.damage.attackStrength)<<' '<<t.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '<<c.endReached<<'\n';
            } else if (op=="distance") {
                float x,other;int armed,targetArmed;std::cin>>x>>other>>armed>>targetArmed;
                const int32_t distance=ss6::playerDistance(x,other);
                std::cout<<distance<<' '<<rules.far(distance,armed,targetArmed)<<'\n';
            } else if (op=="range"||op=="range-matchup") {
                unsigned attacker=0,target=0;
                if(op=="range-matchup")std::cin>>attacker>>target;
                int distance,armed,targetArmed;std::cin>>distance>>armed>>targetArmed;
                bool far=rules.far(distance,armed,targetArmed,attacker,target);
                std::cout<<far<<' '<<unsigned(rules.lightStateFlags(far))<<'\n';
            } else if (op=="clash") {
                uint32_t flags;int table,state,clash;unsigned strength;
                std::cin>>flags>>table>>state>>strength>>clash;
                auto result=ss6::queueWeaponClash(flags,table,state,strength,clash);
                std::cout<<result.flags23c<<' '<<result.table<<' '<<result.state<<'\n';
            } else if (op=="push") {
                ss6::PushActor a,b;int width;
                std::cin>>a.x>>a.y>>a.flags248>>b.x>>b.y>>b.flags248>>width;
                ss6::ordinaryPush(a,b,width);
                std::cout<<a.x<<' '<<b.x<<' '<<a.flags248<<' '<<b.flags248<<'\n';
            } else throw std::runtime_error("Unknown ordinary probe command");
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
