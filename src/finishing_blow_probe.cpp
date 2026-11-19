#include "finishing_blow.hpp"
#include "collision.hpp"
#include "match_progress.hpp"
#include "state_entry.hpp"
#include <iostream>

int main(int argc,char** argv) {
    if(argc!=2)return 1;
    const ss6::InputBindings bindings(argv[1]);
    int mode;
    while(std::cin>>mode) {
        ss6::StateEntryActor source{},target{};
        ss6::PlayerMatchStats stats{};
        ss6::ContactEvent event{};
        unsigned strength=0,weak=0;
        bool projectile=false;
        if(!(std::cin>>source.state194>>source.state1a4>>strength>>source.flags23c>>source.flags244>>source.flags248
             >>target.state194>>target.state1a4>>target.flags23c>>target.flags240>>weak>>event.a.fields.group>>projectile
             >>target.pendingDamageA38>>target.fieldA30>>stats.hitCount0c>>stats.outcome1c>>stats.outcome20>>source.character))return 1;
        source.stateFlags19a=strength&255;
        source.aliasFlags1aa=strength>>8;
        event.b.fields.low7=weak;
        const bool counter=ss6::isCounterContact(target,stats,event);
        if(mode<2)ss6::recordContactFinish(source,target,stats,event,projectile,mode==1,counter,bindings);
        else ss6::recordScriptFinish(source,target,stats,projectile,mode==3,bindings);
        std::cout<<counter<<' '<<source.flags244<<' '<<source.flags248<<' '<<stats.outcome1c<<' '<<stats.outcome20<<'\n';
    }
}
