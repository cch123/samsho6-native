#include "asset_files.hpp"
#include "match_ending.hpp"
#include "battle_round.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
MatchEndingRules::MatchEndingRules(const std::filesystem::path& assets) {
    std::ifstream in(resolveAsset(assets/"ending_choices.bin"),std::ios::binary);
    for(auto& row:choices_)for(auto& word:row) {
        word=0;
        for(unsigned b=0;b<4;++b){const int c=in.get();if(c==EOF)throw std::runtime_error("Truncated ending choices");word|=uint32_t(c)<<(b*8);}
    }
    if(in.peek()!=EOF)throw std::runtime_error("Invalid ending choice size");
}
bool MatchEndingRules::available(int character,unsigned choice,uint8_t version) const {
    if(character>=49||character==43)return false;
    if(character<0||choice>=16)throw std::runtime_error("Ending choice outside original table");
    const auto& row=choices_[unsigned(character)+(version?49:0)];
    if(!row[0])throw std::runtime_error("Unresolved alternate ending character table");
    return row[choice+1]!=0;
}
int MatchEndingRules::select(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) const {
    const auto winner=b.matchEnd.winner08;
    if(winner==-1)return 5;
    if(winner<0||winner>1)throw std::runtime_error("Invalid final winner");
    const auto& a=players[unsigned(winner)].actor;const auto& other=players[unsigned(1-winner)].actor;
    const auto& stats=b.match.players[unsigned(winner)];
    const bool high=a.fieldA30>=100; //14ab70, inclusive; not the idle threshold.
    if(b.match.result.result==2)return 5; //Preserve battle+2c on timeout/draw early returns.
    const auto hit=stats.outcome1c;int fallback=5;
    if(stats.outcome20==0)fallback=high?0:1;
    else if(selectedCharacter(a)==selectedCharacter(other))fallback=6; // 1455f4 compares a14
    else if(stats.outcome20==1)fallback=high?2:3;
    else if(high)fallback=4;
    b.endingParameter2c=(hit==-1||hit==5)?0:70;
    if(hit==-1)return fallback;
    const auto system=players[unsigned(winner)].config.system;int choice=-1;
    if(system==5&&uint32_t(hit)<2)choice=high?7:8;
    else if(system==0&&hit==2)choice=9;
    else if(system==1&&uint32_t(hit)<2)choice=10;
    else if(system==2&&hit==1)choice=11;
    else if(system==3&&hit==1)choice=12;
    else if(system==3&&hit==3)choice=13;
    else if(system==4&&hit==1)choice=14;
    else if(system==4&&hit==3)choice=15;
    else if(system>=6&&system<=8&&uint32_t(hit)<4)choice=high?7:8;
    if(choice<0)return fallback;
    //The fallback7/8 is returned directly even if its own table slot is
    //empty. A second availability check would alter the original decision.
    return available(selectedCharacter(a),unsigned(choice),b.matchEnd.characterVersion43d052)?choice:high?7:8;
}
void MatchEndingRules::recordFinal(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) const {
    if(b.matchEnd.profileActive123a168)
        throw std::runtime_error("Final result does not support network reporting");
    auto& e=b.matchEnd;
    e.winner08=b.match.players[0].complete()?(b.match.players[1].complete()?-1:0):1;
    e.stage28=std::bit_cast<int32_t>(e.metadataStage04);e.result8c=select(b,players);
    //Even the disabled profile branch of139f20 calls11c208. It clears
    //mask1, rather than resetting all saved profile flags.
    e.profileFlags1239090&=~1u;
}
}
