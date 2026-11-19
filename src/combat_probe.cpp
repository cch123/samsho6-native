#include "combat_decision.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Expected asset directory");
        ss6::CombatTables tables(argv[1]);
        std::string command;
        while (std::cin>>command) {
            if (command=="defense" || command=="decision") {
                ss6::CollisionPlayer source;ss6::DefenseSnapshot target;
                unsigned flags,aConsumed=0,bConsumed=0,route=7;int descriptor;
                if (command=="decision") std::cin>>route>>aConsumed>>bConsumed;
                std::cin>>source.objectFlags104>>source.objectFlags108>>target.actorFlags23c>>target.actorFlags244
                    >>target.stateTable>>target.stateIndex>>flags>>target.fieldA20>>target.fieldC8>>target.field3C0
                    >>target.field39C>>target.field398>>target.system>>descriptor;
                target.stateFlags=uint8_t(flags);
                if (descriptor>=0 && descriptor<=255) target.system6DescriptorByteC=uint8_t(descriptor);
                if (command=="defense") std::cout<<unsigned(ss6::selectDefense(source,target));
                else {
                    ss6::ContactEvent event{};event.route=route;
                    const ss6::ContactMarks a{0,source.objectFlags104,source.objectFlags108,uint8_t(aConsumed)},b{1,0,0,uint8_t(bConsumed)};
                    const auto decision=ss6::inspectContactDecision(tables,event,source,target,a,b);
                    std::cout<<int(decision.kind)<<' '<<unsigned(decision.defense)<<' '<<unsigned(a.consumed)<<' '<<unsigned(b.consumed);
                }
            } else if (command=="projectile") {
                ss6::CollisionPlayer source,target;
                ss6::ContactEvent event{};
                ss6::DefenseSnapshot defense;
                unsigned sBits,tBits,sPause,tPause,stateFlags;
                std::cin>>event.route>>source.objectKind>>target.objectKind>>source.owner>>target.owner
                        >>source.objectFlags104>>source.objectFlags108>>sBits>>tBits>>sPause>>tPause
                        >>defense.stateTable>>defense.stateIndex>>stateFlags>>defense.field398>>defense.field39C;
                defense.stateFlags=uint8_t(stateFlags);
                ss6::ContactMarks a{source.objectKind,source.objectFlags104,source.objectFlags108,uint8_t(sBits)};
                ss6::ContactMarks b{target.objectKind,0,0,uint8_t(tBits)};
                const auto kind=ss6::projectileContact(event,source,target,a);
                bool pause=false;
                unsigned choice=0;
                if (kind==ss6::ProjectileContact::ClashProjectiles)
                    pause=ss6::markProjectileClash(b,uint8_t(sPause),uint8_t(tPause));
                else if (kind==ss6::ProjectileContact::StrikePlayer)
                    choice=ss6::inspectContactDecision(tables,event,source,defense,a,b).defense;
                std::cout<<int(kind)<<' '<<choice<<' '<<unsigned(b.consumed)<<' '<<pause;
            } else if (command=="marks") {
                ss6::ContactMarks state;unsigned byte;int index;
                std::cin>>state.objectKind>>state.flags104>>state.flags108>>byte>>index;
                state.consumed=uint8_t(byte);
                const bool consumed=ss6::contactConsumed(state,index);
                ss6::markContactConsumed(state,index);
                std::cout<<consumed<<' '<<unsigned(state.consumed)<<' '<<state.flags104<<' '<<state.flags108;
            } else if (command=="indices") {
                unsigned route;std::cin>>route;const auto pair=tables.consumptionIndices(route);
                std::cout<<pair[0]<<' '<<pair[1];
            } else if (command=="registry") {
                unsigned count;std::cin>>count;
                if (count>1000) throw std::runtime_error("Registry fixture too large");
                ss6::ContactRegistry registry;
                for (unsigned i=0;i<count;++i) {
                    uint32_t identity,character,action;unsigned reset,byte;ss6::ContactMarks state;
                    std::cin>>reset>>identity>>character>>action>>state.flags104>>byte;
                    state.consumed=uint8_t(byte);
                    if (reset) registry.reset();
                    const bool added=registry.add(identity,character,action,state);
                    std::cout<<added<<' '<<unsigned(state.consumed)<<' '<<state.flags104<<' '<<registry.objects().size()<<' ';
                }
                std::cout<<registry.objects().size();
                for (const auto identity:registry.objects()) std::cout<<' '<<identity;
            } else throw std::runtime_error("Unknown combat probe command");
            if (!std::cin) throw std::runtime_error("Malformed combat fixture");
            std::cout<<'\n';
        }
    } catch (const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
