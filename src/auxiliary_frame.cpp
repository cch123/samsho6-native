#include "auxiliary_objects.hpp"
#include "actor_history.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
int32_t signedWord(uint32_t v){return std::bit_cast<int32_t>(v);}
void admit(const AuxiliaryObject& o) {
    if(o[0xcc/4]!=2&&o[0xcc/4]!=3&&o[0xcc/4]!=4&&o[0xcc/4]!=5&&o[0xcc/4]!=6&&o[0xcc/4]!=7&&o[0xcc/4]!=9&&o[0xcc/4]!=10)
        throw std::runtime_error("Auxiliary frame currently admits projectile, weapon, common and afterimage objects");
}
MotionState motion(const AuxiliaryObject& o) {
    return {signedWord(o[0x4c/4]),signedWord(o[0x50/4]),signedWord(o[0x54/4]),
            signedWord(o[0x58/4]),signedWord(o[0x5c/4]),signedWord(o[0x60/4]),
            std::bit_cast<float>(o[0x40/4]),std::bit_cast<float>(o[0x44/4])};
}
void storeMotion(AuxiliaryObject& o,const MotionState& m) {
    const std::array<int32_t,6> values{m.dx,m.vx,m.ax,m.dy,m.vy,m.ay};
    for(unsigned i=0;i<6;++i)o[0x4c/4+i]=uint32_t(values[i]);
    o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x44/4]=std::bit_cast<uint32_t>(m.y);
}
const AuxiliaryOwner& owner(const AuxiliaryObject& o,const AuxiliaryFrame& f,bool opponent=false) {
    const auto h=o[0x118/4];
    if(!h||h>2)throw std::runtime_error("Auxiliary frame needs the actual actor owner");
    const auto& result=f.owners[opponent?2-h:h-1];
    if(!result.body)throw std::runtime_error("Auxiliary frame owner body is missing");
    return result;
}
void updateDelta(AuxiliaryObject& o,const AuxiliaryFrame& f) {
    o[0x30/4]=battleSpeedDelta(f.speedMode140);
    if(!o[0x118/4])return;
    const auto& own=owner(o,f);const auto flags=o[0x108/4];
    if(flags&0x10000)o[0x30/4]=(*own.body)[0x30/4];
    //40000 blocks the opponent branch even when the owner's8000000 isoff.
    if(flags&0x40000) {
        if(own.flags23c&0x08000000)o[0x30/4]=(*own.body)[0x30/4];
    }else if(flags&0x20000)o[0x30/4]=(*owner(o,f,true).body)[0x30/4];
}
void completion(AuxiliaryObject& o,const AuxiliaryFrame& f,TaggedTaskPools& p) {
    auto& flags=o[0x108/4];
    if(flags&0x4000) {
        if(o[0xcc/4]!=3)flags=(flags&~0x4000u)|0x2000;
        else if((o[0xc0/4]&&!(o[0x104/4]&1))||std::bit_cast<float>(o[0x44/4])<0.0f) {
            // 147558: a companion (kind 3) lent out with 0x4000 (victim end op 25) returns to its own
            // task once its ACT ends or it drops below the floor: task[0] = o+8, 128 = 0, 12c = -1.
            p.tasks.at(o[1]-1)[0]=o[2];o[0x128/4]=0;o[0x12c/4]=0xffffffffu;flags&=~0x4000u;
        }
    }
    if((flags&0x2000)&&o[0xc0/4]&&!(o[0x104/4]&1))flags|=0x1000;
    if((flags&0x8000)&&owner(o,f).effectiveTable==2)flags|=0x1000;
}
void parentVisuals(AuxiliaryObject& o,const AuxiliaryFrame& f) {
    if(!o[0x118/4])return;
    const auto& own=owner(o,f);const auto flags=o[0x108/4];
    if(flags&0x30000) {
        const auto& parent=*owner(o,f,!(flags&0x10000)).body;
        std::copy_n(parent.begin()+0x40/4,12,o.begin()+0x40/4);
    }
    constexpr uint32_t inherited=0x40810000;
    if(flags&0x04000000) {
        o[0x38/4]=(o[0x38/4]&~inherited)|((*own.body)[0x38/4]&inherited);
        o[0x8c/4]=(*own.body)[0x8c/4];
    }else if(!(flags&0x80000)) {
        o[0x38/4]&=~inherited;o[0x8c/4]=0xff808080;
        if(own.postureA2c==7){o[0x38/4]|=0x40000000;o[0x8c/4]=0xff000000;}
    }
}
}
void AuxiliaryObjects::animate(AuxiliaryObject& o,const GaugeState& g,uint32_t& jumpFlags) {
    admit(o);
    if(signedWord(o[0xdc/4])>0||(o[0x104/4]&0x110)||(o[0xfc/4]&0x00200000))return;
    if(o[0x104/4]&0x6000)jumpFlags|=1;
    const auto oldTime=o[0x2c/4],oldStep=o[0x28/4];const auto r=record(o);
    const auto count=resources_.at(slots_.at(o[0xc/4])).aid.at(0x1000+o[0x24/4]);
    o[0x2c/4]+=resolveObjectDelta(o[0x30/4],o[0x10/4],g);
    bool changed=false;
    if(signedWord(o[0x2c/4])>=int32_t(r.duration)*256) {
        bool land=true;
        if(r.headerFlags&0x4000) {
            const auto y=ScalarFloat::integer(ScalarFloat{o[0x44/4]}.truncate());
            const auto dy=ScalarFloat::integer(signedWord(o[0x58/4])>>16);
            land=((o[0x38/4]&0x40000)?y.sub(dy):y.add(dy)).truncate()<=0;
            if(land){o[0x44/4]=o[0x58/4]=o[0x5c/4]=o[0x60/4]=0;o[0x3c/4]|=0x100;}
        }
        if(land) {
            //Original advances at most one record, retaining only thelow
            //fractional byte. Large deltas never catch up multiple records.
            o[0x2c/4]&=255;++o[0x28/4];
            if(o[0x28/4]>=count) {
                if(!(jumpFlags&1)&&(r.headerFlags&0x8000)) {
                    o[0xc4/4]=o[0x24/4]=uint32_t(int32_t(r.endKind));o[0x28/4]=0;
                    o[0x104/4]&=~0x04000000u;changed=true;
                }else if(r.endKind==2) {
                    o[0x28/4]=0;o[0xc0/4]=1;o[0x38/4]&=~0x10000000u;
                }else {
                    o[0x28/4]=count-1;o[0xc0/4]=1;
                    o[0x3c/4]=(o[0x3c/4]&~255u)|uint32_t(int32_t(r.endKind));
                }
            }
            changed|=o[0x28/4]!=oldStep;
        }
    }
    if(changed) {enter(o);publishJudgment(o);judgment(o);}
    else if(signedWord(oldTime)/256<signedWord(o[0x2c/4])/256)publishJudgment(o);
    jumpFlags&=~1u;o[0x104/4]&=~0x2000u;
}
void AuxiliaryObjects::move(AuxiliaryObject& o,const GaugeState& g) {
    admit(o);auto m=motion(o);clampRetreat(m,o[0x108/4]);storeMotion(o,m);
    if(signedWord(o[0xdc/4])>0) {
        ++o[0xe0/4];o[0xe4/4]=(signedWord(o[0xe0/4])/2)&1?uint32_t(-2):2;o[0xe8/4]=0;
        o[0xdc/4]=uint32_t(std::max(0,signedWord(o[0xdc/4]-o[0x30/4])));return;
    }
    o[0xdc/4]=o[0xe4/4]=o[0xe8/4]=0;
    if(o[0xfc/4]&255)--o[0xfc/4];
    if(o[0xfc/4]&0x00300000)return;
    const auto delta=resolveObjectDelta(o[0x30/4],o[0x10/4],g);
    if(!(o[0x104/4]&0x20)) {
        if(o[0x38/4]&0x02000000) {
            //This ACT family uses integer screen velocity, without the
            //usual16-bit scale, acceleration, or mirror sign changes.
            m.x=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(m.x)}.add(ScalarFloat::integer(signedWord(uint32_t(m.vx)*delta)>>8)).bits);
            m.y=std::bit_cast<float>(ScalarFloat{std::bit_cast<uint32_t>(m.y)}.add(ScalarFloat::integer(signedWord(uint32_t(m.vy)*delta)>>8)).bits);
        }else advanceMotion(m,delta,false);
    }
    //Even frozen integration commits already accumulated displacement.
    if(o[0xc8/4]==1)advanceMotion(m,0,true,o[0x38/4]&0x80000,o[0x38/4]&0x40000);
    storeMotion(o,m);
    if(o[0x38/4]&0x01000000) { //121308, per-visit color change, not delta scaled
        uint32_t color=0;
        for(unsigned channel=0;channel<4;++channel) {
            const unsigned shift=24-channel*8;
            const auto value=signedWord(((o[0x8c/4]>>shift)&255)+o[0x90/4+channel*2]);
            color|=uint32_t(std::clamp(value,0,255))<<shift;
        }
        o[0x8c/4]=color;
    }
}
void objectCompletion(AuxiliaryObject& o,const AuxiliaryFrame& f,TaggedTaskPools& p){completion(o,f,p);}
void AuxiliaryObjects::updateRegistry(TaggedTaskPools& p,std::span<const uint32_t> registry,const AuxiliaryFrame& f) {
    for(auto task:registry)if(task) {
        auto& o=p.objects.at(p.tasks.at(task-1)[7]-1);admit(o);updateDelta(o,f);
        animate(o,f.gauges,f.jumpFlags46a99c);move(o,f.gauges);
        if(o[0x104/4]&8) {
            const ScalarFloat x{o[0x40/4]},lo=ScalarFloat::integer(34),hi=ScalarFloat::integer(606);
            if(x.less(lo))o[0x40/4]=lo.bits;else if(hi.less(x))o[0x40/4]=hi.bits;
        }
        completion(o,f,p);
    }
}
void AuxiliaryObjects::visitRegistry(TaggedTaskPools& p,std::span<uint32_t> registry,const std::function<void(uint32_t)>& visit) {
    if(registry.size()>256)throw std::runtime_error("Auxiliary registry exceeds source callback snapshot");
    std::array<bool,256> empty{};
    for(unsigned i=0;i<registry.size();++i)empty[i]=registry[i]==0;
    for(unsigned i=0;i<registry.size();++i)if(!empty[i]&&registry[i]) {
        const auto task=registry[i],object=p.tasks.at(task-1)[7];auto& o=p.objects.at(object-1);admit(o);
        //Only emptiness is snapshotted. New tasks in previously occupied
        //future slots are visited; newly filled empty slots wait one visit.
        visit(task);
        if((o[0x108/4]&0x02001000)==0x1000) {
            p.freeObject(object);p.tasks.at(task-1)[1]=2;registry[i]=0;
        }
        //This write intentionally occurs even after returning the object
        //to its free list. The task itself waits for112838 reclamation.
        o[0x108/4]&=~0x02000000u;
    }
}
void AuxiliaryObjects::drawRegistry(TaggedTaskPools& p,std::span<const uint32_t> registry,const AuxiliaryFrame& f,ObjectDrawQueue& queue) {
    for(auto task:registry)if(task) {
        auto& o=p.objects.at(p.tasks.at(task-1)[7]-1);admit(o);
        commitRequested(o);parentVisuals(o,f);
        if(o[0xcc/4]==10) {
            const auto& own=owner(o,f);
            if(!own.history)throw std::runtime_error("Afterimage needs its owner history");
            ActorAfterimage trail;
            trail.lag=o[0x128/4];trail.alpha=o[0x12c/4];trail.depthOffset=o[0x130/4];trail.flags104=o[0x104/4];
            trail.update(*own.history,own.effectiveTable,std::bit_cast<float>((*own.body)[0xb0/4]),(*own.body)[0x14/4]);
            o[0x40/4]=std::bit_cast<uint32_t>(trail.sample.x);o[0x44/4]=std::bit_cast<uint32_t>(trail.sample.y);
            o[0x24/4]=trail.sample.action;o[0x28/4]=trail.sample.step;o[0x38/4]=trail.sample.flags;
            o[0xb0/4]=std::bit_cast<uint32_t>(trail.depth);o[0x8c/4]=trail.color;o[0x104/4]=trail.flags104;
        }
        commitRequested(o);
        if(!(o[0x104/4]&2))queue.submit(o,f.gauges);
    }
}
}
