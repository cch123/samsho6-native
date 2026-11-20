#include "chamcham_pet.hpp"
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
F f32(float v){return F{std::bit_cast<uint32_t>(v)};}
bool mirrored(const AuxiliaryObject& o){return o[0x38/4]&mirror;}
int32_t& mode128(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x128/4]);}
int32_t& mode12c(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x12c/4]);}
bool clipDone(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& b){o[0x38/4]=(o[0x38/4]&~mirror)|(b[0x38/4]&mirror);} //11dbb8
F ahead(const AuxiliaryObject& body,F d){return mirrored(body)?X(body).sub(d):X(body).add(d);}
bool suspended(AuxiliaryObject& o) { // 204b68
    if(mode12c(o)>=10)return false;
    if(F{0}.less(Y(o)))return true;
    o[0x104/4]&=~0x100u;return false;
}
bool besideOwner(AuxiliaryObject& o,const AuxiliaryObject& body) { // 204ba8
    if(mode128(o)>=0xc)return false;
    const F dx=ahead(body,f32(-28.0f)).sub(X(o));
    return dx.less(F::integer(32))&&F::integer(-32).less(dx);
}
int followDelta(AuxiliaryObject& o,const AuxiliaryObject& ob) { // 204070
    const int m=mode128(o);
    const F tx=m==0x18?ahead(ob,F{o[0xf4/4]}):ahead(ob,f32(-28.0f));
    F dx=tx.sub(X(o));F ad=dx;ad.bits&=0x7fffffff;
    if(m<0xb) {
        if(!F::integer(12).less(ad)){dx=F{0};copyFacing(o,ob);}
        else if(F::integer(96).less(ad)&&m!=5&&m!=7) {
            if(X(o).less(tx))o[0x38/4]&=~mirror;
            else if(tx.less(X(o)))o[0x38/4]|=mirror;
        }
    }
    if(mirrored(o))dx.bits^=0x80000000u;
    return dx.truncate();
}
}

