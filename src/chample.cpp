#include "chample.hpp"
#include "ground_state.hpp"
#include "stage_item_delivery.hpp"
#include <bit>
#include <stdexcept>

// Mina's companion. Addresses refer to SLPS_255.59; see docs/mina-callbacks.txt
// section 6. Object words are indexed by original byte offset / 4.
namespace ss6 {
namespace {
using F=ScalarFloat;
constexpr uint32_t mirror=0x80000,ready=0x100000;
F f32(float v){return {std::bit_cast<uint32_t>(v)};}
F X(const AuxiliaryObject& o){return {o[0x40/4]};}
F Y(const AuxiliaryObject& o){return {o[0x44/4]};}
bool mirrored(const AuxiliaryObject& o){return o[0x38/4]&mirror;}
bool ended(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
int32_t& state128(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x128/4]);}
int32_t& state12c(AuxiliaryObject& o){return reinterpret_cast<int32_t&>(o[0x12c/4]);}
void copyFacing(AuxiliaryObject& o,const AuxiliaryObject& from) {
    o[0x38/4]=(o[0x38/4]&~mirror)|(from[0x38/4]&mirror);
}
// "Face toward X": equal positions keep the current facing.
void faceToward(AuxiliaryObject& o,F x) {
    if(x.less(X(o)))o[0x38/4]|=mirror;
    else if(X(o).less(x))o[0x38/4]&=~mirror;
}
F ahead(const AuxiliaryObject& body,F distance) {
    return mirrored(body)?X(body).sub(distance):X(body).add(distance);
}
F absolute(F v){v.bits&=0x7fffffff;return v;}
bool unported(const char* what){throw std::runtime_error(std::string("Chample ")+what+" requires an unported stage-item operation");}

// 1fdc68
bool suspended(AuxiliaryObject& o) {
    if(state12c(o)==19)return true;
    if(state12c(o)>=10)return false;
    if(F{0}.less(Y(o)))return true;
    o[0x104/4]&=~0x100u;return false;
}
// 1fdcb8
bool besideOwner(AuxiliaryObject& o,const AuxiliaryObject& body) {
    if(state128(o)>=13||suspended(o))return false;
    const auto f=ahead(body,F::integer(32)).sub(X(o));
    return f.less(F::integer(32))&&F::integer(-32).less(f);
}
// 1fc910: signed distance to the follow point, in Chample's own facing.
int followDistance(AuxiliaryObject& o,const AuxiliaryObject& body) {
    const F offset=state128(o)==38?F{o[0xf4/4]}:F::integer(32);
    const F t=ahead(body,offset);
    F f=t.sub(X(o));
    const F a=absolute(f);
    if(state128(o)<11) {
        if(!F::integer(12).less(a)){f=F{0};copyFacing(o,body);}
        else if(F::integer(96).less(a)&&state128(o)!=5&&state128(o)!=7) {
            if(X(o).less(t))o[0x38/4]&=~mirror;
            else if(t.less(X(o)))o[0x38/4]|=mirror;
        }
    }
    if(mirrored(o))f.bits^=0x80000000;
    return f.truncate();
}
// 141018: landed floor item, else 8 for a live bomb, else -1.
int itemKind(const ChampleWorld& w) {
    if(w.delivery&&w.delivery->itemIndex()!=-1)return w.delivery->itemIndex();
    if(w.battleBomb) {
        const auto act=(*w.battleBomb)[0x24/4];
        if(act==0x4c||act==0x4e||act==0x85)return 8;
    }
    return -1;
}
// 141090
int itemPosition(const ChampleWorld& w) {
    if(w.delivery&&w.delivery->itemIndex()!=-1)return F{std::bit_cast<uint32_t>(w.delivery->itemX())}.truncate();
    if(w.battleBomb) {
        const auto act=(*w.battleBomb)[0x24/4];
        if(act==0x4c||act==0x4e||act==0x85)return X(*w.battleBomb).truncate();
    }
    return 0;
}

// 1fca70: enter the requested state. Returns true when a state was entered.
bool enter(AuxiliaryObjects& objects,AuxiliaryObject& o,ChampleWorld& w) {
    const auto& body=w.body;
    const int kind=itemKind(w);
    const int itemX=itemPosition(w);
    const bool hp100=w.owner.fieldA30>=100,armed=w.owner.flags23c&0x1000;
    if(state128(o)==state12c(o))return false;
    AuxiliaryObjects::stop(o);o[0x104/4]&=~0x400002u;
    int next=state128(o);
    auto req=[&](unsigned act,bool immediate=false,bool force=false){objects.request(o,act,immediate,force);};
    switch(next) {
    case 0:req(769);break; case 1:req(770);break; case 2:req(771);break; case 3:req(772);break;
    case 4:req(773);break; case 5:req(774,false,true);break; case 6:req(775);break; case 7:req(776);break;
    case 8:req(778);break; case 9:req(779);break; case 10:req(780);break; case 11:req(781);break;
    case 12:req(782);break;
    case 13:faceToward(o,X(body));req(790);break;
    case 14:req(791);o[0x130/4]=uint32_t(X(o).truncate());break;
    case 15:req(792);o[0x44/4]=0;o[0x40/4]=F::integer(int32_t(o[0x130/4])).bits;break;
    case 16:o[0x44/4]=0;req(793);break;
    case 17:req(794);o[0x130/4]=0x3c00;break;
    case 18:req(795);break;
    case 19:req(791);o[0x104/4]|=2;break;
    case 20:req(806);break;
    case 21:case 22:req(807);faceToward(o,X(body));break;
    case 23:
        if(kind==-1){req(782);next=12;}
        else{req(796);faceToward(o,F::integer(itemX));}
        break;
    case 25:if(kind==-1){req(782);next=12;}else req(797);break;
    case 26:unported("eating");break;
    case 27:if(kind==-1){req(782);next=12;}else{faceToward(o,X(w.opponentBody));req(799);}break;
    case 29:if(kind==-1){req(782);next=12;}else{req(800);faceToward(o,X(body));}break;
    case 30:copyFacing(o,body);req(803);break;
    case 32:req(805);break;
    case 33:
        copyFacing(o,body);
        o[0x40/4]=ahead(body,F::integer(120)).bits;o[0x44/4]=body[0x44/4];
        req(812);break;
    case 34:
        AuxiliaryObjects::stop(o);
        if(w.ownerWon) {
            if(!armed)req(813);
            else{o[0xf4/4]=F::integer(hp100?30:20).bits;next=38;o[0x134/4]=0xffffffffu;}
        } else if(!hp100)req(814+unsigned(w.random.bounded(3)));
        else{o[0x134/4]=823;next=38;o[0xf4/4]=F::integer(40).bits;}
        break;
    case 35:AuxiliaryObjects::stop(o);req(820);break;
    case 36:AuxiliaryObjects::stop(o);req(w.opponentWon?818:817);break;
    case 37:AuxiliaryObjects::stop(o);req(819);break;
    case 39:copyFacing(o,body);req(o[0x134/4]);break;
    case 40:req(821);break;
    case 41:req(822);break;
    case 42:
        AuxiliaryObjects::stop(o);
        o[0x40/4]=ahead(body,F::integer(-16)).bits;o[0x44/4]=0;copyFacing(o,body);
        o[0x104/4]|=0x400002;break;
    default:break; // 24, 28, 31, 38 and >= 43 make no request
    }
    if(next==38)req(773,false,true);
    state12c(o)=state128(o)=next;
    return true;
}

// 1fd120 with a3 == 0 (its only caller).
void update(AuxiliaryObjects& objects,AuxiliaryObject& o,ChampleWorld& w,int d) {
    const auto& body=w.body;
    const int kind=itemKind(w);
    const int itemX=itemPosition(w);
    bool done=false;
    switch(state128(o)) {
    case 0:if(d)done=true;else if(w.owner.flags23c&8)state128(o)=2;break;
    case 1:if(d)done=true;else if(!(w.owner.flags23c&8))state128(o)=3;break;
    case 2:if(ended(o))state128(o)=1;break;
    case 3:if(ended(o))state128(o)=0;break;
    case 4:case 6:case 7:done=true;break;
    case 5:case 8:case 9:case 10:case 11:case 12:case 15:case 18:case 28:case 31:case 32:case 40:case 41:
        if(ended(o))done=true;break;
    case 13:
        AuxiliaryObjects::stop(o);
        if(w.owner.state194!=0x00420001){o[0x44/4]=0;done=true;}
        else if(mirrored(o)?!X(body).less(X(o)):!X(o).less(X(body)))o[0x40/4]=body[0x40/4];
        else {
            const F dx=absolute(X(o).sub(X(body)));
            F s=F::integer(24).sub(Y(o)).mul(F::integer(4)).div(dx);
            if(F::integer(8).less(s))s=F::integer(8);
            o[0x50/4]=0x40000;o[0x5c/4]=uint32_t(s.mul(F::integer(65536)).truncate());
        }
        break;
    case 14:case 19:case 24:break;
    case 16:if(ended(o))state128(o)=17;break;
    case 17:
        if(ended(o)) {
            o[0x130/4]-=o[0x30/4];
            if(int32_t(o[0x130/4])<=0){o[0x130/4]=0x3c00;objects.request(o,794,false,true);}
        }
        break;
    case 20:unported("item production");break;
    case 21:case 22:if(ended(o))done=true;else unported("item carrying");break;
    case 25:if(kind==-1)state128(o)=12;else if(ended(o))unported("item pickup");break;
    case 26:if(ended(o))done=true;else if(o[0x104/4]&0x100)unported("eating notice");break;
    // 27 tests completion before the item: "(it = 1b5ac0()) == 0 || kind == -1".
    case 27:if(ended(o))done=true;else if(kind==-1)state128(o)=12;else unported("item throw");break;
    case 29:if(kind==-1)state128(o)=12;else unported("item delivery");break;
    case 23:
        if(kind==-1)state128(o)=12;
        else if(std::abs(F::integer(itemX).sub(X(o)).truncate())<4){AuxiliaryObjects::stop(o);state128(o)=25;}
        else faceToward(o,F::integer(itemX));
        break;
    case 30:
        if(o[0x104/4]&0x2c0000)state128(o)=32;
        else if(o[0x104/4]&4)done=true;
        else if(mirrored(o)?X(o).less(X(w.opponentBody).sub(F::integer(64))):X(w.opponentBody).add(F::integer(64)).less(X(o)))done=true;
        else if(ended(o)&&w.opponent.stateTable()==2)state128(o)=12;
        break;
    case 33:if(ended(o)){done=true;o[0x108/4]|=ready;}break;
    case 34:case 35:case 36:case 37:case 39:
        o[0x104/4]&=~0x100u;if(ended(o))o[0x108/4]|=ready;break;
    case 38:
        if(d)faceToward(o,ahead(body,F{o[0xf4/4]}));
        else if(o[0x134/4]!=0xffffffffu)state128(o)=39;
        else{AuxiliaryObjects::stop(o);objects.request(o,769,false,true);o[0x108/4]|=ready;}
        break;
    case 42:
        if(w.owner.state194==0x00300000)o[0x104/4]|=2;
        else{done=true;objects.request(o,769,true,true);}
        break;
    default:break;
    }
    if(done) {
        const F f=F::integer(d);
        if(F::integer(48).less(f))state128(o)=6;
        else if(f.less(F::integer(-48)))state128(o)=7;
        else if(F::integer(12).less(f))state128(o)=4;
        else if(f.less(F::integer(-12))){state12c(o)=-1;state128(o)=5;}
        else state128(o)=(w.owner.flags23c&8)?1:0;
    }
}
}

