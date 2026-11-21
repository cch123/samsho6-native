#include "combat_stage_09.hpp"
#include "game_random.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
using R=StageClockRecord;
// 8.8 durations after the once-only 1a7350(56fec0, 1) scaling pass.
constexpr R rowTimeline[]{{0,3072},{1,3072},{2,3072},{3,3072}};           // 56fe38
constexpr R objectTimeline[]{{0,3072},{1,3072},{2,3072},{1,3072},{0,3072}}; // 56fe60
constexpr unsigned animatedRow=2;

// 1b18ec / 1b1a28 / 1b1b18: the three copies of the object clock. Unlike the
// row prologue, the end of the table is re-evaluated in the same visit, and
// only the first object (state 132ae44) keeps its remainder and draws the
// library RNG: three times in five it repeats the last record.
void advanceObject(StageClock& clock,bool first,uint32_t delta,GameRandom& random) {
    const int size=int(std::size(objectTimeline));
    for(;;) {
        const int32_t duration=objectTimeline[clock.step].duration;
        if(clock.elapsed<duration) {
            clock.picture=unsigned(objectTimeline[clock.step].picture);
            break;
        }
        clock.elapsed-=duration;
        if(int(++clock.step)<size) {
            clock.picture=unsigned(objectTimeline[clock.step].picture);
            break;
        }
        if(first) {
            const int choice=int(((random.nextLibrary()&0x7fff)*5)>>15);
            if(choice<3)--clock.step;
            else clock.step=0;
        } else {
            clock.step=0;
            clock.elapsed=0;
        }
    }
    clock.elapsed=std::bit_cast<int32_t>(uint32_t(clock.elapsed)+delta);
}
}

void CombatStage09State::reload(const CombatStage09State& previous) {
    // 570388 guards 1b13b8 (row clock); 1b1428 runs 1a7290 on the object
    // states on every load.
    row=previous.row;
    rowPicture=previous.rowPicture;
    objects={};
    objectPictures={};
}

void CombatStage09State::visit(uint32_t delta,GameRandom& random) {
    // Every clock advances on a hidden visit too: only the drawing helpers
    // test 50e04c.
    advanceStageClock(row,rowTimeline,delta);
    rowPicture=row.picture;
    for(unsigned n=0;n<objects.size();++n) {
        advanceObject(objects[n],n==0,delta,random);
        objectPictures[n]=objects[n].picture;
    }
}

void drawCombatStage09(Projector& r,const StageCommandGroups& groups,const CombatStage09State& state,const AngleTrig&) {
    r.mode=0;
    {
        // 1b1788..1b17e4: 123020(0, 0, 10000) gives the horizon line; 113be0
        // fills the screen above it from texture rows that end at 394. The
        // strip's depth key is the bare order number (114d78), not 114d88.
        const F y=r.projection.point(scalar(0),scalar(0),r.projection.scale(10000))[1];
        const F x=scalar(0),top=scalar(0),w=scalar(640);
        const F x1=x.add(w),y1=top.add(y);
        const auto below=[](F a,F b){return number(a)<0&&number(b)<0;};
        const auto above=[](F a,F b,float bound){return number(a)>bound&&number(b)>bound;};
        if(!(below(x,x1)||above(x,x1,640)||below(top,y1)||above(top,y1,480))) { // 114e98
            const float key=number(F::integer(int(r.counter)));
            ++r.counter;
            const F texel=scalar(1.f/1024.f);
            const F u=scalar(0).mul(texel),v=scalar(394).sub(y).mul(texel);
            const F u1=u.add(w.mul(texel)),v1=v.add(y.mul(texel));
            CombatStageStrip strip{5,0xffffffff,key,{},0};
            strip.vertices={{number(x),number(top),number(u),number(v)},{number(x),number(y1),number(u),number(v1)},
                            {number(x1),number(top),number(u1),number(v)},{number(x1),number(y1),number(u1),number(v1)}};
            r.strips.push_back(std::move(strip));
        }
    }
    r.run(groups[0].front()); // 1a5868(5, 32, 4): the floor, still alpha mode 0
    r.mode=1;
    // 1b1e58(0, 8), the two 1a4e80/1a4ee0 pieces (exported behind row 7) and
    // 1b1e58(8, 16).
    for(unsigned row=0;row<CombatStage09State::rowCount;++row)
        r.run(groups[1+row].at(row==animatedRow?state.rowPicture:0));
    // Shadow + sprite per object; the suffix has one variant per picture.
    const auto& tail=groups[1+CombatStage09State::rowCount];
    for(unsigned n=0;n<3;++n)
        r.run(std::span(tail.at(state.objectPictures[n])).subspan(2*n,2));
}
}
