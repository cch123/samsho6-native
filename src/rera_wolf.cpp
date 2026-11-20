#include "rera_wolf.hpp"
#include "state_entry.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000;
F X(const AuxiliaryObject& o){return F{o[0x40/4]};}
F Y(const AuxiliaryObject& o){return F{o[0x44/4]};}
int32_t& mode128(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x128/4]);}
int32_t& mode12c(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x12c/4]);}
bool clipLive(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& b){o[0x38/4]=(o[0x38/4]&~mirror)|(b[0x38/4]&mirror);} //11dbb8
// The follow point 40 behind the owner: x + (-40.0) facing right, x - (-40.0) facing left.
F followPoint(const AuxiliaryObject& b){const F x=X(b),k{std::bit_cast<uint32_t>(-40.0f)};return (b[0x38/4]&mirror)?x.sub(k):x.add(k);}
}
bool reraWolfBusy(AuxiliaryObject& o) {
    if(mode128(o)==mode12c(o)&&mode128(o)==0x19)return false;
    if(F{0}.less(Y(o)))return true;
    o[0x104/4]&=~0x100u;return false;
}
bool reraWolfNear(AuxiliaryObject& o,const AuxiliaryObject& b) {
    if(mode128(o)>=12)return false;
    if(reraWolfBusy(o))return false;
    const F dx=followPoint(b).sub(X(o));
    return dx.less(F::integer(80))&&F::integer(-80).less(dx);
}
uint32_t spawnReraWolf(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                       unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x1f96a0);
    if(!handle)throw std::runtime_error("Missing Rera wolf object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=((body[0x38/4]&mirror)?X(body).add(F::integer(100)):X(body).sub(F::integer(100))).bits;
    o[0x44/4]=0;
    objects.request(o,0x301,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000; // 1a3220's shared tail
    return handle;
}
void updateReraWolf(AuxiliaryObjects& objects,AuxiliaryObject& o,const ReraWolfWorld& w) {
    const auto& ob=w.body;const auto& owner=w.owner;
    const auto R=[&](unsigned act,bool imm=false,bool force=false){objects.request(o,act,imm,force);};
    const int32_t cur=mode128(o),prev=mode12c(o);
    if(reraWolfBusy(o))return;
    if(cur==prev&&prev<0xb) {
        const auto f=owner.flags23c;
        if(f&0x800000)mode128(o)=0x19;
        else if(f&0x1000000)mode128(o)=0x18;
        else if(reraWolfNear(o,ob)&&(f&4)&&owner.stateIndex()>=0x20)mode128(o)=0xb;
    }
    // 1f9938: state entry.
    bool entered=false;
    {
        int32_t next=mode128(o);const int32_t was=mode12c(o);
        const bool fp=w.ownerWon,s6=w.opponentWon,s7=owner.fieldA30>=100,armed=owner.flags23c&0x1000;
        if(next!=was) {
            if(was==8)AuxiliaryObjects::stop(o);
            o[0x104/4]&=~0x400002u;
            const auto S=[&]{AuxiliaryObjects::stop(o);};
            if(uint32_t(next)<28)switch(next) {
            case 0:S();R(0x301);break;case 1:S();R(0x302);break;case 2:S();R(0x303);break;case 3:S();R(0x304);break;
            case 4:R(0x305);break;case 5:R(0x306);break;case 6:R(0x307);break;case 7:R(0x308,false,true);break;
            case 8:S();R(0x309);break;case 9:S();R(0x30a);break;case 10:S();R(0x30b);break;case 11:S();R(0x30c);break;
            case 12: {
                const F ox=X(w.opponentBody);
                if(ox.less(X(o)))o[0x38/4]|=mirror;else if(X(o).less(ox))o[0x38/4]&=~mirror;
                S();R(0x336);break;
            }
            case 13:R(0x337);break;case 14:S();R(0x338);break;case 15:S();R(0x339);break;
            case 16:R(0x33a);break;case 17:R(0x32d);break;case 18:R(0x32e);break;
            case 19:o[0x108/4]|=0x100000;break;
            case 20:S();next=was;if(!fp||armed||s7)o[0x108/4]|=0x100000;break;
            case 21:S();R(0x30f);break;
            case 22:S();R(s6?0x30e:0x30d);break;
            case 23:S();R(0x310);break;
            case 24:S();copyFacing(o,ob);R(0x302);break;
            case 26:
                S();o[0x40/4]=((ob[0x38/4]&mirror)?X(ob).add(F::integer(42)):X(ob).sub(F::integer(42))).bits;
                o[0x44/4]=0;copyFacing(o,ob);o[0x104/4]|=0x400002;break;
            default:break;
            }
            mode12c(o)=next;mode128(o)=next;entered=true;
        }
    }
    if(!entered) {
        // 1f9808: signed distance to the follow point, in the wolf's facing frame.
        const int32_t st=mode128(o);
        const F tx=followPoint(ob);
        F dx=tx.sub(X(o));F a=dx;a.bits&=0x7fffffffu;
        if(st<12) {
            if(!F::integer(12).less(a)){dx=F{0};copyFacing(o,ob);}
            else if(F::integer(114).less(a)&&uint32_t(st-5)>=4) {
                if(X(o).less(tx))o[0x38/4]&=~mirror;else if(tx.less(X(o)))o[0x38/4]|=mirror;
            }
        }
        if(o[0x38/4]&mirror)dx.bits^=0x80000000u;
        const int d=dx.truncate();
        // 1f9cf8 (flag 0).
        bool go=false;
        const auto f23c=owner.flags23c;
        switch(st) {
        case 0:if(d!=0)go=true;else if(f23c&8)mode128(o)=2;break;
        case 1:if(d!=0)go=true;else if(!(f23c&8))mode128(o)=3;break;
        case 2:if(clipLive(o))mode128(o)=1;break;
        case 3:if(clipLive(o))mode128(o)=0;break;
        case 4:case 5:go=true;break;
        case 6:case 7:if(d==0||clipLive(o))go=true;break;
        case 8:case 9:case 10:case 11:case 15:case 16:case 18:if(clipLive(o))go=true;break;
        case 12:if(clipLive(o))mode128(o)=0xd;break;
        case 13: {
            const auto f104=o[0x104/4];
            if(clipLive(o)) {
                const F ox=X(w.opponentBody);
                const bool turn=(o[0x38/4]&mirror)?X(o).less(ox):ox.less(X(o));
                if(turn)mode128(o)=0x10;
            } else if(f104&0xc0000)mode128(o)=0xe;
            else if(f104&0x200000)mode128(o)=0xf;
            else if(uint8_t(o[0x100/4])&2)mode128(o)=0xf;
            break;
        }
        case 14:if(clipLive(o))mode128(o)=0xf;break;
        case 17:if(!F{0}.less(Y(o))){AuxiliaryObjects::stop(o);go=true;o[0x44/4]=0;mode128(o)=0x12;}break;
        case 19:if(clipLive(o)){go=true;o[0x108/4]|=0x100000;}break;
        case 20:case 21:case 22:case 23: {
            const auto f=o[0x104/4];o[0x104/4]=f&~0x100u;
            if(o[0xc0/4]&&!(f&1))o[0x108/4]|=0x100000;
            break;
        }
        case 24:if(!(f23c&0x1000000))go=true;break;
        case 25:if(!(f23c&0x800000))go=true;break;
        case 26:
            if(owner.state194==0x00300000)o[0x104/4]|=2;
            else{go=true;R(0x301,true,true);}
            break;
        case 27:if(o[0xc0/4])go=!(o[0x104/4]&1);break;
        default:break;
        }
        if(go) {
            const F fd=F::integer(d);
            if(F::integer(120).less(fd)){mode128(o)=6;mode12c(o)=-1;}
            else if(fd.less(F::integer(-120))) {
                if(st==6)mode128(o)=8;else{mode128(o)=7;mode12c(o)=-1;}
            }
            else if(F::integer(12).less(fd))mode128(o)=4;
            else if(fd.less(F::integer(-12)))mode128(o)=5;
            else mode128(o)=(f23c&8)?1:0;
            if(f23c&0x800000){R(0x304);mode128(o)=0x19;}
        }
    }
    // 1a3ba8(o, prev == 0x19 ? 0.0 : -6.0), prev read at task entry.
    o[0xec/4]=0;
    if(prev==0x19){o[0xf0/4]=0;o[0xb4/4]=0;}
    else{o[0xf0/4]=std::bit_cast<uint32_t>(-6.0f);o[0xb4/4]=std::bit_cast<uint32_t>(-5.0f);}
}
}
