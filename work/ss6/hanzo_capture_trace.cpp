#include "local_versus.hpp"
#include "nakoruru_capture.hpp"
#include <bit>
#include <iostream>

namespace {
unsigned tick;
void word(auto v) { std::cout << ' ' << uint32_t(v); }
void fighter(ss6::PlayerObject& body,const ss6::StateEntryActor& actor) {
    const auto& clock=body.timeline.clock();
    for(auto n:{actor.state194,actor.flags23c,actor.flags248,uint32_t(actor.queuedActionA3c),
                uint32_t(actor.timerDelta),uint32_t(actor.timers[23]),uint32_t(actor.stateFlags19a)})word(n);
    for(auto n:actor.callbacks260)word(n);
    for(auto n:actor.registry28c)word(n);
    for(auto n:{uint32_t(body.timeline.action().id()),clock.step,clock.endReached,clock.endControl,
                clock.flags104,clock.objectFlags})word(n);
    const auto& m=body.timeline.motion();
    for(float n:{m.x,m.y})word(std::bit_cast<uint32_t>(n));
    for(auto n:{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay})word(n);
}
}
namespace ss6 {
void measuredCapture(PlayerObject&,StateEntryActor&,StateEntryContext&,const GroundStateFrame&);
void updateFighterCapture(PlayerObject& b,StateEntryActor& a,StateEntryContext& ctx,const GroundStateFrame& frame) {
    const bool paired=a.callbacks260[0]==0x165cc0&&a.pendingCharacter254==3;
    auto snapshot=[&] {fighter(b,a);fighter(frame.weaponLock->opponentBody,frame.weaponLock->opponent);};
    if(paired){word(tick);snapshot();}
    measuredCapture(b,a,ctx,frame);
    if(paired){snapshot();std::cout<<'\n';}
}
}
int main(int argc,char** argv) {
    ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,{},true);
    std::array<uint32_t,2> old{},held{};
    for(tick=1;std::cin>>held[0]>>held[1];++tick) {
        std::array<ss6::NormalizedPadSample,2> pads;
        for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~old[i]};
        old=held;session.tick(pads);
    }
}
