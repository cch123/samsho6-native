#include "native_match.hpp"
#include "cpu_reactions.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
void NativeMatch::enableCpu(unsigned seat,int level) {
    if(seat>=fighters_.size() || level<0)throw std::invalid_argument("Invalid CPU seat or level");
    if(updates || cpuSeats_[seat])throw std::logic_error("CPU seats must be selected before battle updates");
    // 145ef0 and 146348 observe both seats, including the human opponent.
    // Both banks must be ready before enabling either perception pass.
    if(!cpuTactics_[0]) {
        std::array<std::unique_ptr<CpuTactics>,2> tables;
        for(unsigned side=0;side<2;++side)
            tables[side]=std::make_unique<CpuTactics>(assets_,fighters_[side].actor.character);
        cpuTactics_=std::move(tables);
    }
    auto& actor=fighters_[seat].actor;
    actor.controlKindA20=1;
    actor.controlModeC8=35;
    cpuLevels_[seat]=level;
}

CpuCommand NativeMatch::runCpu(unsigned seat,PermissionContext& permission,const SelectionThreat& threat) {
    auto& fighter=fighters_[seat];
    auto& actor=fighter.actor;
    const auto& enemy=fighters_[1-seat].actor;
    const auto& tactics=*cpuTactics_[seat];
    auto& battle=battle_;
    const auto command=[&]{return CpuCommand{actor.control88,std::bit_cast<int32_t>(actor.control8c)};};
    cpuTimerUp(actor,9);
    if(cpuTimerDown(actor,1))return command();

    // 15aa18 clears the training-controller flag for ordinary fight mode 35.
    actor.flags240&=~1u;
    CpuDecisionFrame frame;
    frame.level100=cpuLevels_[seat];
    frame.difficulty=unsigned(battle.gameLevel43d05c); // Option 43d05c; independent of the fighter's AI level.
    frame.clockValue=battle.remainingSeconds();
    frame.roundIndex=battle.match.roundIndex;
    frame.battleMode=battle.gameMode;
    frame.cameraLeft=battle.camera.left;
    frame.cameraRight=battle.camera.right;

    std::array<CpuReactionProjectile,96> projectiles;
    size_t count=0;
    const auto& pools=battle.entry.tasks;
    for(unsigned side=0;side<2;++side) {
        for(auto task:fighters_[side].storage.objectTasks) {
            if(!task)continue;
            const auto& object=pools.objects.at(pools.tasks.at(task-1)[7]-1);
            const auto kind=object[0xcc/4];
            const auto id=std::bit_cast<int32_t>(object[0xd0/4]);
            const auto x=std::bit_cast<float>(object[0x40/4]);
            if(kind==5)projectiles[count++]={object[0x10/4],id,object[0x38/4],x};
            if(side==seat || (kind!=2 && kind!=3))continue;
            auto& first=kind==2?frame.kind2:frame.kind3;
            if(!first)first=CpuObservedObject{id,std::bit_cast<int32_t>(object[0xd4/4]),int(object[0x14/4]),x};
        }
    }
    SelectionActor observedEnemy=enemy;
    if(enemy.auxiliaryObject04) {
        // Both threat queries can run before the opponent's own actor visit.
        // Read the separate object's current state for the decision and guard.
        const auto& companion=pools.objects.at(enemy.auxiliaryObject04-1);
        observedEnemy.auxiliaryState128=companion[0x128/4];
        observedEnemy.auxiliaryFlag134=companion[0x134/4];
    }
    frame.kind3Active=frame.kind3 && auxiliaryThreatActive(observedEnemy);
    const CpuExecutionFrame execution{fighter.config,human_.bindings(),tactics,battle.random,
                                      human_.characterFlags(actor.character),frame.level100,actor.cpuWall178,&enemy,
                                      distance_,human_.opponentThreat(actor,observedEnemy,threat),frame.roundIndex,std::bit_cast<int32_t>(fighter.body.delta30)};
    const auto& opponentScore=battle.match.players[1-seat];
    const CpuReactionFrame reaction{human_.permissions(),permission,opponentScore.wins,opponentScore.requiredWins,
                                    seat,std::span(projectiles).first(count)};
    actor.controlB0=updateCpuReaction(actor,enemy,frame,execution,reaction);
    if(actor.controlB0)return command();
    if(frame.clockValue>=0 && frame.clockValue<=10)cpuTimerDown(actor,5);
    advanceCpuSequence(actor,fighter.config,frame,tactics,battle.random);
    decideCpuAction(actor,enemy,fighter.config,frame,tactics,battle.random);
    executeCpuInstruction(actor,execution);
    if(actor.stateTable()!=2)actor.controlFlagsB4&=~0x7f0u;
    return command();
}
}

