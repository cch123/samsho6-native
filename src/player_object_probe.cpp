#include "player_object.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2&&argc!=3) throw std::runtime_error("Usage: ss6-player-object-probe ASSETS [FIGHTER]");
        ss6::ActionBank bank(argv[1],true,argc==3?unsigned(std::stoul(argv[2])):0);
        ss6::PlayerObject object(bank,0);
        auto& player=object.timeline;
        std::string op;
        while (std::cin>>op) {
            if (op=="request") { unsigned id,force; std::cin>>id>>force;object.request(id,force); }
            else if (op=="commit") object.commitRequested();
            else if (op=="rewind") object.rewindFirstRecord();
            else if (op=="pending") { unsigned bits;std::cin>>bits;object.pendingFlags=uint16_t(bits); }
            else if (op=="animate") { uint32_t delta;std::cin>>delta;object.animate(delta); }
            else if (op=="move") { uint32_t delta;std::cin>>delta;object.move(delta); }
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
                     <<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<' '<<object.pendingFlags<<'\n';
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
