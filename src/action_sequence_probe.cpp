#include "action_runtime.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-action-sequence-probe ASSETS");
        ss6::ActionBank bank(argv[1],true);
        ss6::ActionTimeline player(bank,0);
        std::string op;
        while (std::cin>>op) {
            if (op=="start") { unsigned id; std::cin>>id; player.start(bank.get(id)); }
            else if (op=="stop") player.stopMotion();
            else if (op=="advance") { uint32_t delta; std::cin>>delta; player.advance(delta); }
            else if (op=="flags") {
                uint32_t a,b,c; std::cin>>a>>b>>c; player.setObjectFlags(a,b,c);
            } else if (op=="motion") {
                ss6::MotionState m; std::cin>>m.dx>>m.vx>>m.ax>>m.dy>>m.vy>>m.ay>>m.x>>m.y;
                player.setMotion(m);
            } else throw std::runtime_error("Unknown action sequence command");
            const auto& c=player.clock(); const auto& m=player.motion();
            std::cout<<player.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '<<c.endReached<<' '
                     <<c.endControl<<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '<<c.chainedAction<<' '
                     <<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay<<' '
                     <<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<'\n';
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
