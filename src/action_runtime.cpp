#include "action_runtime.hpp"
#include "fighter_resource_path.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
using Bytes = std::vector<uint8_t>;
Bytes read(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw std::runtime_error("Cannot read " + path.string());
    auto size = stream.tellg();
    if (size < 0 || size > 16*1024*1024) throw std::runtime_error("Invalid action resource size");
    Bytes bytes(static_cast<size_t>(size));
    stream.seekg(0);
    if (!stream.read(reinterpret_cast<char*>(bytes.data()), size)) throw std::runtime_error("Truncated action resource");
    return bytes;
}
uint32_t field(const Bytes& data, size_t offset, size_t width) {
    if (offset > data.size() || width > data.size()-offset) throw std::runtime_error("Action field out of bounds");
    uint32_t value = 0;
    for (size_t i=0; i<width; ++i) value |= uint32_t(data[offset+i]) << (8*i);
    return value;
}
int16_t half(const Bytes& data, size_t offset) { return std::bit_cast<int16_t>(uint16_t(field(data,offset,2))); }
}

int fighterActionRecord(unsigned resource,unsigned action,int start,unsigned count,int32_t step) {
    // Hanzo's empty-hand reversal really requests the zero-length ACT 693.
    // 1212c0 first reads its start record, then 120c78 leaves the clock at
    // count-1. Both reads must retain ACT 693 for drawing and callbacks.
    const bool sparse=resource==3&&action==693&&!count&&start>0&&(step==0||step==-1);
    if(start<0||(!sparse&&(step<0||uint32_t(step)>=count)))
        throw std::runtime_error("Invalid ACT record "+std::to_string(action)+" in fighter bank "+std::to_string(resource));
    return start+step;
}

ActionClip::ActionClip(const std::filesystem::path& assets, unsigned id, bool mutedInspection,unsigned resource)
    :ActionClip(read(fighterResourcePath(assets,"aid",resource)),read(fighterResourcePath(assets,"act",resource)),
                id,mutedInspection,resource) {}

