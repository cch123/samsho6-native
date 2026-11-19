#include "round_rules.hpp"
#include <iostream>
#include <string>
int main() {
    try {
        std::string op;
        while (std::cin>>op) {
            if (op=="gates") {
                uint32_t f,p,o;int t,s,d,timer,far;std::cin>>f>>p>>t>>s>>d>>o>>timer>>far;
                std::cout<<ss6::ordinaryStateGates(f,p,t,s,uint8_t(d),o,timer,far)<<'\n';
            } else if (op=="victory") {
                uint32_t p,f;int t,s,ended,condition;std::cin>>p>>f>>t>>s>>ended>>condition;
                std::cout<<int(ss6::victoryRequest(p,f,t,s,ended,condition))<<'\n';
            } else if (op=="ko") {
                uint32_t p,f;int t,s,timer,lock;std::cin>>p>>f>>t>>s>>timer>>lock;
                std::cout<<ss6::knockoutRequest(p,f,t,s,timer,lock)<<'\n';
            } else if (op=="lock") {
                int f,s,l;std::cin>>f>>s>>l;std::cout<<unsigned(ss6::roundInputFlags(uint8_t(f),s,l))<<'\n';
            } else if (op=="pause") {
                ss6::BattlePause p;std::cin>>p.remaining>>p.delay;
                p.advance();std::cout<<p.remaining<<' '<<p.delay<<' '<<p.paused<<'\n';
            } else if (op=="meters") {
                int state,pause;std::cin>>state>>pause;std::cout<<ss6::ordinaryMetersActive(state,pause)<<'\n';
            } else throw std::runtime_error("Unknown round-rule probe operation");
            if (!std::cin) throw std::runtime_error("Invalid round-rule probe arguments");
        }
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
