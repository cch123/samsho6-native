#include "stage_item_delivery.hpp"
#include "auxiliary_objects.hpp"
#include "motion.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr std::array<unsigned,19> fallingAction{58,60,62,64,66,68,70,72,77,81,86,91,96,101,106,111,116,121,126}; // 5734b0
constexpr uint32_t release=0x1b5520, falling=0x1b5638, resting=0x1b57c8;
float number(uint32_t word){return std::bit_cast<float>(word);}
ScalarFloat scalar(float x){return {std::bit_cast<uint32_t>(x)};}
void stopX(AuxiliaryObject& o){std::fill_n(o.begin()+0x4c/4,3,0);}
void stop(AuxiliaryObject& o){std::fill_n(o.begin()+0x4c/4,6,0);}
MotionState motion(const AuxiliaryObject& o) {
    return {int32_t(o[0x4c/4]),int32_t(o[0x50/4]),int32_t(o[0x54/4]),
            int32_t(o[0x58/4]),int32_t(o[0x5c/4]),int32_t(o[0x60/4]),number(o[0x40/4]),number(o[0x44/4])};
}
void store(AuxiliaryObject& o,const MotionState& m) {
    o[0x4c/4]=uint32_t(m.dx);o[0x50/4]=uint32_t(m.vx);o[0x54/4]=uint32_t(m.ax);
    o[0x58/4]=uint32_t(m.dy);o[0x5c/4]=uint32_t(m.vy);o[0x60/4]=uint32_t(m.ay);
    o[0x40/4]=scalar(m.x).bits;o[0x44/4]=scalar(m.y).bits;
}
bool complete(const AuxiliaryObject& o){return o[0xc0/4]&&!(o[0x104/4]&1);}
void enter(AuxiliaryObject& o,AuxiliaryObjects& bank) {
    const auto r=bank.record(o);
    o[0x3c/4]=0;o[0x104/4]&=~0x18000u;
    if(r.headerFlags&0x400) {
        // Courier ACT46 publishes an attachment to the object itself.
        // 120d10 leaves the three payload words intact on later records.
        o[0x104/4]|=0x8000;o[0x10c/4]=uint16_t(r.effectCommand[0])&0x7ff;
        o[0x110/4]=uint32_t(r.effectCommand[1]);o[0x114/4]=uint32_t(r.effectCommand[2]);
    }
    if(!complete(o)){auto m=motion(o);enterMotion(m,r.motion);store(o,m);}
}
void play(AuxiliaryObject& o,AuxiliaryObjects& bank,unsigned action) {
    o[0x24/4]=action;o[0x28/4]=o[0x2c/4]=o[0xc0/4]=0;
    o[0x38/4]|=0x10000000;enter(o,bank);
}
void drawAndAdvance(AuxiliaryObject& o,const GaugeState& g,AuxiliaryObjects& bank,ObjectDrawQueue& draws) {
    const auto delta=resolveObjectDelta(o[0x30/4],o[0x10/4],g);
    auto m=motion(o);advanceMotion(m,delta,o[0xc8/4]==1,o[0x38/4]&0x80000);store(o,m);
    if(!(o[0x104/4]&2))draws.submit(o,g);
    o[0x104/4]&=~2u;
    unsigned length=0;const auto r=bank.record(o,&length);
    auto& time=o[0x2c/4];time+=delta;
    if(int32_t(time)<r.duration*256)return;
    if(r.headerFlags&0x4000) {
        // Zero-duration airborne records still wait until the integer Y
        // reaches ground. The courier reads a zero duration to release the item.
        if(ScalarFloat{o[0x44/4]}.truncate()+(int32_t(o[0x58/4])>>16)>0)return;
        o[0x44/4]=0;o[0x3c/4]|=0x100;std::fill_n(o.begin()+0x58/4,3,0);
    }
    time&=255;const auto old=o[0x28/4]++;
    if(o[0x28/4]>=length) {
        o[0xc0/4]=1;
        if(r.endKind==2){o[0x28/4]=0;o[0x38/4]&=~0x10000000u;}
        else {o[0x28/4]=length-1;o[0x3c/4]=(o[0x3c/4]&~255u)|uint16_t(r.endKind);}
    }
    if(old!=o[0x28/4])enter(o,bank);
}
}
StageItemDelivery::StageItemDelivery() {
    auto& o=courier_;
    o[0xc/4]=o[0x10/4]=2;o[0x14/4]=51;o[0x1c/4]=51*5;o[0x30/4]=256;
    o[0x38/4]=0x10000000;o[0x48/4]=0x42c80000;o[0x70/4]=0x3f800000;
    item_=o;o[0x38/4]|=0x20000000;
}
void StageItemDelivery::clear(){floorKind_=-1;callback_=0;busy_=false;}
void StageItemDelivery::hideNextDraw(){courier_[0x104/4]|=2;item_[0x104/4]|=2;}
float StageItemDelivery::itemX() const{return number(item_[0x40/4]);}
void StageItemDelivery::start(int kind,int targetX,int fromRight,const StageCamera& camera) {
    if(busy_)return;
    if(unsigned(kind)>=fallingAction.size())throw std::out_of_range("Unknown stage item kind");
    current_=-1;courierActive_=true;phase_=0;deliveryKind_=kind;
    const auto depth=scalar(camera.depth);
    const auto width=depth.less({0xc3c80000})?depth.add({0x43480000}).mul({0xbfcccccc}):scalar(320);
    const auto radius=width.mul({0x3f000000}),center=scalar(camera.projectionX);
    startLeft_=number(center.sub(radius).sub(scalar(100)).bits);
    startRight_=number(center.add(radius).add(scalar(100)).bits);
    targetX_=number(ScalarFloat::integer(targetX).bits);
    auto& flags=courier_[0x38/4];flags=(flags&~0x80000u)|(fromRight==1?0x80000:0);
    floorKind_=-1;busy_=true;callback_=0;
}
void StageItemDelivery::updateCourier(AuxiliaryObjects& bank) {
    auto& o=courier_;const bool mirrored=o[0x38/4]&0x80000;const float x=number(o[0x40/4]);
    switch(phase_) {
    case 0:
        wanted_=45;phase_=1;o[0xc8/4]=1;o[0x40/4]=scalar(mirrored?startRight_:startLeft_).bits;break;
    case 1:
        if(mirrored?x<=targetX_+30:x>=targetX_-30){wanted_=46;phase_=2;stopX(o);}break;
    case 2:
        if(o[0x3c/4]==1){wanted_=47;phase_=3;stopX(o);}break;
    case 3:
        if(complete(o)) {
            wanted_=45;phase_=4;targetX_=number(mirrored?0xc3195554:0x44465555);
        } else if(bank.record(o).duration==0)callback_=release;
        break;
    case 4:
        if(mirrored?x<targetX_:x>targetX_){stopX(o);courierActive_=false;}break;
    }
    if(current_!=wanted_){current_=wanted_;play(o,bank,unsigned(current_));}
}
void StageItemDelivery::updateItem(const GaugeState& g,AuxiliaryObjects& bank) {
    auto& o=item_;
    switch(callback_) {
    case release: {
        stop(o);o[0x104/4]&=~0x100u;play(o,bank,fallingAction[deliveryKind_]);
        o[0xc8/4]=1;o[0x40/4]=ScalarFloat{courier_[0x40/4]}.sub(scalar(6)).bits;
        const ScalarFloat z{courier_[0x48/4]};
        if(courier_[0x38/4]&0x20000000) {
            const auto one=scalar(1),distance=scalar(400);
            const auto lift=one.sub(distance.div(z.add(distance))).add(one).mul(scalar(53));
            o[0x44/4]=ScalarFloat{o[0x44/4]}.add(lift).bits;
        }
        o[0x48/4]=z.bits;o[0xb0/4]=0;callback_=falling;break;
    }
    case falling:
        if(number(o[0x48/4])>0) {
            // The depth sweep uses the raw global delta, not the paused
            // object selector used by 120618 for horizontal/vertical motion.
            const auto raw=g.delta46a908;
            auto ticks=ScalarFloat::integer(int32_t(raw));
            if(raw>>31){ticks=ScalarFloat::integer(int32_t((raw>>1)|(raw&1)));ticks=ticks.add(ticks);}
            const auto z=ScalarFloat{o[0x48/4]}.add(ticks.mul(scalar(-1.5f)).mul({0x3b800000}));
            o[0x48/4]=z.bits;
            if(z.less({0})){o[0x48/4]=0;o[0xb0/4]=scalar(-150).bits;}
            else if(int32_t(o[0x5c/4])<0)o[0xb0/4]=scalar(-150).bits;
        }
        if(number(o[0x44/4])<=0){o[0x44/4]=0;floorKind_=deliveryKind_;stop(o);}
        if(complete(o)&&number(o[0x44/4])<=0) {
            play(o,bank,fallingAction[deliveryKind_]-1);callback_=resting;
            o[0x48/4]=0;o[0xb0/4]=scalar(-150).bits;stop(o);
        }
        break;
    case resting:if(complete(o))clear();break;
    }
}
void StageItemDelivery::visit(const GaugeState& g,AuxiliaryObjects& bank,ObjectDrawQueue& draws) {
    if(courierActive_)updateCourier(bank);
    if(callback_)updateItem(g,bank);
    if(courierActive_)drawAndAdvance(courier_,g,bank,draws);
    if(callback_)drawAndAdvance(item_,g,bank,draws);
}
}
