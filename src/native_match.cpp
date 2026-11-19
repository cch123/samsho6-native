#include "native_match.hpp"
#include "cpu_decision.hpp"
#include "thrown_stage_item.hpp"
#include "mamahaha.hpp"
#include "konru.hpp"
#include "rimururu_special.hpp"
#include "hanzo_projectile.hpp"
#include "chample.hpp"
#include "mina_special.hpp"
#include "fighter_roster.hpp"
#include "contact_presentation.hpp"
#include "console_versus_session.hpp"
#include "finishing_blow.hpp"
#include "fighter_depth.hpp"
#include "weapon_deflection.hpp"
#include "haohmaru_flask.hpp"
#include "combined_slash.hpp"
#include "throw_victim.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
// The result task reads the software controller's physical word directly.
// Unlike the fighters, it never runs the attack/chord input decoder.
uint32_t resultPad(uint32_t logical) {
    constexpr std::array<uint32_t,8> physical{0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000};
    uint32_t bits=logical&0xf8;
    for(unsigned i=0;i<physical.size();++i)if(logical&(PadLight<<i))bits|=physical[i];
    return bits;
}
DamageActor meter(const StateEntryActor& a,unsigned system) {
    DamageActor m;m.character=a.character;m.system=int32_t(system);m.state194=a.state194;
    m.swordCurrent=a.swordCurrent134;m.swordMaximum=a.swordMaximum138;m.swordWait=a.swordWait130;
    m.rageState=a.rageState120;m.rageAmount=a.rageAmount124;m.rageDecay=a.rageDecay128;
    m.systemAmount140=a.systemAmount140;m.concentrationUsed11c=a.concentrationUsed11c;
    m.defenseAdjustment=int(a.fieldA50);m.life=a.fieldA30;m.flags23c=a.flags23c;m.flags248=a.flags248;m.armed=a.flags23c&0x1000;
    m.attackStrength=(a.effectiveFlags()&4)?2:(a.effectiveFlags()&2)?1:0;
    return m;
}
void storeMeter(StateEntryActor& a,const DamageActor& m) {
    a.swordCurrent134=m.swordCurrent;a.swordMaximum138=m.swordMaximum;a.swordWait130=m.swordWait;
    a.rageState120=m.rageState;a.rageAmount124=m.rageAmount;a.rageDecay128=m.rageDecay;
    a.flags23c=m.flags23c;a.flags248=m.flags248;
}
}
NativeMatch::NativeMatch(const std::filesystem::path& path,int roundTime,VersusMode mode,const NativeMatch* rematchFrom,
                         std::array<unsigned,2> spirits,std::optional<VersusLineup> selection,int selectedStage,
                         std::array<CpuSeatDecision,2> cpuSeats)
    :assets_(path),lineup_(selection.value_or(rematchFrom?rematchFrom->lineup():VersusLineup{{{0,spirits[0],0},{0,spirits[1],1}}})),
     resourceSlots_{lineup_[0].character,lineup_[1].character,51},
     banks_{ActionBank(path,true,resourceSlots_[0]),ActionBank(path,true,resourceSlots_[1])},
     selectedStage_(!selection&&rematchFrom?rematchFrom->chosenStage():selectedStage),
     fromFaceoff_(selection && rematchFrom && rematchFrom->faceoff()),
     fighters_{MatchFighter(banks_[0]),MatchFighter(banks_[1])},ground_(path),human_(path),
     initialize_(path,resourceSlots_),gauges_(path),effects_(path),sounds_(path),captions_(path,&sounds_),stage_(path),ending_(path),lock_(path),
     aux_(path,resourceSlots_),damage_(path),reactions_(path),judgments_{JudgmentData(path,resourceSlots_[0]),JudgmentData(path,resourceSlots_[1]),JudgmentData(path,51)},collisions_(path),projectiles_(path),
     combat_(path),rounds_({initialize_,ground_,effects_,stage_,captions_,ending_,lock_,&sounds_}) {
    auto& b=battle_;
    // 1183f8 + 1b8bc0: the factory volume setting is 100, scaled by 0.25 * 512.
    b.audio.streamParameter5a9e78=0x3200;
    const auto& limits=BattleRoundState::roundTimeLimits;
    if(mode==VersusMode::Console) {
        if(rematchFrom) {
            const auto& old=rematchFrom->battle_;
            promptClock_=rematchFrom->promptClock_;
            // 1db2e0 tears down fight-owned objects, then marks GameData+A4.
            // The session scores, global game data and both random streams survive.
            b.consoleMenu.inheritRematch(old.consoleMenu);
            b.stageItemsOption4c3828=selection&&rematchFrom->characterSelect()?rematchFrom->characterSelect()->stageOption:old.stageItemsOption4c3828;
            b.matchEnd=old.matchEnd;
            b.matchEnd.endFlagA4=1;
            b.voiceGate5850e0=old.voiceGate5850e0;
            sceneAudioEntered_=true; // 125274 ran the new scene entry at the fade midpoint.
            b.random=old.random;
            if(!selection)rageGauge_=rematchFrom->rageGauge_;
            sounds_=rematchFrom->sounds_;sounds_.beginFrame();
            if(roundTime==-1)roundTime=limits.at(old.timeOption13c);
        }
        b.matchEnd.submodeA0=2;
        b.matchEnd.metadataStage04=selectConsoleVersusStage(b.random,selectedStage_);
    }
    for(unsigned arena=0;arena<combatStages_.size();++arena) {
        combatStages_[arena].stage=arena;
        if(rematchFrom)combatStages_[arena].inheritRematch(rematchFrom->combatStages_[arena]);
    }
    // Factory settings 111410 use 60 for VS. A zero supplied explicitly
    // means unlimited. The fixed-match profile retains its unlimited default.
    if(roundTime==-1)roundTime=mode==VersusMode::Console?60:0;
    const auto option=std::find(limits.begin(),limits.end(),roundTime);
    if(option==limits.end())throw std::runtime_error("Round time must be 60, 90, 99 or 0 for unlimited");
    b.timeOption13c=int(option-limits.begin());
    b.entry.resolvePoolLinks=true;
    b.currentState=-1;b.requestedState=0;
    b.entry.tasks.initializeOwners();b.entry.tasks.initializeTasks();b.entry.tasks.initializeObjects();
    // Residency handles identify the bank selected for each already-loaded texture.
    for(unsigned n:{1u,2u,3u,4u,5u,6u,7u,8u,9u,12u,13u,14u,15u,16u,17u,20u,21u,22u})
        b.effectResidency.slots[n]=n+1;
    // The arena records vertices with the camera available at priority 10.
    // Player movement and publication of the next camera occur later in the tick.
    b.entry.tasks.createTask(10,activeStage().handler(),0x10,0xfa1);
    // The versus HUD has a persistent priority-20 task. It samples after
    // priority-5 meter decay and before contacts for the current update.
    b.entry.tasks.createTask(20,0x1bab38,0x10,0x1773);
    referee_.initialize(b.stageEvent);
    b.entry.tasks.createTask(20,0x1b4228,0x10,0xfa2);
    b.entry.tasks.createTask(30,0x1b51b8,0x10,0xfa3);
    aux_.setSoundObserver([this](int16_t command,const AuxiliaryObject& object) {
        const auto seat=object[0x0c/4];
        return sounds_.act(command,int(seat),int(object[0x14/4]),seat<2?fighters_[seat].actor.flags23c:0,
                           battle_.gameMode,0,battle_.random);
    });
    captions_.onConcentrationFinished([this]{gauges_.releaseConcentration(battle_,players());});
    captions_.onExplosionFinished([this]{gauges_.releaseExplosion(battle_,players());});
    aux_.setEffectObserver([this](unsigned id,uint32_t flags,unsigned slot,float x,float y) {
        captions_.startWorld(id,flags,slot,x,y,-10,1,battle_.entry.tasks,battle_.effectResidency,battle_.random);
    });
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];auto& a=f.actor;
        f.body.ownerCC=f.body.resourceSlot0c=i;
        // 1398c0 rebuilds each actor from the retained versus selections.
        // The initial fixed mirror assigns Haohmaru's second palette to P2.
        const auto& pick=lineup_[i];
        if(pick.spirit>5||!playableFighter(pick.character))throw std::invalid_argument("Unsupported versus selection");
        f.config.character=a.character=pick.character;
        cpuSeats_[i]=std::move(cpuSeats[i]);
        if(cpuSeats_[i]){a.controlKindA20=1;a.controlModeC8=35;}
        // 148ea0 supplies the opposing character's damage descriptor bank.
        a.damageCharacterA18=lineup_[1-i].character;
        f.config.system=pick.spirit;
        a.fieldA28=f.body.field20=pick.palette;
        if(rematchFrom)b.match.players[i].requiredWins=rematchFrom->battle_.match.players[i].requiredWins;
        f.body.timeline.setObjectFlags(0x10000000u|(i<<19),0x40000000,0x40);
        f.body.timeline.setSoundObserver([this,i](int16_t c,const ActionClock& clock){
            auto& f=fighters_[i];
            const int channel=sounds_.record(c,clock,i,f.actor.character,f.actor.flags23c,battle_.gameMode,0,battle_.random);
            if(channel>=0&&(uint16_t(c)&0x4000))f.body.sound34=uint32_t(channel)|0xc000u;
        });
        f.body.timeline.setEffectObserver([this,i](unsigned id,uint32_t flags,float x,float y){
            captions_.startWorld(id,flags,i,x,y,-10,1,battle_.entry.tasks,battle_.effectResidency,battle_.random);
        });
        a.flags23c=0x1000;a.state1a4=0xffffffffu;a.fieldA30=200;a.registry28c[2]=0xffffffffu;
        f.sampling.player=i;f.sampling.expectedFacing=i!=0;f.sampling.gameMode=b.gameMode;
        for(unsigned k=0;k<8;++k)mappings_[i].normal[k]=mappings_[i].mode6[k]=1u<<(8+k);
        human_.initialize(f.input,f.config);
        GroundStateRuntime::captureBody(f.body,a);
    }
    // 139760 runs 13fd80 inside the scene-transition callback. At the
    // black midpoint the fighters and clock already exist; priority 50
    // can sample the next pad only on the following scheduler dispatch.
    if(mode==VersusMode::Console)initialize_.begin(ground_,players(),b,effects_);
}
std::array<RoundPlayerRef,2> NativeMatch::players() {
    auto ref=[](MatchFighter& f){return RoundPlayerRef{f.body,f.actor,f.input,f.config,f.storage,f.objects};};
    return {ref(fighters_[0]),ref(fighters_[1])};
}
CollisionPlayer NativeMatch::collisionPlayer(unsigned i) const {
    const auto& f=fighter(i);const auto& a=f.actor;const auto& t=f.body.timeline;const auto& c=t.clock();
    CollisionPlayer p;
    p.owner=i;p.judgmentProfile=a.character;p.objectFlags104=c.flags104;p.objectFlags108=c.flags108;p.actorFlags=a.flags23c;
    p.stateTable=int16_t(a.stateTable());p.stateIndex=int16_t(a.stateIndex());p.stateFlags=a.effectiveFlags();
    p.field1c8=a.timers[6];p.x=t.motion().x;p.y=t.motion().y;p.mirrorX=c.objectFlags&0x80000;
    p.mirrorY=c.objectFlags&0x40000;p.judgmentFlags=t.record().judgmentFlags;p.judgments=judgments_.at(i).forRecord(t.record());
    return p;
}
bool NativeMatch::resolveStrike(const ContactEvent& e,const CollisionPlayer& from,const CollisionPlayer& to,ContactMarks& sm,ContactMarks& tm,uint32_t sourceHandle) {
    auto& source=fighters_[from.owner];auto& target=fighters_[to.owner];
    auto* projectile=sourceHandle?&battle_.entry.tasks.objects.at(sourceHandle-1):nullptr;
    auto& a=source.actor;auto& b=target.actor;const auto& features=target.input.sampledFeatures;
    DefenseSnapshot defense;
    defense.system=int(target.config.system);
    // During blockstun a fight CPU keeps the height of its guard reaction.
    // Human and practice controls can change height with the sampled direction.
    defense.fieldA20=b.controlKindA20;
    defense.fieldC8=b.controlModeC8;
    defense.actorFlags23c=b.flags23c;defense.actorFlags244=b.flags244;
    defense.stateTable=int16_t(b.stateTable());defense.stateIndex=int16_t(b.stateIndex());defense.stateFlags=b.effectiveFlags();
    defense.field3C0=features[0xfc/4];defense.field39C=features[0xd8/4];defense.field398=features[0xd4/4];
    const auto decision=inspectContactDecision(combat_,e,from,defense,sm,tm);
    if(decision.kind!=DecisionKind::GuardBranch&&decision.kind!=DecisionKind::HitBranch)return false;
    const bool guard=decision.kind==DecisionKind::GuardBranch;
    auto& stats=battle_.match.players[from.owner];
    const bool counter=!guard&&isCounterContact(b,stats,e);
    auto am=meter(a,source.config.system),bm=meter(b,target.config.system);
    const int amount=damage_.applyOrdinaryContact(e.auxiliary,am,bm,guard,a.stateTable()==1&&a.stateIndex()>=64,projectile!=nullptr);
    storeMeter(a,am);storeMeter(b,bm);
    if(!guard)interruptConcentration(to.owner);
    ReactionTarget t;static_cast<ActorContactHistory&>(t)=b;
    t.flags23c=b.flags23c;t.flags244=b.flags244;t.flags24c=b.flags24c;t.stateTable=int16_t(b.stateTable());
    ActorTimers at{a.timerDelta,a.timers},bt{b.timerDelta,b.timers};
    bool chip=false;
    if(guard) {
        unsigned action=0;
        reactions_.applyGuard(t,at,bt,decision.defense,unsigned(e.extra),action);
        const auto group=e.a.fields.group;
        chip=decision.defense!=3&&((sm.flags108&0x100)||(!(b.flags23c&0x1000)&&(group==0||group==1||group==4)));
        if(chip)battle_.queueLifeChange(b,a.flags23c,1);
        ++source.guards;sm.consumed|=8;
        // 1554e0 uses the body's current move descriptor. Even a successful
        // guard leaves an unflagged swing (including some multi-hit slashes) running.
        if(!projectile&&!(a.flags23c&(0x200000u|0x800000u))&&(a.flags23c&0x1000)&&(a.effectiveFlags()&8)) {
            const auto recoil=queueWeaponClash(a.flags23c,a.stateTable(),a.stateIndex(),unsigned(e.extra),false);
            a.flags23c=recoil.flags23c;a.pendingTable=recoil.table;a.pendingIndex=recoil.state;
        }
    } else {
        const unsigned part=e.b.fields.type>=1&&e.b.fields.type<=3?e.b.fields.type-1:0;
        if(e.a.fields.type==15) {
            // 14d1f0 is the shake inside the ongoing capture. It advances
            // the shared random stream once and leaves the victim's ACT running.
            const int magnitude=1+battle_.random.bounded(2);
            b.bodyFieldE4=uint32_t(std::bit_cast<int32_t>(b.bodyFieldE4)>0?-magnitude:magnitude);
        } else if(e.a.fields.type>=36) {
            if(applyCapturedHit(t,e.a.fields.type)) {
                b.bodyField124=sourceHandle;
                if(projectile)sm.flags108|=0x02000000;
            }
        } else {
            reactions_.applyGroundHit(t,at,bt,e.a.fields.type,part,counter,
                       !projectile&&(a.flags23c&0x20),projectile?0:am.attackStrength,a.flags248,
                       projectile||(a.stateTable()==1&&a.stateIndex()>=64));
        }
        t.field250=e.a.fields.group;t.field251=e.a.fields.variant;
        t.contactKind252=e.a.fields.remainder;
        // 155b7c credits a reflected character projectile to its original
        // resource slot. Shared stage items use the victim's opposing fighter.
        const unsigned slot=projectile?(*projectile)[0x0c/4]:from.owner;
        t.pendingCharacter254=slot<2?fighters_[slot].actor.character:a.character;
        battle_.match.players[to.owner].field18=int(e.b.fields.type==3);
        battle_.queueLifeChange(b,a.flags23c,amount);
        ++source.hits;sm.consumed|=4;tm.consumed|=2;
    }
    if(!projectile&&a.state194==0x150001&&(!guard||t.forceState))
        setCombinedSlashPause(reactions_,guard?(decision.defense==3?8u:unsigned(t.pendingState)):unsigned(t.previousReaction),guard,at,bt);
    if(projectile&&(guard?t.forceState:e.a.fields.type<36)) {
        const auto timing=reactions_.descriptor(guard?(decision.defense==3?8:t.pendingState):t.secondaryReaction);
        aux_.pauseWhirlwind(*projectile,timing.firstTimer,timing.secondTimer);
        // 157c60 shares only timer zero with the current collision owner.
        // The original caster still supplies the resource after reflection.
        if((*projectile)[0x10/4]!=2 && collisions_.sharesProjectileHitstop((*projectile)[0x14/4],(*projectile)[0x24/4]))
            a.timers[0]=int32_t((*projectile)[0xdc/4]);
    }
    // 156fb8 reads state 1/38 only on a body. An ice projectile already in
    // flight keeps its own impact flash when its owner starts Issen.
    const auto impactSourceState=from.objectKind<2?a.state194:0;
    presentContact(captions_,battle_,e,to,decision.defense,chip,counter,impactSourceState,aux_);
    // Both ordinary presentation callbacks cancel the victim's retained
    // ACT voice after the sparks and before 156d68 chooses the impact.
    const auto group=e.a.fields.group;
    if(guard?decision.defense!=3:(group<=3||group==5||impactSourceState==0x260001))
        sounds_.stop(target.body.sound34);
    if(!projectile)a.timers=at.values;
    b.timers=bt.values;static_cast<ActorContactHistory&>(b)=t;
    b.flags23c=t.flags23c;b.flags244=t.flags244;
    const int category=projectile?projectileFinishCategory(*projectile,a,b,human_.bindings()):10;
    if(projectile&&!guard&&category==11)a.flags244|=0x80000000u; // 157b50 also records nonlethal technique hits.
    recordContactFinish(a,b,stats,e,projectile!=nullptr,guard,counter,human_.bindings(),category);
    const bool matchBlow=b.fieldA30>0&&b.pendingDamageA38>=b.fieldA30&&stats.wins+1>=stats.requiredWins;
    sounds_.contact(group,decision.defense,b.flags23c&0x1000,matchBlow,
                    counter,source.body.timeline.action().id(),battle_.random);
    if(!guard) {
        ++stats.hitCount0c;
        // The priority-20 HUD consumes the attacking seat's notification on
        // its next visit. Blocked contacts and isolated hits have no label.
        if(stats.hitCount0c>=2)rageGauge_.players[from.owner].combo.requested=int(stats.hitCount0c);
    }
    if(t.forceState){b.pendingTable=t.pendingTable;b.pendingIndex=t.pendingState;b.request18c=1;}
    if(projectile) {
        const auto descriptor=(*projectile)[0xd0/4];
        if(!guard) {
            // 156ad8 applies the penalty after this hit has dealt damage.
            // The round reset owns its lifetime. A bomb shows a separate
            // notice and bypasses the thrower's successful-item counter.
            if(descriptor==109) {
                b.fieldA50=std::min(100u,b.fieldA50+20);
                b.flags248|=0x400;
                battle_.itemNotices.show(StageItemLabel::DefenseDown,int(to.x));
            } else if(descriptor==110)battle_.itemNotices.show(StageItemLabel::Bomb,int(to.x));
            if(descriptor!=110&&from.objectKind==5) {
                auto& count=a.characterBytesF22[6];
                if(count<99)++count;
            }
        } else if(descriptor==147) {
            b.bodyField124=sourceHandle;b.pendingCharacter254=35;
            b.pendingTable=2;b.pendingIndex=96;b.request18c=1;
        }
    }
    return true;
}
void NativeMatch::interruptConcentration(unsigned target) {
    // 1a44dc ends the defender's active concentration on both direct and
    // scripted hits. A guard can deal chip damage while preserving the clock.
    auto& fighter=fighters_[target];
    if(fighter.config.system==4 && fighter.actor.systemState13c==3)
        BattleGauges::endConcentration(battle_,fighter.actor,target);
}
void NativeMatch::scriptDamage(unsigned target,int base,DamageOrigin origin,int projectileCategory) {
    auto& source=fighters_[1-target].actor;
    auto& victim=fighters_[target].actor;
    auto from=meter(source,fighters_[1-target].config.system),to=meter(victim,fighters_[target].config.system);
    // 1413d8 passes mode 2 for both a throw record and the whirlwind landing.
    const int amount=damage_.applyOrdinaryContact(base,from,to,false,false,2);
    battle_.queueLifeChange(victim,source.flags23c,amount);
    storeMeter(source,from);storeMeter(victim,to);
    interruptConcentration(target);
    recordScriptFinish(source,victim,battle_.match.players[1-target],
                       origin==DamageOrigin::ProjectileRecord,origin==DamageOrigin::CaptureScript,human_.bindings(),projectileCategory);
}
void NativeMatch::strikeMikiri(const ContactEvent& event,const CollisionPlayer& from,const CollisionPlayer& to,
                              const AuxiliaryObject& image,ContactMarks& source,ContactMarks& target) {
    if(source.flags104&0x06000000)return;
    auto& attacker=fighters_[from.owner];auto& defender=fighters_[to.owner];
    auto& a=attacker.actor;auto& b=defender.actor;
    const bool extended=b.flags248&0x02000000;
    if(!extended)mikiriFlashLeft_=3;
    battle_.timers.lock=extended?16:13;
    battle_.gauges.focus46a948=int32_t(to.owner);
    for(auto& tone:std::span(battle_.gauges.paletteTones).subspan(512))tone|=4;
    b.flags23c|=0x08000000u;a.flags23c&=~0x08000000u;
    sounds_.sample(-1,57);
    const bool useStrength=event.auxiliary && collisions_.usesAttackDamage(event.a.fields.type,from.judgmentProfile);
    damage_.gainKenSecret(useStrength?event.auxiliary:16,meter(a,attacker.config.system),meter(b,defender.config.system),
                          useStrength?0:2,b);
    auto& evaded=b.characterBytesF22[3];
    if(evaded<99)++evaded;
    // A decoy consumes the attack and produces the hit spark. The owner
    // keeps their HP and never enters the ordinary victim reaction.
    presentContact(captions_,battle_,event,to,0,false,false,from.objectKind<2?a.state194:0,aux_);
    source.consumed|=0x15;source.flags104|=0x02000000;
    if(source.flags108&0x80)source.flags104|=0x04000000;
    target.flags104|=0x00400000;
    const bool standing=image[0x24/4]==86 || image[0x24/4]==87;
    if(standing && from.objectKind<2)a.timers[0]=4*256;
    b.timers[33]=10*256;b.timers[31]=(standing?14:10)*256;
}
void NativeMatch::setCaptureObjectGates(bool captured,bool entering) {
    auto& pools=battle_.entry.tasks;
    auto mark=[&](const auto& registry) {
        for(auto task:registry)if(task) {
            auto& flags=pools.objects.at(pools.tasks.at(task-1)[7]-1)[0x104/4];
            if(captured)flags|=0x800000u;else flags&=~0x800000u;
        }
    };
    // 141740 clears both fighters after release. During capture it touches
    // only the common pool, so the eagle's command 7 can reopen its own hitbox.
    if(entering||!captured)for(const auto& f:fighters_)mark(f.storage.objectTasks);
    mark(battle_.objectTasks);
}
void NativeMatch::resolveContacts() {
    // 1424b0 registers the shared bomb first, then each body and its owned
    // objects. Equal-priority contacts retain this insertion order.
    struct Participant {CollisionPlayer snapshot;ContactMarks marks;uint32_t handle;};
    std::vector<Participant> participants;
    ContactRegistry registry;
    auto add=[&](CollisionPlayer p,unsigned action,uint32_t handle) {
        ContactMarks m{p.objectKind,p.objectFlags104,p.objectFlags108,0};
        registry.add(uint32_t(participants.size()),handle?battle_.entry.tasks.objects.at(handle-1)[0x14/4]:fighters_.at(p.owner).actor.character,action,m);
        p.objectFlags104=m.flags104;
        participants.push_back({std::move(p),m,handle});
    };
    auto& pools=battle_.entry.tasks;
    auto registerObjects=[&](std::span<const uint32_t> tasks,unsigned kind) {
        for(auto task:tasks)if(task) {
            const auto h=pools.tasks.at(task-1)[7];const auto& o=pools.objects.at(h-1);
            if(o[0xcc/4]!=kind)continue;
            CollisionPlayer p;p.owner=o[0x10/4];p.judgmentProfile=o[0x18/4];p.objectKind=kind;p.objectTypeD0=int32_t(o[0xd0/4]);
            if((kind==2||kind==5)&&p.objectTypeD0>=0)
                p.descriptorFlagsA=collisions_.projectileFlags(p.objectTypeD0);
            p.x=std::bit_cast<float>(o[0x40/4]);p.y=std::bit_cast<float>(o[0x44/4]);
            p.objectFlags104=o[0x104/4];p.objectFlags108=o[0x108/4];p.mirrorX=o[0x38/4]&0x80000;p.mirrorY=o[0x38/4]&0x40000;
            const auto record=aux_.record(o);p.judgmentFlags=record.judgmentFlags;p.judgments=judgments_.at(o[0x0c/4]).forRecord(record);
            add(std::move(p),o[0x24/4],h);
        }
    };
    registerObjects(battle_.objectTasks,5);
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];f.actor.flags248&=~0x40u;
        auto body=collisionPlayer(i);body.objectKind=i;
        add(std::move(body),f.body.timeline.action().id(),0);
        for(unsigned kind:{2u,3u,5u,9u})registerObjects(f.storage.objectTasks,kind);
    }
    std::vector<ContactEvent> events;
    for(auto i:registry.objects()) {
        auto& src=participants[i];
        auto& fighter=fighters_[src.snapshot.owner];
        int directDamage=0;
        if(src.handle) {
            auto& damageWord=pools.objects.at(src.handle-1)[0xd8/4];
            directDamage=int(damageWord);damageWord=0;
        } else directDamage=fighter.body.timeline.takeRecordDamage();
        if(directDamage&&!(fighter.actor.flags248&0x8000))
            scriptDamage(1-src.snapshot.owner,directDamage,src.handle?DamageOrigin::ProjectileRecord:DamageOrigin::FighterRecord,
                         src.handle?projectileFinishCategory(pools.objects.at(src.handle-1),fighter.actor,
                             fighters_[1-src.snapshot.owner].actor,human_.bindings()):10);
        for(auto j:registry.objects())if(i!=j)
            collectContacts(collisions_,src.snapshot,participants[j].snapshot,i,j,events);
    }
    orderContacts(events);
    unsigned highestRoute=11;
    for(const auto& e:events) {
        if(e.route>highestRoute)break;
        auto& src=participants[e.a.player];auto& dst=participants[e.b.player];
        const auto i=src.snapshot.owner,j=dst.snapshot.owner;auto& a=fighters_[i];auto& b=fighters_[j];
        auto& sm=src.marks;auto& tm=dst.marks;
        const auto which=combat_.consumptionIndices(e.route);
        if(dst.snapshot.objectKind==9 && e.route==10) {
            strikeMikiri(e,src.snapshot,dst.snapshot,pools.objects.at(dst.handle-1),sm,tm);
            continue;
        }
        if(src.snapshot.objectKind==9 || dst.snapshot.objectKind==9)continue;
        if(src.handle||dst.handle) {
            const auto disposition=projectileContact(e,src.snapshot,dst.snapshot,sm);
            if(disposition==ProjectileContact::StrikePlayer) {
                if(resolveStrike(e,src.snapshot,dst.snapshot,sm,tm,src.handle)) {
                    markContactConsumed(sm,which[0]);markContactConsumed(tm,which[1]);
                }
            } else if(disposition==ProjectileContact::ClashProjectiles) {
                auto& from=pools.objects.at(src.handle-1);auto& to=pools.objects.at(dst.handle-1);
                if(markProjectileClash(tm,uint8_t(from[0xfc/4]),uint8_t(to[0xfc/4]))) {
                    aux_.pauseWhirlwind(from,2,0);aux_.pauseWhirlwind(to,2,0);
                    const int x=e.centerX+battle_.random.bounded(24)-12;
                    const int y=e.centerY+battle_.random.bounded(12)-6;
                    captions_.startContact(25,x,y,1,pools,battle_.effectResidency,battle_.random);
                    sounds_.sample(-1,14);
                }
            } else if(disposition==ProjectileContact::ReflectProjectile) {
                auto& reflected=pools.objects.at(dst.handle-1);
                if(dst.snapshot.objectKind==5) {
                    auto& count=a.actor.characterBytesF22[7];
                    if(count<99)++count;
                }
                aux_.reflectProjectile(reflected,i);
                // Later events in this same ordered queue read the new team
                // and facing. The original caster still owns the task.
                dst.snapshot.owner=i;dst.snapshot.mirrorX=bool(reflected[0x38/4]&0x80000);
                dst.snapshot.objectFlags104=tm.flags104=reflected[0x104/4];
                dst.snapshot.objectFlags108=tm.flags108=reflected[0x108/4];
                const int x=e.centerX+battle_.random.bounded(24)-12;
                const int y=e.centerY+battle_.random.bounded(12)-6;
                captions_.startContact(25,x,y,1,pools,battle_.effectResidency,battle_.random);
                sounds_.sample(-1,14);
            } else if(disposition!=ProjectileContact::None)throw std::runtime_error("Unsupported projectile interception route "+std::to_string(e.route));
            continue;
        }
        if(contactConsumed(sm,which[0])||contactConsumed(tm,which[1]))continue;
        if(e.route==0) {
            breakGroundThrows(a.actor,b.actor);
            captions_.startContact(7,e.centerX,e.centerY,1,pools,battle_.effectResidency,battle_.random);
            sounds_.sample(-1,14);
            highestRoute=0;
        } else if(e.route==2&&b.actor.stateTable()==1&&(b.actor.stateIndex()==23||b.actor.stateIndex()==24)) {
            if(!resolveWeaponDeflection(e,a.body,a.actor,b.body,b.actor))continue;
            if(b.actor.variantA48==3) {
                captions_.startContact(9,e.centerX,e.centerY,1,pools,battle_.effectResidency,battle_.random);
                sounds_.sample(-1,22);
                sounds_.stop(a.body.sound34);
            } else {
                sounds_.sample(-1,63);
                sounds_.stop(a.body.sound34);
            }
            highestRoute=2;
        } else if(e.route==4&&collisions_.captureIndex(e.a.fields.type,a.actor.character)!=0xff) {
            // 1551c0 hands both ACTs to the victim script on a command throw.
            // There is no contact damage or guard check before that handoff.
            b.actor.pendingCharacter254=a.actor.character;b.actor.bodyField124=0;
            b.actor.pendingTable=2;b.actor.pendingIndex=80+collisions_.captureIndex(e.a.fields.type,a.actor.character);b.actor.request18c=1;
            sounds_.stop(b.body.sound34);highestRoute=4;
        } else if(e.route==4&&e.a.fields.type==32) {
            catchGroundThrow(a.body,a.actor,sm,b.body,b.actor,tm);
            sounds_.stop(b.body.sound34);
            highestRoute=4;
        } else if(e.route==11) {
            const auto am=a.body.timeline.motion(),bm=b.body.timeline.motion();
            PushActor p{am.x,am.y,a.actor.flags248},q{bm.x,bm.y,b.actor.flags248};
            ordinaryPush(p,q,e.width);a.body.timeline.setPosition(p.x,p.y);b.body.timeline.setPosition(q.x,q.y);
            a.actor.flags248=p.flags248;b.actor.flags248=q.flags248;
        } else if(e.route==7) {
            if(!resolveStrike(e,src.snapshot,dst.snapshot,sm,tm))continue;
        } else if(e.route==8||e.route==9) {
            if(e.route==9&&(sm.flags104&0x06000000))continue;
            // The first eligible blade-on-blade contact can start a lock.
            // 13fd80 preserves bit 1 across rounds after 145a18 sets it.
            const bool lock=e.route==8&&!(battle_.flags138&2)&&
                (battle_.timeOption13c==3||battle_.remainingSeconds()>=11);
            if(lock)battle_.field08=1;
            else {
                for(unsigned slot:{i,j}) {
                    auto& x=fighters_[slot].actor;
                    const auto clash=queueWeaponClash(x.flags23c,x.stateTable(),x.stateIndex(),meter(x,fighters_[slot].config.system).attackStrength,true);
                    x.flags23c=clash.flags23c;x.pendingTable=clash.table;x.pendingIndex=clash.state;
                }
                presentWeaponClash(captions_,battle_,e);
                sounds_.sample(-1,22);
            }
        } else throw std::runtime_error("Battle contact route "+std::to_string(e.route)+" requires its original handler");
        markContactConsumed(sm,which[0]);markContactConsumed(tm,which[1]);
    }
    for(auto index:registry.objects()) {
        auto& p=participants[index];auto& m=p.marks;
        if(m.consumed&16)m.flags104|=0x200000;else if(m.consumed&4)m.flags104|=0x40000;else if(m.consumed&8)m.flags104|=0x80000;
        if(p.handle) {
            auto& object=pools.objects.at(p.handle-1);
            object[0x100/4]=(object[0x100/4]&~255u)|m.consumed;
            object[0x104/4]=m.flags104;object[0x108/4]=m.flags108;
        } else fighters_[p.snapshot.owner].body.setFlags(m.flags104,m.flags108);
    }
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];auto& body=f.body;auto& other=fighters_[1-i].actor;auto& entry=battle_.entry;
        entry.player=i;entry.opponentFlagsB8=other.flagsB8;
        ground_.afterContacts(body,f.actor,f.input,f.config,entry);other.flagsB8=entry.opponentFlagsB8;
    }
}
namespace {
// 146a98: true unless the point is inside the camera's horizontal span widened
// by the margin and below its top plus the vertical margin. EE CVT.W.S truncates.
bool outsideView(const StageCamera& camera,uint32_t x,uint32_t y,int32_t margin,int32_t vertical) {
    const int32_t ix=ScalarFloat{x}.truncate(),iy=ScalarFloat{y}.truncate();
    if(camera.left-margin<ix&&ix<camera.right+margin)return !(iy<camera.top+vertical);
    return true;
}
}
void NativeMatch::minaProjectileTask(unsigned i,uint32_t task) {
    auto& b=battle_;auto& f=fighters_[i];
    const auto parent=f.body.childParentWords(),opponent=fighters_[1-i].body.childParentWords();
    auto* companion=f.actor.auxiliaryObject04?&b.entry.tasks.objects.at(f.actor.auxiliaryObject04-1):nullptr;
    ProjectileOwner owner{aux_,b.entry.tasks,f.storage.objectTasks,i,f.actor,parent,opponent,b.camera,b.random,companion};
    updateDescriptorProjectile(projectiles_,owner,task);
}
uint32_t NativeMatch::spawnMinaProjectile(unsigned i,unsigned id,unsigned variant,const ScriptRow* row) {
    auto& b=battle_;auto& f=fighters_[i];
    auto parent=f.body.childParentWords();
    const auto& command=f.body.timeline.attachedEffect();
    parent[0x110/4]=uint32_t(command[1]);parent[0x114/4]=uint32_t(command[2]);
    const auto opponent=fighters_[1-i].body.childParentWords();
    auto* companion=f.actor.auxiliaryObject04?&b.entry.tasks.objects.at(f.actor.auxiliaryObject04-1):nullptr;
    ProjectileOwner owner{aux_,b.entry.tasks,f.storage.objectTasks,i,f.actor,parent,opponent,b.camera,b.random,companion};
    return row?spawnScriptProjectile(projectiles_,owner,*row):spawnDescriptorProjectile(projectiles_,owner,id,variant);
}
void NativeMatch::minaScriptEvent(unsigned i,uint8_t type) {
    auto& b=battle_;auto& f=fighters_[i];auto& pools=b.entry.tasks;
    if(type==34) {
        // 1fdea8 draws its RNG only in the alternate mode, which the console
        // versus profile never selects; its shoulder object is not ported.
        if(f.actor.flags23c&0x100000)throw UnportedFighterState(f.actor.character,f.actor.stateTable(),f.actor.stateIndex());
        return;
    }
    if(type!=33)throw std::runtime_error("Unexpected Mina script event");
    unsigned count=0;
    for(auto task:f.storage.objectTasks)if(task) {
        const auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        if(o[0xcc/4]==2&&o[0xd0/4]==0x5e)++count;
    }
    // Event 33: ten distinct sky arrows, or five scattered 0x52 arrows while
    // two earlier volleys are still alive.
    for(unsigned n=0;n<(count<2?10u:5u);++n) {
        const auto handle=spawnMinaProjectile(i,count<2?0x55+n:0x52,0,nullptr);
        if(!handle)continue;
        auto& o=pools.objects.at(handle-1);o[0x108/4]|=0x40000;
        if(count>=2){if(b.random.bounded(2)==0)o[0x38/4]&=~0x80000u;else o[0x38/4]|=0x80000u;}
    }
}
void NativeMatch::markOffscreen() {
    // 142f30, called by 140270 after every object has moved and before the
    // stage phase: each body (margin 48), its 48-slot registry, then the
    // battle's 64-slot registry. Bit 4 of +104 is both set and cleared here.
    auto& pools=battle_.entry.tasks;
    const auto mark=[&](uint32_t& flags,bool out){flags=out?flags|4u:flags&~4u;};
    const auto registry=[&](std::span<const uint32_t> list) {
        for(auto task:list)if(task) {
            auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            int32_t margin=48;
            if(o[0xcc/4]==2) {
                const auto id=o[0xd0/4];
                margin=id==0x2f?64:id==0x36?72:id==0x63?128:48;
            }
            mark(o[0x104/4],outsideView(battle_.camera,o[0x40/4],o[0x44/4],margin,32));
        }
    };
    for(auto& f:fighters_) {
        const auto& m=f.body.timeline.motion();auto c=f.body.timeline.clock();
        mark(c.flags104,outsideView(battle_.camera,std::bit_cast<uint32_t>(m.x),std::bit_cast<uint32_t>(m.y),48,0));
        f.body.setFlags(c.flags104,c.flags108);
        registry(f.storage.objectTasks);
    }
    registry(battle_.objectTasks);
}
void NativeMatch::updateStage() {
    markOffscreen();
    std::array<StageActor,2> stage;
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];auto& a=f.actor;ground_.captureBody(f.body,a);
        stage[i]={a.x,a.y,a.flags23c,a.flags244,a.bodyFlags38,a.flags24c,int16_t(a.stateTable()),int16_t(a.stateIndex()),
                  a.stateTable()==2?ground_.damageFlags(a):uint8_t(0),f.sampling.expectedFacing};
        stage[i].historyX=f.storage.history.samples[0].x;
    }
    // 145ef0 reads last tick’s cached distance but this tick’s moved bodies.
    // 1426d8 publishes the new distance only after both seats classify it.
    for(unsigned seat=0;seat<2;++seat)if(cpuTactics_[seat])
        observeCpuDistances(fighters_[seat].actor,fighters_[1-seat].actor,distance_,*cpuTactics_[seat]);
    // 14293c samples only the two fighter bodies. A projectile's own ACT
    // cannot shake the stage. The whirlwind's captured victim can request
    // it through their body, even while the caster has returned to idle.
    const uint16_t shake=(fighters_[0].body.pendingFlags|fighters_[1].body.pendingFlags)&0xc0;
    if(shake) {
        if(shake&0x40)battle_.camera.requestShake(16,-1);
        if(shake&0x80)battle_.camera.requestShake(-1,16);
        for(auto& fighter:fighters_)fighter.body.pendingFlags&=uint16_t(~shake);
    }
    distance_=updateOrdinaryStage(stage,battle_.camera,battle_.flags138&4)[0];
    battle_.flags138&=~4u;
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];f.body.timeline.setPosition(stage[i].x,stage[i].y);f.actor.flags24c=stage[i].flags24c;
        f.sampling.expectedFacing=stage[i].expectedMirror;ground_.captureBody(f.body,f.actor);
    }
}
void NativeMatch::visitActor(unsigned i,const std::array<NormalizedPadSample,2>& pads) {
    auto& f=fighters_[i];auto& a=f.actor;auto& other=fighters_[1-i];auto& b=battle_;
    a.opponentX=other.body.timeline.motion().x;f.sampling.battleState=b.currentState;
    SelectionThreat threat;threat.distance=distance_;PermissionContext permission;
    // 175858/1758e8 gate both supers on the live game mode (4c3808).
    permission.mode4c3808=b.gameMode;
    permission.stageObjectIndex=b.stageItems.itemIndex();permission.stageObjectX=b.stageItems.itemX();
    const auto& pools=b.entry.tasks;
    if(a.auxiliaryObject04) {
        const auto& companion=pools.objects.at(a.auxiliaryObject04-1);
        a.auxiliaryState128=companion[0x128/4];a.auxiliaryState12c=companion[0x12c/4];
        a.auxiliaryTimer130=companion[0x130/4];a.auxiliaryFlag134=companion[0x134/4];
        a.auxiliaryX=std::bit_cast<float>(companion[0x40/4]);a.auxiliaryY=std::bit_cast<float>(companion[0x44/4]);
        a.auxiliaryFlags104=companion[0x104/4];a.auxiliaryAction24=companion[0x24/4];
        a.auxiliaryFrameC0=companion[0xc0/4];a.auxiliaryPendingC4=int32_t(companion[0xc4/4]);
    }
    auto readObject=[&](uint32_t task) {
        const auto& o=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        return PermissionObject{int32_t(o[0xcc/4]),int32_t(o[0xd4/4]),int32_t(o[0x24/4]),o[0x108/4],std::bit_cast<float>(o[0x40/4])};
    };
    for(unsigned n=0;n<f.storage.objectTasks.size();++n) {
        if(auto t=f.storage.objectTasks[n])permission.ownObjects[n]=readObject(t);
        if(auto t=other.storage.objectTasks[n])threat.opponentObjectKinds[n]=readObject(t).kind;
    }
    for(unsigned n=0;n<b.objectTasks.size();++n)if(auto t=b.objectTasks[n])permission.battleObjects[n]=readObject(t);
    if(a.flags23c&0x80) {
        ActorTimers timers{a.timerDelta,a.timers};
        const int old=timers.increase(26);
        a.timers=timers.values;
        // 149558 uses the pre-increment fixed clock. A KO voice is latched
        // once, even when hitstop holds this clock across successive visits.
        if(old>0x600&&!(a.flags248&0x80)) {
            sounds_.sample(int(i),b.match.players[1-i].complete()?27:26);
            a.flags248|=0x80;
        }
    }
    SystemCancelContext cancel;cancel.controlOwner=&a;cancel.controlInput=&f.input;cancel.controlConfig=&f.config;
    std::function<CpuCommand()> decideCpu;
    if(cpuLevels_[i]>=0)decideCpu=[this,i,&permission,&threat]{return runCpu(i,permission,threat);};
    else if(cpuSeats_[i])decideCpu=[this,i]{return cpuSeats_[i](fighters_[i],fighters_[1-i],battle_);};
    human_.requests(a,other.actor,f.input,b.sampler,f.sampling,pads,mappings_,f.config,permission,threat,cancel,decideCpu);
    ground_.restoreBody(f.body,a);ground_.beforeCallbacks(f.body,a);
    WeaponLockActorContext shared{other.body,other.actor,b.camera,distance_,aux_,f.storage.objectTasks};
    GroundStateFrame frame;frame.remainingSeconds=b.remainingSeconds();frame.opponentX=a.opponentX;frame.opponentFlags23c=other.actor.flags23c;
    frame.opponentCharacter=other.actor.character;frame.opponentSystem=other.config.system;
    frame.spawnMikiri=[&](unsigned action){
        f.storage.history.reset(ActorHistory::capture(f.body,f.body.historyOffsetEc,f.body.historyOffsetF0));
        aux_.spawnMikiri(b.entry.tasks,f.storage.objectTasks,i,a.flags23c,f.body.childParentWords(),action);
    };
    frame.captureDamage=[&](int base){scriptDamage(i,base,DamageOrigin::CaptureScript);};
    frame.battle=&b;
    frame.startExplosion=[&]{gauges_.startExplosion(b,a,i,f.config.system);};
    frame.issenMusic=[&](bool restart){
        if(restart)RoundControl::startStageMusic(b,&sounds_);
        else {sounds_.stopMusic();b.audio.musicActive123a174=0;b.audio.musicPreloaded123a178=false;}
    };
    frame.opponentObjectTasks=other.storage.objectTasks;
    if(a.character==24)frame.scriptEvent=[this,i](uint8_t type){minaScriptEvent(i,type);};
    frame.suppressCaptureObjects=[this]{setCaptureObjectGates(true,true);};
    frame.opponentInput=&other.input;
    frame.sound=&sounds_;frame.objects=&f.objects;frame.random=&b.random;frame.effects=&effects_;frame.weaponLock=&shared;
    frame.matchStats=&b.match.players[i];frame.opponentStats=&b.match.players[1-i];
    b.entry.player=i;b.entry.opponentFlagsB8=other.actor.flagsB8;
    ground_.visit(f.body,a,f.input,f.config,b.entry,frame);other.actor.flagsB8=b.entry.opponentFlagsB8;
    // 149788 runs after the actor callback. A hit that crosses the low-life
    // threshold affects the next input decision, and survives the gauge tick.
    damage_.updateCriticalRage(a,int(f.config.system));
    finishActorInput(a,f.sampling,pads,mappings_);
    f.storage.history.update(ActorHistory::capture(f.body,f.body.historyOffsetEc,f.body.historyOffsetF0),a.timerDelta);
}
void NativeMatch::auxiliaryPhase(ObjectPhase phase) {
    auto& b=battle_;auto& pools=b.entry.tasks;
    // 140120 prepares priority before submitting either fighter, including
    // on paused visits. The draw queue preserves submission order on ties.
    if(phase==ObjectPhase::Draw)updateFighterDepths(b,players());
    std::array<AuxiliaryObject,2> parents;
    AuxiliaryFrame frame{b.gauges,auxiliaryJumpFlags_,int32_t(b.field140),{}};
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];const auto& body=f.body;const auto& c=body.timeline.clock();auto& o=parents[i];
        o=body.childParentWords();o[0x10/4]=i;o[0x24/4]=body.timeline.action().id();o[0x28/4]=c.step;
        o[0x2c/4]=c.fractionalTime;o[0x3c/4]=c.endControl;o[0x8c/4]=body.color8c;
        o[0xc0/4]=c.endReached;o[0xc4/4]=uint32_t(c.chainedAction);o[0xe4/4]=f.actor.bodyFieldE4;o[0xe8/4]=f.actor.bodyFieldE8;
        o[0xec/4]=std::bit_cast<uint32_t>(body.historyOffsetEc);o[0xf0/4]=std::bit_cast<uint32_t>(body.historyOffsetF0);
        o[0xfc/4]=uint32_t(body.pendingFlags)<<16;o[0x104/4]=c.flags104;o[0x108/4]=c.flags108;o[0x134/4]=body.scriptLatch134;
        frame.owners[i]={&o,f.actor.flags23c,f.actor.fieldA2c,f.actor.stateTable(),&f.storage.history};
    }
    for(unsigned i=0;i<3;++i) {
        auto list=i==2?std::span<uint32_t>(b.objectTasks):std::span<uint32_t>(fighters_[i].storage.objectTasks);
        switch(phase) {
        case ObjectPhase::Move:aux_.updateRegistry(pools,list,frame);break;
        case ObjectPhase::Callbacks:
            aux_.visitRegistry(pools,list,[&](uint32_t task) {
                switch(pools.tasks.at(task-1)[0]) {
                case 0:break; // Afterimages are generated from history in the draw phase.
                case 0x1ed440:
                    updateMamahaha(aux_,pools.objects.at(pools.tasks.at(task-1)[7]-1),parents.at(i),
                                  fighters_.at(i).actor,b.match.players.at(i).complete(),b.camera);
                    break;
                case 0x1ee110:
                    updateKonru(aux_,pools.objects.at(pools.tasks.at(task-1)[7]-1),parents.at(i),fighters_.at(i).actor,
                                fighters_.at(1-i).actor.character,parents.at(1-i)[0x24/4]);
                    break;
                case 0x1fc750: {
                    // 1473b8(battle+14c,64,5): the first kind-5 battle object.
                    const AuxiliaryObject* bomb=nullptr;
                    for(auto t:b.objectTasks)if(t) {
                        const auto& obj=pools.objects.at(pools.tasks.at(t-1)[7]-1);
                        if(obj[0xcc/4]==5){bomb=&obj;break;}
                    }
                    ChampleWorld world{parents.at(i),fighters_.at(i).actor,parents.at(1-i),fighters_.at(1-i).actor,b.random,
                        b.match.players.at(i).complete(),b.match.players.at(1-i).complete(),&b.stageItems,bomb};
                    updateChample(aux_,pools.objects.at(pools.tasks.at(task-1)[7]-1),world);
                    break;
                }
                case 0x1fbfc8:case 0x1fc420:updateMinaWeapon(pools,task,parents.at(i),fighters_.at(i).actor);break;
                case 0x145e30:lock_.task(b,players(),task);break;
                case 0x16e3b8:updateElementHurt(aux_,b,task,players());break;
                case 0x1415a8:updateThrownStageItem(aux_,pools,task);break;
                case 0x16c700:case 0x16c760:case 0x16c7c0:
                    updateRimururuIce(aux_,pools,task,b.camera,parents.at(i)[0x24/4]);break;
                case 0x16cac0:case 0x16c818:case 0x16c8d0:case 0x16c940:minaProjectileTask(i,task);break;
                case 0x16def0: {
                    const auto& object=pools.objects.at(pools.tasks.at(task-1)[7]-1);
                    if(object[0xcc/4]==5)updateThrownStageItem(aux_,pools,task);
                    else if(object[0x14/4]==24)minaProjectileTask(i,task);
                    else if(object[0x14/4]==2)updateRimururuIce(aux_,pools,task,b.camera,parents.at(i)[0x24/4]);
                    else if(object[0x14/4]==3)updateHanzoProjectile(aux_,pools,task);
                    else if(object[0xd0/4]==1)updateHaohmaruFlask(aux_,pools,task);
                    else aux_.updateWhirlwind(pools,task);
                    break;
                }
                case 0x1701c0:aux_.landWeapon(pools,task);break;
                case 0x170340:
                    if(aux_.shatterWeapon(pools,list,task,i,fighters_[i].actor.flags23c,parents[i])) {
                        auto& a=fighters_[i].actor;
                        if(a.character!=48){a.flags23c|=0x2000;a.timers[14]=600*256;}
                    }
                    break;
                case 0x147540:aux_.releaseHold(pools,task);break;
                default:throw std::runtime_error("Unhandled battle object callback");
                }
            });
            break;
        case ObjectPhase::Draw:
            if(i<2&&!(parents[i][0x104/4]&2))objectDraws_.submit(parents[i],b.gauges);
            aux_.drawRegistry(pools,list,frame,objectDraws_);
            break;
        }
    }
    if(phase==ObjectPhase::Draw) {
        // 1401e0 resolves the backdrop after both body and attachment lists
        // have submitted. The white Issen frame affects their NEXT color
        // update. Timer 4's black backdrop has priority and leaves colors alone.
        battleBackdropColor_=0;
        if(b.timers.values[4]>0)battleBackdropColor_=0xff000000;
        else if(b.flags138&0x10) {
            battleBackdropColor_=0xffffffff;
            for(auto& fighter:fighters_)fighter.actor.fieldA2c=7;
        } else if((b.flags138&0x60)==0x20){referee_.hideNextDraw();b.stageItems.hideNextDraw();}
        objectDraws_.sort();
    }
}
void NativeMatch::visitReferee(bool retainFighters) {
    auto& b=battle_;
    if(!retainFighters)refereeDrawSlot_=objectDraws_.count;
    else if(refereeSubmitted_) {
        // In the result menu priority 50 retains the fighter pictures while
        // priority 20 still runs. Replace just this task's contribution at
        // its original insertion point, including changes in visibility.
        auto it=objectDraws_.slots.begin();
        std::move(it+refereeDrawSlot_+1,it+objectDraws_.count,it+refereeDrawSlot_);
        --objectDraws_.count;
    }
    const auto before=objectDraws_.count;
    const auto& left=fighters_[0].body.timeline;
    const StageEventPlayers positions{left.motion().x,fighters_[1].body.timeline.motion().x,
                                      bool(left.clock().objectFlags&0x80000)};
    const unsigned oldCount=refereeSubmitted_;
    const int seat=referee_.visit(b.stageEvent,positions,b.requestedState,b.gauges,aux_,objectDraws_);
    refereeSubmitted_=objectDraws_.count!=before;
    if(retainFighters&&refereeSubmitted_) {
        auto it=objectDraws_.slots.begin();
        std::rotate(it+refereeDrawSlot_,it+before,it+objectDraws_.count);
    }
    if(retainFighters)itemDrawSlot_=itemDrawSlot_-oldCount+unsigned(refereeSubmitted_);
    if(seat>=0) {
        auto& owner=fighters_.at(unsigned(seat));
        aux_.deliverWeapon(b.entry.tasks,owner.storage.objectTasks,unsigned(seat),owner.actor.character,
                           owner.actor.flags23c,owner.body.childParentWords(),b.stageEvent.x);
    }
    // 1b4340 is the last operation of the referee task. Each weapon marker
    // follows the first registered kind-4 object, even if a later one landed.
    std::array<int,2> groundedX{-1,-1};
    for(unsigned side=0;side<2;++side)for(auto task:fighters_[side].storage.objectTasks) {
        if(!task)continue;
        const auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(task-1)[7]-1);
        if(o[0xcc/4]!=4)continue;
        if(std::bit_cast<float>(o[0x44/4])<=0)groundedX[side]=ScalarFloat{o[0x40/4]}.truncate();
        break;
    }
    b.itemNotices.visit(b.gauges.delta46a908,b.camera,groundedX,
                        {fighters_[0].actor.controlKindA20!=0,fighters_[1].actor.controlKindA20!=0});
}
void NativeMatch::visitStageItems(bool retainFighters) {
    auto& q=objectDraws_;
    if(!retainFighters)itemDrawSlot_=q.count;
    else {
        // Priority 50 keeps its previous fighter pictures while the VS menu
        // is open. Replace just the moving courier/item submissions before them.
        std::move(q.slots.begin()+itemDrawSlot_+itemDrawCount_,q.slots.begin()+q.count,q.slots.begin()+itemDrawSlot_);
        q.count-=itemDrawCount_;
    }
    const unsigned before=q.count;
    battle_.stageItems.visit(battle_.gauges,aux_,q);
    itemDrawCount_=q.count-before;
    if(retainFighters){
        std::rotate(q.slots.begin()+itemDrawSlot_,q.slots.begin()+before,q.slots.begin()+q.count);
        q.sort();
    }
}
int NativeMatch::curtainFrame() const {
    if(unavailable_)return -1;
    if(faceoff_ && faceoff_->transitionTick)return int(faceoff_->transitionTick)-1;
    if(fromFaceoff_ && updates<16)return 17+int(updates);
    return -1;
}
int NativeMatch::selectWhiteLevel() const {
    // 125678 increases by integer 255/30 from level zero. At the scene
    // callback the hold has finished and the next visit starts at level 256.
    if(titleFadeTick_) {
        // Type 1, speed 0: advance by 255/10 each visit; hold three
        // visits at full white while the two scene callbacks exchange tasks.
        if(titleFadeTick_<=15)return std::min(256,(titleFadeTick_-1)*25);
        return std::max(0,256-(titleFadeTick_-16)*25);
    }
    if(faceoff_)return std::clamp(264-faceoff_->background*8,0,256);
    return std::clamp((selectFade_-1)*8,0,256);
}
void NativeMatch::enterTitleAudio() {
    sounds_.stopGroup(1);
    sounds_.bindPlayers(51,lineup_[1].character);
    sounds_.playMusic(1,0x3200);
}
void NativeMatch::openTitle(bool returningFromVersus) {
    title_.emplace(returningFromVersus);
    titleFadeTick_=0;titleAudioPending_=!returningFromVersus;
    if(returningFromVersus) {
        // 1db334 clears GameData before setting its continue and end flags.
        // The continue flag also selects the shared PLEASE WAIT text if the
        // player cancels back out of the mode menu.
        auto& end=battle_.matchEnd;
        end.winner08=-1;end.stage28=end.result8c=end.submodeA0=0;
        end.metadataStage04=end.field18=0;
        end.continue2c=end.endFlagA4=1;
        battle_.stageItemsOption4c3828=0;
        enterTitleAudio();
    }
    else battle_.random={}; // A cold title precedes the first battle's RNG draws.
}
void NativeMatch::enterSelectAudio() {
    sounds_.stopGroup(1);sounds_.stopGroup(1);sounds_.bindPlayers(51,52);
    sounds_.playMusic(2,0x3200);
}
void NativeMatch::leaveUnportedFight(const UnportedFighterState& move) {
    sounds_.beginFrame();sounds_.stopMusic();sounds_.stopGroup(2);
    openCharacterSelect();unavailable_=true;
    const char* fighter=versusFighterName(move.character);
    missingMove_=std::string(fighter)+" MOVE "+std::to_string(move.table)+"/"+std::to_string(move.state)+" IS IN DEVELOPMENT";
}
void NativeMatch::openCharacterSelect(bool boot) {
    // 1db2e0 invalidates both character-confirmed flags on reselect. The
    // loser (last entrant in a draw) still owns the later stage choice.
    characterSelect_.emplace();
    characterSelect_->random=boot?GameRandom{}:battle_.random;
    characterSelect_->stageOwner=battle_.consoleMenu.session.lastEntrant;
    if(!boot) {
        characterSelect_->stageOption=battle_.stageItemsOption4c3828;
        for(unsigned i=0;i<2;++i)characterSelect_->seats[i].palette=lineup_[i].palette;
    }
    faceoff_.reset();unavailable_=false;unavailableStage_=-1;missingMove_.clear();
    selectFade_=0;selectAudioPending_=boot;
    if(!boot)enterSelectAudio();
}
VersusLineup NativeMatch::selectedLineup() const {
    VersusLineup picks{};
    for(unsigned i=0;i<2;++i) {
        const auto& seat=characterSelect_->seats[i];
        picks[i]={unsigned(seat.selected),unsigned(seat.spirit),unsigned(seat.palette)};
    }
    return picks;
}
void NativeMatch::buildPresentationDraws(ObjectDrawQueue& queue) const {
    // ACT489 uses the fighters' tile and palette allocator. Insert the portraits
    // where priority 20 ran, before sorting. The scene-only dump omits these two
    // HUD submissions so its caller can inspect the unobstructed arena.
    const auto rows=objectDraws_.active();
    queue.count=std::min<unsigned>(portraitPosition_,rows.size());
    std::copy_n(rows.begin(),queue.count,queue.slots.begin());
    const auto firstRemaining=queue.count;
    if(hudClock_.visible) {
        GaugeState sample{};
        sample.words910[2]=portraitClocks_[0];
        sample.words910[3]=portraitClocks_[1];
        FighterIdentityHud::submitPortraits(queue,sample,resourceSlots_,identityHud_);
    }
    const auto remaining=std::min(rows.size()-firstRemaining,queue.slots.size()-queue.count);
    std::copy_n(rows.begin()+firstRemaining,remaining,queue.slots.begin()+queue.count);
    queue.count+=unsigned(remaining);
    queue.sort();
}

