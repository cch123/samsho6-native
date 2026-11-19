#include "damage.hpp"
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv) {
    try {
        if (argc!=2) throw std::runtime_error("Usage: ss6-meter-probe ASSETS");
        ss6::DamageTables tables(argv[1]);ss6::DamageActor a;
        int table,state,transition,strength;uint32_t f104,f108;
        while (std::cin>>a.swordCurrent>>a.swordMaximum>>a.swordWait>>a.rageState>>a.rageAmount
               >>a.rageDecay>>table>>state>>strength>>f104>>f108>>transition) {
            a.attackStrength=uint8_t(strength);
            tables.advanceOrdinaryMeters(a,table,state,f104,f108,transition);
            std::cout<<a.swordCurrent<<' '<<a.swordMaximum<<' '<<a.swordWait<<' '<<a.rageState
                     <<' '<<a.rageAmount<<' '<<a.rageDecay<<' '<<f108<<'\n';
        }
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; }
}
