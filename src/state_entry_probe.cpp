#include "state_entry.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main() {
 try {
    unsigned op;
    while(std::cin>>op) {
        ss6::StateEntryActor a;unsigned flags,alias;
        std::cin>>a.flags23c>>a.character>>a.state194>>a.state1a4>>a.stateCharacter198>>a.aliasCharacter1a8>>flags>>alias
            >>a.request18c>>a.pendingTable>>a.pendingIndex>>a.aliasRequest19c>>a.aliasPendingTable>>a.aliasPendingIndex
            >>a.auxiliaryState128>>a.auxiliaryAction24>>a.auxiliaryPendingC4>>a.auxiliaryFrameC0>>a.auxiliaryFlags104>>a.timerDelta;
        a.stateFlags19a=uint8_t(flags);a.aliasFlags1aa=uint8_t(alias);for(auto& v:a.timers)std::cin>>v;
        ss6::StateEntryPlan plan;int result=-1;
        if(op==0)result=ss6::stateRequestDiffers(a);
        else if(op==1)ss6::commitStateRequest(a);
        else plan=ss6::prepareStateEntry(a);
        std::cout<<result;
        if(op==2)std::cout<<' '<<plan.required<<' '<<plan.previousTable<<' '<<plan.previousIndex<<' '<<plan.table<<' '<<plan.index<<' '<<plan.finishAttackAfterEntry;
        std::cout<<' '<<a.flags23c<<' '<<a.state194<<' '<<a.state1a4<<' '<<a.stateCharacter198<<' '<<a.aliasCharacter1a8<<' '<<unsigned(a.stateFlags19a)<<' '<<unsigned(a.aliasFlags1aa)
            <<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '<<a.aliasRequest19c<<' '<<a.aliasPendingTable<<' '<<a.aliasPendingIndex
            <<' '<<a.auxiliaryState128<<' '<<a.auxiliaryAction24<<' '<<a.auxiliaryPendingC4<<' '<<a.auxiliaryFrameC0<<' '<<a.auxiliaryFlags104;
        for(auto v:a.timers)std::cout<<' '<<v;
        if(!std::cin)throw std::runtime_error("Incomplete state-entry fixture");
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
