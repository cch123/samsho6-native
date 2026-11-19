#include "action_selection.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
namespace {
ss6::SelectionActor actor() {
    ss6::SelectionActor a;unsigned byte,half;
    std::cin>>a.flags23c>>a.flags244>>a.flags248>>byte>>a.state194>>a.state1a4>>a.character>>a.variantA48>>a.bodyFlags38>>half>>a.x>>a.opponentX;
    a.flags24c=uint8_t(byte);a.bodyPendingFE=uint16_t(half);return a;
}
ss6::InputSystemConfig config() {
    ss6::InputSystemConfig c;std::array<uint8_t,16> d;
    std::cin>>c.system>>c.character;
    for(auto& v:d){unsigned n;std::cin>>n;v=uint8_t(n);}if(c.system==6)c.descriptor=d;return c;
}
ss6::ActorCommandInput input() {
    ss6::ActorCommandInput a;unsigned count;
    std::cin>>count;for(unsigned i=0;i<count;++i){unsigned index,value;std::cin>>index>>value;a.sampledFeatures.at(index)=value;}
    std::cin>>count;for(unsigned i=0;i<count;++i){unsigned index,value;std::cin>>index>>value;a.normal.at(index).recognized=value;}
    return a;
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::ActionSelection selections(argv[1]);std::string op;
    while(std::cin>>op) {
        if(op=="map") {
            unsigned kind,state,column,flags;std::cin>>kind>>state>>column>>flags;
            std::cout<<unsigned(kind?selections.attackTransition(state,column,flags,kind==2):selections.normalTransition(state,column,flags))<<'\n';
        } else if(op=="system") {
            auto c=config();std::cout<<ss6::inputSystemColumn(c)<<'\n';
        } else if(op=="restricted_state") {
            unsigned state;std::cin>>state;std::cout<<unsigned(selections.restrictedState(state))<<'\n';
        } else if(op=="face") {
            auto a=actor();bool force;std::cin>>force;
            std::cout<<a.faceOpponent(force)<<' '<<a.bodyFlags38<<' '<<a.stateTable()<<' '<<a.stateIndex()<<'\n';
        } else if(op=="normal_request") {
            auto a=actor();std::cin>>a.flags240>>a.controlKindA20>>a.controlModeC8>>a.request18c>>a.pendingTable>>a.pendingIndex;
            auto opponent=actor();std::cin>>opponent.bodyAction24>>opponent.auxiliaryState128>>opponent.auxiliaryFlag134;
            ss6::SelectionThreat context;unsigned count;std::cin>>context.distance>>count;
            for(unsigned i=0;i<count;++i){unsigned slot;int32_t kind;std::cin>>slot>>kind;context.opponentObjectKinds.at(slot)=kind;}
            auto c=config();auto in=input();bool restricted;std::cin>>restricted;
            const auto allowed=ss6::inputGuardAllowed(a,c),threat=selections.opponentThreat(a,opponent,context);
            const auto queued=selections.requestNormal(a,opponent,in,c,context,restricted);
            std::cout<<allowed<<' '<<threat<<' '<<queued<<' '<<a.bodyFlags38<<' '<<a.flags248<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<'\n';
        } else if(op=="translate_normal") {
            auto a=actor();int state;std::cin>>a.flags240>>a.controlKindA20>>a.controlModeC8>>state;
            std::cout<<selections.translateNormalState(a,state)<<'\n';
        } else if(op=="request_attack"||op=="request_chain"||op=="request_supplemental"||op=="request_system_only") {
            auto a=actor();std::cin>>a.bodyFlags104>>a.request18c>>a.pendingTable>>a.pendingIndex;
            auto opponent=actor();auto c=config();auto in=input();
            const bool queued=op=="request_chain"?selections.requestChain(a,opponent,in,c):op=="request_attack"?selections.requestAttack(a,in):selections.requestSupplemental(a,in,op=="request_system_only");
            std::cout<<queued<<' '<<a.bodyFlags38<<' '<<a.variantA48<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<'\n';
        } else if(op=="normal"||op=="system_normal"||op=="attack"||op=="chain"||op=="restricted_normal"||op=="supplemental"||op=="system_only") {
            auto a=actor();unsigned state;bool threat;std::cin>>state>>threat;auto c=config();auto in=input();
            int next=op=="normal"?int(selections.normal(a,in,state,threat,c)):op=="restricted_normal"?int(selections.restrictedNormal(a,in,state,c)):op=="system_normal"?selections.systemNormal(a,in,state,c):op=="supplemental"||op=="system_only"?selections.supplemental(a,in,state,op=="system_only"):selections.attack(a,in,state,op=="chain");
            std::cout<<next<<' '<<a.bodyFlags38<<' '<<a.variantA48<<'\n';
        } else throw std::runtime_error("Unknown action selection probe operation");
        if(!std::cin)throw std::runtime_error("Incomplete action selection fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
