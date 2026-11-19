#include "ten_chain.hpp"
#include "knockout.hpp"
#include <array>

namespace ss6 {
namespace {
// Four follow-up state numbers per ACT from the original table at 4e8618.
// Index zero is the opener. Its only outgoing transition is automatic on hit.
constexpr std::array<std::array<int,4>,16> follow{{
    {-1,-1,-1,-1}, {41,44,47,-1}, {42,-1,-1,-1}, {43,50,-1,-1},
    {-1,-1,-1,-1}, {-1,45,-1,-1}, {-1,-1,46,-1}, {-1,-1,-1,-1},
    {-1,-1,48,-1}, {-1,-1,-1,49}, {-1,-1,-1,-1}, {-1,51,-1,-1},
    {-1,-1,52,-1}, {-1,-1,53,-1}, {-1,-1,54,-1}, {-1,-1,-1,-1}
}};
}
void beginTenChain(PlayerObject& body,StateEntryActor& actor,float opponentX) {
    actor.bodyState128=unsigned(actor.stateIndex()-39);
    actor.bodyLatch12c=0;
    actor.opponentX=opponentX;actor.faceOpponent();
    const auto& clock=body.timeline.clock();
    body.timeline.setObjectFlags(actor.bodyFlags38,clock.flags104,clock.flags108);
    actor.queuedActionA3c=242+int(actor.bodyState128);
    actor.flags248&=~0x800u;
    actor.callbacks260[0]=0x16bc68;actor.callbacks260[1]=1;actor.callbacks260[2]=0xffffffff;
}
bool updateTenChain(const PlayerObject& body,StateEntryActor& actor,const ActorCommandInput& input,
                    const InputSystemConfig& config,const StateCallbacks& callbacks) {
    const auto& clock=body.timeline.clock();
    const bool hit=clock.flags104&0x40000;
    const unsigned phase=actor.bodyState128;
    int next=phase==0&&hit?40:-1;
    if(next==-1&&!(clock.flags108&2)) {
        unsigned held=0;
        for(unsigned b=0;b<4;++b)held+=bool(input.sampledFeatures[0x16c/4+b]);
        // 16bc68 demands one held attack button. It then scans all edges
        // in A/B/C/D order and accepts the first valid branch for this ACT.
        if(held==1)for(unsigned b=0;b<4;++b) {
            if(input.sampledFeatures[0x18/4+b])next=follow.at(phase)[b];
            if(next!=-1)break;
        }
    }
    if(hit&&!actor.bodyLatch12c) {
        actor.bodyLatch12c=1;
        if(phase==15)callbacks.addTenChainRage(actor,config);
    }
    if(next<0)return actionEnded(body,actor.queuedActionA3c);
    actor.pendingTable=1;actor.pendingIndex=int16_t(next);actor.request18c=1;
    return false;
}
}
