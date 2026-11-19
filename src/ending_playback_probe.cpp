#include "ending_playback.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if(argc!=2)throw std::runtime_error("Usage: ss6-ending-playback-probe ASSETS");
        ss6::ActionBank bank(argv[1],true);
        auto storage=std::make_unique<ss6::PlayerObject>(bank);
        ss6::EndingPlayback ending;
        ss6::ActorTimers timers;unsigned player=0;
        uint32_t posture=0x1000,gates=0;
        std::string op;
        while(std::cin>>op) {
            if(op=="reset") {
                storage=std::make_unique<ss6::PlayerObject>(bank);
                storage->setFlags(storage->timeline.clock().flags104|0x200,storage->timeline.clock().flags108);
                ending={};timers={};player=0;posture=0x1000;gates=0;
            }
            auto& object=*storage;
            if(op=="reset") {}
            else if(op=="begin"||op=="final") {
                int loser,life;std::cin>>loser>>posture>>gates>>life;
                if(loser)ending.beginLoser(object,posture,gates);
                else ending.beginWinner(object,posture,gates,life,op=="final");
            } else if(op=="intro") {
                std::cin>>player>>gates;ending.beginIntroduction(object,gates,player);
            } else if(op=="defer") {
                int ticks;std::cin>>ticks;ending.deferIntroduction(object,timers,ticks);
            } else if(op=="commit")object.commitRequested();
            else if(op=="animate"||op=="move") {
                uint32_t delta;std::cin>>delta;timers.delta=int32_t(delta);
                if(op=="animate")object.animate(delta);else object.move(delta);
            } else if(op=="callback")ending.update(object,gates,&timers,player);
            else if(op=="flags") {
                uint32_t a,b,c;std::cin>>a>>b>>c;object.timeline.setObjectFlags(a,b,c);
            } else throw std::runtime_error("Unknown ending playback probe command");
            const auto& c=object.timeline.clock();const auto& m=object.timeline.motion();
            std::cout<<gates<<' '<<int(ending.phase)<<' '
                <<object.timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '
                <<c.endReached<<' '<<c.endControl<<' '<<c.objectFlags<<' '<<c.flags104<<' '
                <<c.flags108<<' '<<c.chainedAction<<' '<<object.pendingFlags<<' '
                <<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay<<' '
                <<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<' '<<timers.values[34]<<'\n';
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