uint32_t spawnChamchamPet(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                          unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x203ec0);
    if(!handle)throw std::runtime_error("Missing Chamcham pet object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=(mirrored(body)?X(body).add(F::integer(100)):X(body).sub(F::integer(100))).bits;
    o[0x44/4]=0;
    objects.request(o,0x301,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000; // 1a3220's shared tail
    return handle;
}

void updateChamchamPet(AuxiliaryObjects& objects,AuxiliaryObject& o,const ChamchamPetWorld& w) {
    const auto& ob=w.body;const auto& owner=w.owner;
    const auto R=[&](unsigned act,bool force=false){objects.request(o,act,false,force);};
    const bool same=mirrored(o)==mirrored(ob);
    if(suspended(o))return;
    if(mode128(o)==mode12c(o)&&mode128(o)<10&&besideOwner(o,ob)) {
        const int idx=owner.stateIndex();
        if(owner.stateTable()==2){if(idx>=0x20)mode128(o)=0xc;}
        else if(owner.stateTable()==1&&same) {
            if(idx==0x24)mode128(o)=0x1b;
            else if(!(owner.flags23c&8))mode128(o)=0xa;
            else mode128(o)=0xb;
        } else if(owner.stateTable()==0&&unsigned(idx-0x30)<3)mode128(o)=0x1c;
    }
    // 2041d0: mode entry.
    bool entered=false;
    {
        int next=mode128(o);const int prev=mode12c(o);
        const bool A=w.ownerWon,B=w.opponentWon,L=owner.fieldA30>=100,W=owner.flags23c&0x1000;
        if(next!=prev) {
            AuxiliaryObjects::stop(o);
            o[0x104/4]&=~(0x400000u|2u);
            const auto park=[&](unsigned act){o[0x44/4]=0;AuxiliaryObjects::stop(o);copyFacing(o,ob);R(act);};
            const auto later=[&](uint32_t act,float f4){next=0x18;o[0x134/4]=act;o[0xf4/4]=std::bit_cast<uint32_t>(f4);};
            if(unsigned(next)<0x1d)switch(next) {
            case 0:R(0x301);break;case 1:R(0x302);break;case 2:R(0x303);break;case 3:R(0x304);break;case 4:R(0x305);break;
            case 5:R(0x306,true);break;
            case 6:R(0x307);break;case 7:R(0x308);break;case 8:R(0x309);break;case 9:R(0x30a);break;
            case 10:R(0x30c);break;case 11:R(0x30d);break;case 12:R(0x30e);break;
            case 13:park(0x25c);break;
            case 14:R(0x26a);break;case 15:R(0x26b);break;
            case 16:park(0x262);break;
            case 17:park(0x25e);break;
            case 18:break;
            case 19:
                copyFacing(o,ob);
                o[0x40/4]=(mirrored(o)?X(ob).add(F::integer(100)):X(ob).sub(F::integer(100))).bits;
                o[0x44/4]=ob[0x44/4];R(0x301);break;
            case 20:
                if(A){if(L)R(W?0x313:0x314);else if(W)later(0x315,-41.0f);else R(0x316);}
                else{if(L)R(W?0x30f:0x310);else if(W)later(0x311,-30.0f);else R(0x312);}
                break;
            case 21:R(0x31a);break;
            case 22:if(B)R(0x318);else later(0x317,-44.0f);break;
            case 23:later(0x319,-3.0f);break;
            case 24:break;
            case 25:copyFacing(o,ob);R(o[0x134/4]);break;
            case 26:
                AuxiliaryObjects::stop(o);
                o[0x40/4]=ahead(ob,F::integer(8)).bits;o[0x44/4]=0;copyFacing(o,ob);o[0x104/4]|=0x400002;
                break;
            case 27:R(0x31b);break;case 28:R(0x31c);break;
            }
            if(next==0x18)R(0x305,true);
            mode12c(o)=next;mode128(o)=next;entered=true;
        }
    }
    if(!entered) {
        const int d=followDelta(o,ob);
        // 204618: mode update.
        bool done=false;
        const auto shot=[&](unsigned id,float dy,bool to18){
            const auto f=o[0x104/4];
            if(clipDone(o)){done=true;return;}
            if(!(f&0x100))return;
            o[0x104/4]=f&~0x100u;
            if(to18)mode128(o)=0x12;
            if(!w.spawnDescriptor)throw std::runtime_error("Chamcham's pet fires through 16d2b0");
            auto* p=w.spawnDescriptor(id);
            if(!p)throw std::runtime_error("Original 16d2b0 writes through a null object");
            (*p)[0x40/4]=(mirrored(o)?X(o).sub(F::integer(8)):X(o).add(F::integer(8))).bits;
            (*p)[0x44/4]=Y(o).add(f32(dy)).bits;
            (*p)[0xb0/4]=F{o[0xb0/4]}.sub(F::integer(2)).bits;(*p)[0x104/4]|=0x20000; //11dff8
        };
        switch(mode128(o)) {
        case 0:
            if(d!=0)done=true;else if(owner.flags23c&8)mode128(o)=2;
            o[0xc0/4]=0;break;
        case 1:if(d!=0)done=true;else if(!(owner.flags23c&8))mode128(o)=3;break;
        case 2:if(clipDone(o))mode128(o)=1;break;
        case 3:if(clipDone(o))mode128(o)=0;break;
        case 4:case 6:case 7:done=true;break;
        case 5:case 8:case 9:case 10:case 11:case 12:case 15:if(clipDone(o))done=true;break;
        case 13:if(clipDone(o))done=true;else if(o[0x100/4]&2)mode128(o)=0xe;break;
        case 14:if(clipDone(o))mode128(o)=0xf;break;
        case 16:shot(0x7c,0.0f,false);break;
        case 17:shot(0x7d,-12.0f,true);break;
        case 18: {
            const auto f=o[0x104/4];
            if(clipDone(o))done=true;
            else if((f&0x100)&&!F{0}.less(Y(o))){o[0x44/4]=0;o[0x104/4]=f&~0x100u;}
            break;
        }
        case 19:if(clipDone(o)){done=true;o[0x108/4]|=0x100000;}break;
        case 20:case 21:case 22:case 23:case 25: {
            const auto f=o[0x104/4];o[0x104/4]=f&~0x100u;
            if(o[0xc0/4]&&!(f&1))o[0x108/4]|=0x100000;
            break;
        }
        case 24:
            if(d!=0) {
                const F tx=ahead(ob,F{o[0xf4/4]});
                if(X(o).less(tx))o[0x38/4]&=~mirror;else o[0x38/4]|=mirror;
            } else if(o[0x134/4]!=0xffffffffu)mode128(o)=0x19;
            else{AuxiliaryObjects::stop(o);R(0x301,true);o[0x108/4]|=0x100000;}
            break;
        case 26:
            if(owner.state194==0x00300000)o[0x104/4]|=2;
            else{done=true;objects.request(o,0x301,true,true);}
            break;
        case 27:case 28:if(o[0xc0/4])done=!(o[0x104/4]&1);break;
        default:break;
        }
        if(done) {
            const F fd=F::integer(d);
            if(F::integer(48).less(fd))mode128(o)=6;
            else if(fd.less(F::integer(-48)))mode128(o)=7;
            else if(F::integer(12).less(fd))mode128(o)=4;
            else if(fd.less(F::integer(-12))){mode12c(o)=-1;mode128(o)=5;}
            else mode128(o)=(owner.flags23c&8)?1:0;
        }
    }
    // 1a3ba8(o, -6.0)
    o[0xec/4]=0;o[0xf0/4]=std::bit_cast<uint32_t>(-6.0f);o[0xb4/4]=std::bit_cast<uint32_t>(-5.0f);
}
}
