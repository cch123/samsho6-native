// Exercise the same screen instance across selected, continued and reselected fights.
#define main viewerMain
#include "viewer.cpp"
#undef main

namespace {
std::vector<int> clockState(const ss6::CombatStageState& stage) {
    std::vector<int> result;
    if(stage.stage==0) {
        for(const auto& v:stage.layers)result.insert(result.end(),{v.elapsed,int(v.picture),int(v.step)});
    } else {
        for(const auto& v:stage.layers01)result.insert(result.end(),{v.elapsed,int(v.picture),int(v.flags)});
    }
    return result;
}
}

int main(int argc,char** argv) {
    if(argc!=4)return 2;
    try {
        const fs::path assets=argv[1],dump=argv[3];
        std::ifstream input(argv[2]);
        ss6::LocalVersus game(assets,-1,ss6::VersusMode::Console,{},true);
        VersusScreen screen(assets);
        std::array<std::vector<int>,ss6::CombatStageState::stageCount> saved;
        std::array<uint32_t,2> previous{},held{};
        game.onTick([&](const ss6::NativeMatch& old){
            const auto& state=old.combatStage();
            if(state.visible)saved.at(state.stage)=clockState(state);
        });
        unsigned count;
        while(ss6::readVersusReplaySegment(input,count,held))for(unsigned tick=0;tick<count;++tick) {
            std::array<ss6::NormalizedPadSample,2> pads;
            for(unsigned s=0;s<2;++s)pads[s]={held[s],held[s]&~previous[s]};
            previous=held;
            game.tick(pads);
            const auto& match=game.match();
            if(match.characterSelect())continue;
            const auto& state=match.combatStage();
            const auto& clocks=saved.at(state.stage);
            if(match.updates==0 && !clocks.empty() && clocks!=clockState(state))
                throw std::runtime_error("Returning to an arena reset its clocks");
            if(match.updates!=600)continue;
            screen.paint(match,dump);
            const auto raw=readFile(dump);
            Bytes expected(640*448*4);
            ss6::CombatStage(assets,state.stage).paint(state,match.battle().gauges.paletteTones,expected);
            if(raw.size()!=expected.size()+8 || !std::equal(expected.begin(),expected.end(),raw.begin()+8))
                throw std::runtime_error("The active screen used a different arena from the battle");
            std::cout<<game.matchNumber()<<' '<<state.stage<<'\n';
        }
    } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}

