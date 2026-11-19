#pragma once
#include <array>
#include <cstdint>
#include <vector>
namespace ss6 {
struct StageProjection { float x,y,scale; };
struct CameraCommand { uint8_t kind=0;int32_t parameter=0; };
// Two-resource00 camera, including the original timed shake and command queue.
// Float arithmetic uses the same explicitly provisional model as damage.
struct StageCamera {
    int32_t delta=256;
    float x=320,y=120,width=320;
    int32_t left=160,right=480,top=240;
    float targetX=320,targetY=120,targetWidth=320;
    int32_t vx=0,vy=0,vwidth=0;
    int32_t shakeX44=0,shakeY48=0; // Independent 8.8 clocks at camera+44/+48.
    // 0x122ed8 projection globals. Keeping these separate matters: bounds
    // correction can change camera.x/y after projection has been published.
    float projectionX=320,projectionY=120,depth=-400,depthOffset=0,verticalOffset=-120;
    std::vector<CameraCommand> commands;
    void resetRound(); // 146388/146418; publishes using the existing delta and shake clocks
    void requestShake(int xDuration,int yDuration); // 141528/146ba0
    void appendCommand(unsigned kind,int32_t parameter);
    bool commandsComplete() const;
    bool consumeCommand(int32_t elapsed);
    void target(float x0,float y0,float x1,float y1);
    void move();
    void publish();
    void update(float x0,float y0,float x1,float y1,int32_t elapsed=256,bool freezeCamera=false);
    StageProjection project(float actorX,float actorY,float z=0) const;
};
struct StageActor {
    float x=0,y=0;
    uint32_t flags23c=0,flags244=0,objectFlags=0;
    uint8_t flags24c=0;
    int16_t table=0,state=0;
    uint8_t reactionFlags=0;
    bool expectedMirror=false;
    float historyX=0; // Actor+a6c, latest saved X before the complete guard recoil.
};
float clampOrdinaryActor(StageActor& actor,const StageCamera& camera);
//147f48 with force1: separate truncated anchors, then apply142d00 to each.
//The force0 collision-box path is different and is not represented here.
void separateActorAnchors(std::array<StageActor,2>& actors,const StageCamera&,int32_t distance);
// 0x1426d8 ordinary resource00 positioning and camera update. The caller
// consumes body shake requests before publication. Facing changes here are intent.
std::array<int32_t,2> updateOrdinaryStage(std::array<StageActor,2>& actors,StageCamera& camera,bool freezeCamera=false);
} // namespace ss6
