#include "poppy.hpp"
#include "state_entry.hpp"
#include "command_input.hpp"
#include "stage_camera.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
F X(const AuxiliaryObject& o){return F{o[0x40/4]};}
F Y(const AuxiliaryObject& o){return F{o[0x44/4]};}
bool mirrored(const AuxiliaryObject& o){return o[0x38/4]&mirror;}
int32_t& state128(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x128/4]);}
int32_t& state12c(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x12c/4]);}
bool ended(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
F f32(float v){return F{std::bit_cast<uint32_t>(v)};}
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& b){o[0x38/4]=(o[0x38/4]&~mirror)|(b[0x38/4]&mirror);} //11dbb8
// 1f0e80 / 1f0000: the follow point 68 behind the owner.
F followPoint(const AuxiliaryObject& body){return mirrored(body)?X(body).sub(f32(-68.0f)):X(body).add(f32(-68.0f));}
bool besideOwner(AuxiliaryObject& o,const AuxiliaryObject& body) { // 1f0e80
    if(state128(o)>=11)return false;
    const F f=followPoint(body).sub(X(o));
    return f.less(F::integer(32))&&F::integer(-32).less(f);
}
bool suspended(AuxiliaryObject& o) { // 1f0e30
    if(state128(o)==state12c(o)&&state128(o)>=6)return false;
    if(F{0}.less(Y(o)))return true;
    o[0x44/4]=0;o[0x104/4]&=~0x100u;return false;
}
int followDistance(AuxiliaryObject& o,const AuxiliaryObject& body) { // 1f0000
    const int s=state128(o);
    const F t=followPoint(body);
    F f=t.sub(X(o));
    F a=f;a.bits&=0x7fffffff;
    if(s<7) {
        if(!F::integer(12).less(a)){f=F{0};copyFacing(o,body);}
        else if(F::integer(64).less(a)&&s!=2&&s!=4) {
            if(X(o).less(t))o[0x38/4]&=~mirror;
            else if(t.less(X(o)))o[0x38/4]|=mirror;
        }
    }
    if(mirrored(o))f.bits^=0x80000000u;
    return f.truncate();
}
} // namespace

void dropBesideOpponent(AuxiliaryObject& o,const AuxiliaryObject& opp,int v) { // 1efc98
    AuxiliaryObjects::stop(o);
    o[0x50/4]=0;o[0x54/4]=0;
    o[0x44/4]=std::bit_cast<uint32_t>(300.0f);
    o[0x5c/4]=0xffff0000u;o[0x60/4]=0xffff6000u;
    const F ox=X(opp),d=F::integer(20);
    if(v==0||v==2)o[0x40/4]=(mirrored(o)?ox.add(d):ox.sub(d)).bits;
    else{o[0x40/4]=(mirrored(o)?ox.sub(d):ox.add(d)).bits;o[0x38/4]^=mirror;} //11db88
}

