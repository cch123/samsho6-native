#include "input_features.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
using Buttons=std::array<uint32_t,13>;
Buttons decode(uint32_t bits,const std::array<uint32_t,8>& mapping) {
    Buttons b{};
    for(unsigned i=0;i<4;++i)b[i]=(bits>>(i+4))&1;
    for(unsigned i=0;i<5;++i)b[i+4]=(bits&mapping[i])!=0;
    b[9]=(bits>>3)&1;
    for(unsigned i=5;i<8;++i)b[i+5]=(bits&mapping[i])!=0;
    return b;
}
uint16_t pack(const Buttons& b) {
    uint16_t bits=0;
    for(unsigned i=0;i<b.size();++i)bits|=uint16_t(b[i]<<i);
    return bits;
}
void diagonals(InputFeatures& f,unsigned first) {
    const unsigned i=first/4;
    for(unsigned d=1;d<8;d+=2)f[i+d]=0;
    //177908 resolves only the first matching pair. Opposite directions are
    //not neutralized: changing this would alter keyboard/recorded inputs.
    for(unsigned d=0;d<8;d+=2) {
        const auto next=(d+2)%8;
        if(f[i+d]&&f[i+next]){f[i+d]=f[i+next]=0;f[i+d+1]=1;break;}
    }
}
}
void InputSampler::sampleRaw(unsigned player,const NormalizedPadSample& pad,const InputMapping& mapping,const InputSamplingContext& c) {
    if(player>=pressLatches.size())throw std::runtime_error("Invalid input player");
    Buttons held{},pressed{};
    const bool validIndex=uint32_t(c.replayIndex)<replayHeld.size();
    if(c.playback) {
        //The unsigned bounds check also rejects negative replay positions.
        //Out-of-range playback supplies neutral input without erasing data.
        if(validIndex)for(unsigned i=0;i<13;++i) {
            held[i]=(replayHeld[c.replayIndex]>>i)&1;
            pressed[i]=(replayPressed[c.replayIndex]>>i)&1;
        }
    } else {
        const auto& masks=c.gameMode==6?mapping.mode6:mapping.normal;
        held=decode(pad.held,masks);pressed=decode(pad.pressed,masks);
        if(validIndex){replayHeld[c.replayIndex]=pack(held);replayPressed[c.replayIndex]=pack(pressed);}
    }
    const bool firstSwap=c.facing!=c.reverseDirections,secondSwap=c.actualFacing!=c.reverseDirections;
    auto f=[&](unsigned offset)->uint32_t& {return features[offset/4];};
    f(0xf0)=pressed[firstSwap?3:2];f(0xe8)=pressed[firstSwap?2:3];
    f(0x134)=pressed[secondSwap?3:2];f(0x12c)=pressed[secondSwap?2:3];
    for(auto o:{0xd0,0xfc,0x114,0x140,0x154})f(o)=held[c.reverseDirections?0:1];
    for(auto o:{0xe0,0x104,0x124,0x148,0x164})f(o)=held[c.reverseDirections?1:0];
    f(0x100)=f(0xd8)=held[firstSwap?3:2];
    f(0xf8)=f(0xc8)=held[firstSwap?2:3];
    f(0x144)=f(0x11c)=held[secondSwap?3:2];
    f(0x13c)=f(0x10c)=held[secondSwap?2:3];
    f(0xf4)=f(0x138)=pressed[c.reverseDirections?1:0];
    f(0xec)=f(0x130)=pressed[c.reverseDirections?0:1];
    f(0x15c)=held[c.reverseDirections?3:2];f(0x14c)=held[c.reverseDirections?2:3];
    for(unsigned i=0;i<6;++i) {
        f(0x16c+4*i)=held[4+i];f(4*i)=f(0x18+4*i)=pressed[4+i];
    }
    constexpr unsigned chords[3][2]={{1,2},{0,1},{0,3}};
    //Expand configured combination buttons after recording their original
    //13-bit input. Playback must expand them using the same rule.
    for(unsigned i=0;i<3;++i)for(auto b:chords[i]) {
        if(pressed[10+i])f(b*4)=f(0x18+b*4)=1;
        if(held[10+i])f(0x16c+b*4)=1;
    }
}
void InputSampler::advance(unsigned player,const NormalizedPadSample& pad,const InputMapping& mapping,const InputSamplingContext& c) {
    sampleRaw(player,pad,mapping,c);
    auto f=[&](unsigned offset)->uint32_t& {return features[offset/4];};
    for(auto start:{0xc8,0x10c}) {
        f(start-4)=!(f(start)||f(start+8)||f(start+16)||f(start+24));
        diagonals(features,start);
    }
    diagonals(features,0x14c);
    for(unsigned i=0;i<4;++i)f(0x184+4*i)=!f(0xf8+4*i);
    for(unsigned i=0;i<6;++i)f(0x30+4*i)=f(0x18+4*i);
    for(unsigned i=0;i<6;++i) {
        if(f(0x16c+4*i))for(unsigned j=0;j<6;++j)if(i!=j)f(0x30+4*j)=0;
        f(0x48+4*i)=!f(0x16c+4*i);
        auto& latch=pressLatches[player][i];
        if(f(4*i))latch=4;else if(latch)--latch;
        f(4*i)=latch!=0;
    }
    unsigned pair=0;
    for(unsigned i=0;i<5;++i)for(unsigned j=i+1;j<5;++j)f(0x60+4*pair++)=f(i*4)&&f(j*4);
    //The original repeats024 at0x9c; it does NOT test034. Preserve the
    //shipped predicate, including this asymmetry in three-button inputs.
    constexpr unsigned triples[10][3]={{0,1,2},{0,1,3},{0,1,4},{0,2,3},{0,2,4},{0,2,4},{1,2,3},{1,2,4},{1,3,4},{2,3,4}};
    for(unsigned i=0;i<10;++i)f(0x88+4*i)=f(triples[i][0]*4)&&f(triples[i][1]*4)&&f(triples[i][2]*4);
    f(0xb0)=f(0)&&f(4)&&f(8)&&f(12);
    f(0xb4)=f(0x18)||f(0x1c)||f(0x20);
    f(0xb8)=f(0x16c)||f(0x170)||f(0x174)||f(0x178)||f(0x17c);
    f(0xbc)=!f(0xb8);
    f(0x194)=f(0xc8)||f(0xd8);
    f(0x198)=f(0x150)||f(0x154)||f(0x158)||f(0x15c)||f(0x160)||f(0x164)||f(0x168);
    f(0x19c)=f(0x14c)||f(0x150)||f(0x154)||f(0x158)||f(0x160)||f(0x164)||f(0x168);
    constexpr unsigned directions[]={0xfc,0x100,0xf8,0x104,0xc8,0xcc,0xd0,0xd4,0xd8,0xdc,0xe0,0xe4};
    for(unsigned b=0;b<4;++b)for(unsigned d=0;d<12;++d)f(0x1a0+b*0x30+d*4)=f(directions[d])&&f(0x18+b*4);
    constexpr unsigned fifthDirections[]={0xc4,0xcc,0xd4,0xd0,0xd8,0xc8};
    for(unsigned i=0;i<6;++i)f(0x260+i*4)=f(fifthDirections[i])&&f(0x28);
    f(0x278)=f(0xc8)&&f(0x2c);f(0x27c)=f(0xd8)&&f(0x2c);
    f(0x280)=f(0x194)&&f(0x20)&&!f(0x16c)&&!f(0x170)&&!f(0x178)&&!f(0x17c);
    f(0x284)=f(0x194)&&f(0x24)&&!f(0x16c)&&!f(0x170)&&!f(0x174)&&!f(0x17c);
    constexpr unsigned chordDirections[]={0xc8,0xd8,0xe4,0xcc,0x190};
    for(unsigned i=0;i<5;++i)f(0x288+i*4)=f(chordDirections[i])&&f(0x70);
    f(0x29c)=(f(0xc4)||f(0xc8))&&f(0x70);
    f(0x2a0)=(f(0xc4)||f(0xd4)||f(0xd8))&&f(0x60);
    f(0x2a4)=f(0xd0)&&f(0xb4);f(0x2a8)=f(0xfc)&&f(0xb4);
    //0xc0 is never written by177310/177908. Do not clear the entire feature
    //array here; the original preserves that word across sampling calls.
}
}
