#include "combat_stage_state.hpp"
#include "game_random.hpp"
#include <bit>
#include <stdexcept>
#include <span>

namespace ss6 {
namespace {
struct Record { unsigned picture; int duration; };
// Whole ticks in the original 8.8 duration tables starting at 512f30.
// Each negative-picture terminator loops to record zero. The 2nd and 7th
// sequences duplicate another layer's timing but use different geometry.
constexpr Record two[]{{0,30},{1,30}};
constexpr Record threeLong[]{{0,60},{1,6},{2,12},{0,12},{1,6},{2,12},{0,36},{1,12},{2,12},{0,12}};
constexpr Record threeShort[]{{0,12},{1,6},{2,12},{0,6},{2,12},{0,24},{1,12},{2,6}};
constexpr Record threeMedium[]{{0,12},{1,6},{2,12},{0,18},{1,6},{2,6},{0,12},{2,12},{0,6}};
constexpr Record four[]{{0,60},{1,6},{2,12},{3,12},{1,6},{2,12},{3,12},{0,36},{1,12},{2,12},{3,12}};
constexpr std::array<std::span<const Record>,7> sequences{two,two,threeLong,threeShort,threeMedium,four,threeShort};
struct Timing01 { int period, cycle, idle; };
constexpr std::array<Timing01,10> timing01{{
    {1024,4096,0}, {1024,3072,0}, {1024,6144,0},
    {3072,12288,7680}, {3072,12288,7680}, {3072,12288,7680}, {3072,12288,7680},
    {3072,12288,7680}, {3072,18432,7680}, {3072,12288,7680}
}};

void advance01(CombatStageLayer01& layer,const Timing01& timing,uint32_t delta,GameRandom& random) {
    const auto next=std::bit_cast<int32_t>(uint32_t(layer.elapsed)+delta);
    if(layer.flags&1) {
        layer.picture=layer.elapsed/timing.period;
        layer.elapsed=next%timing.cycle;
    } else if(layer.flags&2) {
        layer.picture=layer.elapsed/timing.period;
        layer.elapsed=next;
        if(next>=timing.cycle) {
            layer.flags&=~2u;
            layer.elapsed=0;
        }
    } else {
        // 1a86cc draws from the same libc RNG as gameplay. Even a paused
        // frame can roll if the clock is zero. The first picture stays zero
        // on the successful roll and the active branch begins next visit.
        if(layer.elapsed==0) {
            const unsigned choice=((random.nextLibrary()&0x7fff)*10)>>15;
            layer.flags=choice==0 ? 2 : 0;
        }
        layer.picture=0;
        layer.elapsed=next>timing.idle ? 0 : next;
    }
}
}

unsigned CombatStageState::pictureForRow(unsigned row) const {
    if(stage==1) {
        for(unsigned i=0;i<rows01.size();++i)if(rows01[i]==row)return layers01[i].picture;
    } else {
        for(unsigned i=0;i<rows.size();++i)if(rows[i]==row)return layers[i].picture;
    }
    return 0;
}

void CombatStageState::visit(const StageCamera& published,uint32_t delta,bool backdropPreviouslyDrawn,GameRandom* random) {
    // This callback submits its strips before the battle owner moves and
    // republishes the camera. Keeping that projection is observable when
    // one player jumps or the fighters separate near a screen edge.
    camera=published;
    visible=true;
    // 50e04c suppresses every stage-zero strip. The seven picture clocks
    // still advance on this visit, even when no scenery reaches the GPU.
    suppressGeometry=backdropPreviouslyDrawn;
    if(stage>=1&&!random)throw std::logic_error("Stages after 0 require the shared game random generator");
    switch(stage) {
    case 2:stage02.visit(delta,*random);return;
    case 3:stage03.visit(delta,*random);return;
    case 4:stage04.visit(delta,*random);return;
    case 5:stage05.visit(delta,*random);return;
    case 6:stage06.visit(delta,*random);return;
    case 7:stage07.visit(delta,*random);return;
    case 8:stage08.visit(delta,*random);return;
    case 9:stage09.visit(delta,*random);return;
    case 10:stage10.visit(delta,*random);return;
    case 11:stage11.visit(delta,*random);return;
    default:break;
    }
    if(stage==1) {
        if(!random)throw std::logic_error("Stage 1 requires the shared game random generator");
        for(unsigned n=0;n<layers01.size();++n)advance01(layers01[n],timing01[n],delta,*random);
        return;
    }
    for(unsigned n=0;n<layers.size();++n) {
        auto& layer=layers[n];
        const auto sequence=sequences[n];
        const int duration=sequence[layer.step].duration*256;
        // 1a7d60 carries the remainder but takes at most one step per visit.
        // An expired record can therefore still change picture at delta zero.
        if(layer.elapsed>=duration) {
            layer.elapsed-=duration;
            if(++layer.step==sequence.size())layer.step=0;
        }
        layer.picture=sequence[layer.step].picture;
        layer.elapsed=std::bit_cast<int32_t>(uint32_t(layer.elapsed)+delta);
    }
}
void CombatStageState::inheritRematch(const CombatStageState& previous) {
    // The old task is cancelled by tag. 1a77bc skips reinitialization of the
    // process-owned animation descriptors on subsequent loads of stage zero.
    layers=previous.layers;
    // 5152a8 is a separate once flag. Switching away leaves stage 1 in RAM.
    layers01=previous.layers01;
    stage02.reload(previous.stage02);
    stage03.reload(previous.stage03);
    stage04.reload(previous.stage04);
    stage05.reload(previous.stage05);
    stage06.reload(previous.stage06);
    stage07.reload(previous.stage07);
    stage08.reload(previous.stage08);
    stage09.reload(previous.stage09);
    stage10.reload(previous.stage10);
    stage11.reload(previous.stage11);
    visible=false;
    suppressGeometry=false;
}
}