uint32_t spawnPoppy(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                    unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x1efe78);
    if(!handle)throw std::runtime_error("Missing Poppy object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=(mirrored(body)?X(body).add(F::integer(68)):X(body).sub(F::integer(68))).bits;
    o[0x44/4]=0;
    objects.request(o,0x301,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000; // 1a3220's shared tail
    return handle;
}

void updatePoppy(AuxiliaryObjects& objects,TaggedTaskPools& pools,AuxiliaryObject& o,const PoppyWorld& w) {
    const auto& body=w.body;const auto& owner=w.owner;
    const auto R=[&](unsigned act){objects.request(o,act,false,false);};
    const auto S=[&]{AuxiliaryObjects::stop(o);};
    const bool same=mirrored(o)?mirrored(body):!mirrored(body);
    if(suspended(o))return;
    if(state128(o)==state12c(o)&&state128(o)<6&&besideOwner(o,body)) {
        const int idx=owner.stateIndex();const uint32_t f=owner.flags23c;
        if(f&4){if(idx>=0x20)state128(o)=6;}
        else if((f&1)&&same&&!(unsigned(idx-0x49)<4)) {
            if(owner.state194==0x00160001)state128(o)=9;
            else if(!(f&8))state128(o)=7;
            else state128(o)=8;
        }
    }
    // 1f0138: state entry.
    bool entered=false;
    {
        int next=state128(o);const int cur=state12c(o);
        const int w40=owner.stateIndex()-0x40;
        const bool hp100=owner.fieldA30>=100,armed=owner.flags23c&0x1000;
        if(next!=cur) {
            o[0x104/4]&=~(0x400000u|2u);
            const auto effect=[&]{ // 16c408(cb(owner), 0x317, 0, 0) at Poppy's position
                const auto h=objects.create(pools,w.ownerRegistry,w.ownerSeat,owner.flags23c,body,0x1396,6,0);
                if(!h)throw std::runtime_error("Original 16c408 writes through a null object");
                auto& e=pools.objects.at(h-1);objects.request(e,0x317,false,true);e[0x108/4]|=0x2000;
                e[0x40/4]=o[0x40/4];e[0x44/4]=o[0x44/4];
            };
            if(unsigned(next)<0x35)switch(next) {
            case 0:S();R(0x301);break;
            case 1:R(0x302);break;case 2:R(0x303);break;case 3:R(0x304);break;
            case 4:objects.request(o,0x305,false,true);break;
            case 5:S();R(0x30c);break;case 6:S();R(0x308);break;case 7:S();R(0x307);break;case 8:S();R(0x309);break;
            case 9:S();o[0x134/4]=0;R(0x301);break;
            case 10: {
                if(!w.ownerInput)throw std::runtime_error("Poppy state 10 reads the owner's buttons");
                const auto& in=w.ownerInput->sampledFeatures;
                R(in[96]?0x34e:in[91]?0x34a:in[92]?0x34b:in[93]?0x34c:in[94]?0x34d:in[95]?0x34f:0x307);
                break;
            }
            case 11:S();R(0x30a);break;case 12:S();R(0x30b);break;
            case 13:case 17:copyFacing(o,body);R(0x30e);break;
            case 14:if(w40>=0x12)o[0xfc/4]|=1u<<16;R(0x30f);break; // body+fe halfword |= 1
            case 15:S();R(0x310);break;case 16:S();R(0x311);break;
            case 18:if(w40>=0x12)o[0xfc/4]|=1u<<16;R(0x312);break;
            case 19:S();R(0x313);break;case 20:S();R(0x314);break;case 21:S();R(0x315);break;
            case 22:case 29:S();copyFacing(o,body);R(0x316);break;
            case 23:case 30:R(0x331);break;
            case 24:
                o[0x40/4]=(mirrored(o)?X(body).sub(F::integer(48)):X(body).add(F::integer(48))).bits;
                o[0x44/4]=Y(body).sub(F::integer(8)).bits;
                R(0x318);effect();break;
            case 31:R(0x31c);dropBesideOpponent(o,w.opponentBody,1);effect();break;
            case 25:case 28:R(0x319);break;case 26:R(0x31a);break;case 27:S();R(0x31b);break;
            case 32:S();R(0x31d);break;case 33:S();R(0x31e);break;case 34:S();R(0x32a);break;
            case 35:S();R(0x32b);break;case 36:S();R(0x32c);break;
            case 37:R(0x316);break;
            case 38: {
                const int32_t k=(std::bit_cast<int32_t>(o[0x130/4])+1)%2;
                copyFacing(o,body);dropBesideOpponent(o,w.opponentBody,k);S();R(0x326);break; // 1efc70 = 1efc98 + 11d990
            }
            case 39:S();R(0x327);break;
            case 40:case 44:S();R(0x30e);break;
            case 41:R(0x31f);break;case 42:S();R(0x320);break;case 43:S();R(0x321);break;
            case 45:S();R(0x322);break;
            case 46:R(0x33b);break; // 11dbb8(o, o): a self-copy
            case 47:
                if(w.ownerWon) {
                    if(hp100&&!armed){S();R(0x33e);break;}
                } else if(hp100){S();R(armed?0x33c:0x33d);break;}
                o[0x108/4]|=0x100000;next=cur; // ready: the commit writes the old state back
                break;
            case 48:S();R(0x340);break;
            case 49:S();R(w.opponentWon?0x343:0x342);break;
            case 50:S();R(0x341);break;
            case 51:
                S();o[0x40/4]=(mirrored(body)?X(body).add(F::integer(42)):X(body).sub(F::integer(42))).bits;
                o[0x44/4]=0;copyFacing(o,body);o[0x104/4]|=0x400002;break;
            case 52:break;
            }
            state12c(o)=next;state128(o)=next;entered=true;
        }
    }
    if(!entered) {
        const int d=followDistance(o,body);
        // 1f07b8: state update.
        bool done=false;
        const auto to=[&](int n){state128(o)=n;};
        const auto& cam=w.camera;
        const uint32_t f=o[0x104/4];
        switch(state128(o)) {
        case 0:if(d!=0)done=true;break;
        case 1:case 2:done=true;break;
        case 9: {
            const int32_t t=std::bit_cast<int32_t>(o[0x134/4])+std::bit_cast<int32_t>(o[0x30/4]);
            o[0x134/4]=uint32_t(t);
            if(((t<0?t+255:t)>>8)>=30)to(10);
            break;
        }
        case 10:case 27:case 28:o[0x104/4]=f&~0x100u;if(o[0xc0/4]&&!(f&1))done=true;break;
        case 11:
            if((f&0x100)&&!F{0}.less(Y(o))){o[0x44/4]=0;o[0x104/4]=f&~0x100u;}
            else if(o[0xc0/4]&&!(f&1)&&!F{0}.less(Y(o))){o[0x44/4]=0;to(12);}
            break;
        case 13:if(ended(o))to(14);break;
        case 14:
            if(o[0x100/4]&2)to(11);else if(f&0xc0000)to(16);else if(f&0x200000)to(15);else if(ended(o))to(15);
            break;
        case 16:if(ended(o))to(4);break;
        case 17:if(ended(o))to(18);break;
        case 18:
            if(o[0x100/4]&2)to(11);else if(f&0x40000)to(20);else if(f&0x80000)to(21);
            else if(f&0x200000)to(19);else if(ended(o))to(19);
            break;
        case 22:if(owner.stateTable()!=1)to(28);else if(ended(o))to(23);break;
        case 23:if(owner.stateTable()!=1)to(28);break;
        case 24: {
            if(Y(o).less(F{0})){to(25);break;}
            const int x=F{o[0x40/4]}.truncate();const bool right=!mirrored(o);
            if(right?!(x<cam.right-0x30):!(cam.left+0x30<x))to(26); // 146a50(cam, x, 0x30, !mirror, 1)
            break;
        }
        case 25:case 26:
            if(Y(o).less(F{0})){to(27);break;}
            if(F::integer(int32_t(cam.top)).less(Y(o))){o[0x60/4]=0;o[0x5c/4]=uint32_t(-std::bit_cast<int32_t>(o[0x5c/4]));}
            if(X(o).less(F::integer(int32_t(cam.left)))||F::integer(int32_t(cam.right)).less(X(o)))
                {o[0x54/4]=0;o[0x50/4]=uint32_t(-std::bit_cast<int32_t>(o[0x50/4]));}
            break;
        case 29:if(ended(o))to(30);break;
        case 30:if(ended(o))to(31);break;
        case 31:if(f&0x2c0000)to(32);else if(Y(o).less(F{0}))to(33);break;
        case 32:if(Y(o).less(F{0}))to(33);break;
        case 34:if(f&0x280000)to(36);else if(ended(o))to(35);break;
        case 37:if(ended(o))to(38);break;
        case 38:if(Y(o).less(F{0}))to(39);break;
        case 40:if(ended(o))to(41);break;
        case 41:if(f&0x2c0000)to(42);else if(ended(o)&&!F{0}.less(Y(o)))to(43);break;
        case 42:if(ended(o)&&!F{0}.less(Y(o)))to(43);break;
        case 44:if(ended(o))to(45);break;
        case 46:if(ended(o)){done=true;o[0x108/4]|=0x100000;}break;
        case 47:case 48:case 49:case 50:
            o[0x104/4]=f&~0x100u;if(o[0xc0/4]&&!(f&1))o[0x108/4]|=0x100000;
            break;
        case 51:
            if(owner.state194==0x00300000)o[0x104/4]|=2;
            else{done=true;objects.request(o,0x301,true,true);}
            break;
        case 52:if(o[0xc0/4])done=!(o[0x104/4]&1);break;
        case 3:case 4:case 5:case 6:case 7:case 8:case 12:case 15:case 19:case 20:case 21:
        case 33:case 35:case 36:case 39:case 43:case 45:
            if(ended(o))done=true;break;
        default:break;
        }
        if(done) {
            const F fd=F::integer(d);
            if(F::integer(100).less(fd)){state12c(o)=-1;state128(o)=3;}
            else if(fd.less(F::integer(-100))){state12c(o)=-1;state128(o)=4;}
            else if(F::integer(12).less(fd))state128(o)=1;
            else if(fd.less(F::integer(-12)))state128(o)=2;
            else state128(o)=0;
        }
    }
    // 1a3ba8(o, -6.0): o.ec = 0, o.f0 = -6.0, o.b4 = -6.0 + 1.0.
    o[0xec/4]=0;o[0xf0/4]=std::bit_cast<uint32_t>(-6.0f);o[0xb4/4]=std::bit_cast<uint32_t>(-5.0f);
}
}
