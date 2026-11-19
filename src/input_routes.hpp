#pragma once
#include "special_requests.hpp"
#include "input_features.hpp"

namespace ss6 {
struct SystemCancelContext {
    NormalizedPadSample pad;
    InputMapping mapping;
    //The control structure stores its own actor index. Preserve that lookup
    //as explicit references: the owner need not alias the requesting actor.
    PermissionActor* controlOwner=nullptr;
    ActorCommandInput* controlInput=nullptr;
    const InputSystemConfig* controlConfig=nullptr;
    unsigned diagnostics=0;
};
bool requestSystemCancel(PermissionActor&,ActorCommandInput&,const InputSystemConfig&,const ActionSelection&,SystemCancelContext&); //14c0d0
void filterCharacterSpecials(const PermissionActor&,ActorCommandInput&); //14ce28
void requestAliasFallback(PermissionActor&,const ActorCommandInput&); //1ec4c8/209840
bool requestAlternate(PermissionActor&,const PermissionActor&,const ActorCommandInput&,const InputSystemConfig&,const InputBindings&,const ActionSelection&,const SelectionThreat&); //14ca28
void dispatchInputRequests(PermissionActor&,const PermissionActor&,ActorCommandInput&,const InputSystemConfig&,const InputBindings&,const ActionSelection&,const SelectionThreat&,SystemCancelContext&); //149bc0
void requestLockedInput(PermissionActor&,const PermissionActor&,ActorCommandInput&,InputSampler&,unsigned player,int32_t battleState,
    const InputSystemConfig&,const ActionSelection&,const SelectionThreat&); //14bb48
bool requestForcedState(PermissionActor&,const ActorCommandInput&,const InputSystemConfig&); //149980
//1494f0's permission/forced/ordinary-request sequence, after sampling. This
//does not stand in for the rest of the scheduler or state-entry callbacks.
void processRecognizedInput(PermissionActor&,const PermissionActor&,ActorCommandInput&,const InputSystemConfig&,const InputBindings&,const InputPermissions&,const ActionSelection&,PermissionContext&,const SelectionThreat&,SystemCancelContext&);
}
