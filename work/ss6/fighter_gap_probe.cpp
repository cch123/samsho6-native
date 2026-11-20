#include <cstdlib>
// Pipeline step C (docs/development-plan.txt): drives a console VS session
// from the selection grid with recorded pads and reports the first unported
// fighter state or runtime failure, plus the states/ACTs each seat visited.
// Usage: fighter_gap_probe <assets> [none|p1|p2|both] < "p1 p2" pad lines
#include "local_versus.hpp"
#include <iostream>
#include <set>
#include <string>
int main(int argc,char** argv) {
    unsigned tick=0;
    std::array<std::set<std::pair<int,int>>,2> states;std::array<std::set<int>,2> actions;std::array<int,2> systems{-1,-1};
    auto summary=[&] {
        for(unsigned i=0;i<2;++i) {
            std::cout<<"STATES "<<i;for(auto [t,s]:states[i])std::cout<<' '<<t<<'/'<<s;std::cout<<'\n';
            std::cout<<"ACTS "<<i;for(auto a:actions[i])std::cout<<' '<<a;std::cout<<'\n';
        }
        std::cout<<"SYSTEMS "<<systems[0]<<' '<<systems[1]<<'\n';
    };
    try {
        const std::string cpu=argc>2?argv[2]:"none";
        const auto seats=cpu=="none"?std::array<bool,2>{}:ss6::versusCpuSeats(cpu);
        ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},ss6::VersusEntry::CharacterSelect,seats);
        std::array<uint32_t,2> last{},held{};unsigned matches=0,lastNumber=session.matchNumber();
        for(tick=1;std::cin>>held[0]>>held[1];++tick) {
            std::array<ss6::NormalizedPadSample,2> p;
            for(unsigned i=0;i<2;++i)p[i]={held[i],held[i]&~last[i]};last=held;
            session.tick(p);
            const auto& m=session.match();
            if(m.selectionUnavailable()&&!m.missingMove().empty()) {
                std::cout<<"GAP "<<tick<<' '<<m.missingMove()<<'\n';summary();return 2;
            }
            if(m.characterSelect())continue;
            for(unsigned i=0;i<2;++i) {
                const auto& f=m.fighter(i);
                states[i].insert({f.actor.stateTable(),f.actor.stateIndex()});
                actions[i].insert(int(f.body.timeline.action().id()));
                systems[i]=int(f.config.system);
            }
            if(std::getenv("SS6_TRACE_SEAT")) { // per-tick state of one seat (debugging)
                const auto& f=m.fighter(unsigned(std::atoi(std::getenv("SS6_TRACE_SEAT"))));
                std::cout<<"T "<<tick<<' '<<f.actor.stateTable()<<'/'<<f.actor.stateIndex()<<std::hex<<" cb "<<f.actor.callbacks260[0]
                         <<" act "<<f.body.timeline.action().id()<<" rec "<<f.body.timeline.clock().step<<" f104 "<<f.body.timeline.clock().flags104
                         <<std::dec<<" y "<<f.body.timeline.motion().y<<" vy "<<f.body.timeline.motion().vy<<'\n';
            }
            if(session.matchNumber()!=lastNumber){lastNumber=session.matchNumber();++matches;}
        }
        const auto& m=session.match();
        std::cout<<"END "<<tick<<" matches "<<matches<<" state "<<m.battle().currentState;
        if(!m.characterSelect())for(unsigned i=0;i<2;++i)std::cout<<" life"<<i<<' '<<m.fighter(i).actor.fieldA30<<" wins"<<i<<' '<<m.battle().match.players[i].wins;
        std::cout<<'\n';summary();
    } catch(const std::exception& e) {
        std::cout<<"ERROR "<<tick<<' '<<e.what()<<'\n';summary();return 1;
    }
}
