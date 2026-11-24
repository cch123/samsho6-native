#include "asset_files.hpp"
#include "action_runtime.hpp"
#include "fighter_resource_path.hpp"
#include "fighter_roster.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>
#include <string>

namespace ss6 {
namespace {
using Bytes = std::vector<uint8_t>;
Bytes read(const std::filesystem::path& path) {
    std::ifstream stream(resolveAsset(path), std::ios::binary | std::ios::ate);
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
// Victim poses queued by the table-B rows (victim_rows.bin) of every
// playable source fighter: 165f18 queues 0x500+v, and 0x501+v for the
// unarmed form unless the row type is 6 or 0x58.
const std::set<unsigned>& victimPoses(const std::filesystem::path& assets) {
    static std::map<std::filesystem::path,std::set<unsigned>> cache;
    auto found=cache.find(assets);
    if(found!=cache.end())return found->second;
    const auto data=read(assets/"victim_rows.bin");
    std::set<unsigned> poses;
    size_t at=51*8;
    for(unsigned c=0;c<51;++c) {
        const auto n=field(data,c*8+4,4);
        for(uint32_t i=0;i<n;++i,at+=20) {
            const auto v=half(data,at+2);const auto type=data.at(at+19);
            if(!playableFighter(c)||data.at(at)==0xff||v==-1)continue;
            poses.insert(0x500u+unsigned(v));
            if(type!=6&&type!=0x58)poses.insert(0x501u+unsigned(v));
        }
    }
    if(at!=data.size())throw std::runtime_error("Invalid victim_rows.bin");
    for(const auto& r:routineVictimPoses)if(playableFighter(r.source))
        for(unsigned id=r.poses.first;id<=r.poses.last;++id)poses.insert(id);
    return cache.emplace(assets,std::move(poses)).first->second;
}
}

int fighterActionRecord(unsigned resource,unsigned action,int start,unsigned count,int32_t step) {
    // Hanzo's empty-hand reversal really requests the zero-length ACT 693.
    // 1212c0 first reads its start record, then 120c78 leaves the clock at
    // count-1. Both reads must retain ACT 693 for drawing and callbacks.
    // Amakusa's 1f4588 effect requests the zero-length ACT 0x2d9 the same way, as does an unarmed
    // victim of Rasetsu Galford's row 5 (victim ACT 0x54c is empty in every bank); the weaponless
    // banks 45..47 leave every unarmed victim ACT (0x500 + odd) empty, and 11d908 does not check.
    // Their ordinary ACTs also end by jumping into the empty ACTs 49 / 51 / 701 / 770. Makai Gaoh's
    // boss bank (43) leaves 1,592 ACTs empty (count 0, start > 0); its ordinary moves request them.
    const bool sparse=((resource==43)||(resource==3&&action==693)||(resource==11&&action==0x2d9)||(resource==32&&action==0x22c)||(resource==33&&action==0x300)||(action>=0x500&&action<0x600)||
        (resource>=45&&resource<=47&&(action==49||action==51||action==701||action==770)))&&!count&&start>0&&(step==0||step==-1);
    if(start<0||(!sparse&&(step<0||uint32_t(step)>=count)))
        throw std::runtime_error("Invalid ACT record "+std::to_string(action)+" in fighter bank "+std::to_string(resource));
    return start+step;
}

ActionClip::ActionClip(const std::filesystem::path& assets, unsigned id, bool mutedInspection,unsigned resource)
    :ActionClip(read(fighterResourcePath(assets,"aid",resource)),read(fighterResourcePath(assets,"act",resource)),
                id,mutedInspection,resource,victimPoses(assets).count(id)!=0) {}

ActionClip::ActionClip(const Bytes& aid,const Bytes& act,unsigned id,bool mutedInspection,unsigned resource,bool capturePose) : id_(id) {
    // Timing admission is separate from renderer admission. In particular,
    // hit reactions carry a weapon alpha value the inspector must not ignore.
    // Purple Nakoruru's bank (42) carries Nakoruru's actions (148df0 / 11d5b0 logic resource 1).
    const unsigned logic=resource==42?1:resource;
    const bool nakoruruAttack=logic==1&&((id>=38&&id<=43)||(id>=529&&id<=534)||(id>=540&&id<=548)||(id>=554&&id<=558)||
        (id>=564&&id<=565)||(id>=571&&id<=572)||(id>=578&&id<=582)||(id>=588&&id<=590)||(id>=596&&id<=601)||
        (id>=624&&id<=631)||(id>=637&&id<=642)||(id>=655&&id<=660)||(id>=670&&id<=675)||
        id==681||id==682||(id>=691&&id<=704)||id==715||id==716);
    // These original bank-02 body moves are alternately controlled by their
    // ACT and their actor phase. A zero-duration record waits for that phase.
    const bool rimururuAction=resource==2&&(id<=165||(id>=185&&id<=445)||(id>=489&&id<=507)||
        (id>=529&&id<=638));
    // Body moves whose zero-duration records wait for the actor callbacks
    // (fighter_roster.hpp heldActions). capturePose: the victim poses of the
    // playable fighters' table-B rows, supplied by the caller.
    const bool heldAction=heldFighterAction(logic,id);
    if (!capturePose && !heldAction && !nakoruruAttack && !rimururuAction && id>29 && !(id>=34&&id<=37) && !(id>=44&&id<=77) && !(id>=84&&id<=87) && !(id>=92&&id<=95) && !(id>=100&&id<=103) && !(id>=126&&id<=164) &&
        !(id>=185&&id<=240) && !(id>=242&&id<=257) && !(id>=264&&id<=266) && !(id>=278&&id<=305) && !(id>=307&&id<=319) &&
        !(id>=338&&id<=373) && !(id>=378&&id<=395) &&
        !(id>=424&&id<=429) && !(id>=396&&id<=419) && !(id>=430&&id<=441) && !(id>=492&&id<=506) && !(id>=529&&id<=531) && id!=539 && !(id>=549&&id<=554) &&
        !(id>=568&&id<=570) && !(id>=584&&id<=586) && id!=592 && id!=598 && id!=599 && id!=612 && id!=613 && id!=625 && !(id>=1294&&id<=1297) && !(id>=1280&&id<=1285) && id!=1793 &&
        // Presentation actions of the arcade scenes: Continue / Game Over 700 / 701, map walk 703 / 704,
        // VS result pose 1fb, dialogue stands 400 / 401 (arcade_presentation.cpp).
        !(id>=0x700&&id<=0x704) && id!=0x1fb && id!=0x400 && id!=0x401)
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
        if (record.headerFlags&~uint32_t(0xfffc00))
            throw std::runtime_error("Action record requires unimplemented flags (resource "+std::to_string(resource)+
                " ACT "+std::to_string(id)+" record "+std::to_string(step)+" header "+std::to_string(record.headerFlags)+")");
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
        if (record.motion.kind!=0 && record.motion.kind!=1 && record.motion.kind!=2 && record.motion.kind!=5 && record.motion.kind!=9 && record.motion.kind!=10 && record.motion.kind!=11 && record.motion.kind!=12 && record.motion.kind!=13 && record.motion.kind!=14 && record.motion.kind!=15 && record.motion.kind!=16 && record.motion.kind>=0 && record.motion.kind<19)
            throw std::runtime_error("Motion command outside the action integration subset");
        for(unsigned i=0;i<3;++i)record.effectCommand[i]=half(act,offset + 0x2e + i*2);
        // The body and its attached ACT have independent clocks. A zero ID
        // instead asks the actor to consult its current move script.
        if((record.headerFlags&0x400)&&((uint16_t(record.effectCommand[0])&0x1800)<0x1000)&&
           (uint16_t(record.effectCommand[0])&0x7ff)&&!((id==592||id==625)&&record.effectCommand[0]==593)&&
           !(resource==0&&id==502&&record.effectCommand[0]==508)&&
           !(id==164&&record.effectCommand[0]==0x836)&&
           // The only remaining personal attachments in any bank: Purple Nakoruru's ACT 252 (ACT 260)
           // and Poppy's victim ACT 1297 (ACT 68); both go through the generic 1474a0 attachment path.
           !(resource==42&&id==252&&record.effectCommand[0]==260)&&!(resource==44&&id==1297&&record.effectCommand[0]==68)&&
           !heldAction&&!capturePose&&!(nakoruruAttack&&(record.effectCommand[0]==794||record.effectCommand[0]==0x813))&&
           !(rimururuAction&&(record.effectCommand[0]==769||record.effectCommand[0]==774||
                              record.effectCommand[0]==775||(record.effectCommand[0]>=587&&record.effectCommand[0]<=589))))
            throw std::runtime_error("Nonzero attached ACT effect requires object-phase support (ACT "+std::to_string(id)+" bank "+std::to_string(resource)+")");
        // 120bc4 reads the completion field only at the end of the clip.
        // Intermediate charge poses in ACT 158 carry an unused value of 3.
        const bool last=step+1==count;
        // Nakoruru's win poses return to the actor callback twice. The
        // concentration pose and heavy pursuit use the same original hold.
        // 120c78 also accepts zero: the final record stays visible and +c0
        // completes the actor callback with the low end-control byte cleared.
        // Bank 42's own introduction (ACT 492, 22 records) ends with completion 0 where bank 1's ends with 1.
        // A held (callback-released) action of a script fighter may also end by holding its last record.
        // Among all victim ACTs 0x500..0x6ff only bank 47's 0x622 (Iroha's dance victim) ends with 0.
        const bool zeroEnd=record.endKind==0&&(zeroEndAction(logic,int(id))||(resource==42&&id==492)||(resource==47&&id==0x622)||(heldAction&&scriptStubFighter(logic)));
        const bool nakoruruHold=id==154||id==155||capturePose||id==386||id==387||nakoruruAttack||(logic==1&&(id==150||id==151||id==239||id==495||id==497));
        if (record.duration<0 || (record.duration==0 && !heldAction && !nakoruruHold && !rimururuAction && !(record.headerFlags&0x4000) && id!=492 && !(id>=232&&id<=235) && id!=225 && id!=226 && id!=229 && id!=238 && id!=426 && id!=427 && id!=428 && id!=429 && id!=430 && id!=431 && id!=266 && id!=342 && id!=343 && id!=392 && id!=393 && !(id>=209&&id<=218) && !(id>=549&&id<=551) && !(id>=568&&id<=570) && !(id>=529&&id<=531) && id!=1284 && id!=1285 && id!=130 && !(id>=133&&id<=135) && id!=140 && id!=26 && id!=27 && id!=36) ||
            (last && !(record.headerFlags&0x8000) && !zeroEnd  && record.endKind!=1 && record.endKind!=2) ||
            (last && (record.headerFlags&0x8000) && record.endKind<0))
            throw std::runtime_error("Unsupported duration or completion command in ACT "+std::to_string(id)+
                " (bank "+std::to_string(resource)+" record "+std::to_string(step)+"/"+std::to_string(count)+
                " duration "+std::to_string(record.duration)+" end "+std::to_string(record.endKind)+
                " flags "+std::to_string(record.headerFlags)+")");
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
    if((record.headerFlags&0x2000)&&voiceCutObserver_)voiceCutObserver_();
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
    return clips_.emplace(id,ActionClip(aid_,act_,id,mutedInspection_,resource_,victimPoses(assets_).count(id)!=0)).first->second;
}
} // namespace ss6
