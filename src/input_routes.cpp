#include "input_routes.hpp"
#include "actor_state.hpp"
#include "input_lifecycle.hpp"
#include <stdexcept>

namespace ss6 {
namespace {
bool customCancel(const InputSystemConfig& c) {
    if(c.system>8)throw std::runtime_error("Invalid input cancellation system");
    if(c.system!=6)return false;
    if(!c.descriptor)throw std::runtime_error("System6 cancellation needs its descriptor");
    return (*c.descriptor)[4]==18; //14fd70, not the stock system5 option.
}
bool controlCancel(PermissionActor& a,unsigned bit,SystemCancelContext& context) {
    if(!context.controlOwner||!context.controlInput||!context.controlConfig)
        throw std::runtime_error("AI cancel requires its original control-owner context");
    const bool requested=a.controlFlagsB4&bit;a.controlFlagsB4&=~bit;
    //15ae30/15aee0 consume the bit even when the control mode rejects it.
    if(a.controlModeC8!=35||!customCancel(*context.controlConfig))return false;
    if(requested)context.controlInput->normal[context.controlOwner->state194==0x00380000?26:29].recognized=1;
    return requested;
}
}
bool requestSystemCancel(PermissionActor& a,ActorCommandInput& input,const InputSystemConfig& config,const ActionSelection& actions,SystemCancelContext& context) {
    const auto table=a.stateTable(),state=a.stateIndex();
    const auto column=inputSystemColumn(config);
    if(!customCancel(config)||column!=5||(a.flags23c&0x10))return false;
    bool ready=false;
    if(a.timers[31]>0) {
        ready=table==0&&(state==56||state==58||state==60);
        if(a.timers[33]>0)ready=false;
        else {
            const bool command=a.controlKindA20==1?controlCancel(a,0x4000,context):(context.pad.pressed&context.mapping.normal[4])!=0;
            if(!command)ready=false;
        }
    }
    if(a.timers[32]>0) {
        if(table==0||(table==2&&uint32_t(state)<6))ready=true;
        if(a.controlKindA20==1&&!controlCancel(a,0x8000,context))ready=false;
    }
    if(!ready)return false;
    const auto next=actions.systemNormal(a,input,0,config);
    if(next==255)return false;
    if(a.timers[31]>0)a.flags248|=0x02000000;
    a.pendingTable=0;a.pendingIndex=int16_t(next);a.request18c=1;
    a.timers[31]=a.timers[32]=0;++context.diagnostics;
    return true;
}
void filterCharacterSpecials(const PermissionActor& a,ActorCommandInput& input) {
    const auto clear=[&](std::initializer_list<unsigned> slots){for(auto i:slots)input.special[i].recognized=0;};
    if(a.flags23c&0x100000) {
        switch(a.character) {
        case 1:clear({24,13,16,17,22,23});break;
        case 23:clear({10,5,6,7,8,9});break;
        case 24:clear({17,4,6,7,8,9,10,11,16});break;
        case 25:
            //This rewrites only the published result, never the underlying
            //motion progress or buffer, and canonicalizes a nonzero word to1.
            input.special[4].recognized=input.special[3].recognized!=0;
            input.special[3].recognized=0;
            if(!(a.flags23c&0x1000))input.special[2].recognized=0;
            break;
        }
    } else {
        if(a.character==24)clear({28,21,22,23,24,25,26,27});
        if(a.character==25)clear({9,7,8});
    }
}
void requestAliasFallback(PermissionActor& a,const ActorCommandInput& input) {
    ActorTimers timers{a.timerDelta,a.timers};timers.increase(23);a.timers[23]=timers.values[23];
    if(int16_t(a.state1a4)!=0)return;
    if(input.sampledFeatures[9]||a.timers[23]>=0x2a00) {
        //11d990 stops all six motion words before issuing the main request.
        a.offsetX4c=a.velocityX50=a.accelerationX54=a.offsetY58=a.velocityY5c=a.accelerationY60=0;
        a.bodyFlags104&=~0x140u;
        int next=input.sampledFeatures[57]?20:input.sampledFeatures[55]?21:input.sampledFeatures[56]?19:
                 input.sampledFeatures[64]?34:input.sampledFeatures[62]?33:32;
        if(a.character!=45&&(a.flags23c&0x100000)){next=32;a.flags244|=0x800;}
        a.pendingTable=0;a.pendingIndex=int16_t(next);return;
    }
    if(a.character==45)return;
    int next=-1;
    if(input.sampledFeatures[6]||input.sampledFeatures[7])next=a.flags23c&0x1000?0:2;
    else if(input.sampledFeatures[8])next=a.flags23c&0x1000?1:2;
    if(next!=-1){a.aliasPendingTable=1;a.aliasPendingIndex=int16_t(next);a.aliasRequest19c=1;}
}
bool requestAlternate(PermissionActor& a,const PermissionActor& opponent,const ActorCommandInput& input,const InputSystemConfig& config,const InputBindings& bindings,const ActionSelection& actions,const SelectionThreat& threat) {
    if(a.flags23c&0x200000) {
        if(!requestSpecial(a,input))requestAliasFallback(a,input);
        return true;
    }
    if(!(a.flags23c&0x800000))return false;
    const auto state=a.stateIndex(),table=a.stateTable();
    if(requestSpecialCancel(a,input,config,bindings)||requestSpecial(a,input))return true;
    if((a.flags244&10)==2&&!(table==1&&state>=64)&&!(table==0&&(state==23||state==24))) {
        int next=input.normal[0].recognized?23:input.normal[1].recognized?24:-1;
        next=actions.translateNormalState(a,next);
        if(next!=-1){a.pendingTable=0;a.pendingIndex=int16_t(next);return true;}
    }
    if(actions.requestAttack(a,input)||actions.requestChain(a,opponent,input,config))return true;
    actions.requestNormal(a,opponent,input,config,threat);
    //True means this alternate route handled dispatch, even with no request.
    return true;
}
void dispatchInputRequests(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,const InputSystemConfig& config,const InputBindings& bindings,const ActionSelection& actions,const SelectionThreat& threat,SystemCancelContext& context) {
    if(!a.request18c) {
        if(a.character==24&&!(a.flags23c&0x100000)&&
           (a.controlKindA20==0||(a.controlKindA20==1&&(a.controlModeC8==36||a.controlModeC8==37)))) {
            if(input.sampledFeatures[62])a.flags244|=0x4000;else a.flags244&=~0x4000u;
        }
        filterCharacterSpecials(a,input);
        //The original orders these callers explicitly. A successful request
        //ends dispatch; the alternate route can also consume dispatch alone.
        if(requestAlternate(a,opponent,input,config,bindings,actions,threat)||
           actions.requestSupplemental(a,input,true)||requestSpecialCancel(a,input,config,bindings)||
           requestSpecial(a,input)||actions.requestSupplemental(a,input,false)||
           requestSystemCancel(a,input,config,actions,context)||actions.requestAttack(a,input)||
           actions.requestChain(a,opponent,input,config))return;
    }
    actions.requestNormal(a,opponent,input,config,threat);
}
void requestLockedInput(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,InputSampler& sampler,unsigned player,int32_t battleState,
        const InputSystemConfig& config,const ActionSelection& actions,const SelectionThreat& threat) {
    if(battleState!=3)return;
    if(config.system==6) {
        if(!config.descriptor)throw std::runtime_error("System6 locked input needs descriptor");
        if((*config.descriptor)[13]==42)actions.requestNormal(a,opponent,input,config,threat,true);
    }
    toggleLockedCharacterMode(a,input,sampler,player);
}
bool requestForcedState(PermissionActor& a,const ActorCommandInput& input,const InputSystemConfig& config) {
    const bool standing=!(a.flags244&2)&&!(a.flags23c&0x10)&&a.stateTable()==0;
    const auto queue=[&](int table,int state,bool force) {
        a.pendingTable=int16_t(table);a.pendingIndex=int16_t(state);
        if(force)a.request18c=1;
        return true;
    };
    if(!(a.flags244&2)&&(a.flags23c&0x80))return queue(2,a.flags23c&0x10?31:30,true);
    if(a.character==48&&!(a.flags23c&0x1000)&&standing)return queue(0,51,false);
    if(a.rageState120==1) {
        if(standing&&!(a.flags248&2)) {
            a.flags248|=2;
            bool startup=config.system==1;
            if(config.system==6) {
                if(!config.descriptor)throw std::runtime_error("System6 forced request needs descriptor");
                startup=(*config.descriptor)[8]==32;
            }
            if(startup)return queue(0,63,false);
        }
    } else a.flags248&=~2u;
    if(a.flags244&0x200000) {
        if(!(a.flags23c&0x1000))a.flags244&=~0x200000u;
        else if(standing&&!a.timers[21]) {
            a.pendingCharacter254=uint8_t(a.character);a.flags244&=~0x200000u;
            return queue(2,96,true);
        }
    }
    if(a.character==16&&input.special[15].recognized&&
       (a.state194==0x00100002||a.state194==0x00090002||a.state194==0x00360000)) {
        const auto amount=a.characterBytesF14[1];
        if(amount&&!a.auxiliaryFlag134) {
            a.auxiliaryFlag134=1;a.auxiliaryTimer130=unsigned(amount)*0x7800+0x3c00;
            const auto action=unsigned(amount)+605;
            //1f7638 queues11d908 without immediate commit. An already
            //running action preserves pending object fields, but the meter
            //and active flag above have still been written.
            if(a.auxiliaryAction24!=action) {
                a.auxiliaryPendingC4=int32_t(action);a.auxiliaryFrameC0=0;a.auxiliaryFlags104|=1;
            }
        }
    }
    return false;
}
void processRecognizedInput(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,const InputSystemConfig& config,const InputBindings& bindings,
        const InputPermissions& permissions,const ActionSelection& actions,PermissionContext& permissionsContext,const SelectionThreat& threat,SystemCancelContext& cancelContext) {
    //In the original these two views alias the same feature9 word.
    a.sampledButton9=input.sampledFeatures[9];
    permissions.apply(a,opponent,config,permissionsContext,input,bindings);
    if(!requestForcedState(a,input,config))dispatchInputRequests(a,opponent,input,config,bindings,actions,threat,cancelContext);
}
}
