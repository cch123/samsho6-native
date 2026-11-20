#include "cpu_input.hpp"

namespace ss6 {
void publishCpuCommand(const CpuCommand& command,bool facingLeft,ActorCommandInput& input) {
    input.clearPublished();
    auto feature=[&](unsigned offset)->uint32_t& {return input.sampledFeatures[offset/4];};
    const auto bit=[&](unsigned n){return (command.mask>>n)&1u;};
    // Both override masks return before any buttons or command slots can be
    // published. They set one exact diagonal without expanding it.
    if(bit(24)){feature(0xd4)=1;return;}
    if(bit(23)){feature(0xd8)=1;return;}

    bool neutral=true;
    for(unsigned i=0;i<9;++i)if(bit(i)){feature(0xc4+4*i)=1;neutral=false;}
    for(unsigned i=0;i<8;++i)if(bit(15+i)){feature(0x14c+4*i)=1;neutral=false;}
    const std::array<bool,4> directions={
        bool(feature(0xe4)||feature(0xc8)||feature(0xcc)),
        bool(feature(0xcc)||feature(0xd0)||feature(0xd4)),
        bool(feature(0xd4)||feature(0xd8)||feature(0xdc)),
        bool(feature(0xdc)||feature(0xe0)||feature(0xe4))
    };
    for(unsigned i=0;i<4;++i) {
        feature(0xe8+4*i)=feature(0xf8+4*i)=directions[i];
        feature(0x184+4*i)=!directions[i];
    }
    constexpr std::array<unsigned,8> mirror={4,3,2,1,0,7,6,5};
    for(unsigned i=0;i<8;++i) {
        auto& absolute=feature(0x14c+4*i);
        if(!absolute)absolute=feature(0xc8+4*(facingLeft?mirror[i]:i));
    }
    if(neutral)feature(0xc4)=1;
    for(unsigned i=0;i<6;++i) {
        if(bit(9+i))feature(4*i)=feature(0x18+4*i)=feature(0x16c+4*i)=1;
        else feature(0x48+4*i)=1;
    }
    feature(0xb4)=feature(0x18)||feature(0x1c)||feature(0x20);
    if(command.slot>=31)input.special.at(command.slot-31).recognized=1;
    else if(command.slot!=-1)input.normal.at(command.slot).recognized=1;
    constexpr std::array<unsigned,4> extraSlots={6,7,8,18};
    for(unsigned i=0;i<extraSlots.size();++i)if(bit(25+i))input.special[extraSlots[i]].recognized=1;
    if(bit(29))feature(0x60)=1;
    // This suppresses direction edges, while held and inverted direction
    // predicates keep the values produced above (15dd54..15dd64).
    if(bit(30))for(unsigned i=0;i<4;++i)feature(0xe8+4*i)=0;
}
}
