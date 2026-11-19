#include "damage.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-damage-probe ASSETS");
        ss6::DamageTables tables(argv[1]);
        std::string op;
        while (std::cin>>op) {
            if (op=="contact"||op=="special-contact") {
                ss6::DamageActor source,target;
                int auxiliary,guard,strength;
                std::cin>>auxiliary>>guard>>source.swordCurrent>>source.swordMaximum>>source.rageState
                        >>source.flags23c>>strength>>target.life>>target.rageState>>target.rageAmount
                        >>target.rageDecay>>target.swordCurrent>>target.swordMaximum>>target.flags248;
                source.attackStrength=uint8_t(strength);
                auto amount=tables.applyOrdinaryContact(auxiliary,source,target,guard,op=="special-contact");
                std::cout<<amount<<' '<<source.swordCurrent<<' '<<source.flags23c<<' '
                         <<target.rageState<<' '<<target.rageAmount<<' '<<target.rageDecay<<' '
                         <<target.swordCurrent<<' '<<target.swordMaximum<<' '<<target.flags248<<'\n';
            } else if (op=="damage"||op=="matchup") {
                int auxiliary,mode,sourceArmed,targetArmed;
                ss6::DamageActor source,target;
                if(op=="matchup")std::cin>>source.character>>source.system>>target.character>>target.system;
                std::cin>>auxiliary>>mode>>source.swordCurrent>>source.swordMaximum>>source.rageState
                        >>sourceArmed>>target.life>>target.defenseAdjustment>>targetArmed;
                source.armed=sourceArmed; target.armed=targetArmed;
                auto result=tables.calculate(auxiliary,source,target,unsigned(mode));
                std::cout<<result.sourceAmount.bits<<' '<<result.damage<<'\n';
            } else {
                uint32_t a,b;
                std::cin>>a>>b;
                ss6::ScalarFloat left{a},right{b},result{};
                if (op=="add") result=left.add(right);
                else if (op=="sub") result=left.sub(right);
                else if (op=="mul") result=left.mul(right);
                else if (op=="div") result=left.div(right);
                else throw std::runtime_error("Unknown scalar command");
                std::cout<<result.bits<<'\n';
            }
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
