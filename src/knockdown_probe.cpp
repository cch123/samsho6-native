#include "knockdown.hpp"
#include <bit>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Usage: ss6-knockdown-probe ASSETS");
    ss6::ActionBank bank(argv[1],true);auto object=std::make_unique<ss6::PlayerObject>(bank);
    ss6::KnockdownPlayback playback;ss6::DownedState a;ss6::DownedInput input;ss6::ActorTimers timers;ss6::GameRandom random;
    std::string op;
    while(std::cin>>op) {
        ss6::DownedEvents events;
        if(op=="reset") {
            object=std::make_unique<ss6::PlayerObject>(bank);object->setFlags(0x200,object->timeline.clock().flags108);
            playback={};a={};input={};timers={};random={};
        } else if(op=="flags") {
            uint32_t x,y,z,byte;std::cin>>x>>y>>z>>a.flags23c>>a.flags244>>a.flags248>>byte;
            a.flags24c=uint8_t(byte);object->timeline.setObjectFlags(x,y,z);
        } else if(op=="motion") {
            ss6::MotionState m;std::cin>>m.dx>>m.vx>>m.ax>>m.dy>>m.vy>>m.ay>>m.x>>m.y;object->timeline.setMotion(m);
        } else if(op=="input") {
            unsigned custom;std::cin>>input.pressRecovery>>input.back100>>input.down>>input.controlKind
              >>input.training>>input.trainingAction>>input.trainingRecovery>>input.specialInputs>>input.character
              >>input.specialReady>>input.aiStayDown>>input.opponentX>>input.system.system>>custom;
            std::array<uint8_t,16>d{};d[11]=uint8_t(custom);input.system.descriptor=d;
        } else if(op=="state") {
            std::cin>>a.table>>a.index;a.pendingTable=a.pendingIndex=-1;a.forceState=false;
        } else if(op=="choice") {
            unsigned count;std::cin>>a.recoveryA4c>>count;a.landingCount253=uint8_t(count);
        } else if(op=="random")std::cin>>random.mode>>random.gameSeed>>random.librarySeed;
        else if(op=="heavy")playback.beginHeavy(*object,a,timers);
        else if(op=="down")playback.beginDown(*object,a);
        else if(op=="rise")playback.beginRise();
        else if(op=="commit")object->commitRequested();
        else if(op=="animate"||op=="move") {
            unsigned delta;std::cin>>delta;timers.delta=int32_t(delta);
            if(op=="animate")object->animate(delta);else object->move(delta);
        } else if(op=="callback")events=playback.update(*object,a,timers,input,random);
        else if(op=="choose")playback.chooseRecovery(*object,a,input,random);
        else if(op=="request")playback.requestRecovery(*object,a,input);
        else if(op=="landing")events.dust=ss6::landingReady(*object);
        else throw std::runtime_error("Unknown knockdown command");
        if(!std::cin)throw std::runtime_error("Truncated knockdown command");
        const auto& c=object->timeline.clock();const auto& m=object->timeline.motion();
        std::cout<<int(playback.phase)<<' '<<a.flags23c<<' '<<a.flags244<<' '<<a.flags248<<' '
         <<a.flagsB8<<' '<<a.opponentFlagsB8<<' '<<a.opponentFlags248<<' '<<unsigned(a.landingCount253)<<' '
         <<a.recoveryA4c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '<<a.forceState<<' '<<events.dust<<' '<<events.lifeAdjustment<<' ';
        for(auto t:timers.values)std::cout<<t<<' ';
        std::cout<<object->timeline.action().id()<<' '<<c.step<<' '<<c.fractionalTime<<' '
         <<c.endReached<<' '<<c.endControl<<' '<<c.objectFlags<<' '<<c.flags104<<' '<<c.flags108<<' '
         <<c.chainedAction<<' '<<object->pendingFlags<<' '<<m.dx<<' '<<m.vx<<' '<<m.ax<<' '<<m.dy<<' '<<m.vy<<' '<<m.ay<<' '
         <<std::bit_cast<uint32_t>(m.x)<<' '<<std::bit_cast<uint32_t>(m.y)<<' '
         <<random.gameSeed<<' '<<uint32_t(random.librarySeed)<<' '<<uint32_t(random.librarySeed>>32)<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
