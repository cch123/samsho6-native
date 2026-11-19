#include "input_lifecycle.hpp"
#include "actor_state.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
void updateCharacterCharge(PermissionActor& a,const ActorCommandInput& input,int32_t battleState,int32_t battleField18) {
    if(a.character!=9||(battleState<4&&!battleField18)||a.state194==0x004d0001)return;
    if(a.controlKindA20==1&&a.controlModeC8!=36&&a.controlModeC8!=37)return;
    if(input.sampledFeatures[46]) {
        ActorTimers timers{a.timerDelta,a.timers};timers.increase(19);a.timers[19]=timers.values[19];
    } else if(a.timers[19]>0) {
        const auto held=a.timers[19]>>8;a.timers[19]=0;
        //The level is published on release only. A nonpositive old timer
        //preserves the prior byte, while a short positive charge writes0.
        a.characterBytesF14[4]=held>=4800?5:held>=1200?4:held>=360?3:held>=180?2:held>=60?1:0;
    }
}
ActorInputRoute sampleActorInput(PermissionActor& a,const PermissionActor& opponent,ActorCommandInput& input,InputSampler& sampler,
        const CommandInput& commands,const ActorInputSampling& frame,const std::array<NormalizedPadSample,2>& pads,const std::array<InputMapping,2>& mappings) {
    if(a.controlKindA20!=0&&a.controlModeC8!=36&&!(a.flags240&4))
        return a.flags24c&1?ActorInputRoute::AiSuppressed:ActorInputRoute::AiRequired;
    if(!frame.opponentSamplingAllowed&&(opponent.flags23c&0x08000000))return ActorInputRoute::HumanSuppressed;
    if(frame.player>=2)throw std::runtime_error("Input source must be an original player0/1");
    const auto player=a.flags240&8?1-frame.player:frame.player;
    InputSamplingContext c;
    c.facing=frame.expectedFacing;c.actualFacing=a.bodyFlags38&0x80000;c.reverseDirections=a.timers[20]>0;
    c.playback=a.flags240&4;c.replayIndex=a.flags240&6?frame.replayIndex:-1;c.gameMode=frame.gameMode;
    const bool transformed=a.flags23c&0x100000;
    //Only the definition halfwords change. Resetting the slots here would
    //erase motions/buffers across the character's transformation boundary.
    if(a.character==24) {
        input.special[0].definition=input.special[1].definition=transformed?114:196;
        input.special[2].definition=input.special[3].definition=transformed?64:197;
        input.special[5].definition=transformed?41:116;
    } else if(a.character==25)input.special[0].definition=transformed?269:206;
    input.sampleAndAdvance(commands,sampler,player,pads[player],mappings[player],c,a.timers[0]<=0);
    //This still runs for a disabled owner, using its previous feature frame.
    updateCharacterCharge(a,input,frame.battleState,frame.battleField18);
    return ActorInputRoute::HumanVisited;
}
bool inputRequestsLocked(const PermissionActor& a) {
    return (a.flags24c&1)||(a.flags23c&0x30000000)==0x10000000;
}
void toggleLockedCharacterMode(PermissionActor& a,ActorCommandInput& input,InputSampler& sampler,unsigned player) {
    if(a.character!=11)return;
    const bool active=a.flags23c&0x400000;
    if(!input.special[active?21:9].recognized)return;
    //This call site consumes latches and all completion buffers, but keeps
    //the published results and partial command progress for this visit.
    sampler.clearPressLatches(player);input.clearBuffers();a.flags23c^=0x400000;
}
void clearSystemCancelWindow(PermissionActor& a,const NormalizedPadSample& pad,const InputMapping& mapping) {
    if(a.timers[31]>0&&(pad.pressed&mapping.normal[4]))a.timers[31]=0;
}
void finishActorInput(PermissionActor& a,ActorInputSampling& frame,const std::array<NormalizedPadSample,2>& pads,const std::array<InputMapping,2>& mappings) {
    if(frame.battleState>=4||frame.battleField18>0) {
        frame.replayIndex=std::bit_cast<int32_t>(uint32_t(frame.replayIndex)+1u);
        if(a.flags240&4)frame.replayIndex%=720;
    }
    //Unlike sampling, this late raw-button test uses the unswapped player
    //and normal mapping even in mode6, and runs after the replay increment.
    clearSystemCancelWindow(a,pads.at(frame.player),mappings.at(frame.player));
}
}