ActionClip::ActionClip(const Bytes& aid,const Bytes& act,unsigned id,bool mutedInspection,unsigned resource) : id_(id) {
    // Timing admission is separate from renderer admission. In particular,
    // hit reactions carry a weapon alpha value the inspector must not ignore.
    const bool nakoruruAttack=resource==1&&((id>=38&&id<=43)||(id>=529&&id<=534)||(id>=540&&id<=548)||(id>=554&&id<=558)||
        (id>=564&&id<=565)||(id>=571&&id<=572)||(id>=578&&id<=582)||(id>=588&&id<=590)||(id>=596&&id<=601)||
        (id>=624&&id<=631)||(id>=637&&id<=642)||(id>=655&&id<=660)||(id>=670&&id<=675)||
        id==681||id==682||(id>=691&&id<=704)||id==715||id==716);
    // These original bank-02 body moves are alternately controlled by their
    // ACT and their actor phase. A zero-duration record waits for that phase.
    const bool rimururuAction=resource==2&&(id<=165||(id>=185&&id<=445)||(id>=489&&id<=507)||
        (id>=529&&id<=638));
    // Hanzo's capture and disappearance animations hold records until
    // their actor callbacks explicitly resume them.
    const bool hanzoAction=resource==3&&(id<=165||(id>=185&&id<=445)||(id>=489&&id<=507)||(id>=529&&id<=754));
    // Mina's bank-24 body moves follow the same actor-held record rules as
    // Hanzo's: her script interpreter and callbacks resume held records.
    const bool minaAction=resource==24&&(id<=166||(id>=185&&id<=445)||(id>=489&&id<=509)||(id>=517&&id<=720));
    // 1499/1500 and 1502/1503 are the shared victim poses of Mina's table-B rows 1 and 3.
    const bool capturePose=(id>=1299&&id<=1304)||(id>=1307&&id<=1308)||(id>=1310&&id<=1322)||(id>=1325&&id<=1326)||id==1499||id==1500||id==1502||id==1503;
    if (!capturePose && !hanzoAction && !minaAction && !nakoruruAttack && !rimururuAction && id>29 && !(id>=34&&id<=37) && !(id>=44&&id<=77) && !(id>=84&&id<=87) && !(id>=92&&id<=95) && !(id>=100&&id<=103) && !(id>=126&&id<=164) &&
        !(id>=185&&id<=240) && !(id>=242&&id<=257) && !(id>=264&&id<=266) && !(id>=278&&id<=305) && !(id>=307&&id<=319) &&
        !(id>=338&&id<=373) && !(id>=378&&id<=387) &&
        !(id>=390&&id<=393) && !(id>=396&&id<=419) && !(id>=430&&id<=441) && !(id>=492&&id<=506) && !(id>=529&&id<=531) && id!=539 && !(id>=549&&id<=554) &&
        !(id>=568&&id<=570) && !(id>=584&&id<=586) && id!=592 && id!=598 && id!=599 && id!=612 && id!=613 && id!=625 && !(id>=1294&&id<=1297) && !(id>=1280&&id<=1285) && id!=1793)
        throw std::runtime_error("Unsupported action "+std::to_string(id));
    if (aid.size() != 0x1800 || act.size()%60) throw std::runtime_error("Unsupported AID/ACT resource layout");
    // 0x1212c0 reads signed AID starts and multiplies the record number by 60.
    // 0x120bc4 separately reads the per-action byte count at AID + 0x1000.
    const int16_t start = half(aid,id*2);
    const int count = aid[0x1000+id];
    recordCount_=unsigned(count);
    if ((size_t(fighterActionRecord(resource,id,start,count,count?count-1:0))+1)*60 > act.size())
        throw std::runtime_error("Invalid ACT "+std::to_string(id)+" in fighter bank "+std::to_string(resource));
    for (int step=count?0:-1; step<std::max(1,count); ++step) {
        const size_t offset = size_t(start+step)*60;
        // Fail explicitly on commands outside the admitted revision/subset;
        // ignoring an unknown motion or effect would hide missing behavior.
        ActionRecord record{};
        record.headerFlags=field(act,offset,4);
        if (record.headerFlags&~uint32_t(0xffdc00))
            throw std::runtime_error("Action record requires unimplemented flags");
        for (size_t part=0; part<record.parts.size(); ++part) record.parts[part] = half(act,offset+4+part*2);
        record.duration = half(act,offset+0x34);
        record.endKind = half(act,offset+0x3a);
        record.sourceRecord = uint32_t(start+step);
        record.motion.kind = half(act,offset+0x20);
        for (size_t i=0; i<6; ++i) record.motion.values[i]=half(act,offset+0x22+i*2);
        for (size_t i=0; i<8; ++i) record.judgmentRefs[i]=half(act,offset + 0x0e + i*2);
        record.judgmentFlags = uint16_t(field(act,offset+0x1e,2));
        record.soundCommand = half(act,offset+0x38);
        if (record.soundCommand && !mutedInspection)
            throw std::runtime_error("Sound-bearing ACT requires an enabled sound-command consumer or muted inspection");
        if (record.motion.kind!=0 && record.motion.kind!=1 && record.motion.kind!=2 && record.motion.kind!=5 && record.motion.kind!=9 && record.motion.kind!=10 && record.motion.kind!=11 && record.motion.kind!=12 && record.motion.kind!=13 && record.motion.kind!=14 && record.motion.kind!=15 && record.motion.kind!=16 && record.motion.kind!=19)
            throw std::runtime_error("Motion command outside the action integration subset");
        for(unsigned i=0;i<3;++i)record.effectCommand[i]=half(act,offset + 0x2e + i*2);
        // The body and its attached ACT have independent clocks. A zero ID
        // instead asks the actor to consult its current move script.
        if((record.headerFlags&0x400)&&((uint16_t(record.effectCommand[0])&0x1800)<0x1000)&&
           (uint16_t(record.effectCommand[0])&0x7ff)&&!((id==592||id==625)&&record.effectCommand[0]==593)&&
           !(resource==0&&id==502&&record.effectCommand[0]==508)&&
           !(id==164&&record.effectCommand[0]==0x836)&&
           !hanzoAction&&!minaAction&&!(nakoruruAttack&&(record.effectCommand[0]==794||record.effectCommand[0]==0x813))&&
           !(rimururuAction&&(record.effectCommand[0]==769||record.effectCommand[0]==774||
                              record.effectCommand[0]==775||(record.effectCommand[0]>=587&&record.effectCommand[0]<=589))))
            throw std::runtime_error("Nonzero attached ACT effect requires object-phase support");
        // 120bc4 reads the completion field only at the end of the clip.
        // Intermediate charge poses in ACT 158 carry an unused value of 3.
        const bool last=step+1==count;
        // Nakoruru's win poses return to the actor callback twice. The
        // concentration pose and heavy pursuit use the same original hold.
        // 120c78 also accepts zero: the final record stays visible and +c0
        // completes the actor callback with the low end-control byte cleared.
        const bool zeroEnd=record.endKind==0&&((resource==1&&(id==162||id==163))||(resource==3&&id==732));
        const bool nakoruruHold=id==154||id==155||capturePose||id==386||id==387||nakoruruAttack||(resource==1&&(id==150||id==151||id==239||id==495||id==497));
        if (record.duration<0 || (record.duration==0 && !hanzoAction && !minaAction && !nakoruruHold && !rimururuAction && !(record.headerFlags&0x4000) && id!=492 && !(id>=232&&id<=235) && id!=225 && id!=226 && id!=229 && id!=238 && id!=430 && id!=431 && id!=266 && id!=342 && id!=343 && id!=392 && id!=393 && !(id>=209&&id<=218) && !(id>=549&&id<=551) && !(id>=568&&id<=570) && !(id>=529&&id<=531) && id!=1284 && id!=1285 && id!=130 && !(id>=133&&id<=135) && id!=140 && id!=26 && id!=27 && id!=36) ||
            (last && !(record.headerFlags&0x8000) && !zeroEnd  && record.endKind!=1 && record.endKind!=2) ||
            (last && (record.headerFlags&0x8000) && record.endKind<0))
            throw std::runtime_error("Unsupported duration or completion command in ACT "+std::to_string(id));
        records_.push_back(record);
    }
}

