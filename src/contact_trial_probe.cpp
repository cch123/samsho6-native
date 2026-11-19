#include "contact_trial.hpp"
#include "trial_script.hpp"
#include <iostream>
#include <iomanip>
#include <string>
#include <stdexcept>
int main(int argc,char** argv) {
 try {
  if (argc!=2) throw std::runtime_error("Usage: ss6-contact-trial-probe ASSETS");
  std::cout<<std::setprecision(17);
  ss6::ContactTrial trial(argv[1]);
  while (ss6::readTrialCommand(trial,std::cin)) {
   std::cout<<trial.updates<<' '<<trial.winner;
   for (unsigned i=0;i<2;++i) {
    const auto& a=trial.actor(i);const auto& t=a.object.timeline;
    std::cout<<' '<<a.life.life<<' '<<a.table<<' '<<a.state<<' '<<t.action().id()<<' '<<t.clock().step
             <<' '<<t.motion().x<<' '<<a.timers.values[0]<<' '<<a.timers.values[1]<<' '<<a.delta
             <<' '<<a.hitCount<<' '<<a.guardCount;
   }
   for (unsigned i=0;i<2;++i) {
    const auto& a=trial.actor(i).damage;
    std::cout<<' '<<a.swordCurrent<<' '<<a.swordMaximum<<' '<<a.swordWait
             <<' '<<a.rageState<<' '<<a.rageAmount<<' '<<a.rageDecay;
   }
   const auto& c=trial.camera;
   std::cout<<' '<<c.x<<' '<<c.y<<' '<<c.width<<' '<<c.left<<' '<<c.right;
   for(unsigned i=0;i<2;++i)std::cout<<' '<<unsigned(trial.actor(i).reaction.flags24c)<<' '<<trial.actor(i).expectedMirror;
   for(unsigned i=0;i<2;++i) {
    const auto& a=trial.actor(i);const auto& c=a.object.timeline.clock();
    std::cout<<' '<<a.object.timeline.motion().y<<' '<<int(a.knockout.phase)<<' '<<a.landingDustEvents
             <<' '<<c.endReached<<' '<<c.fractionalTime<<' '<<c.flags104;
   }
   std::cout<<' '<<trial.roundState<<' '<<trial.pendingRoundState<<' '<<trial.roundBodiesReady;
   for(unsigned i=0;i<2;++i)std::cout<<' '<<trial.actor(i).reaction.flags244;
   std::cout<<' '<<trial.battlePause.remaining<<' '<<trial.battlePause.delay<<' '<<trial.battlePause.paused;
   std::cout<<' '<<trial.effects.knockoutActive()<<' '<<trial.effects.draws().size()<<' '<<trial.roundPresentationReady;
   std::cout<<' '<<trial.roundEndingReady<<' '<<trial.camera.commands.size()<<' '<<trial.camera.commandsComplete();
   std::cout<<' '<<(trial.camera.commands.empty() ? -1 : int(trial.camera.commands.front().kind));
   for(unsigned i=0;i<2;++i)std::cout<<' '<<int(trial.actor(i).ending.phase);
   for(const auto& p:trial.match.players) {
    std::cout<<' '<<p.wins<<' '<<p.requiredWins<<' '<<p.rating<<' '<<p.score<<' '<<p.bonus;
    for(auto h:p.history)std::cout<<' '<<unsigned(h);
   }
   std::cout<<' '<<trial.match.result.result<<' '<<trial.match.result.ui<<' '<<trial.match.complete();
   for(auto v:trial.battleTimers.values)std::cout<<' '<<v;
   std::cout<<' '<<trial.effects.openingActive();
   std::cout<<' '<<trial.match.roundIndex<<' '<<trial.matchFinished<<' '<<trial.continueRounds;
   for(unsigned i=0;i<2;++i) {
    const auto& a=trial.actor(i);const auto& m=a.object.timeline.motion();
    std::cout<<' '<<int(a.knockdown.phase)<<' '<<a.downEntryQueued<<' '<<a.downed.pendingTable<<' '<<a.downed.pendingIndex
      <<' '<<a.life.flags23c<<' '<<a.life.conditions<<' '<<unsigned(a.stateFlags)<<' '<<a.timers.values[2]<<' '<<a.timers.values[6]
      <<' '<<unsigned(a.downed.landingCount253)<<' '<<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay;
   }
   std::cout<<'\n';
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
