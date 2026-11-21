#include "combat_stage_11.hpp"
#include "game_random.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"

namespace ss6 {
namespace {
using namespace stage_draw;
constexpr float amplitudes[5]{5,10,15,20,25};      // 5733e8
constexpr int32_t phaseSteps[5]{64,72,80,88,96};   // 573400
constexpr int32_t fadeSteps[5]{64,72,80,88,96};    // 573418
// 1b3e68 and its siblings: one of five entries from the libc generator.
unsigned pick(GameRandom& random) {return ((random.nextLibrary()&0x7fff)*5)>>15;}
}

void CombatStage11State::reload(const CombatStage11State&) {
    // No initializer is guarded by 5733e4: 1b3e20 clears all seven objects
    // on every constructor run and 1b3ee0 rebuilds their piece tables.
    objects={};
    initialized=false;
}

// 1b3e20
void CombatStage11State::initialize(GameRandom& random) {
    objects={};
    for(auto& o:objects) {
        o.fadeStep=fadeSteps[pick(random)];
        o.phaseStep=phaseSteps[pick(random)];
    }
    initialized=true;
}

// The seven 1b3fb0 calls of one task visit. Only the picture clock follows
// 46a908; the bob and the fade advance once per visit, hidden or not.
void CombatStage11State::visit(uint32_t delta,GameRandom& random) {
    if(!initialized)initialize(random);
    for(auto& o:objects) {
        o.drawnAmplitude=o.amplitude;
        o.drawnPhase=o.phase;
        o.phase+=o.phaseStep;
        if(o.phase&0x10000) {
            o.phase&=0xffff;
            o.amplitude=std::bit_cast<uint32_t>(amplitudes[pick(random)]);
            o.phaseStep=phaseSteps[pick(random)];
        }
        // The picture is taken before the step and the clock is reduced by
        // 0x2400 at most once, so a step above 0x2400 selects entries 3..9,
        // which 1b3ee0 leaves empty (nothing is drawn).
        o.picture=o.pictureClock/0xc00;
        o.pictureClock=std::bit_cast<int32_t>(uint32_t(o.pictureClock)+delta);
        if(o.pictureClock>=0x2400)o.pictureClock-=0x2400;
        o.drawnFade=o.fade;
        o.fade+=o.fadeStep;
        if(o.fade>0x6500) {
            o.fade=0x1500;
            o.fadeStep=fadeSteps[pick(random)];
        }
    }
}

void drawCombatStage11(Projector& r,const StageCommandGroups& groups,const CombatStage11State& state,const AngleTrig& trig) {
    r.mode=0;
    r.color=0xffffffff;
    {
        // 1b3c08..1b3d18: atlas rectangle 572950 {0,0,1024,599} of slot 4,
        // anchored at world Z 700 and queued at Z 30000.
        const F center=scalar(320),width=scalar(1024),height=scalar(599);
        const F left=center.sub(width.mul(scalar(.25f))).sub(center).mul(scalar(2.749999761581421f)).add(center);
        const F scale=r.projection.scale(700);
        const F x=r.projection.point(left,scalar(0),scale)[0];
        const F stretchX=scale.div(scalar(0.3636363446712494f));
        const F y=r.projection.point(scalar(0),scalar(38),scale)[1];
        const F stretchY=scale.div(scalar(0.3636363446712494f)).mul(scalar(1.2000000476837158f));
        const F tall=height.mul(stretchY);
        r.rectangle(4,30000,x,y.sub(tall),width.mul(stretchX),tall,scalar(0),scalar(0),width,height);
    }
    const auto& prefix=groups[0].front();
    r.run(std::span(prefix).first(1));    // 1a5868: floor mesh 50e110 built by 1b39a8
    r.mode=1;
    r.run(std::span(prefix).subspan(1));  // 1a6210: 15 pieces at 5731d8
    for(unsigned n=0;n<CombatStage11State::objectCount;++n) {
        const auto& o=state.objects[n];
        // Entries past the three pictures have a zero piece count; beyond
        // entry 9 the original reads neighbouring object fields (not modeled).
        if(o.picture<0||o.picture>=int(groups[1+n].size()))continue;
        StageCommand cmd=groups[1+n][o.picture].front();
        // 1b3fd4..1b4014: x = home x + 0, y = home y + amplitude * sine.
        const F bob=F{o.drawnAmplitude}.mul(F{trig.sine(uint32_t(o.drawnPhase))});
        cmd.parameters[0]=number(scalar(cmd.parameters[0]).add(scalar(0)));
        cmd.parameters[1]=number(scalar(cmd.parameters[1]).add(bob));
        // 1b40b0..1b40e8: alpha = trunc(sine(fade) * 255) in the vertex color.
        const uint32_t alpha=uint32_t(F{trig.sine(uint32_t(o.drawnFade))}.mul(scalar(255)).truncate());
        r.color=alpha<<24|0xffffff;
        r.sprites(cmd);
    }
    r.color=0xffffffff;
}
}