uint32_t spawnChample(AuxiliaryObjects& objects,TaggedTaskPools& pools,std::span<uint32_t> registry,
                      unsigned player,uint32_t flags,const AuxiliaryObject& body) {
    const auto handle=objects.create(pools,registry,player,flags,body,0x138c+player,3,0x1fc750);
    if(!handle)throw std::runtime_error("Missing Chample object slot");
    auto& o=pools.objects.at(handle-1);
    o[0x40/4]=ahead(body,F::integer(-100)).bits;
    o[0x44/4]=0;
    objects.request(o,769,true,false);
    o[0x128/4]=0;o[0x12c/4]=0xffffffffu;
    // 1a3220's shared tail; character 16 alone keeps 108:40000 clear.
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;o[0x108/4]|=0x40000;
    return handle;
}
void updateChample(AuxiliaryObjects& objects,AuxiliaryObject& o,ChampleWorld& w) {
    const auto& body=w.body;
    const bool same=!((o[0x38/4]^body[0x38/4])&mirror);
    if(suspended(o))return;
    if(state128(o)==state12c(o)&&state128(o)<10&&besideOwner(o,body)) {
        const int table=w.owner.stateTable(),index=w.owner.stateIndex();
        if(table==2){if(index>=32)state128(o)=12;}
        else if(table==1) {
            if(same) {
                if(index==36)state128(o)=40;
                else if(w.owner.flags23c&8)state128(o)=11;
                else if(unsigned(index-82)>=3u)state128(o)=10;
            }
        } else if(table==0&&unsigned(index-48)<3u)state128(o)=41;
    }
    if(!enter(objects,o,w))update(objects,o,w,followDistance(o,body));
    // 1a3ba8(o,-6.0): history offsets used by the draw pass.
    o[0xec/4]=0;o[0xf0/4]=f32(-6.0f).bits;o[0xb4/4]=f32(-5.0f).bits;
}
bool champleAvailable(const AuxiliaryObject& o) {
    const int s=int32_t(o[0x12c/4]);
    return !(s==14||s==16||s==17||(s>=20&&s<=23)||(s>=25&&s<=32));
}
void commandChamplePresentation(AuxiliaryObject& o,uint32_t state) {
    o[0x108/4]&=~ready;
    if(champleAvailable(o))o[0x128/4]=state;else o[0x108/4]|=ready;
}
}
