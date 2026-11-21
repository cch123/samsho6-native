#include "round_initialization.hpp"
#include "cpu_execution.hpp"
#include "mamahaha.hpp"
#include "konru.hpp"
#include "chample.hpp"
#include "poppy.hpp"
#include "rera_wolf.hpp"
#include "karuta.hpp"
#include "karakuri_puppet.hpp"
#include "chamcham_pet.hpp"
#include "kazuki_fire.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <stdexcept>

namespace ss6 {
void resetActorControl(StateEntryActor& a,GameRandom& random) {
    a.controlFlagsB4=a.flagsB8=a.controlFlagsBC=0;
    //This draw occurs even for human players. Skipping it shifts every
    //later draw made by the shared battle random generator.
    a.controlCC=uint32_t(random.bounded(2));a.control88=0;a.control8c=0xffffffff;
    resetCpuSequence(a);
    a.controlTimers0c[9]=0;
    const auto mode=a.controlModeC8;
    const bool delayed=mode-38<32||mode-4<7||mode-15<5||mode-21<4||mode-26<4||mode-31<4;
    a.controlTimers0c[1]=delayed?60*256:0;
}
void RoundInitialization::begin(GroundStateRuntime& ground,PlayerObject& body,StateEntryActor& a,
        ActorCommandInput& input,const InputSystemConfig& config,StateEntryContext& context,
        const GroundStateFrame& frame,RoundActorStorage& storage,bool first) {
    if(!playableFighter(a.character)||a.character!=config.character||(config.system>5&&config.system!=8)||context.player>=2||
       !frame.random||body.resourceSlot0c>=3||((a.flags23c&0x400000)&&a.character!=11)||a.rageState120<0||a.rageState120>3)
        throw std::runtime_error("Round initialization requires a supported fighter, spirit, default options and a random context");
    const unsigned c=a.character;
    const unsigned neededObjects=3+(c==1||c==2||c==4||c==16||c==19||c==24||c==32||c==33||c==34||c==45); // the companion of 1a3220
    if(context.tasks.freeObjectCount<neededObjects||
       std::count(storage.objectTasks.begin(),storage.objectTasks.end(),0u)<neededObjects)
        throw std::runtime_error("Round initialization needs space for the companion and afterimages");
    auto task=context.tasks.freeTaskHead;
    for(unsigned i=0;i<neededObjects;++i) {
        if(!task)throw std::runtime_error("Round initialization needs tasks for the companion and afterimages");
        task=context.tasks.tasks.at(task-1)[3];
    }
    if(frame.objects)frame.objects->bindTasks(context.tasks,storage.objectTasks);
    a.fieldA30=a.maximumLifeA34=200;a.pendingDamageA38=0;a.fieldA2c=0;
    RoundActorFlags flags{a.flags23c,a.flags240,a.flags244,a.flags248,a.flags24c};flags.resetRound();
    a.flags23c=flags.flags23c;a.flags240=flags.flags240;a.flags244=flags.flags244;
    a.flags248=flags.flags248;a.flags24c=flags.flags24c;
    if(frame.training&&frame.trainingRage==1)a.flags248&=~2u; // 149048: SPIRIT GAUGE MAX
    a.fieldA50=0;a.characterBytesF14[8]=3;a.characterBytesF14[7]=a.characterBytesF14[4]=0;
    a.characterBytesF22.fill(0);
    if((a.characterBytesF14[5]&0x3f)==0x3f)a.characterBytesF14[5]=0;
    if((a.characterBytesF14[13]&0x7f)==0x7f)a.characterBytesF14[13]=0;
    const auto clock=body.timeline.clock();
    body.timeline.setObjectFlags((clock.objectFlags&~0x80000u)|(context.player?0x80000:0),clock.flags104,clock.flags108);
    body.timeline.stopMotion();body.timeline.setPosition(context.player?400:240,0);
    DamageActor meter;meter.system=config.system;meter.rageState=a.rageState120;meter.rageAmount=a.rageAmount124;meter.rageDecay=a.rageDecay128;
    meter.swordWait=a.swordWait130;meter.swordCurrent=a.swordCurrent134;meter.swordMaximum=a.swordMaximum138;
    if(config.system==5) {
        // 14eea0 starts every round at the factory 32-point secret reserve,
        // clearing any recharge delay left by a technique in the last round.
        a.bonusState14c=a.bonusTime150=0;
        a.bonusRate154=256;a.systemMeter158=32*256;
    }
    if(config.system==4) {
        // The factory reserve is in life points, then shifted into 8.8
        // storage. Subsequent rounds retain the result of meditation.
        if(first)a.systemAmount140=20<<8;
        if(a.systemState13c==3) {
            a.systemState13c=4;a.systemDecay148=0;a.systemAmount140=0;
        } else if(a.systemState13c==2)a.systemState13c=1;
    }
    meters_.resetOrdinaryRoundMeters(meter);
    a.rageState120=meter.rageState;a.rageAmount124=meter.rageAmount;a.rageDecay128=meter.rageDecay;
    a.swordCurrent134=meter.swordCurrent;a.swordMaximum138=meter.swordMaximum;
    if(frame.training&&(frame.trainingRage==1||frame.trainingRage==2)&&a.rageState120!=3) {
        // 14ecdc: 14f3b0/14f428 (practice gauge MAX or INFINITY) select the full-rage start 14edc0.
        if(a.rageState120<=0)a.swordCurrent134=a.swordMaximum138=meters_.raisedSwordLimit(int(config.system));
        a.rageState120=1;a.rageAmount124=0xb800;a.rageCharge12c=0;a.rageDecay128=meters_.decay(int(config.system),a.character);
    }
    ActorTimers timers{a.timerDelta,a.timers};timers.resetRound();a.timerDelta=timers.delta;a.timers=timers.values;
    resetActorControl(a,*frame.random);
    //14ff80 only queues the new state. Preserve existing18c and let149d08
    //perform the actual transition, including its precise buffer consumption.
    a.pendingTable=0;a.pendingIndex=first?39:0;
    ground.visit(body,a,input,config,context,frame);
    const auto parent=body.childParentWords();
    // 149174 creates the companion before the three history objects.
    switch(a.character) {
    case 1:case 45:a.auxiliaryObject04=spawnMamahaha(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);break;
    case 2:a.auxiliaryObject04=spawnKonru(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);break;
    case 24:
        a.auxiliaryObject04=spawnChample(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        // 149184 -> 1a3340 runs only for the first-round introduction.
        if(first)commandChamplePresentation(context.tasks.objects.at(a.auxiliaryObject04-1),33);
        break;
    case 19: // 1f95e8 (1a32dc); the first round's 1a3340 introduction is command 0x13
        a.auxiliaryObject04=spawnReraWolf(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        if(first)commandPoppy(context.tasks.objects.at(a.auxiliaryObject04-1),0x13);
        break;
    case 33: // 2038a0 (1a330c)
        a.auxiliaryObject04=spawnKaruta(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        break;
    case 32: // 201ac0 (1a32fc)
        a.auxiliaryObject04=spawnKarakuriPuppet(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        break;
    case 34: // 203e08 (1a331c); the first round's 1a3340 introduction is command 0x13
        a.auxiliaryObject04=spawnChamchamPet(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        if(first)commandPoppy(context.tasks.objects.at(a.auxiliaryObject04-1),0x13);
        break;
    case 16: // 1f7258 at the current fire level (f15)
        a.auxiliaryObject04=spawnKazukiFire(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent,a.characterBytesF14[1]);
        break;
    case 4:
        a.auxiliaryObject04=spawnPoppy(objects_,context.tasks,storage.objectTasks,context.player,a.flags23c,parent);
        if(first)commandPoppy(context.tasks.objects.at(a.auxiliaryObject04-1),0x2e); // 1a3340
        break;
    default:a.auxiliaryObject04=0;break;
    }
    for(unsigned i=0;i<3;++i) {
        const auto handle=objects_.create(context.tasks,storage.objectTasks,context.player,a.flags23c,parent,0x1396,6,0);
        if(!handle)throw std::runtime_error("Afterimage allocation failed");
        auto& object=context.tasks.objects.at(handle-1);
        objects_.request(object,0,false,true);object[0x108/4]|=0x2000;
        object[0xcc/4]=10;object[0x104/4]|=0x400300;
        object[0x128/4]=(i+1)*5;object[0x12c/4]=144-i*48;object[0x130/4]=i+1;
        storage.afterimageObjects[i]=handle;
    }
    //History captures the old body, after colors and new-state registration
    //but BEFORE149918/11d8e0. Restarting the clip here loses that history.
    storage.history.reset(ActorHistory::capture(body,body.historyOffsetEc,body.historyOffsetF0));
}
}
