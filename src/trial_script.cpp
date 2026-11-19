#include "trial_script.hpp"
#include "contact_trial.hpp"
#include <stdexcept>
#include <string>
namespace ss6 {
bool readTrialCommand(ContactTrial& trial,std::istream& in) {
    std::string op;if (!(in>>op)) return false;
    if (op=="reset") trial.reset();
    else if(op=="rounds")trial.enableRoundContinuation();
    else if(op=="match")trial.startMatch();
    else if(op=="heavy-hurt") {
        unsigned player;if(!(in>>player))throw std::runtime_error("Expected initial heavy-hurt player");
        trial.startHeavyHurtFixture(player);
    }
    else if(op=="win-limit") {
        unsigned wins;if(!(in>>wins))throw std::runtime_error("Expected fixture win limit");
        trial.setWinRequirement(wins);
    }
    else if (op=="opening") {
        unsigned label;
        if(!(in>>label))throw std::runtime_error("Expected opening fixture label1..10");
        trial.startOpeningFixture(label);
    }
    else if (op=="knockout") {
        unsigned player,action;
        if (!(in>>player>>action)) throw std::runtime_error("Expected KO fixture player and action");
        trial.startKnockoutPreview(player,action);
    }
    else if (op=="life") {
        unsigned player;int life;
        if (!(in>>player>>life)) throw std::runtime_error("Expected fixture player and initial life");
        trial.setInitialLife(player,life);
    }
    else if (op=="place") {
        float a,b;if (!(in>>a>>b)) throw std::runtime_error("Expected two fixture positions");
        trial.place(a,b);
    } else if (op=="command") {
        unsigned player,value;
        if (!(in>>player>>value)||player>1||value>7) throw std::runtime_error("Expected player 0/1 and trial command 0..7");
        trial.command(player,TrialCommand(value));
    } else if (op=="tick") {
        unsigned n;if (!(in>>n)||n>1000000) throw std::runtime_error("Invalid fixture tick count");
        while(n--)trial.tick();
    } else throw std::runtime_error("Unknown trial command: "+op);
    return true;
}
}
