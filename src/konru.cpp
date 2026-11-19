#include "konru.hpp"
#include "companion_motion.hpp"
#include "state_entry.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
F scalar(float x){return {std::bit_cast<uint32_t>(x)};}
F offsetX(const AuxiliaryObject& body,F offset) {
    const F x{body[0x40/4]};
    return body[0x38/4]&mirror?x.sub(offset):x.add(offset);
}
// The original advances the angle by six degrees per visit. These are the
// sixty results of its truncated angle conversion and 10b4f8 sine routine.
constexpr std::array<uint32_t,60> hoverSine{
    0x0,0x3dd605b0,0x3e54d9b1,0x3e9e2dea,0x3ed03f05,0x3efffc5f,
    0x3f16760b,0x3f2b4819,0x3f3e3e2e,0x3f4f1a43,0x3f5db1bf,0x3f69dbbb,
    0x3f73780e,0x3f7a6746,0x3f7e9882,0x3f800000,0x3f7e992a,0x3f7a6894,
    0x3f7379fe,0x3f69de49,0x3f5db4e6,0x3f4f1df5,0x3f3e4264,0x3f2b4cc6,
    0x3f167b20,0x3f0003a1,0x3ed04a83,0x3e9e39dc,0x3e54f246,0x3dd637b6,
    0x38c95110,0xbdd605b4,0xbe54d9af,0xbe9e2de7,0xbed03f07,0xbefffc60,
    0xbf16760a,0xbf2b4817,0xbf3e3e2f,0xbf4f1a43,0xbf5db1bd,0xbf69dbba,
    0xbf73780e,0xbf7a6745,0xbf7e9882,0xbf800000,0xbf7e992a,0xbf7a6895,
    0xbf7379fd,0xbf69de4a,0xbf5db4e4,0xbf4f1df3,0xbf3e4264,0xbf2b4cc5,
    0xbf167b1f,0xbf0003a3,0xbed04a80,0xbe9e39d9,0xbe54f250,0xbdd637aa
};
}
uint32_t spawnKonru(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                    unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x1ee110);
    if(!handle)throw std::runtime_error("Missing Konru object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=offsetX(body,scalar(-100)).bits;
    o[0x44/4]=F{body[0x44/4]}.add(scalar(80)).bits;
    objects.request(o,773,true,false);
    o[0x128/4]=0;
    return handle;
}

void updateKonru(AuxiliaryObjects& objects,AuxiliaryObject& o,const AuxiliaryObject& body,const StateEntryActor& owner,
                 unsigned opponentCharacter,unsigned opponentAction) {
    if(o[0x24/4]!=773||owner.state194==0x300000)return;
    if(o[0x104/4]&2){objects.request(o,773,true,true);o[0x104/4]&=~2u;}
    const unsigned act=body[0x24/4];
    // Armed low-life wins have different pet positions for a round and a set.
    const bool roundWin=act==497, setWin=act==501;
    const F x=offsetX(body,scalar(roundWin?27:setWin?108:-50));
    F y=scalar(roundWin?82:setWin?70:64);
    // 14ac90 anchors the idle spirit at world height while this opponent's
    // capture animation carries the owner. Both victory poses remain body-relative.
    if(roundWin||setWin||opponentCharacter!=33||(opponentAction!=576&&opponentAction!=577))
        y=F{body[0x44/4]}.add(y);
    const F dx=x.sub({o[0x40/4]}),dy=y.sub({o[0x44/4]});
    const auto distance=dx.mul(dx).add(dy.mul(dy)).sqrt();
    if(steerCompanion(o,x,dx,dy,distance,{scalar(0.06f),scalar(30),scalar(0.1f),scalar(65536)}) &&
       (roundWin||setWin)) {
        if(setWin)o[0xfc/4]|=8u<<16;
        o[0x40/4]=body[0x40/4];o[0x44/4]=body[0x44/4];
        o[0x38/4]=(o[0x38/4]&~mirror)|(body[0x38/4]&mirror);
        objects.request(o,roundWin?771:772,false,false);
    }
    auto& angle=o[0x128/4];
    angle=(angle+6)%36000;
    o[0xf0/4]=F{hoverSine[(angle%360)/6]}.mul(scalar(-2)).bits;
}
}

