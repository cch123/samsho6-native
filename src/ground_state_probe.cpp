#include "ground_state.hpp"
#include "battle_round.hpp"
#include "scheduled_opening.hpp"
#include "human_input.hpp"
#include "ending_playback.hpp"
#include "round_initialization.hpp"
#include "sound_selection.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

int main(int argc,char** argv) {
 try {
    if(argc!=2&&argc!=3)throw std::runtime_error("Expected assets directory and optional fighter");
    // Optional argv[2]: the fighter resource (default resource 00).
    const unsigned fighter=argc==3?unsigned(std::stoul(argv[2])):0;
    ss6::ActionBank bank(argv[1],true,fighter);ss6::GroundStateRuntime ground(argv[1]);ss6::HumanInputPipeline human(argv[1]);
    ss6::ReactionTables reactions(argv[1]);
    ss6::RoundInitialization roundInitialization(argv[1]);ss6::RoundActorStorage roundStorage;
    ss6::SoundSelection sounds(argv[1]);
    ss6::BattleEffects effects(argv[1]);ss6::GameRandom random;unsigned dustEvents=0;
    std::unique_ptr<ss6::PlayerObject> object;
    ss6::StateEntryActor a,opponent;ss6::ActorCommandInput input;ss6::InputSampler sampler;
    ss6::StateEntryContext entry;ss6::InputSystemConfig config;ss6::ActorInputSampling frame;
    ss6::PermissionContext permission;ss6::SelectionThreat threat;ss6::GroundStateFrame groundFrame;
    ss6::CallbackContext objects;bool phases=false,contactPhases=false;uint32_t delta=256;
    ss6::PlayerMatchStats matchStats;
    bool koPhases=false;unsigned recoveryDiagnostics=0;
    bool colorProjection=false;
    bool queueProjection=false,specialProjection=false;
    bool roundProjection=false;
    ss6::BattleRoundState wallBattle;ss6::ScheduledOpening wallEffects(argv[1]);
    std::array<ss6::NormalizedPadSample,2> pads{};std::array<ss6::InputMapping,2> mappings{};
    for(auto& map:mappings)for(unsigned i=0;i<8;++i)map.normal[i]=map.mode6[i]=1u<<(8+i);
    std::string op;
    while(std::cin>>op) {
        if(op=="reset") {
            unsigned player,mirror;float x,other;std::cin>>player>>mirror>>x>>other;
            a={};opponent={};input={};sampler={};entry={};permission={};frame={};pads={};objects={};phases=contactPhases=false;delta=256;
            effects.reset();random={};dustEvents=0;
            sounds.reset();
            groundFrame={};matchStats={};groundFrame.matchStats=&matchStats;
            koPhases=false;recoveryDiagnostics=0;
            colorProjection=false;
            queueProjection=specialProjection=false;
            roundProjection=false;roundStorage={};
            object=std::make_unique<ss6::PlayerObject>(bank,0);
            object->timeline.setSoundObserver([&](int16_t command,const ss6::ActionClock& clock){sounds.record(command,clock,0,random);});
            object->ownerCC=player;
            object->timeline.setObjectFlags(0x10000000|(mirror?0x80000:0),0x40002200,0x40);
            object->timeline.setPosition(x,0);
            a.flags23c=0x1000;a.flags248=2;a.stateFlags19a=0x9e;a.state1a4=0xffffffff;
            a.fieldA30=200;a.swordCurrent134=a.swordMaximum138=25600;a.conditions15c[1]=1;
            a.registry28c[2]=0xffffffff;a.character=fighter;config.character=fighter;
            opponent.flags23c=0x1000;opponent.x=other;
            frame.player=entry.player=player;frame.expectedFacing=mirror;frame.battleState=4;
            groundFrame.opponentX=other;threat.distance=int(other>x?other-x:x-other);
            groundFrame.objects=&objects;
            groundFrame.effects=&effects;groundFrame.random=&random;
            human.initialize(input,config);
        } else if(op=="wall-camera") {
            wallBattle={};
            std::cin>>wallBattle.camera.left>>wallBattle.camera.right;
            groundFrame.battle=&wallBattle;
            auto& pools=wallBattle.entry.tasks;
            pools.initializeOwners();pools.initializeObjects();pools.initializeTasks();
            for(unsigned i=1;i<=3;++i)wallBattle.effectResidency.slots[i]=i+1;
            object->timeline.setEffectObserver([&](unsigned id,uint32_t flags,float x,float y){
                wallEffects.startWorld(id,flags,frame.player,x,y,-10,1,pools,wallBattle.effectResidency,random);
            });
        } else if(op=="phases") {
            phases=true;
        } else if(op=="round-storage") {
            roundProjection=true;entry.tasks={};entry.tasks.initializeTasks();entry.tasks.initializeObjects();roundStorage={};
        } else if(op=="round-data") {
            std::cin>>a.flags240>>a.fieldA50>>a.auxiliaryObject04>>a.fieldF10
                >>a.rageDecay128>>a.swordWait130>>a.swordCurrent134>>a.swordMaximum138
                >>a.controlFlagsB4>>a.flagsB8>>a.controlCounterC0>>a.controlModeC8
                >>a.control88>>a.control8c>>a.controlFlagsBC>>a.controlC4>>a.controlCC>>a.controlD8>>a.controlE4>>a.controlE8;
            for(auto& v:a.controlTimers0c)std::cin>>v;
            for(auto& v:a.controlMotion38)std::cin>>v;
            for(auto& v:a.characterBytesF14){unsigned value;std::cin>>value;v=uint8_t(value);}
            for(auto& v:a.characterBytesF22){unsigned value;std::cin>>value;v=uint8_t(value);}
            std::cin>>random.mode>>random.gameSeed>>random.librarySeed;
        } else if(op=="round-body") {
            std::cin>>object->resourceSlot0c>>object->delta30>>object->scale70;
            for(auto& value:object->zWords)std::cin>>value;
            std::cin>>object->historyOffsetEc>>object->historyOffsetF0;
        } else if(op=="round-meter") {
            std::cin>>a.rageState120>>a.rageAmount124>>a.fieldA2c>>a.fieldA28;
        } else if(op=="round-replay") {
            uint32_t seed;std::cin>>seed;
            for(unsigned i=0;i<600;++i){sampler.replayHeld[i]=uint16_t(seed+i*13);sampler.replayPressed[i]=uint16_t(seed*3+i*7);}
        } else if(op=="new-round") {
            unsigned first;std::cin>>first;
            roundInitialization.begin(ground,*object,a,input,config,entry,groundFrame,roundStorage,first!=0);
        } else if(op=="commit-body") {
            object->commitRequested();ss6::GroundStateRuntime::captureBody(*object,a);
        } else if(op=="colors") {
            colorProjection=true;
        } else if(op=="special-fields") {
            specialProjection=true;
        } else if(op=="queues") {
            queueProjection=true;
        } else if(op=="queued-action") {
            std::cin>>a.queuedActionA3c>>a.flags248;
        } else if(op=="commit-actor") {
            ground.commitAction(*object,a);
        } else if(op=="color-context") {
            std::cin>>a.rageState120>>a.fieldA2c>>a.fieldA28;
        } else if(op=="combat") {
            phases=contactPhases=true;
        } else if(op=="ko-phases") {
            phases=contactPhases=koPhases=true;
        } else if(op=="life") {
            std::cin>>a.fieldA30>>a.maximumLifeA34>>a.pendingDamageA38;
        } else if(op=="round-context") {
            std::cin>>frame.battleState>>matchStats.wins>>matchStats.requiredWins;
        } else if(op=="intro-defer"||op=="intro-release") {
            ss6::ActorTimers timers{a.timerDelta,a.timers};ss6::EndingPlayback ending;
            if(op=="intro-defer") {int ticks;std::cin>>ticks;ending.deferIntroduction(*object,timers,ticks);}
            else ss6::EndingPlayback::releaseIntroduction(*object,timers);
            a.timers=timers.values;ss6::GroundStateRuntime::captureBody(*object,a);
        } else if(op=="posture") {
            std::cin>>a.flags23c>>a.flags244;
        } else if(op=="body-motion") {
            ss6::MotionState m;std::cin>>m.dx>>m.vx>>m.ax>>m.dy>>m.vy>>m.ay>>m.x>>m.y;
            object->timeline.setMotion(m);ss6::GroundStateRuntime::captureBody(*object,a);
        } else if(op=="watchdog") {
            recoveryDiagnostics+=ground.beforeCallbacks(*object,a);
        } else if(op=="watchdog-fixture") {
            float y;std::cin>>a.state194>>a.flags23c>>a.timers[15]>>a.timerDelta
                >>a.request18c>>a.pendingTable>>a.pendingIndex>>y;
            object->timeline.setPosition(object->timeline.motion().x,y);a.y=y;
        } else if(op=="hit"||op=="guard") {
            ss6::ReactionTarget target;static_cast<ss6::ActorContactHistory&>(target)=a;
            target.flags23c=a.flags23c;target.flags244=a.flags244;target.flags24c=a.flags24c;target.stateTable=int16_t(a.stateTable());
            ss6::ActorTimers own{a.timerDelta,a.timers},source{opponent.timerDelta,opponent.timers};
            if(op=="hit") {
                unsigned raw,part,special,air;std::cin>>raw>>part>>special>>air;
                opponent.state194=((raw==12?8:0)<<16)|1;opponent.flags23c=0x1000|(air?0x20:0);
                opponent.stateFlags19a=raw==12?12:8;opponent.bodyAction24=raw==12?189:185;
                reactions.applyGroundHit(target,source,own,raw,part,special,air,raw==12?2:0,opponent.flags248);
            } else {
                unsigned defense,strength,ignored;std::cin>>defense>>strength;
                opponent.state194=1;opponent.flags23c=0x1000;opponent.bodyAction24=185;
                reactions.applyGuard(target,source,own,defense,strength,ignored);
            }
            static_cast<ss6::ActorContactHistory&>(a)=target;
            a.flags23c=target.flags23c;a.flags244=target.flags244;a.timers=own.values;opponent.timers=source.values;
            if(target.forceState){a.pendingTable=target.pendingTable;a.pendingIndex=target.pendingState;a.request18c=1;}
        } else if(op=="clash") {
            unsigned strength;std::cin>>strength;
            const auto r=ss6::queueWeaponClash(a.flags23c,a.stateTable(),a.stateIndex(),strength,true);
            a.flags23c=r.flags23c;a.pendingTable=r.table;a.pendingIndex=r.state;
        } else if(op=="attack") {
            int state;std::cin>>state;a.pendingTable=1;a.pendingIndex=int16_t(state);
        } else if(op=="damage") {
            int state;std::cin>>state;a.pendingTable=2;a.pendingIndex=int16_t(state);a.request18c=1;
        } else if(op=="objects") {
            objects.ownObjects[2]=1;objects.ownObjects[7]=2;objects.ownObjects[9]=1;
            objects.objects[1]={3,0x12345678,0x200042};objects.objects[2]={3,0x89abcdef,0x208080};
        } else if(op=="timer") {
            unsigned index;int32_t value;std::cin>>index>>value;a.timers.at(index)=value;
        } else if(op=="history") {
            for(auto* v:{&a.field250,&a.field251,&a.contactKind252,&a.landingCount253,&a.pendingCharacter254,&a.previousReaction,&a.secondaryReaction,&a.field257}) {
                unsigned word;std::cin>>word;*v=uint8_t(word);
            }
            std::cin>>a.heavyReaction>>a.extraReaction25c;
        } else if(op=="state") {
            int state;std::cin>>state;a.pendingTable=0;a.pendingIndex=int16_t(state);
        } else if(op=="other") {
            std::cin>>groundFrame.opponentX;opponent.x=groundFrame.opponentX;
        } else if(op=="lock") {
            unsigned flags;std::cin>>flags;a.flags24c=uint8_t(flags);
        } else if(op=="threat") {
            unsigned active;std::cin>>active;
            opponent.state194=active?1:0;opponent.bodyAction24=active?185:0;
            opponent.flags23c=active?0x1001:0x1000;
        } else if(op=="tick"||op=="pad") {
            if(!object)throw std::runtime_error("Reset required");
            const bool raw=op=="pad";
            if(raw)std::cin>>pads[frame.player].held>>pads[frame.player].pressed;
            if(contactPhases)ground.afterContacts(*object,a,input,config,entry);
            object->animate(object->delta30);object->move(object->delta30);ss6::GroundStateRuntime::captureBody(*object,a);
            a.opponentX=groundFrame.opponentX;
            threat.distance=ss6::playerDistance(a.x,groundFrame.opponentX);
            if(contactPhases){delta=a.timers[1]?128:256;a.timerDelta=int32_t(delta);}
            object->delta30=delta;
            if(phases)ground.prepareInput(a,opponent,input,objects,threat.distance);
            if(contactPhases) {
                ss6::LifeState life;life.life=a.fieldA30;life.maximum=a.maximumLifeA34;life.pendingDamage=a.pendingDamageA38;
                life.flags23c=a.flags23c;life.conditions=a.conditions15c[1];life.y=a.y;
                ss6::ActorTimers timers{a.timerDelta,a.timers};ss6::commitLife(life,timers);
                a.fieldA30=life.life;a.pendingDamageA38=life.pendingDamage;a.flags23c=life.flags23c;a.timers=timers.values;
            }
            if(raw) {
                ss6::SystemCancelContext cancel;cancel.controlOwner=&a;cancel.controlInput=&input;cancel.controlConfig=&config;
                const auto route=human.requests(a,opponent,input,sampler,frame,pads,mappings,config,permission,threat,cancel);
                if(route==ss6::ActorInputRoute::AiRequired)throw std::runtime_error("AI outside human fixture");
                ss6::GroundStateRuntime::restoreBody(*object,a);
            }
            groundFrame.opponentFlags23c=opponent.flags23c;
            if(koPhases)recoveryDiagnostics+=ground.beforeCallbacks(*object,a);
            dustEvents+=ground.visit(*object,a,input,config,entry,groundFrame).dust;
            if(raw)ss6::finishActorInput(a,frame,pads,mappings);
            ground.commitAction(*object,a);
            object->commitRequested();ss6::GroundStateRuntime::captureBody(*object,a);
        } else throw std::runtime_error("Unknown ground probe command");
        if(!std::cin)throw std::runtime_error("Incomplete ground fixture");
        std::cout<<a.state194<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '
            <<unsigned(a.stateFlags19a)<<' '<<a.flags23c<<' '<<a.flags244<<' '<<a.flags248<<' '<<a.controlCounterC0;
        for(auto v:a.conditions15c)std::cout<<' '<<v;
        for(auto v:a.callbacks260)std::cout<<' '<<v;
        for(auto v:a.timers)std::cout<<' '<<v;
        const auto c=object->timeline.clock();const auto m=object->timeline.motion();
        std::cout<<' '<<object->timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '<<c.endReached
            <<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '<<object->pendingFlags
            <<' '<<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay
            <<' '<<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y);
        for(auto v:input.sampledFeatures)std::cout<<' '<<v;
        for(const auto& slots:{std::span<const ss6::CommandSlot>(input.normal),std::span<const ss6::CommandSlot>(input.special)})
            for(const auto& s:slots)std::cout<<' '<<s.recognized<<' '<<s.cancelAllowed<<' '<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered);
        for(const auto& p:sampler.pressLatches)for(auto v:p)std::cout<<' '<<unsigned(v);
        std::cout<<' '<<a.stateCharacter198<<' '<<a.swordWait130<<' '<<entry.opponentFlagsB8<<' '<<entry.attackMarker12d2300<<' '<<unsigned(a.flags24c);
        for(unsigned h:{1u,2u}) {
            const auto found=objects.objects.find(h);
            if(found==objects.objects.end())std::cout<<" 0 0";
            else std::cout<<' '<<found->second.fieldD4<<' '<<found->second.flags108;
        }
        for(auto v:{a.field250,a.field251,a.contactKind252,a.landingCount253,a.pendingCharacter254,a.previousReaction,a.secondaryReaction,a.field257})std::cout<<' '<<unsigned(v);
        std::cout<<' '<<a.heavyReaction<<' '<<a.extraReaction25c;
        for(auto v:a.override27c)std::cout<<' '<<v;
        std::cout<<' '<<a.bodyFieldE4<<' '<<a.bodyFieldE8<<' '<<a.timerDelta<<' '<<opponent.flags248;
        for(auto v:opponent.timers)std::cout<<' '<<v;
        std::cout<<' '<<a.recoveryA4c<<' '<<a.flagsB8<<' '<<dustEvents;
        if(koPhases)std::cout<<' '<<a.fieldA30<<' '<<a.maximumLifeA34<<' '<<a.pendingDamageA38<<' '<<recoveryDiagnostics;
        if(colorProjection)std::cout<<' '<<object->color8c<<' '<<object->field20<<' '<<a.fieldA28
            <<' '<<a.fieldA2c<<' '<<a.rageState120<<' '<<a.rageAmount124;
        if(queueProjection)std::cout<<' '<<a.queuedActionA3c<<' '<<c.chainedAction;
        if(specialProjection) {
            for(auto word:a.registry28c)std::cout<<' '<<word;
            std::cout<<' '<<object->scriptLatch134;
        }
        if(roundProjection) {
            std::cout<<' '<<a.queuedActionA3c<<' '<<c.chainedAction<<' '<<object->color8c<<' '<<object->field20;
            std::cout<<' '<<a.fieldA30<<' '<<a.maximumLifeA34<<' '<<a.pendingDamageA38
                <<' '<<a.flags240<<' '<<a.fieldA2c<<' '<<a.fieldA50<<' '<<a.auxiliaryObject04<<' '<<a.fieldF10
                <<' '<<a.rageState120<<' '<<a.rageAmount124<<' '<<a.rageDecay128<<' '<<a.swordWait130<<' '<<a.swordCurrent134<<' '<<a.swordMaximum138
                <<' '<<a.controlFlagsB4<<' '<<a.flagsB8<<' '<<a.controlCounterC0<<' '<<a.controlModeC8
                <<' '<<a.control88<<' '<<a.control8c<<' '<<a.controlFlagsBC<<' '<<a.controlC4<<' '<<a.controlCC<<' '<<a.controlD8<<' '<<a.controlE4<<' '<<a.controlE8;
            for(auto v:a.controlTimers0c)std::cout<<' '<<v;
            for(auto v:a.controlMotion38)std::cout<<' '<<v;
            for(auto v:a.characterBytesF14)std::cout<<' '<<unsigned(v);
            for(auto v:a.characterBytesF22)std::cout<<' '<<unsigned(v);
            std::cout<<' '<<random.mode<<' '<<random.gameSeed<<' '<<random.librarySeed
                <<' '<<object->resourceSlot0c<<' '<<object->delta30<<' '<<object->scale70;
            for(auto v:object->zWords)std::cout<<' '<<v;
            std::cout<<' '<<std::bit_cast<uint32_t>(object->historyOffsetEc)<<' '<<std::bit_cast<uint32_t>(object->historyOffsetF0);
            std::cout<<' '<<unsigned(roundStorage.history.fraction);
            for(const auto& sample:roundStorage.history.samples)std::cout<<' '<<sample.flags<<' '<<sample.action<<' '<<sample.step
                <<' '<<std::bit_cast<uint32_t>(sample.x)<<' '<<std::bit_cast<uint32_t>(sample.y);
            for(auto v:roundStorage.objectTasks)std::cout<<' '<<v;
            for(auto v:roundStorage.afterimageObjects)std::cout<<' '<<v;
            const auto hash=[](const auto& rows) {uint64_t h=14695981039346656037ull;for(const auto& row:rows)for(uint32_t value:row){h^=value;h*=1099511628211ull;}return h;};
            std::cout<<' '<<entry.tasks.freeTaskHead<<' '<<entry.tasks.freeObjectHead<<' '<<entry.tasks.freeObjectCount<<' '<<hash(entry.tasks.tasks)<<' '<<hash(entry.tasks.objects);
            std::cout<<' '<<input.specialCount<<' '<<input.specialStart<<' '<<input.enabled;
            for(auto v:input.specialPriority)std::cout<<' '<<unsigned(v);
            for(const auto& slots:{std::span<const ss6::CommandSlot>(input.normal),std::span<const ss6::CommandSlot>(input.special)})
                for(const auto& slot:slots)std::cout<<' '<<slot.definition<<' '<<slot.alternateDirections;
            std::cout<<' '<<frame.replayIndex;
            for(auto v:sampler.replayHeld)std::cout<<' '<<v;
            for(auto v:sampler.replayPressed)std::cout<<' '<<v;
            for(auto v:sounds.previous)std::cout<<' '<<v;
        }
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
