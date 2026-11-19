#include "reaction.hpp"
#include "knockdown.hpp"
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
bool updateGroundReaction(PlayerObject& object) {
    const auto c=object.timeline.clock();
    object.setFlags((c.flags104|0x2000)&~uint32_t(0x100),c.flags108);
    return c.endReached&&!(c.flags104&1);
}
bool applyCapturedHit(ReactionTarget& t,unsigned rawType) {
    if(rawType<36||rawType>=64)throw std::runtime_error("Invalid captured reaction");
    if(t.flags23c&0x02000000) {
        t.flags23c=(t.flags23c|0x04000000)&~0x02000000u;
        return false;
    }
    // Raw 36+ bypasses common reaction 14d198, including its hitstop and
    // repeated-hit bookkeeping. The descriptor byte selects a captured state.
    t.pendingTable=2;t.pendingState=int16_t(80+rawType-36);t.forceState=true;
    return true;
}
ReactionTables::ReactionTables(const std::filesystem::path& assets) {
    std::ifstream file(assets/"reaction_common.bin",std::ios::binary|std::ios::ate);
    if (!file || file.tellg()!=2048) throw std::runtime_error("Expected 2048-byte reaction_common.bin");
    file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(data_.data()),data_.size())) throw std::runtime_error("Truncated reaction tables");
}
ReactionDescriptor ReactionTables::descriptor(unsigned state) const {
    if (state>=80) throw std::runtime_error("Character-specific reaction descriptor not implemented");
    size_t offset=864+state*14;
    auto half=[&](unsigned n) { return uint16_t(data_[offset+n])|uint16_t(data_[offset+n+1])<<8; };
    return {uint16_t(half(0)),std::bit_cast<int16_t>(uint16_t(half(2))),std::bit_cast<int16_t>(uint16_t(half(4))),
            uint16_t(half(6)),uint16_t(half(8)),{data_[offset+10],data_[offset+11],data_[offset+12],data_[offset+13]}};
}
unsigned ReactionTables::ordinaryAction(unsigned state,bool armed,bool onBack) const {
    if(state==52||state==53)return 408+2*(state-52)+!armed;
    if(state==54)return 414+!armed;
    if(state==58)return 430+!armed;
    if(state==75)return 412+!armed;
    if(state>=55&&state<=57)return 432+(state-55)*2+!armed;
    if(state==61)return (onBack?418:416)+!armed; // 170960, hit while down.
    if(state==74)return 378+!armed; // 175538 chooses the airborne hit action at 4e8c48.
    if(KnockdownPlayback::supportsFall(int(state)))return KnockdownPlayback::fallAction(int(state),armed);
    if (state<32 || state>=50) throw std::runtime_error("Reaction action outside grounded slash subset");
    unsigned group=(state-32)/3,strength=(state-32)%3;
    size_t offset=1984+group*4;
    uint32_t base=uint32_t(data_[offset])|uint32_t(data_[offset+1])<<8|
                  uint32_t(data_[offset+2])<<16|uint32_t(data_[offset+3])<<24;
    return base+strength*2+!armed;
}
bool ReactionTables::applyGuard(ReactionTarget& target,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                               unsigned defense,unsigned strength,unsigned& action) const {
    if (defense<1||defense>4||strength>2)
        throw std::runtime_error("Unsupported guard reaction");
    if (target.flags244&0x80000) return false;
    // 14d628 requests normal 53 for a perfect guard. Its stop timers
    // come from damage descriptor 8 regardless of the incoming strength.
    const unsigned state=defense==3?8: defense==4?6:strength+(defense==2?3:0);
    const auto timing=descriptor(state);
    target.pendingTable=defense==3?0:2;target.pendingState=defense==3?53:int16_t(state);target.forceState=true;
    if(defense!=3)target.flags244&=~uint32_t(0x02000000);
    sourceTimers.set(0,timing.firstTimer);sourceTimers.set(1,timing.secondTimer);
    targetTimers.set(0,timing.firstTimer+(defense==2 ? 2 : 0));
    targetTimers.set(1,timing.secondTimer);
    //14d650 sets this even for ordinary guard. It belongs to the input
    //timer pass, independently of the two contact-pause timers above.
    targetTimers.set(32,3);
    // 0x1705a8 uses the same action for all three guard strengths. Strength
    // still selects the descriptor above; it must not be discarded there.
    action=(defense==3 ? 316u : defense==4 ? 308u : defense==2 ? 292u : 288u)+!(target.flags23c&0x1000);
    return true;
}
void ReactionTables::startRetreat(unsigned state,MotionState& motion,uint32_t& flags108,int opponentAuxiliary) const {
    const auto timing=descriptor(state);
    if (!timing.horizontalVelocity&&!timing.horizontalAcceleration) return;
    motion.vx=int32_t(timing.horizontalVelocity)*256;
    motion.ax=int32_t(timing.horizontalAcceleration)*256;
    if ((flags108&0x200)&&opponentAuxiliary>=2) {
        motion.vx=-motion.vx;motion.ax=-motion.ax;
    }
    if (motion.vx>0) flags108|=0x400;
    if (motion.vx<0) flags108|=0x800;
}
LightReaction ReactionTables::applyLightHit(ReactionTarget& target,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                                          unsigned bodyPart,bool special,bool sourceAirborne) const {
    uint32_t sourceFlags=0;
    return applyGroundHit(target,sourceTimers,targetTimers,10,bodyPart,special,sourceAirborne,0,sourceFlags);
}
LightReaction ReactionTables::applyGroundHit(ReactionTarget& target,ActorTimers& sourceTimers,ActorTimers& targetTimers,
                                          unsigned rawType,unsigned bodyPart,bool special,bool sourceAirborne,
                                          unsigned sourceStrength,uint32_t& sourceFlags248,bool sourceSpecialMove) const {
    // Raw 21 is Hanzo's CCD finisher. Its entire reaction row points to
    // the forward fall (2/62), including an airborne target.
    const bool ordinaryStrike=(rawType>=10&&rawType<=12)||(rawType>=16&&rawType<=21)||
                              (rawType>=23&&rawType<=31)||rawType==34||rawType==35;
    if(!ordinaryStrike||sourceStrength>2)throw std::runtime_error("Unsupported contact source");
    if (bodyPart>2)
        throw std::runtime_error("Reaction outside ordinary target subset");
    unsigned posture=(target.flags23c&0x10) ? 2 : (target.flags23c&0x40) ? 3 : bool(target.flags23c&8);
    if ((target.flags24c&2) && target.stateTable!=2) posture+=4;
    const unsigned row=rawType*24+bodyPart*8;
    unsigned state=data_[row+posture];
    // 14d324 takes airborne contact pause from the standing column of the
    // same body part. The alternate airborne column (posture 6) keeps its own.
    const unsigned secondary=posture==2 ? data_[row] : state;
    if (special) {
        if (state>=32&&state<=34) state+=12;
        else if (state>=35&&state<=40) state+=9;
        else if (state>=41&&state<=43) state+=3;
    }
    if (sourceAirborne) {
        if (state>=32&&state<=34) state+=9;
        if (state>=35&&state<=37) state+=6;
    }
    // 14d398 skips both normal-attack history flags for attack states
    // 64 and above, even when the special shares a normal JDG contact type.
    const bool heavy=!sourceSpecialMove&&state>=32&&state<50&&(state-32)%3==2;
    if(!sourceSpecialMove&&sourceStrength==2) {
        if(heavy&&target.heavyReaction)state=64;
        sourceFlags248|=0x40000000;
    }
    // Repeated hits alternate the standing upper/lower reaction groups.
    // Secondary timing retains the table selection BEFORE this alteration.
    if (state>=32&&state<=34 && target.previousReaction>=32&&target.previousReaction<=34) state+=3;
    else if (state>=35&&state<=37 && target.previousReaction>=35&&target.previousReaction<=37) state-=3;
    unsigned action=ordinaryAction(state,target.flags23c&0x1000,target.flags244&0x8000);
    auto timing=descriptor(secondary);
    if (target.flags23c&0x02000000) {
        target.flags23c=(target.flags23c|0x04000000)&~uint32_t(0x02000000);
    } else {
        target.pendingTable=2;
        target.pendingState=int16_t(state);
        target.forceState=true;
    }
    sourceTimers.set(0,timing.firstTimer); sourceTimers.set(1,timing.secondTimer);
    targetTimers.set(0,timing.firstTimer); targetTimers.set(1,timing.secondTimer);
    target.previousReaction=uint8_t(state);
    target.heavyReaction=heavy;
    target.secondaryReaction=uint8_t(secondary);
    return {state,secondary,action};
}
} // namespace ss6
