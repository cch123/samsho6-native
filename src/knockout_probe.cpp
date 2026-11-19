#include "knockout.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-knockout-probe ASSETS");
        ss6::ActionBank bank(argv[1],true);
        auto storage=std::make_unique<ss6::PlayerObject>(bank);
        storage->setFlags(storage->timeline.clock().flags104|0x200,storage->timeline.clock().flags108);
        ss6::KnockoutPlayback ko;
        uint32_t flags=0x1080;
        std::string op;
        while (std::cin>>op) {
            if (op=="reset") {
                storage=std::make_unique<ss6::PlayerObject>(bank);
                storage->setFlags(storage->timeline.clock().flags104|0x200,storage->timeline.clock().flags108);
                ko={};flags=0x1080;
            }
            auto& object=*storage;
            int result=0;
            if (op=="reset") {}
            else if (op=="begin") {
                unsigned variant;std::cin>>flags>>variant;
                ko.begin(object,flags,variant);
            } else if (op=="commit") object.commitRequested();
            else if (op=="animate"||op=="move") {
                uint32_t delta;std::cin>>delta;
                if (op=="animate") object.animate(delta);else object.move(delta);
            } else if (op=="callback") result=ko.update(object);
            else if (op=="flags") {
                uint32_t a,b,c;std::cin>>a>>b>>c;object.timeline.setObjectFlags(a,b,c);
            } else if (op=="motion") {
                ss6::MotionState m;std::cin>>m.dx>>m.vx>>m.ax>>m.dy>>m.vy>>m.ay>>m.x>>m.y;
                object.timeline.setMotion(m);
            } else throw std::runtime_error("Unknown KO probe command");
            const auto& c=object.timeline.clock();const auto& m=object.timeline.motion();
            std::cout<<flags<<' '<<int(ko.phase)<<' '<<result<<' '
                <<object.timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '
                <<c.endReached<<' '<<c.endControl<<' '<<c.objectFlags<<' '<<c.flags104<<' '
                <<c.flags108<<' '<<c.chainedAction<<' '<<object.pendingFlags<<' '
                <<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay<<' '
                <<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<'\n';
        }
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
