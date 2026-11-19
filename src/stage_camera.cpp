#include "stage_camera.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <stdexcept>
namespace ss6 {
namespace {
ScalarFloat f(float x) { return {std::bit_cast<uint32_t>(x)}; }
float raw(ScalarFloat x) { return std::bit_cast<float>(x.bits); }
float add(float a,float b) { return raw(f(a).add(f(b))); }
float sub(float a,float b) { return raw(f(a).sub(f(b))); }
float mul(float a,float b) { return raw(f(a).mul(f(b))); }
float div(float a,float b) { return raw(f(a).div(f(b))); }
float integer(int32_t a) { return raw(ScalarFloat::integer(a)); }
void bounded(float a) {
    if (!std::isfinite(a)||std::abs(a)>1000000) throw std::runtime_error("Stage coordinate outside finite model");
}
int32_t speed(float current,float target,int32_t magnitude) {
    return current<target ? magnitude : current>target ? -magnitude : 0;
}
void moveAxis(float& current,float target,int32_t& velocity,int32_t delta) {
    // EE MULT uses the signed low word, including overflow, before CVT.S.W.
    const auto product=std::bit_cast<int32_t>(uint32_t(velocity)*uint32_t(delta));
    current=add(current,mul(integer(product),0x1p-24f));
    if ((velocity>0&&current>=target)||(velocity<0&&current<=target)) {
        current=target;velocity=0;
    }
}
float shakeAxis(int32_t& remaining,int32_t delta,float axisScale) {
    if(remaining<=0)return 0;
    // The phase is sampled at the start of this visit. The EE tests bit 1
    // of the whole count, so two consecutive samples share a direction.
    const int32_t count=remaining>>8;
    const float amplitude=mul(integer(count+7),0.125f);
    remaining=std::bit_cast<int32_t>(uint32_t(remaining)-uint32_t(delta));
    return mul((count&2)?amplitude:-amplitude,axisScale);
}
float targetCenter(float center,float extent,float limit) {
    const float half=mul(extent,.5f);
    if (sub(center,half)<0) return half;
    if (add(center,half)>limit) return sub(limit,half);
    return center;
}
}
void StageCamera::resetRound() {
    x=targetX=320;y=targetY=120;width=targetWidth=320;
    vx=vy=vwidth=0;commands.clear();publish();
}
void StageCamera::target(float x0,float y0,float x1,float y1) {
    for (float v:{x0,y0,x1,y1}) bounded(v);
    // 146460 modifies the input pair before the shared target calculation.
    // In particular cmd2 focuses one player; it does not directly teleport
    // the camera. The usual +48 adjustment to the first Y still follows.
    if(!commands.empty())switch(commands.front().kind) {
        case 1:y0=y1=480;break;
        case 2:
            if(commands.front().parameter) { x0=x1;y0=y1; }
            else { x1=x0;y1=y0; }
            break;
        case 5:y0=y1=0;break;
        case 6:x1=x0;y0=y1=0;break;
        case 7:x0=x1;y0=y1=0;break;
        case 8:y1=y0;break;
        case 9:y0=y1;break;
        case 10:y0=add(y0,48);y1=add(y1,48);break;
        default:break;
    }
    targetWidth=std::clamp(add(std::abs(sub(x0,x1)),80),320.0f,444.0f);
    targetX=targetCenter(mul(add(x0,x1),.5f),targetWidth,640);
    // This asymmetry is in 0x146568: only player0 gets the +48 adjustment.
    // Do not replace it with a symmetric "average character height" rule.
    y0=add(y0,48);
    const float height=std::clamp(add(std::abs(sub(y0,y1)),30),240.0f,336.0f);
    targetY=targetCenter(mul(add(y0,y1),.5f),height,480);
    vx=speed(x,targetX,0x40000);vy=speed(y,targetY,0x200000);vwidth=speed(width,targetWidth,0x20000);
}
void StageCamera::move() {
    moveAxis(x,targetX,vx,delta);moveAxis(y,targetY,vy,delta);moveAxis(width,targetWidth,vwidth,delta);
}
void StageCamera::requestShake(int xDuration,int yDuration) {
    // Negative arguments preserve the other axis; zero cancels it. A new
    // request replaces the remaining time even when it shortens a running one.
    if(xDuration>=0)shakeX44=std::bit_cast<int32_t>(uint32_t(xDuration)<<8);
    if(yDuration>=0)shakeY48=std::bit_cast<int32_t>(uint32_t(yDuration)<<8);
}
void StageCamera::publish() {
    for (float v:{x,y,width}) bounded(v);
    if (width<=0) throw std::runtime_error("Non-positive camera width");
    // 146870 writes the displaced center back to the camera after using it
    // to publish the projection. Translation, world bounds and later target
    // movement therefore all see the accumulated displacement.
    x=add(x,shakeAxis(shakeX44,delta,1.2f));
    y=add(y,shakeAxis(shakeY48,delta,2.4f));
    // 0x122ed8, including the separate MULA.S/MADD.S rounding in the
    // projection. It is deliberately not simplified to -120 * scale.
    projectionX=std::clamp(x,160.0f,480.0f);projectionY=std::max(y,120.0f);
    if (width<=320) { depth=-400;depthOffset=0; }
    else {
        depth=sub(-200,div(mul(width,200),320));
        depthOffset=add(div(mul(-depth,320),width),depth);
    }
    const float scale=div(sub(depth,depthOffset),depth);
    verticalOffset=add(mul(-projectionY,scale),mul(sub(projectionY,120),scale));
    const int32_t iw=int32_t(width);
    const int32_t ih=std::clamp(int32_t(div(mul(integer(iw),480),640)),240,480);
    const float hw=integer(iw/2),hh=integer(ih/2);
    left=int32_t(sub(projectionX,hw));right=int32_t(add(projectionX,hw));
    // Original 0x146984 writes the bottom bound into camera+0x30, which is
    // ALSO the Y velocity field. Preserve that alias instead of fixing it.
    vy=int32_t(sub(projectionY,hh));top=int32_t(add(projectionY,hh));
    if (left<0) { x=add(x,integer(-left));left=0; }
    else if (right>640) { x=add(x,sub(640,integer(right)));right=640; }
    else if (vy<0) vy=0;
    else if (top>480) { y=add(y,sub(480,integer(top)));top=480; }
}
void StageCamera::appendCommand(unsigned kind,int32_t parameter) {
    if(kind>10||commands.size()>=16)throw std::runtime_error("Camera command outside original queue capacity/type");
    // 146b30 scales only cmd3..10; preserve word wrap for signed parameters.
    if(kind>=3)parameter=std::bit_cast<int32_t>(uint32_t(parameter)<<8);
    commands.push_back({uint8_t(kind),parameter});
}
bool StageCamera::commandsComplete() const {
    // 146b00 treats the explicit cmd0 sentinel as complete, not an empty
    // queue. Clearing the queue at entry must not finish the camera script.
    return !commands.empty()&&commands.front().kind==0;
}
bool StageCamera::consumeCommand(int32_t elapsed) {
    if(commands.empty())return false;
    auto& command=commands.front();
    if(command.kind==0)return true;
    if(command.kind==1||command.kind==2) {
        delta=command.kind==1 ? 64 : 192;
        if(int32_t(x)!=int32_t(targetX)||int32_t(y)!=int32_t(targetY)||int32_t(width)!=int32_t(targetWidth))return false;
    } else if(command.parameter>0) {
        command.parameter=std::bit_cast<int32_t>(uint32_t(command.parameter)-uint32_t(elapsed));
        return command.kind==3;
    }
    // One command is consumed per visit. A new sentinel/wait only takes
    // effect on the next visit, including the final move on this visit.
    commands.erase(commands.begin());return false;
}
void StageCamera::update(float x0,float y0,float x1,float y1,int32_t elapsed,bool freezeCamera) {
    target(x0,y0,x1,y1);
    // 1463d0 still publishes projection and bounds while a wall flight holds
    // the camera. Its command timer starts only when that hold is released.
    if(!freezeCamera) {
        delta=256;
        if(!consumeCommand(elapsed))move();
    }
    publish();
}
StageProjection StageCamera::project(float actorX,float actorY,float z) const {
    // 0x123020/122ff0, ordinary layer/global X offset -160. Coordinates
    // are in the original 640-wide projection, before the preview crop.
    const float scale=div(sub(depthOffset,depth),sub(z,depth));
    const float px=sub(mul(sub(actorX,projectionX),scale),-160);
    const float py=add(sub(mul(sub(actorY,projectionY),scale),verticalOffset),mul(scale,12));
    return {add(px,px),sub(448,add(py,py)),scale};
}
float clampOrdinaryActor(StageActor& a,const StageCamera& camera) {
    bounded(a.x);
    if ((a.flags244&0x2000000)&&a.table==0&&a.state==53) {
        // The complete guard redirects its retreat into the opponent. Restore
        // the previous pose before either arena edge can clamp this fighter.
        const auto correction=sub(a.historyX,a.x);
        a.x=a.historyX;
        return correction;
    }
    if (a.flags244&0x20000) return 0;
    const float lo=std::max(add(integer(camera.left),34),34.0f);
    const float hi=std::min(sub(integer(camera.right),34),606.0f);
    const float before=a.x;
    if (a.x<lo) a.x=lo;
    else if (a.x>hi) a.x=hi;
    const float correction=sub(a.x,before);
    // Only selected damage/guard states transmit wall correction to the
    // opponent. Ordinary walking still clamps but must return zero.
    return correction!=0&&a.table==2&&a.state>=0&&a.state<80&&(a.reactionFlags&0x20) ? correction : 0;
}
void separateActorAnchors(std::array<StageActor,2>& a,const StageCamera& camera,int32_t distance) {
    bounded(a[0].x);bounded(a[1].x);
    const auto x0=f(a[0].x).truncate(),x1=f(a[1].x).truncate();
    //Ordering uses the FLOAT anchors, even when both truncate to the same
    //integer. The odd remainder always belongs to the second argument.
    const bool left=a[0].x<a[1].x;
    const int32_t d0=left?-1:1,d1=-d0;
    const uint32_t gap=left?uint32_t(x1)-uint32_t(x0):uint32_t(x0)-uint32_t(x1);
    const int32_t delta=std::bit_cast<int32_t>(uint32_t(distance)-gap);
    const auto product=[](int32_t x,int32_t y){return std::bit_cast<int32_t>(uint32_t(x)*uint32_t(y));};
    a[0].x=add(a[0].x,integer(product(d0,delta)/2));
    const auto adjusted=std::bit_cast<int32_t>(uint32_t(delta)+(delta<0?uint32_t(-1):1u));
    a[1].x=add(a[1].x,integer(product(d1,adjusted)/2));
    const auto c0=f(clampOrdinaryActor(a[0],camera)).truncate();
    const auto c1=f(clampOrdinaryActor(a[1],camera)).truncate();
    //Ordinary normal states clamp but return zero: redistributing their
    //wall displacement here would move the other player a second time.
    if(c0>0)a[1].x=add(a[1].x,integer(product(d1,c0)));
    if(c1>0)a[0].x=add(a[0].x,integer(product(d0,c1)));
}
std::array<int32_t,2> updateOrdinaryStage(std::array<StageActor,2>& a,StageCamera& camera,bool freezeCamera) {
    const std::array<float,2> correction{clampOrdinaryActor(a[0],camera),clampOrdinaryActor(a[1],camera)};
    for (unsigned i=0;i<2;++i) if (!(a[i].flags23c&0x10)) a[i].x=add(a[i].x,mul(correction[1-i],.5f));
    const int x0=int(a[0].x),x1=int(a[1].x);
    for (unsigned i=0;i<2;++i) {
        auto& p=a[i];const bool mirror=p.objectFlags&0x80000;
        p.expectedMirror=x0==x1 ? mirror : (i ? x1>x0 : x0>x1);
        p.flags24c=uint8_t((p.flags24c&~2)|((mirror!=p.expectedMirror) ? 2 : 0));
        if (p.table==1&&p.state>=64) p.expectedMirror=mirror;
    }
    const std::array<int32_t,2> distances{std::abs(int32_t(sub(a[0].x,a[1].x))),std::abs(int32_t(sub(a[0].y,a[1].y)))};
    camera.update(a[0].x,a[0].y,a[1].x,a[1].y,256,freezeCamera);
    for (auto& p:a) if (p.flags24c&4) {
        p.flags24c&=uint8_t(~2);p.expectedMirror=p.objectFlags&0x80000;
    }
    return distances;
}
} // namespace ss6