void NativeMatch::sampleHud() {
    auto& b=battle_;
    const auto& left=fighters_[0].actor;
    const auto& right=fighters_[1].actor;
    // The HUD visits before the round timer and contacts. Its
    // published glyphs can therefore lag the final match state.
    hudClock_={b.remainingSeconds(),roundClockStopped(b.currentState,left,right),true};
    std::array<int32_t,2> amount{left.rageAmount124,right.rageAmount124};
    // 13fd80 asks the HUD to reseed its displayed values at round
    // entry. Later ticks retain fill and flash history across draws.
    rageGauge_.resetOnLastVisit=b.phase130==1;
    identityHud_.sample(b,rageGauge_.resetOnLastVisit);
    portraitClocks_={b.gauges.words910[2],b.gauges.words910[3]};
    if(rageGauge_.resetOnLastVisit){rageGauge_.reset(amount);b.phase130=0;}
    std::array<LifeGaugeInput,2> lifeGauges{};
    for(unsigned i=0;i<2;++i) {
        const auto& a=fighters_[i].actor;
        const auto hurt=a.stateIndex();
        lifeGauges[i]={a.systemState13c,fighters_[i].config.system==5?a.systemMeter158:a.systemAmount140,a.systemTime144,std::max(0,a.fieldA30),
                 a.swordCurrent134,a.swordMaximum138,int(b.match.players[1-i].hitCount0c),
                 a.stateTable()==2&&(hurt>=32||(hurt>=18&&hurt<24))};
    }
    rageGauge_.advance({left.rageState120,right.rageState120},amount,
                       {int32_t(fighters_[0].config.system),int32_t(fighters_[1].config.system)},
                       {left.flags23c,right.flags23c},lifeGauges,b.pause.remaining!=0||b.pause.delay!=0);
}