const ActionRecord& ActionClip::record(uint32_t step) const { return records_.at(step+unsigned(recordCount_==0)); }
uint32_t ActionClip::cycleTicks() const {
    uint32_t ticks = 0;
    for (uint32_t step=0;step<recordCount_;++step) ticks += uint32_t(record(step).duration);
    return ticks;
}

bool ActionTimeline::advance(uint32_t resolvedDelta) {
    // 0x120ce0 advances movement before the action timer. Ground inspection
    // uses object +0xc8 == 1 and the ordinary clock, without battle clamps.
    advanceMotion(motion_,resolvedDelta,true,clock_.objectFlags&0x80000,clock_.objectFlags&0x40000);
    return advanceClock(resolvedDelta);
}
void ActionTimeline::advanceMovement(uint32_t resolvedDelta) {
    clampRetreat(motion_,clock_.flags108);
    advanceMotion(motion_,resolvedDelta,true,clock_.objectFlags&0x80000,clock_.objectFlags&0x40000);
}
bool ActionTimeline::advanceClock(uint32_t resolvedDelta,bool suppressActionJump) {
    const auto previous = clock_.step;
    clock_.fractionalTime += resolvedDelta;
    const int32_t deadline = int32_t(record().duration)*256;
    // 0x120b1c compares signed 32-bit time with duration << 8. Preserve the
    // original wrap and its single-transition limit, even for a large delta.
    if (std::bit_cast<int32_t>(clock_.fractionalTime) < deadline) return false;
    if (record().headerFlags&0x4000) {
        // 0x120b40 tests truncated Y plus the integer pending displacement,
        // not next-frame velocity. A landing hold keeps accumulating time.
        const float y=float(int32_t(motion_.y)),dy=float(motion_.dy>>16);
        const float next=(clock_.objectFlags&0x40000) ? y-dy : y+dy;
        if (int32_t(next)>0) return false;
        motion_.y=0;motion_.dy=motion_.vy=motion_.ay=0;
        clock_.endControl|=0x100;
    }
    // 0x120b98 keeps only the low fractional byte; subtracting the deadline or
    // looping until caught up would change original behavior at high speeds.
    clock_.fractionalTime &= 0xff;
    if (std::bit_cast<int32_t>(++clock_.step) >= int32_t(action_->size())) {
        const auto& last=action_->record(previous);
        const auto kind=last.endKind;
        if ((last.headerFlags&0x8000)&&!suppressActionJump) {
            if (!bank_) throw std::runtime_error("ACT action jump requires an ActionBank");
            action_=&bank_->get(unsigned(kind));
            clock_.chainedAction=kind;
            clock_.step=0;
            clock_.flags104&=~uint32_t(0x04000000);
            // 0x120bf4 jumps without the start-action reset: fractional time,
            // completion and movement survive. It enters even if step was 0.
            enterRecord();
            return true;
        }
        clock_.step = kind==2 ? 0 : action_->size()-1;
        clock_.endReached = 1;
        if (kind==2) clock_.objectFlags &= ~uint32_t(0x10000000);
        else clock_.endControl=(clock_.endControl&0xffffff00)|uint32_t(kind);
    }
    if (previous != clock_.step) enterRecord();
    return previous != clock_.step;
}
void ActionTimeline::enterRecord() {
    clock_.endControl=0;
    const auto& record=action_->record(clock_.step);
    pendingRecordDamage_=uint8_t(record.headerFlags>>16);
    clock_.flags104&=~0x18000u;
    if(record.headerFlags&0x400) {
        const uint16_t command=uint16_t(record.effectCommand[0]);
        const unsigned mode=command&0x1800,id=command&0x7ff;
        if(mode==0||mode==0x800) {
            attachedEffect_={int32_t(id),record.effectCommand[1],record.effectCommand[2]};
            clock_.flags104|=mode==0?0x8000:0x18000;
        } else if(mode==0x1000&&id) {
            if(!effectObserver_)throw std::runtime_error("ACT world effect requires a shared scheduled-effect owner");
            //1204e0 uses signed HIGH halfwords of pending displacement,
            //before120f40 can reset motion. Y command offset itself is
            //always added; only the pending Y displacement follows mirrorY.
            auto x=ScalarFloat{std::bit_cast<uint32_t>(motion_.x)};
            auto y=ScalarFloat{std::bit_cast<uint32_t>(motion_.y)};
            const auto dx=ScalarFloat::integer(motion_.dx>>16),dy=ScalarFloat::integer(motion_.dy>>16);
            x=(clock_.objectFlags&0x80000)?x.sub(dx):x.add(dx);
            y=(clock_.objectFlags&0x40000)?y.sub(dy):y.add(dy);
            const auto ox=ScalarFloat::integer(record.effectCommand[1]);
            x=(clock_.objectFlags&0x80000)?x.sub(ox):x.add(ox);
            y=y.add(ScalarFloat::integer(record.effectCommand[2]));
            effectObserver_(id,clock_.objectFlags,std::bit_cast<float>(x.bits),std::bit_cast<float>(y.bits));
        }
    }
    // The match observer also runs while muted to preserve the selector's RNG.
    if (record.soundCommand) {
        lastSound_=record.soundCommand; ++soundEvents_;
        if(soundObserver_)soundObserver_(record.soundCommand,clock_);
    }
    //120f40's motion-inhibit bit also applies on a forced same-action
    //restart (FE8 ->10440). Do not overwrite residual velocity in that case.
    //120f4c additionally skips completed records unless reentry is requested.
    if (!(clock_.flags104&0x40)&&(!clock_.endReached || (clock_.flags104&1)))
        enterMotion(motion_,record.motion,clock_.flags108&0x200,clock_.flags104&0x80);
}
void ActionTimeline::reset() {
    clock_={}; motion_={}; attachedEffect_={}; lastSound_=0; soundEvents_=0; enterRecord();
}
void ActionTimeline::start(const ActionClip& action) {
    action_=&action;
    clock_.step=clock_.fractionalTime=clock_.endReached=clock_.endControl=0;
    clock_.objectFlags|=0x10000000;
    // 0x120390 does not clear velocity or world position. The actor callback
    // must explicitly stop movement where the original calls 0x11d990.
    enterRecord();
}
void ActionTimeline::stopMotion() {
    motion_.dx=motion_.vx=motion_.ax=motion_.dy=motion_.vy=motion_.ay=0;
    // 0x11d990 also releases the zero-duration hold. KO landing callbacks
    // depend on this to resume the bounce on the next animation pass.
    clock_.flags104&=~uint32_t(0x40|0x100);
}
const ActionClip& ActionBank::get(unsigned id) {
    auto found=clips_.find(id);
    if (found!=clips_.end()) return found->second;
    // Read the selected fighter's resident tables once, including when a
    // clip jumps to another ACT. A failed second read is retried next time.
    if(act_.empty()) {
        aid_=read(fighterResourcePath(assets_,"aid",resource_));
        act_=read(fighterResourcePath(assets_,"act",resource_));
    }
    return clips_.emplace(id,ActionClip(aid_,act_,id,mutedInspection_,resource_)).first->second;
}
} // namespace ss6
