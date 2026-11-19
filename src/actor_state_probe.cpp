#include "actor_state.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main() {
    try {
        std::string op;
        while (std::cin>>op) {
            ss6::ActorTimers timers;
            if (op=="actor") {
                ss6::ActorTimerInput in;std::cin>>in.mainState>>in.effectiveTable>>in.airborne>>in.backD8>>in.back100>>timers.delta;
                for(auto& value:timers.values)std::cin>>value;
                std::cout<<timers.advanceActor(in);for(auto v:timers.values)std::cout<<' '<<v;std::cout<<'\n';
            } else if (op=="life") {
                ss6::LifeState life;
                int training;
                std::cin>>life.life>>life.maximum>>life.pendingDamage>>life.queuedAction
                        >>life.flags23c>>life.conditions>>life.y>>training>>timers.values[28];
                ss6::commitLife(life,timers,training);
                std::cout<<life.life<<' '<<life.pendingDamage<<' '<<life.flags23c<<' '<<timers.values[28]<<'\n';
            } else {
                std::cin>>timers.delta>>timers.values[0]>>timers.values[1];
                int32_t previous;
                if (op=="contact") previous=timers.advanceContactTimers();
                else if (op=="decrease") previous=timers.decrease(0);
                else if (op=="increase") previous=timers.increase(0);
                else throw std::runtime_error("Unknown actor state command");
                std::cout<<previous<<' '<<timers.values[0]<<' '<<timers.values[1]<<'\n';
            }
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
