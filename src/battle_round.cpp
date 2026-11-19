#include "battle_round.hpp"
#include "fighter_roster.hpp"
#include <stdexcept>

namespace ss6 {
int BattleRoundState::remainingSeconds() const {
    if(timeOption13c==3)return -1;
    constexpr int count=90*256;
    return int((int64_t(timers.values[0])+count-1)/count);
}
void BattleRoundInitialization::begin(GroundStateRuntime& ground,const std::array<RoundPlayerRef,2>& players,
                                     BattleRoundState& battle,BattleEffects& effects) {
    if(battle.gameMode!=3)throw std::runtime_error("Battle round initialization requires local versus");
    for(const auto& p:players)if(!playableFighter(p.actor.character)||p.actor.controlKindA20||p.config.character!=p.actor.character||p.config.system>5)
        throw std::runtime_error("Battle round initialization requires supported human fighters and spirits");
    const bool first=battle.match.roundIndex==0;
    battle.sampler.resetRoundSampling();battle.camera.resetRound();battle.timers={};
    const int timeLimit=BattleRoundState::roundTimeLimits.at(battle.timeOption13c);
    battle.timers.set(0,timeLimit*90,battle.gauges.paused46a940?8:1);
    battle.flags138&=2;
    battle.entry.tasks.clearRegistry(battle.objectTasks);
    for(unsigned i=0;i<2;++i) {
        const auto& p=players[i];const auto& other=players[1-i];
        //147d28 is interleaved with149008. Do not clear both registries
        //up front: player0 allocates before player1's old objects are freed.
        battle.entry.tasks.clearRegistry(p.storage.objectTasks);
        battle.match.players[i].resetRound();
        battle.entry.player=i;battle.entry.opponentFlagsB8=other.actor.flagsB8;
        GroundStateFrame frame;
        frame.remainingSeconds=battle.remainingSeconds();
        frame.opponentCharacter=other.actor.character;frame.opponentSystem=other.config.system;
        frame.opponentX=other.body.timeline.motion().x;frame.opponentFlags23c=other.actor.flags23c;
        frame.objects=&p.objects;frame.effects=&effects;frame.random=&battle.random;
        frame.matchStats=&battle.match.players[i];
        frame.opponentStats=&battle.match.players[1-i];
        actors_.begin(ground,p.body,p.actor,p.input,p.config,battle.entry,frame,p.storage,first);
        other.actor.flagsB8=battle.entry.opponentFlagsB8;
    }
    battle.camera.resetRound();battle.field140=0;
    if(first) {battle.timers.set(2,60);battle.requestedState=1;}
    //The later-round path preserves the requested state; the controller
    //normally supplied0. Setting1 here skips the original outer transition.
    battle.field08=battle.field0c=-1;battle.lastItemSecond=0;
    battle.camera.commands.clear();battle.phase130=1;
    battle.stageItems.clear();
}
}
