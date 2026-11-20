#include "battle_gauges.hpp"
#include "fighter_roster.hpp"
#include "battle_round.hpp"
#include "sound_selection.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
uint32_t BattleGauges::start(BattleRoundState& b) {
    //The original does not deduplicate registrations. Lifecycle ordering
    //must prevent unintended duplicate updates, not a hidden singleton.
    return b.entry.tasks.createTask(5,0x11e708,0x10,0x1b5a);
}
void BattleGauges::stop(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) {
    for(const auto& p:players)if(p.config.system==4) {
        // 11e600 discards the time left but keeps stored meditation.
        p.actor.systemTime144=0;
        if(p.actor.systemState13c==3)p.actor.systemState13c=4;
    }
    b.entry.tasks.cancelTasks(0x1b5a);
    // Preserve the two holes in the global arrays, global pause and the
    // lower 512 palette entries when restoring normal combat speed.
    for(unsigned i:{0u,1u,2u,3u,4u,6u,7u,8u,10u,11u})b.gauges.words910[i]=0;
    b.gauges.delta46a908=b.gauges.scale1239d84=b.gauges.scale1239d88=256;
    std::fill(b.gauges.paletteTones.begin()+512,b.gauges.paletteTones.end(),0);
}
void BattleGauges::startExplosion(BattleRoundState& b,StateEntryActor& a,unsigned player,int system) const {
    if(player==UINT32_MAX)return; // 11f270 accepts the -1 sentinel
    if(player>=2)throw std::out_of_range("Invalid explosion player");
    auto& g=b.gauges;
    g.words910.at(2+player)|=2;
    // 14f518 takes the fixed-duration branch for the Zero sword style.
    meters_.beginTenExplosion(a,system);
    const uint32_t otherPhase=g.words910.at(1-player);
    // The other side's still-pending effect takes precedence. Finishing the
    // first of two concurrent explosions must not prematurely restore time.
    g.scale1239d84=(otherPhase==3||otherPhase==5)?0:otherPhase==6?64:256;
}
void BattleGauges::beginConcentration(BattleRoundState& b,unsigned player) {
    auto& g=b.gauges;
    g.scale1239d84=0;g.words910.at(player)=5;g.words910.at(2+player)|=1;
    std::fill(g.paletteTones.begin()+512,g.paletteTones.end(),1);
}
void BattleGauges::endConcentration(BattleRoundState& b,StateEntryActor& actor,unsigned player) {
    auto& g=b.gauges;
    actor.systemTime144=0;actor.systemState13c=4;
    g.words910.at(2+player)&=~1u;g.words910.at(player)=2;
    if(!(g.words910.at(2+(1-player))&1)) {
        g.scale1239d84=256;
        std::fill(g.paletteTones.begin()+512,g.paletteTones.end(),0);
    }
}
void BattleGauges::releaseConcentration(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) const {
    auto& g=b.gauges;
    for(unsigned i=0;i<players.size();++i)if(g.words910[i]==5) {
        g.words910[i]=6;
        auto& actor=players[i].actor;
        if(players[i].config.system==4&&actor.systemState13c!=4) {
            meters_.activateConcentration(actor);
            const auto other=g.words910[1-i];
            g.scale1239d84=other==3||other==5?0:64;
            if(actor.flags248&0x10000)endConcentration(b,actor,i);
        }
        break;
    }
}
void BattleGauges::releaseExplosion(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players) const {
    // World effect 4 does not store the triggering player. Each completion
    // consumes the first queued phase in seat order, including simultaneous use.
    for(unsigned i=0;i<players.size();++i)if(b.gauges.words910[i]==3) {
        b.gauges.words910[i]=4;
        startExplosion(b,players[i].actor,i,players[i].config.system);
        break;
    }
}
void BattleGauges::task(BattleRoundState& b,const std::array<RoundPlayerRef,2>& players,SoundSelection* sound) const {
    auto& g=b.gauges;
    //Keep the low32-bit product and LOGICAL shift. This global delta is
    //updated even when the actor meters subsequently return at their gates.
    g.delta46a908=g.paused46a940?0:(g.scale1239d84*g.scale1239d88)>>8;
    if(b.requestedState!=4||b.timers.lock>0||g.paused46a940)return;
    for(unsigned i=0;i<2;++i) {
        const auto& p=players[i];auto& a=p.actor;
        if(!playableFighter(a.character)||p.config.character!=a.character||(unsigned(p.config.system)>5&&p.config.system!=8))
            throw std::runtime_error("Gauge task requires supported fighters and an ordinary battle spirit");
        if(p.config.system==4) {
            if(a.systemState13c<3) {
                const auto& foe=b.match.players[1-i];
                a.systemState13c=foe.wins<foe.requiredWins-1?0:
                    (a.systemAmount140<a.fieldA30*256?1:2);
            }
            meters_.transferMeditation(a);
            if(a.systemState13c==3&&a.state194!=0x250001) {
                if(b.field08!=1)a.systemTime144-=a.systemDecay148;
                if(a.systemTime144<=0)endConcentration(b,a,i);
            }
        }
        DamageActor m;m.character=a.character;m.system=p.config.system;
        m.rageState=a.rageState120;m.rageAmount=a.rageAmount124;m.rageDecay=a.rageDecay128;m.rageCharge=a.rageCharge12c;
        m.swordCurrent=a.swordCurrent134;m.swordMaximum=a.swordMaximum138;m.swordWait=a.swordWait130;
        m.flags23c=a.flags23c;
        const auto flags=a.effectiveFlags();
        m.attackStrength=(flags&4)?2:(flags&2)?1:0;
        const auto c=p.body.timeline.clock();uint32_t flags108=c.flags108;
        bool chargeFilled=false;
        const auto changed=meters_.advanceOrdinaryMeters(m,a.stateTable(),a.stateIndex(),c.flags104,flags108,b.field08==1,&chargeFilled);
        if(chargeFilled){b.camera.requestShake(-1,30);if(sound)sound->sample(-1,61);}
        a.rageState120=m.rageState;a.rageAmount124=m.rageAmount;a.rageDecay128=m.rageDecay;a.rageCharge12c=m.rageCharge;
        a.swordCurrent134=m.swordCurrent;a.swordMaximum138=m.swordMaximum;a.swordWait130=m.swordWait;
        if(changed)g.words910[i]=2; //11e6f0, rage2 expiry only
        if(a.bonusState14c==1) {
            //Any nonzero delay decrements, including negative raw words.
            //The cap uses configured player identity, not the opponent's HP.
            if(a.bonusTime150)a.bonusTime150=std::bit_cast<int32_t>(uint32_t(a.bonusTime150)-1);
            else {
                const auto limit=int32_t(g.bonusLimits[i])<<8;
                a.systemMeter158=std::bit_cast<int32_t>(uint32_t(a.systemMeter158)+uint32_t(a.bonusRate154));
                if(a.systemMeter158>=limit){a.systemMeter158=limit;a.bonusState14c=0;}
            }
        }
        p.body.setFlags(c.flags104,flags108);GroundStateRuntime::captureBody(p.body,a);
    }
}
}
