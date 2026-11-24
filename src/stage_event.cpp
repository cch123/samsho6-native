#include "asset_files.hpp"
#include "stage_event.hpp"
#include "auxiliary_objects.hpp"
#include "motion.hpp"
#include "scalar_float.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
StageEventRules::StageEventRules(const std::filesystem::path& assets):items(assets) {
    std::ifstream in(resolveAsset(assets/"stage_event.bin"),std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=68)throw std::runtime_error("Invalid stage event tables");
    std::array<uint8_t,68> data{};in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(data.data()),data.size()))throw std::runtime_error("Truncated stage event tables");
    auto word=[&](unsigned at){uint32_t v=0;for(unsigned b=0;b<4;++b)v|=uint32_t(data[at+b])<<(b*8);return v;};
    for(unsigned i=0;i<flags_.size();++i)flags_[i]=word(i*4);
    z_=std::bit_cast<float>(word(60));roundX_=std::bit_cast<float>(word(64));
}
namespace {
ScalarFloat playerCenter(const StageEventPlayers& p) {
    const auto sum=ScalarFloat{std::bit_cast<uint32_t>(p.x0)}.add({std::bit_cast<uint32_t>(p.x1)});
    //1482d8 truncates the rounded mean BEFORE converting it back to float.
    //Averaging coordinates in double, or truncating each separately, differs
    //at negative/fractional positions and at the inclusive20-unit boundary.
    return ScalarFloat::integer(sum.mul({0x3f000000}).truncate());
}
}
bool StageEventRules::outsideCenter(StageEventActor& a,const StageEventPlayers& p) {
    const auto center=playerCenter(p);
    a.objectFlags=p.mirror0?a.objectFlags|0x80000:a.objectFlags&~0x80000u;
    const auto difference=ScalarFloat{std::bit_cast<uint32_t>(a.x)}.sub(center);
    return !ScalarFloat{difference.bits&0x7fffffffu}.less({0x41a00000});
}
void StageEventRules::request(StageEventActor& a,int state,bool force,const StageEventPlayers& players) const {
    if(a.pending)return;
    if(uint32_t(state)>=flags_.size())throw std::runtime_error("Unknown stage event state");
    const auto flags=flags_[unsigned(state)];
    if((flags&0x100)&&state!=a.state) {
        if(a.flags&0x100)a.pending=state;
        else {a.state=state;a.flags=flags;a.request=1;}
        return;
    }
    //Even forced requests cannot interrupt an active100 event. Requesting
    //the same100 event must not restart it or queue a duplicate.
    if(a.flags&0x100)return;
    if(flags&0x20) {
        if(!force&&(a.flags&0x40))return;
        if(outsideCenter(a,players))return;
    }
    if(!force&&state==a.state)return;
    a.state=state;a.flags=flags;a.request=1;
}
void StageEventRules::place(StageEventActor& a,float x,float y) const {
    a.x=a.targetX=x;a.y=y;a.z=z_;a.dx=a.vx=a.ax=0;
}
void StageEventPlayback::initialize(StageEventActor& a) {
    *this={};a={};
    a.x=a.targetX=320;a.z=50;a.objectFlags=0x30000000;
    body_[0xc/4]=body_[0x10/4]=2;body_[0x14/4]=51;body_[0x1c/4]=51*5;
    body_[0x24/4]=25;body_[0x30/4]=256;body_[0xc8/4]=1;
    body_[0x38/4]=a.objectFlags;body_[0x40/4]=std::bit_cast<uint32_t>(a.x);
    body_[0x48/4]=std::bit_cast<uint32_t>(a.z);body_[0x70/4]=0x3f800000;
}
int StageEventPlayback::visit(StageEventActor& a,const StageEventPlayers& players,int battleState,
                              const GaugeState& gauges,AuxiliaryObjects& objects,ObjectDrawQueue& draws) {
    auto& o=body_;
    const bool outside=StageEventRules::outsideCenter(a,players);
    const float center=std::bit_cast<float>(playerCenter(players).bits);
    int deliver=-1;
    if(a.request) {
        a.request=0;current_=-1;phase_=0;tracking_=false;
        a.x=a.targetX;a.dx=a.vx=a.ax=0;
    }
    // 1b4228 dispatches a requested action even if the stage clock is paused.
    // The clock itself resolves through selector 2 just before movement/draw.
    if(a.flags) {
        if(!phase_) {
            static constexpr int first[]{43,31,25,26,36,37,38,39,40,42,42,44,41,37,36};
            wanted_=first[a.state];phase_=1;
            if(a.state==2&&lowered_){wanted_=28;phase_=2;}
            if(a.state!=6&&a.state!=7)lowered_=false;
            if(a.state>=13)o[0x12c/4]=0;
        } else if(o[0x3c/4]==1) {
            switch(a.state) {
            case 1:case 9:
                if(phase_==1){phase_=2;wanted_=a.state==1?25:43;if(a.state==1)a.y=0;}
                else a.flags=0;
                break;
            case 2:
                if(phase_==2){phase_=1;wanted_=25;}else a.flags=0;
                break;
            case 3:
                if(phase_==1){phase_=2;wanted_=27;}else{lowered_=true;a.flags=0;}
                break;
            case 4:case 5:case 6:case 7:case 13:case 14:
                if(!outside&&phase_==1){phase_=2;wanted_=25;}
                else if(a.state>=13&&a.pending) {
                    // Both fighters can lose a weapon before the first throw
                    // finishes. Only the priority-100 event owns this queue.
                    a.state=a.pending;a.pending=0;a.flags=0x100u+unsigned(a.state-13);a.request=1;
                } else {if((a.state==6||a.state==7)&&!outside)lowered_=false;a.flags=0;}
                break;
            default:a.flags=0;break;
            }
        } else if(a.state>=13&&!o[0x12c/4]&&o[0x28/4]==2) {
            o[0x12c/4]=1;deliver=a.state-13;
        }
    } else {
        if(battleState==4||battleState==5) {
            if(!tracking_&&outside){tracking_=true;a.dx=a.vx=a.ax=0;}
            if(tracking_) {
                const bool walkingMirrored=(wanted_==29||wanted_==30)&&players.mirror0;
                if(a.x<center-2)wanted_=walkingMirrored?30:29;
                else if(a.x>center+2)wanted_=walkingMirrored?29:30;
                else {tracking_=false;wanted_=25;a.dx=a.vx=a.ax=0;}
            }
            a.targetX=a.x;
        } else {tracking_=false;wanted_=25;a.dx=a.vx=a.ax=0;}
    }
    auto loadMotion=[&] {
        MotionState m{};m.x=a.x;m.y=a.y;m.dx=a.dx;m.vx=a.vx;m.ax=a.ax;
        m.dy=std::bit_cast<int32_t>(o[0x58/4]);m.vy=std::bit_cast<int32_t>(o[0x5c/4]);
        m.ay=std::bit_cast<int32_t>(o[0x60/4]);return m;
    };
    auto storeMotion=[&](const MotionState& m) {
        a.x=m.x;a.y=m.y;a.dx=m.dx;a.vx=m.vx;a.ax=m.ax;
        o[0x40/4]=std::bit_cast<uint32_t>(m.x);o[0x44/4]=std::bit_cast<uint32_t>(m.y);
        o[0x4c/4]=uint32_t(m.dx);o[0x50/4]=uint32_t(m.vx);o[0x54/4]=uint32_t(m.ax);
        o[0x58/4]=uint32_t(m.dy);o[0x5c/4]=uint32_t(m.vy);o[0x60/4]=uint32_t(m.ay);
    };
    auto enterRecord=[&] {
        o[0x3c/4]=0;
        if(o[0xc0/4])return;
        auto m=loadMotion();enterMotion(m,objects.record(o).motion,false,false);storeMotion(m);
    };
    if(current_!=wanted_) {
        current_=wanted_;o[0x24/4]=unsigned(current_);
        a.objectFlags|=0x10000000;o[0x28/4]=o[0x2c/4]=o[0xc0/4]=0;enterRecord();
    }
    const auto delta=resolveObjectDelta(256,2,gauges);
    auto m=loadMotion();advanceMotion(m,delta,true,players.mirror0,false);storeMotion(m);
    o[0x38/4]=a.objectFlags;o[0x48/4]=std::bit_cast<uint32_t>(a.z);
    if(!(o[0x104/4]&2))draws.submit(o,gauges);
    // 120ce0 submits the old step, then advances 120ac8. The step-2 sword
    // release is checked on the following visit, before another draw.
    unsigned length=0;const auto record=objects.record(o,&length);
    auto& time=o[0x2c/4];time+=delta;
    if(std::bit_cast<int32_t>(time)>=record.duration*256) {
        time&=255;const auto old=o[0x28/4]++;
        if(o[0x28/4]==length) {
            o[0xc0/4]=1;
            if(record.endKind==2){o[0x28/4]=0;a.objectFlags&=~0x10000000u;}
            else {o[0x28/4]=length-1;o[0x3c/4]=(o[0x3c/4]&~255u)|uint16_t(record.endKind);}
        }
        if(old!=o[0x28/4])enterRecord();
    }
    o[0x38/4]=a.objectFlags;o[0x104/4]&=~2u;
    return deliver;
}
}
