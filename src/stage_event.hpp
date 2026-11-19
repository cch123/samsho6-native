#pragma once
#include "object_frame.hpp"
#include "stage_item_schedule.hpp"
#include <array>
#include <cstdint>
#include <filesystem>

namespace ss6 {
//Persistent actor at132c0a8 and its event-request words at132c1e0.
//These are separate from audio: a muted game still updates this state.
struct StageEventActor {
    int32_t state=0,request=0,pending=0;
    uint32_t flags=0,objectFlags=0;
    float x=0,y=0,z=0,targetX=0;
    int32_t dx=0,vx=0,ax=0;
};
struct StageEventPlayers {float x0=0,x1=0;bool mirror0=false;};
class StageEventRules {
public:
    StageItemSchedule items;
    explicit StageEventRules(const std::filesystem::path&);
    void request(StageEventActor&,int state,bool force,const StageEventPlayers&) const; //1b4d90
    void place(StageEventActor&,float x,float y) const; //1b4e88; caller's f14 is unused
    void placeRound(StageEventActor& actor) const {place(actor,roundX_,0);}
    //1b4f78 also copies player0's facing, including on a refused request.
    static bool outsideCenter(StageEventActor&,const StageEventPlayers&);
private:
    std::array<uint32_t,15> flags_{};
    float z_=0,roundX_=0;
};
class AuxiliaryObjects;
// Priority20/tag0xfa2. The battle event and its displayed body survive a round reset.
class StageEventPlayback {
public:
    void initialize(StageEventActor&);
    int visit(StageEventActor&,const StageEventPlayers&,int battleState,const GaugeState&,
              AuxiliaryObjects&,ObjectDrawQueue&);
    void hideNextDraw(){body_[0x104/4]|=2;} // 1b5078
    const AuxiliaryObject& body() const{return body_;}
private:
    AuxiliaryObject body_{};
    int wanted_=25,current_=25,phase_=0;
    bool tracking_=false,lowered_=false;
};

}
