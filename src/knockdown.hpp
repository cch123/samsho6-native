#pragma once
#include "actor_state.hpp"
#include "game_random.hpp"
#include "input_bindings.hpp"
#include "knockout.hpp"

namespace ss6 {
struct DownedState {
    uint32_t flags23c=0x1000,flags244=0,flags248=0,flagsB8=0;
    uint32_t opponentFlagsB8=0,opponentFlags248=0;
    uint8_t flags24c=0,landingCount253=0;
    int32_t recoveryA4c=0;
    int table=2,index=64,pendingTable=-1,pendingIndex=-1;
    bool forceState=false;
};
struct DownedInput {
    InputSystemConfig system;
    unsigned character=0,controlKind=0;
    bool pressRecovery=false,back100=false,down=false;
    bool specialInputs=false,specialReady=false;
    //These are upstream query results (139c88/139ce8,15ade8,1fa1d8),
    //not new AI or input recognition. The local human/system0 path needs none.
    bool training=false,aiStayDown=false;
    int trainingAction=0,trainingRecovery=0;
    float opponentX=0;
    std::optional<std::array<int32_t,2>> wallBounds;
};
struct DownedEvents { bool dust=false;int lifeAdjustment=0; };
enum class DownedPhase { Inactive,FirstLanding,SecondLanding,Finish,DownWait,RiseQueued,Rising,StayDown,RiseDelay,Holding,WallApproach };
class KnockdownPlayback {
public:
    DownedPhase phase=DownedPhase::Inactive;
    //A supplied queue keeps1493c0's actor action separate from149918's
    //body request. Legacy standalone playback commits that boundary here.
    static bool supportsFall(int state);
    static bool backwardFall(int state);
    static bool landsOnBack(int state);
    static unsigned fallVariant(int state);
    static unsigned fallAction(int state,bool armed);
    void beginHeavy(PlayerObject&,DownedState&,ActorTimers&,int32_t* actorAction=nullptr); //171418, table 4e8c50
    void beginDown(PlayerObject&,DownedState&,int32_t* actorAction=nullptr); //170c60
    void beginRise(); //170690, action is requested on the following callback
    DownedEvents update(PlayerObject&,DownedState&,ActorTimers&,const DownedInput&,GameRandom&,int32_t* actorAction=nullptr);
    static void chooseRecovery(const PlayerObject&,DownedState&,const DownedInput&,GameRandom&); //1720b0
    static bool requestRecovery(PlayerObject&,DownedState&,const DownedInput&); //172008
private:
    static void request(DownedState&,int table,int index,bool force=false);
    void finishDown(DownedState&,ActorTimers&); //16fd90
    static void recoverStanding(PlayerObject&,DownedState&,const DownedInput&); //169810
};
}
