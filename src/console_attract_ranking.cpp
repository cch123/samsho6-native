#include "console_attract_ranking.hpp"
#include "game_random.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <stdexcept>

namespace ss6 {
namespace {
template<size_t N>
int chooseUnused(const std::array<int,N>& values,std::array<bool,N>& used,GameRandom& random) {
    size_t slot=unsigned(random.bounded(int(N)));
    while(used[slot])slot=(slot+1)%N;
    used[slot]=true;
    return values[slot];
}

void prepareDemoArcade(RankingDemoMatch& match,GameRandom& random,uint32_t held) {
    // 1483f8 calls 17a2c8 for resource 0 even when neither demo fighter
    // will be Haohmaru. A rejected schedule consumes four more draws.
    constexpr std::array<int,10> candidates={5,6,39,1,35,3,36,30,31,32};
    auto& opponents=match.opponents;
    for(;;) {
        const auto priorSeed=random.gameSeed;
        opponents={0,0,0,12,0,7,51};
        std::array<bool,10> used{};
        for(unsigned row:{0u,1u,2u,4u})opponents[row]=chooseUnused(candidates,used,random);
        if(std::count_if(opponents.begin(),opponents.begin()+5,[](int id){return id>=30&&id<=32;})>=2)break;
        if(random.mode!=0&&random.mode!=-2&&random.gameSeed==priorSeed)
            throw std::invalid_argument("Demo schedule cannot advance with a stationary game RNG");
    }
    constexpr std::array<int,4> replacements={27,11,13,26};
    const int requested=held&16?11:held&32?13:held&128?27:held&64?26:-1;
    if(requested>=0 && std::find(opponents.begin(),opponents.end(),requested)==opponents.end())
        opponents[6]=requested;
    else {
        unsigned slot=unsigned(random.bounded(4));
        while(std::find(opponents.begin(),opponents.end(),replacements[slot])!=opponents.end())slot=(slot+1)%4;
        opponents[6]=replacements[slot];
    }
    constexpr std::array<int,5> stages={4,5,6,7,8};
    std::array<bool,5> usedStages{};
    for(unsigned i=0;i<5;++i) {
        const int id=opponents[i];
        match.stages[i]=id>=30&&id<=32?id-30:chooseUnused(stages,usedStages,random);
    }
    match.stages[5]=9;match.stages[6]=10;
    for(auto& roll:match.roundRolls)roll=1+random.bounded(100);
    for(unsigned i=0;i<match.characterOrder.size();++i) {
        match.characterRolls[i]=random.bounded(12);
        match.characterOrder[i]=int(i);
    }
    // 17bb38 swaps each slot against the full 49-entry array.
    for(auto& id:match.characterOrder)std::swap(id,match.characterOrder[random.bounded(49)]);
}
}

RankingDemoMatch selectRankingDemo(GameRandom& random,uint32_t heldDirection) {
    constexpr std::array<unsigned,6> stages={0,1,2,5,7,8};
    RankingDemoMatch match;
    prepareDemoArcade(match,random,heldDirection);
    match.stage=stages.at(random.bounded(6));
    for(auto& fighter:match.players) {
        // Costume and spirit draws precede the character draw for each seat.
        // Filtering the roster would change the original demo selections.
        fighter.color=unsigned(random.bounded(5));
        fighter.spirit=unsigned(random.bounded(9));
        fighter.character=unsigned(random.bounded(40));
    }
    auto& p1=match.players[0];const auto& p2=match.players[1];
    if(p1.character==p2.character && p1.color==p2.color)p1.color=(p1.color+1)%5;
    return match;
}

int RankingFrame::paletteLevelWrite() const {
    if(phase==1 && tick>=480)return std::min(120,2*(int(tick)-480));
    if(phase==5 && tick<60)return 120-2*int(tick);
    return -1;
}

RankingRows RankingFrame::rowLayout() const {
    RankingRows layout;
    if(phase==3) {
        const bool entering=tick<120, leaving=tick>=240;
        // 1ea4a8 evaluates a cubic Bezier in EE operation order. The last
        // departing row stops one pixel short of its nominal 1280px offset.
        const auto one=ScalarFloat::integer(1),three=ScalarFloat::integer(3);
        for(unsigned i=0;i<5;++i) {
            const int age=std::clamp(int(tick%120)-12*int(4-i),0,59);
            int x=0,stripAlpha=128;
            if(entering||leaving) {
                const auto t=ScalarFloat::integer(age).mul(one.div(ScalarFloat::integer(59)));
                const auto inv=one.sub(t),span=ScalarFloat::integer(i%2?-1280:1280);
                x=entering?span.mul(inv).mul(inv).mul(inv).truncate():
                    span.mul(three).mul(t).mul(t).mul(inv).add(span.mul(t).mul(t).mul(t)).truncate();
                if(leaving)x=-x;
                const auto fade=ScalarFloat::integer(age).mul(ScalarFloat{0x40088888});
                stripAlpha=(leaving?ScalarFloat::integer(128).sub(fade):fade).truncate();
            }
            layout.rows[layout.count++]={i,40+x,96+72*int(i),255,255,stripAlpha};
        }
    } else if(phase==10) {
        const int elapsed=int(tick)-72*(19-int(firstRow));
        const int scroll=std::min(elapsed,72);
        const int brightness=elapsed>=300?std::clamp(1455-4*elapsed,0,255):255;
        for(unsigned i=0;i<6&&firstRow+i<20;++i) {
            const int alpha=i==0?(scroll-50)*11:i==5?255-scroll*11:255;
            layout.rows[layout.count++]={firstRow+i,13,24+scroll+72*int(i),
                                        std::clamp(alpha,0,255),brightness,0};
        }
    }
    return layout;
}

RankingDestination ConsoleAttractRanking::tick(bool startPressed,bool& alternateDemo,bool overseas) {
    draw=next_;
    // Input queues a transition before priority 20 draws. Priority 60 only
    // destroys this task at the opaque midpoint, so its animation keeps time.
    if(startPressed)destination_=RankingDestination::Title;
    auto nextPhase=[&](unsigned age=0){++next_.phase;next_.tick=age;};
    switch(draw.phase) {
    case 0:nextPhase();break;
    case 1:case 2:case 3:case 4:case 5:case 8:case 9: {
        constexpr unsigned duration[]={0,540,60,360,60,360,0,0,240,60};
        if(++next_.tick==duration[draw.phase])nextPhase();
        break;
    }
    case 6:
        // On the opaque frame the original destroys the demo battle. Its
        // trailing increment runs after 1e9758 clears the new phase's clock.
        if(draw.tick*4>=255)nextPhase(1);else ++next_.tick;
        break;
    case 7:nextPhase();break;
    case 10: {
        if(draw.tick==0)draw.firstRow=next_.firstRow=19;
        const unsigned localTick=draw.tick-(19-draw.firstRow)*72;
        if(localTick>=72 && next_.firstRow) --next_.firstRow;
        if(localTick>=360)nextPhase(1);else ++next_.tick;
        break;
    }
    case 11:
        // 1ccea0 alternates the two successor demos in the Japanese profile.
        // The session retains that bit across ranking tasks.
        // 1b9dd0 suppresses the automatic successor if START has already
        // requested the title, including on this same update.
        if(destination_==RankingDestination::None) {
            alternateDemo=overseas?false:!alternateDemo;
            destination_=alternateDemo?RankingDestination::DemoNG:RankingDestination::DemoSG;
        }
        nextPhase();
        break;
    }
    return destination_;
}
}
