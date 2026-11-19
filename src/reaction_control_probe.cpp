#include "reaction.hpp"
#include <iostream>
#include <iomanip>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-reaction-control-probe ASSETS");
        ss6::ReactionTables tables(argv[1]);
        std::cout<<std::setprecision(17);
        std::string operation;
        while (std::cin>>operation) {
            if (operation=="guard"||operation=="guard-timers") {
                ss6::ReactionTarget target;ss6::ActorTimers sourceTimers,targetTimers;
                unsigned defense,strength,action=0;
                std::cin>>target.flags23c>>target.flags244>>defense>>strength;
                if(operation=="guard-timers") {
                    for(auto& value:sourceTimers.values)std::cin>>value;
                    for(auto& value:targetTimers.values)std::cin>>value;
                }
                bool applied=tables.applyGuard(target,sourceTimers,targetTimers,defense,strength,action);
                std::cout<<applied<<' '<<target.flags244<<' '<<target.pendingTable<<' '<<target.pendingState<<' '
                         <<target.forceState<<' '<<sourceTimers.values[0]<<' '<<sourceTimers.values[1]<<' '
                         <<targetTimers.values[0]<<' '<<targetTimers.values[1]<<' '<<action;
                if(operation=="guard-timers") {
                    for(auto value:sourceTimers.values)std::cout<<' '<<value;
                    for(auto value:targetTimers.values)std::cout<<' '<<value;
                }
                std::cout<<'\n';
            } else if (operation=="retreat"||operation=="clamp") {
                unsigned state;uint32_t flags;int other;ss6::MotionState motion;
                std::cin>>state>>flags>>other>>motion.dx>>motion.vx>>motion.ax>>motion.dy>>motion.vy>>motion.ay>>motion.y;
                if (operation=="retreat") tables.startRetreat(state,motion,flags,other);
                else ss6::clampRetreat(motion,flags);
                std::cout<<flags<<' '<<motion.dx<<' '<<motion.vx<<' '<<motion.ax<<' '
                         <<motion.dy<<' '<<motion.vy<<' '<<motion.ay<<' '<<motion.y<<'\n';
            } else throw std::runtime_error("Unknown reaction control operation");
            if (!std::cin) throw std::runtime_error("Truncated reaction command");
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
