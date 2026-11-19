#include "match_progress.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
int32_t word(uint32_t n) { return std::bit_cast<int32_t>(n); }
int32_t add(int32_t a,int32_t b) { return word(uint32_t(a)+uint32_t(b)); }
}
void PlayerMatchStats::resetRound() {
    //147d28 leaves the accumulated match history and both scores intact.
    outcome1c=outcome20=-1;
}
void PlayerMatchStats::initialize(int32_t selected,int32_t source) {
    wins=0;previous24=-1;history.fill(255);score=bonus=rating=0;
    if(uint32_t(selected)<2)rating=source/1000+1;
    resetRound();
}
void PlayerMatchStats::record(int32_t result,bool perfect,bool otherFlag,bool draw) {
    //147db8 writes a byte at history[old wins]. It has no bounds check;
    // reject unsupported overflow instead of clamping/corrupting native data.
    if(wins<0||wins>=int(history.size()))throw std::runtime_error("Match result history exceeds five entries");
    history[size_t(wins)]=uint8_t(uint32_t(result)|(perfect?0x20:0)|(otherFlag?0x40:0));
    wins=add(wins,1);
    const int32_t difference=word(uint32_t(draw?119:104)-uint32_t(rating));
    score=add(score,difference/(draw?20:5));
    if(!draw) {
        if(outcome1c==1)bonus=add(bonus,2);
        else if(outcome20==0)bonus=add(bonus,1);
        if(perfect)bonus=add(bonus,3);
    }
}
void MatchProgress::recordRound(const std::array<int32_t,2>& life,const std::array<int32_t,2>& maximum) {
    if(life[0]==life[1]) {
        result={-1,life[0]==0?1:3,life[0]==0?18:19,true};
        for(auto& p:players)p.record(life[0]==0?4:6,false,false,true);
    } else {
        const unsigned winner=life[0]>life[1]?0:1;
        const bool ko=life[1-winner]<=0;
        result={int(winner),ko?0:2,ko?15:19,false};
        players[winner].record(ko?0:5,life[winner]==maximum[winner],false,false);
    }
}
RoundTransition MatchProgress::transition(int mode,int submode) const {
    //1446b8 onward: submode6 tests the match first; submode5 suppresses
    // the single-player winner branch. Draws wait90 or120, not30.
    const bool finished=complete();
    if(submode==6) { if(finished)return {9,30}; }
    else if(submode!=5&&((mode==1&&result.winner==0)||(mode==2&&result.winner==1)))return {9,30};
    return {finished?10:0,result.draw?(finished?120:90):30};
}
unsigned MatchProgress::openingLabel() const {
    const unsigned label=roundIndex<10?unsigned(roundIndex+1):10;
    //1439b8..1439ec: both players must be one win from the threshold.
    // The first-round label is retained even in a one-win configuration.
    if(label>=2&&players[0].wins+1>=players[0].requiredWins&&
       players[1].wins+1>=players[1].requiredWins)return 10;
    return label;
}
void BattleTimers::set(unsigned index,int32_t ticks,int32_t divisor) {
    const int32_t shifted=word(uint32_t(ticks)<<8);
    //140930 supplies1 or8. Negative divisors and exceptional EE division
    // have not been validated and must not introduce C++ division overflow.
    if(divisor<=0)throw std::runtime_error("Battle timer divisor must be positive");
    values.at(index)=shifted/divisor;
}
void BattleTimers::clear(unsigned index) { values.at(index)=0; }
int32_t BattleTimers::decrease(unsigned index) {
    const int32_t old=values.at(index),next=word(uint32_t(old)-uint32_t(delta));
    values[index]=next<0?0:next;
    return old; // The visit reaching zero still blocks the round dispatcher.
}
int32_t BattleTimers::increase(unsigned index) {
    const int32_t old=values.at(index),next=add(old,delta);
    values[index]=next>0x173400?0x173400:next;
    return old;
}
void BattleTimers::decreaseLock() {
    const int32_t next=add(lock,-1);lock=next<0?0:next;
}
}
