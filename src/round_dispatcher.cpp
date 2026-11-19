#include "round_dispatcher.hpp"
#include "sound_selection.hpp"
#include <stdexcept>

namespace ss6 {
bool RoundDispatcher::enter(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p) const {
    if(b.currentState==b.requestedState)return false;
    const auto& s=services_;
    // 14350c and 1434b0 bracket the battle with the same short/long
    // voice group stops. The IOP leaves its short-voice cursor intact.
    if(s.sound&&(b.requestedState==0||b.requestedState==10)) {
        s.sound->stopGroup(1);s.sound->stopGroup(2);
        if(b.voiceGate5850e0)s.sound->stopMusic();
    }
    switch(b.requestedState) {
    case 0:
        RoundControl::enterRound(s.initialize,s.ground,b,p,s.effects,s.events);
        //enterRound includes the publication footer already. Do not reset
        //timers twice or execute introduction's update during this visit.
        return true;
    case 1:RoundControl::enterIntroduction(b,s.events);break;
    case 2:break; //1438e8 is an actual empty function.
    case 3:RoundControl::enterOpening(b,p,s.events,s.captions,s.sound);break;
    case 4:RoundControl::enterCombat(b,s.sound);break;
    case 5:case 6:RoundControl::enterEnding(b,p,s.captions,s.results,s.sound);break;
    case 7:RoundControl::enterVictoryCamera(b,p);break;
    case 8:RoundControl::enterVictory(b,p,s.events,s.sound);break;
    case 9:throw std::runtime_error("Round result-page entry1447c0 is not implemented");
    case 10:
        if(b.matchEnd.submodeA0==2) {
            b.consoleMenu.enter(b.matchEnd.winner08,{p[0].config.character,p[1].config.character},!b.matchEnd.field18);
            b.matchEnd.endFlagA4=0; // 1daec0 suspends battle and clears the final-result latch.
        } else if(!b.matchEnd.field18) {
            enterVersusResult(b.resultScreen,b.matchEnd,{p[0].config.character,p[1].config.character});
        }
        // Ordinary 1393a0 returns false.
        b.requestedState=-1;
        break;
    default:break; //Unsigned out-of-range table indices still publish.
    }
    //Nested entries may change the request (notably0->1 and profile5->6).
    //Publish the resulting request, never the switch's incoming value.
    b.currentState=b.requestedState;b.field08=0;b.timers.set(1,0);
    return true;
}
void RoundDispatcher::update(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p) const {
    //143260 returns the OLD fixed-point value. Reaching zero this visit
    //still delays entry/update; the next visit observes the expired gate.
    if(b.timers.decrease(2)>0)return;
    if(enter(b,p))return;
    const auto& s=services_;
    switch(b.requestedState) {
    case 1:RoundControl::introduction(b,p);break;
    case 2:
        if(s.sound){s.sound->stopGroup(1);s.sound->stopGroup(2);}
        RoundControl::skippedIntroduction(b);break;
    case 3:RoundControl::opening(b,p,s.events);break;
    case 4:RoundControl::combat(b,p,s.events);break;
    case 5:RoundControl::ending(b,p,s.captions);break;
    case 6:
        if(!b.matchEnd.profileBusy4452ac) {
            b.matchEnd.continue2c=1;
            //A completed profile wait resumes state5 without entering it
            //again: a second entry would award the same round twice.
            b.requestedState=b.currentState=5;
        }
        break;
    case 7:RoundControl::victoryCamera(b,p);break;
    case 8:RoundControl::victory(b,p,b.matchEnd.submodeA0);break;
    case 9:throw std::runtime_error("Round result-page update144848 is not implemented");
    default:break;
    }
    //This also runs when the callback requested a different state, and
    //for the original empty/out-of-range update slots0,10,-1,... .
    b.timers.increase(1);
}
void RoundDispatcher::interaction(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p) const {
    if(b.field08!=b.field0c) {
        if(b.field08==1)services_.weaponLock.enter(b,p,services_.sound);
        b.field0c=b.field08;
        return; //1448f0 entering does not count button presses this visit.
    }
    if(b.field08==1)WeaponLock::update(b,p,services_.sound);
}
void RoundDispatcher::step(BattleRoundState& b,const std::array<RoundPlayerRef,2>& p) const {
    update(b,p);
    //Delay/entry gates suppress only the state callback, not interaction
    //or publication. Later input reads this newly published interaction.
    interaction(b,p);
    RoundControl::snapshotPlayers(b,p);
}
}