void NativeMatch::tick(const std::array<NormalizedPadSample,2>& pads) {
    // 113aa8 samples the flash counter BEFORE 112838 dispatches contacts.
    // Thus the hit itself is visible, followed by three white frames.
    mikiriWhiteFrame_=mikiriFlashLeft_!=0;
    if(mikiriWhiteFrame_)--mikiriFlashLeft_;
    sounds_.beginFrame();
    // 118148 visits the global PRESS START task before the scene and even
    // while 2P menus or combat hide its text. It survives scene replacement.
    promptClock_=(promptClock_+1)%120;
    if(title_) {
        auto& menu=battle_.consoleMenu;
        menu.samplePads({resultPad(pads[0].held),resultPad(pads[1].held)},
                        {resultPad(pads[0].pressed),resultPad(pads[1].pressed)});
        menu.tick(); // The incoming black fade survives the result task.
        if(menu.destination==ConsoleVersusDestination::Title && menu.fadeAlpha==0)
            battle_.matchEnd.continue2c=0; // 1252ec releases PLEASE WAIT on the final fade visit.
        if(titleAudioPending_){enterTitleAudio();titleAudioPending_=false;}
        title_->tick(menu.padCommands(),(pads[0].pressed|pads[1].pressed)&PadStart);
        for(int tone:title_->tones)if(tone>=0)sounds_.sample(tone==1?0:-1,tone);
        if(title_->announce)sounds_.voice(49,0);
        titleFadeTick_=title_->transitionTick;
        if(titleFadeTick_==15) {
            menu.beginSet(title_->confirmingSeat);
            title_.reset();
            sounds_.stopMusic();sounds_.stopGroup(2);
            // 124d50/11d1a8 clear the previous set's game and selection
            // records. The process RNG outlives both, including title visits.
            battle_.matchEnd.submodeA0=2;
            openCharacterSelect(true);
            characterSelect_->random=battle_.random;
            selectAudioPending_=false;enterSelectAudio();
        }
        return;
    }
    if(characterSelect_) {
        if(titleFadeTick_ && ++titleFadeTick_>=27)titleFadeTick_=0;
        const std::array<NormalizedPadSample,2> ui{{
            {resultPad(pads[0].held),resultPad(pads[0].pressed)},
            {resultPad(pads[1].held),resultPad(pads[1].pressed)}}};
        if(unavailable_) {
            if((ui[0].pressed|ui[1].pressed)&0x60f)openCharacterSelect();
            return;
        }
        battle_.consoleMenu.tick(); // complete the global transition from the results menu
        if(selectAudioPending_) {
            enterSelectAudio();selectAudioPending_=false;
        }
        if(faceoff_) {
            const auto picks=selectedLineup();
            const std::array<unsigned,2> characters{picks[0].character,picks[1].character};
            faceoff_->tick({ui[0].pressed,ui[1].pressed},characters,sounds_);
            if(faceoff_->transitionTick==16)sounds_.sample(-1,15);
            if(faceoff_->transitionTick==18) {
                // 125848's third hold visit tears down the VS preview and
                // enters the match in the same priority-60 dispatch.
                sounds_.stopMusic();sounds_.stopGroup(2);
                auto random=battle_.random;
                const auto stage=selectConsoleVersusStage(random,characterSelect_->stage);
                if(!CombatStageState::supports(stage)||!playableFighter(characters[0])||!playableFighter(characters[1])||picks[0].spirit>5||picks[1].spirit>5) {
                    unavailable_=true;unavailableStage_=stage;
                }
                else {
                    sounds_.enterBattleScene(battle_.voiceGate5850e0!=0);
                    faceoff_->complete=true;
                }
            }
            return;
        }
        {
            // Both menu tasks continue drawing while the global white fade runs.
            characterSelect_->tick(ui);
            for(auto event:characterSelect_->audio)sounds_.sample(event.bank,event.tone);
            battle_.random=characterSelect_->random;
        }
        if(characterSelect_->complete&&++selectFade_==36) {
            const auto picks=selectedLineup();
            sounds_.stopMusic();sounds_.stopGroup(2);
            sounds_.stopGroup(1);sounds_.stopGroup(1);sounds_.bindPlayers(picks[0].character,picks[1].character);
            faceoff_.emplace();
        }
        return;
    }
    if(!sceneAudioEntered_) {
        if(lineup_[0].character||lineup_[1].character)sounds_.bindPlayers(lineup_[0].character,lineup_[1].character);
        sounds_.enterBattleScene(battle_.voiceGate5850e0!=0);
        sceneAudioEntered_=true;
    }
    if(battle_.matchEnd.submodeA0==2) {
        auto& menu=battle_.consoleMenu;
        menu.samplePads({resultPad(pads[0].held),resultPad(pads[1].held)},
                        {resultPad(pads[0].pressed),resultPad(pads[1].pressed)});
        // The game polls both ports before the menu task. Its stop bit
        // suspends the fighter and round clocks while the overlay is open.
        if(menu.active && menu.destination==ConsoleVersusDestination::None) {
            // 1392f8 defers the freeze until priority 50. The stage gets its
            // usual priority-10 visit first, even on the first menu update.
            auto& gauges=battle_.gauges;
            activeStage().visit(battle_.camera,gauges.delta46a908,battleBackdropColor_!=0,&battle_.random);
            sampleHud();
            visitReferee(true);
            visitStageItems(true);
            gauges.paused46a940=1;
            gauges.words910[5]=1;
            gauges.delta46a908=0;
        }
        const auto previous=menu.destination;
        for(int tone:menu.tick())if(tone>=0)sounds_.sample(-1,tone);
        if(previous==ConsoleVersusDestination::None && menu.destination!=previous) {
            // 125264 and 125274 run both transition callbacks on this tick.
            // 139778 tears down the old song before 139760 enters CONTINUE.
            if(battle_.voiceGate5850e0)sounds_.stopMusic();
            sounds_.stopMusic();
            if(menu.destination==ConsoleVersusDestination::Title)openTitle(true);
            if(menu.destination==ConsoleVersusDestination::CharacterSelect)openCharacterSelect();
            if(menu.destination==ConsoleVersusDestination::Rematch) {
                auto preview=battle_.random;
                const int arena=selectConsoleVersusStage(preview,selectedStage_);
                if(CombatStageState::supports(arena))sounds_.enterBattleScene(battle_.voiceGate5850e0!=0);
                else {
                    // CONTINUE rerolls RANDOM. Preserve the session while the
                    // player chooses a supported arena from the live selector.
                    openCharacterSelect();unavailable_=true;unavailableStage_=arena;
                }
            }
        }
        if(menu.active)return;
    }
    if(finished) {
        auto& result=battle_.resultScreen;
        auto& gauges=battle_.gauges;
        if(result.scene==VersusScene::Draw && result.presentationReady) {
            // 13847c publishes a fixed camera. Reloading this stage keeps
            // its animation clocks, including across the Game Over skip.
            activeStage().visit(StageCamera{},256,false,&battle_.random);
            std::fill(gauges.paletteTones.begin()+256,gauges.paletteTones.end(),1);
        } else if(!result.presentationReady &&
                  (result.scene==VersusScene::Draw || result.scene==VersusScene::Winner)) {
            // The old priority-10 task still runs before the transition
            // midpoint cancels its tag. The underlying arena keeps moving.
            activeStage().visit(battle_.camera,gauges.delta46a908,battleBackdropColor_!=0,&battle_.random);
            sampleHud();
        } else {
            activeStage().visible=false;
        }
        updateVersusResult(result,{resultPad(pads[0].pressed),resultPad(pads[1].pressed)});
        return;
    }
    auto refs=players();auto& b=battle_;
    ++updates;objectDraws_.beginFrame();draws_.clear();effects_.update();
    TaskDispatch tasks;tasks.call=[&](uint32_t handler,uint32_t task){
        if(handler==0x124898)captions_.task(task,b.entry.tasks,b.effectResidency,b.paletteState,objectDraws_,b.gauges);
        else if(handler==0x11e708)gauges_.task(b,refs,&sounds_);
        else if(handler==activeStage().handler())activeStage().visit(b.camera,b.gauges.delta46a908,battleBackdropColor_!=0,&b.random);
        else if(handler==0x1b4228)visitReferee(false);
        else if(handler==0x1b51b8)visitStageItems(false);
        else if(handler==0x1bab38){portraitPosition_=objectDraws_.count;sampleHud();}
        else throw std::runtime_error("Unimplemented battle task "+std::to_string(handler));
    };
    b.entry.tasks.dispatchTasks(tasks);
    draws_.insert(draws_.end(),effects_.draws().begin(),effects_.draws().end());
    // 139224 returns to 13abb0 every battle tick. Issen clears both music
    // latches on capture, so its next visit prepares the stage stream again
    // while the victim is held. The finishing callback releases that stream.
    if(!b.audio.musicPreloaded123a178) {
        sounds_.preloadMusic(0,int(b.matchEnd.metadataStage04)+5);
        b.audio.musicPreloaded123a178=true;
    }
    // Priority 50 publishes the delta for the next dispatch even after the
    // priority-5 gauge task has ended. KO slowdown still affects the arena.
    b.gauges.words910[5]=0;
    if(b.pause.advance()){
        b.gauges.paused46a940=1;
        auxiliaryPhase(ObjectPhase::Draw);
        return;
    }
    b.gauges.paused46a940=0;
    b.gauges.delta46a908=(b.gauges.scale1239d84*b.gauges.scale1239d88)>>8;
    RoundControl::advanceBattleClock(b,refs);
    resolveContacts();
    rounds_.step(b,refs);
    if(b.consoleMenu.active||b.resultScreen.scene!=VersusScene::None) {
        // The round clock ends here. The winner's pad and page animation
        // continue on their own clock on subsequent visits.
        finished=true;
        auxiliaryPhase(ObjectPhase::Draw);
        return;
    }
    for(unsigned i=0;i<2;++i)fighters_[i].body.animate(resolveObjectDelta(fighters_[i].body.delta30,i,b.gauges));
    for(unsigned i=0;i<2;++i)fighters_[i].body.move(resolveObjectDelta(fighters_[i].body.delta30,i,b.gauges));
    auxiliaryPhase(ObjectPhase::Move);
    updateStage();
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];auto& a=f.actor;
        auto speed=b.timers.rawDelta;
        if(!speed&&(a.flags23c&0x08000000))speed=256;
        f.body.delta30=(speed*(a.timers[1]?128:256))>>8;
        a.timerDelta=resolveObjectDelta(f.body.delta30,i,b.gauges);
        // 151e10 sends the identical scaled delta to the actor and AI timers.
        // A guard, concentration or KO slowdown can therefore age a CPU
        // decision by a fractional tick even when its input is still polled.
        a.cpuTimerDelta08=a.timerDelta;
        ground_.prepareInput(a,fighters_[1-i].actor,f.input,f.objects,distance_);
        LifeState life{a.fieldA30,a.maximumLifeA34,a.pendingDamageA38,a.queuedActionA3c,a.flags23c,a.conditions15c[1],a.y};
        // 1519a0 issues the heal label before HP is capped. A full notice
        // pool suppresses only the label and its sound, never the recovery.
        if(life.pendingDamage<0&&b.itemNotices.heal(int(f.body.timeline.motion().x)))sounds_.sample(-1,65);
        ActorTimers timers{a.timerDelta,a.timers};commitLife(life,timers);
        a.fieldA30=life.life;a.pendingDamageA38=life.pendingDamage;a.flags23c=life.flags23c;
        a.queuedActionA3c=life.queuedAction;a.timers=timers.values;
    }
    RoundControl::inputLocks(b,refs);
    // 146348 snapshots both opponents before P1 can enter a new state.
    for(unsigned seat=0;seat<2;++seat)if(cpuTactics_[seat])
        observeCpuSituation(fighters_[seat].actor,fighters_[1-seat].actor,*cpuTactics_[seat],ground_.entryRules());
    for(unsigned i=0;i<2;++i)visitActor(i,pads);
    for(auto& f:fighters_)ground_.commitAction(f.body,f.actor);
    auxiliaryPhase(ObjectPhase::Callbacks);
    for(unsigned i=0;i<2;++i) {
        auto& f=fighters_[i];f.body.commitRequested();
        const auto c=f.body.timeline.clock();
        const auto state=f.actor.stateIndex();
        // A held ACT record can span several visits. Its object attachment
        // is emitted once on record entry, even when the character is paused.
        const auto attachment=f.body.timeline.attachedEffect()[0];
        const bool sharedEffect=(c.flags104&0x18002)==0x18000;
        if(sharedEffect||((c.flags104&0x18002)==0x8000&&attachment!=0)) {
            auto parent=f.body.childParentWords();
            const auto& command=f.body.timeline.attachedEffect();
            parent[0x110/4]=uint32_t(command[1]);parent[0x114/4]=uint32_t(command[2]);
            aux_.spawnActAttachment(b.entry.tasks,f.storage.objectTasks,b.objectTasks,i,f.actor.flags23c,parent,parent,
                                    unsigned(attachment),sharedEffect);
        }
        if((f.actor.character==2||f.actor.character==3)&&f.actor.stateTable()==1&&state>=64&&(c.flags104&0x18002)==0x8000&&attachment==0) {
            auto parent=f.body.childParentWords();
            const auto& command=f.body.timeline.attachedEffect();
            parent[0x110/4]=uint32_t(command[1]);parent[0x114/4]=uint32_t(command[2]);
            if(f.actor.character==2)spawnRimururuIce(aux_,b.entry.tasks,f.storage.objectTasks,i,f.actor,parent);
            else spawnHanzoProjectile(aux_,b.entry.tasks,f.storage.objectTasks,i,f.actor,parent);
        }
        // 16d9c8 reads the running script row at an ACT spawn marker. Mina's
        // rows fire arrows even from ordinary crouching and jumping slashes.
        if(f.actor.character==24&&f.actor.registry28c[11]&&(c.flags104&0x18002)==0x8000&&attachment==0)
            if(const auto* row=ground_.scripts().current(f.actor))spawnMinaProjectile(i,0,0,row);
        if(f.actor.character==0&&f.actor.stateTable()==1&&state>=64&&
           (c.flags104&0x18002)==0x8000&&attachment==0) {
            auto parent=f.body.childParentWords();
            const auto& command=f.body.timeline.attachedEffect();
            parent[0x110/4]=uint32_t(command[1]);parent[0x114/4]=uint32_t(command[2]);
            if(state<=66)aux_.spawnWhirlwind(b.entry.tasks,f.storage.objectTasks,i,f.actor.flags23c,parent,unsigned(state-64));
            else if((state>=68&&state<=73)||state==79)aux_.spawnRisingSlashTrail(b.entry.tasks,f.storage.objectTasks,i,f.actor.flags23c,parent,state);
            else if(state==77)spawnHaohmaruFlask(aux_,b.entry.tasks,f.storage.objectTasks,i,f.actor.flags23c,parent);
        }
        f.body.setFlags(c.flags104&~0x18000u,c.flags108);ground_.captureBody(f.body,f.actor);
        // 1474a0 scans this seat immediately after its body. A particle born
        // from an ice projectile inherits the owner's palette and facing, but
        // its offsets are relative to the projectile that submitted the ACT.
        auto& pools=b.entry.tasks;
        for(auto task:f.storage.objectTasks)if(task) {
            auto& emitter=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            auto& flags=emitter[0x104/4];
            if((flags&0x8002)==0x8000&&emitter[0x0c/4]<2) {
                auto parent=f.body.childParentWords();
                const auto action=emitter[0x10c/4];
                aux_.spawnActAttachment(pools,f.storage.objectTasks,b.objectTasks,i,f.actor.flags23c,parent,emitter,
                                        action,(flags&0x10000)!=0);
            }
            flags&=~0x18000u;
        }
    }
    auxiliaryPhase(ObjectPhase::Draw);
    const bool captured=std::any_of(fighters_.begin(),fighters_.end(),[](const MatchFighter& f){
        return f.actor.stateTable()==2&&f.actor.stateIndex()>=80;
    });
    setCaptureObjectGates(captured,false);
    if(b.stageItems.itemIndex()==8) {
        spawnStageBomb(aux_,b.entry.tasks,b.objectTasks,b.stageItems.itemX());
        b.stageItems.clear();
    }
}
}
