#include "reaction.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc<2||argc>3) throw std::runtime_error("Usage: ss6-reaction-probe ASSETS [--ground|--flow]");
        ss6::ReactionTables tables(argv[1]);
        const std::string mode=argc==3?argv[2]:"";
        if(mode=="--flow") {
            ss6::ActionBank bank(argv[1],true);
            unsigned state,delta,mirror,ticks;
            while(std::cin>>state>>delta>>mirror>>ticks) {
                ss6::PlayerObject object(bank,0);
                object.timeline.setObjectFlags(0x10000000|(mirror?0x80000:0),0x200,0);
                object.request(tables.ordinaryAction(state,true),true);object.commitRequested();
                for(unsigned tick=0;tick<ticks;++tick) {
                    object.animate(delta);object.move(delta);
                    const bool recovered=ss6::updateGroundReaction(object);
                    const auto& t=object.timeline;const auto c=t.clock();
                    std::cout<<t.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '<<c.endReached<<' '
                             <<c.flags104<<' '<<c.flags108<<' '<<recovered<<' ';
                }
                std::cout<<'\n';
            }
            return 0;
        }
        const bool extended=mode=="--ground"||mode=="--special";
        if(!mode.empty()&&!extended)throw std::runtime_error("Unknown reaction probe mode");
        uint32_t flags,flags24c,previous,part,special,sourceAirborne;
        int table;
        while (std::cin>>flags>>flags24c>>previous>>table>>part>>special>>sourceAirborne) {
            ss6::ReactionTarget target;
            target.flags23c=flags;target.flags24c=uint8_t(flags24c);target.previousReaction=uint8_t(previous);target.stateTable=int16_t(table);
            ss6::ActorTimers sourceTimers,targetTimers;
            unsigned raw=10,strength=0,heavy=0;uint32_t sourceFlags=0;
            if(extended) {
                if(!(std::cin>>raw>>strength>>heavy>>sourceFlags))throw std::runtime_error("Truncated ground reaction");
                target.heavyReaction=heavy;
            }
            auto result=tables.applyGroundHit(target,sourceTimers,targetTimers,raw,part,special,sourceAirborne,strength,sourceFlags,mode=="--special");
            std::cout<<target.flags23c<<' '<<target.pendingTable<<' '<<target.pendingState<<' '<<target.forceState<<' '
                     <<unsigned(target.previousReaction)<<' '<<unsigned(target.secondaryReaction)<<' '
                     <<sourceTimers.values[0]<<' '<<sourceTimers.values[1]<<' '
                     <<targetTimers.values[0]<<' '<<targetTimers.values[1]<<' '<<result.action;
            if(extended)std::cout<<' '<<target.heavyReaction<<' '<<sourceFlags;
            std::cout<<'\n';
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
