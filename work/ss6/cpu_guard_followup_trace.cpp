#include "native_match.hpp"
#include <bit>
#include <iostream>

using namespace ss6;

static void snapshot(const NativeMatch& match) {
    const auto& pools=match.battle().entry.tasks;
    for(unsigned side=0;side<2;++side) {
        const auto& f=match.fighter(side);
        const auto& a=f.actor;
        const auto& c=f.body.timeline.clock();
        const auto& input=f.input.sampledFeatures;
        std::cout<<"fighter "<<side<<' '<<a.character<<' '<<f.config.system<<' '
                 <<a.stateTable()<<' '<<a.stateIndex()<<' '<<unsigned(a.effectiveFlags())<<' '
                 <<a.flags23c<<' '<<a.flags244<<' '<<a.timers[6]<<' '<<a.controlKindA20<<' '
                 <<a.controlModeC8<<' '<<input[0xfc/4]<<' '<<input[0xd8/4]<<' '<<input[0xd4/4]<<' '
                 <<a.fieldA30<<' '<<f.hits<<' '<<f.guards<<' '<<a.rageState120<<' '<<a.rageAmount124
                 <<' '<<a.swordCurrent134<<' '<<a.swordMaximum138<<' '<<a.flags248<<'\n';
        std::cout<<"object "<<side<<' '<<side<<' '<<side<<' '<<a.character<<' '<<a.character<<" -1 "
                 <<f.body.timeline.action().id()<<' '<<c.step<<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108
                 <<' '<<std::bit_cast<uint32_t>(f.body.timeline.motion().x)
                 <<' '<<std::bit_cast<uint32_t>(f.body.timeline.motion().y)<<'\n';
        for(unsigned kind:{2u,3u,5u,9u})for(auto task:f.storage.objectTasks)if(task) {
            const auto& obj=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            if(obj[0xcc/4]!=kind)continue;
            std::cout<<"object "<<kind;
            for(unsigned off:{0xcu,0x10u,0x14u,0x18u,0xd0u,0x24u,0x28u,0x38u,0x104u,0x108u,0x40u,0x44u})
                std::cout<<' '<<obj[off/4];
            std::cout<<'\n';
        }
    }
}

// Repeat genuine human motions against the independently running CPU. Both-CPU
// cases feed neutral pads and leave all decisions to the two tactical banks.
static uint32_t playerPad(unsigned side,unsigned tick,unsigned pattern) {
    const unsigned forward=side?PadLeft:PadRight,back=forward^(PadLeft|PadRight);
    const unsigned phase=tick%60;
    if(phase<15)return forward;
    if(phase==15)return PadDown;
    if(phase==16)return PadDown|forward;
    if(phase==17)return forward|(PadLight<<(pattern%3));
    if(phase>=35&&phase<54)return PadDown|back;
    if(phase==55)return PadKick|(pattern%2?PadDown:0);
    return 0;
}

int main(int argc,char** argv) {
    if(argc!=2)return 1;
    unsigned left,right,spirit0,spirit1,mask,pattern,tick;
    while(std::cin>>left>>right>>spirit0>>spirit1>>mask>>pattern>>tick) {
        VersusLineup lineup{{{left,spirit0,0},{right,spirit1,1}}};
        NativeMatch m(argv[1],60,VersusMode::Console,nullptr,{},lineup);
        for(unsigned seat=0;seat<2;++seat)if(mask&(1u<<seat))m.enableCpu(seat);
        std::array<uint32_t,2> previous{};
        for(unsigned k=0;k<tick;++k) {
            if(m.finished)return 2;
            std::array<NormalizedPadSample,2> pads{};
            for(unsigned seat=0;seat<2;++seat)if(!(mask&(1u<<seat))) {
                const auto key=playerPad(seat,k,pattern);
                pads[seat]={key,key&~previous[seat]};previous[seat]=key;
            }
            if(k+1==tick)snapshot(m);
            m.tick(pads);
        }
        for(unsigned seat=0;seat<2;++seat) {
            const auto& f=m.fighter(seat);
            std::cout<<"after "<<seat<<' '<<f.actor.fieldA30<<' '<<f.hits<<' '<<f.guards<<' '
                     <<f.actor.stateTable()<<' '<<f.actor.stateIndex()<<' '<<f.body.timeline.action().id()<<' '
                     <<f.actor.timerDelta<<' '<<f.actor.timers[0]<<' '<<f.actor.timers[1]<<' '<<f.actor.timers[32]<<'\n';
        }
        std::cout<<"end\n";
    }
}

