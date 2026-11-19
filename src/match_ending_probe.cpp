#include "battle_round.hpp"
#include <iostream>
#include <stdexcept>

int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::MatchEndingRules rules(argv[1]);ss6::ActionBank bank(argv[1],true);
    std::array<ss6::PlayerObject,2> bodies{{ss6::PlayerObject(bank,189),ss6::PlayerObject(bank,189)}};
    std::array<ss6::StateEntryActor,2> actors;
    std::array<ss6::ActorCommandInput,2> inputs;
    std::array<ss6::InputSystemConfig,2> configs;
    std::array<ss6::RoundActorStorage,2> storage;
    std::array<ss6::CallbackContext,2> contexts;
    const std::array<ss6::RoundPlayerRef,2> players{{
        {bodies[0],actors[0],inputs[0],configs[0],storage[0],contexts[0]},
        {bodies[1],actors[1],inputs[1],configs[1],storage[1],contexts[1]}}};
    unsigned op;
    while(std::cin>>op) {
        if(op==2) {
            int character;unsigned choice,version;std::cin>>character>>choice>>version;
            std::cout<<rules.available(character,choice,uint8_t(version))<<'\n';continue;
        }
        ss6::BattleRoundState b;auto& e=b.matchEnd;unsigned version;
        std::cin>>e.winner08>>b.match.result.result>>b.endingParameter2c>>version
            >>e.stage28>>e.result8c>>e.profileFlags1239090>>e.metadataStage04>>e.continue2c>>e.endFlagA4;
        e.characterVersion43d052=uint8_t(version);
        for(unsigned i=0;i<2;++i) {
            auto& a=actors[i];auto& s=b.match.players[i];
            std::cin>>a.character>>configs[i].system>>a.fieldA30>>s.wins>>s.requiredWins>>s.outcome1c>>s.outcome20;
        }
        if(!std::cin)throw std::runtime_error("Incomplete ending choice fixture");
        int result=0;
        if(op==0)result=rules.select(b,players);
        else if(op==1)rules.recordFinal(b,players);
        else throw std::runtime_error("Unknown ending choice operation");
        std::cout<<result<<' '<<e.winner08<<' '<<b.match.result.result<<' '<<b.endingParameter2c<<' '
            <<+e.characterVersion43d052<<' '<<e.stage28<<' '<<e.result8c<<' '<<e.profileFlags1239090<<' '
            <<e.metadataStage04<<' '<<e.continue2c<<' '<<e.endFlagA4;
        for(unsigned i=0;i<2;++i) {
            const auto& a=actors[i];const auto& s=b.match.players[i];
            std::cout<<' '<<a.character<<' '<<configs[i].system<<' '<<a.fieldA30<<' '<<s.wins<<' '
                <<s.requiredWins<<' '<<s.outcome1c<<' '<<s.outcome20;
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
