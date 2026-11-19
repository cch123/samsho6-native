#include "stage_camera.hpp"
#include <iostream>
#include <bit>
#include <string>
#include <stdexcept>
namespace {
void cameraIn(ss6::StageCamera& c) {
    std::cin>>c.delta>>c.x>>c.y>>c.width>>c.left>>c.right>>c.top
            >>c.targetX>>c.targetY>>c.targetWidth>>c.vx>>c.vy>>c.vwidth;
}
void cameraOut(const ss6::StageCamera& c) {
    std::cout<<c.delta;
    for(float v:{c.x,c.y,c.width})std::cout<<' '<<std::bit_cast<uint32_t>(v);
    for(int32_t v:{c.left,c.right,c.top})std::cout<<' '<<v;
    for(float v:{c.targetX,c.targetY,c.targetWidth})std::cout<<' '<<std::bit_cast<uint32_t>(v);
    for(int32_t v:{c.vx,c.vy,c.vwidth})std::cout<<' '<<v;
    for(float v:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})std::cout<<' '<<std::bit_cast<uint32_t>(v);
}
}
int main() { try {
    std::string op;
    while(std::cin>>op) {
        ss6::StageCamera c;cameraIn(c);
        if(op=="queue") {
            unsigned count,steps,kind;int32_t parameter,elapsed;float x0,y0,x1,y1;
            std::cin>>count;
            for(unsigned i=0;i<count;++i) { std::cin>>kind>>parameter;c.appendCommand(kind,parameter); }
            std::cin>>steps>>elapsed>>x0>>y0>>x1>>y1;
            for(unsigned i=0;i<=steps;++i) {
                if(i)c.update(x0,y0,x1,y1,elapsed);
                cameraOut(c);std::cout<<' '<<c.commandsComplete()<<' '<<c.commands.size();
                for(const auto& q:c.commands)std::cout<<' '<<unsigned(q.kind)<<' '<<q.parameter;
                std::cout<<'\n';
            }
            continue;
        }
        if(op=="stage") {
            std::array<ss6::StageActor,2> a;
            for(auto& p:a) {
                unsigned flags,desc;std::cin>>p.x>>p.y>>p.flags23c>>p.flags244>>p.objectFlags>>flags>>p.table>>p.state>>desc;
                p.flags24c=uint8_t(flags);p.reactionFlags=uint8_t(desc);
            }
            const auto d=ss6::updateOrdinaryStage(a,c);cameraOut(c);
            for(auto& p:a)std::cout<<' '<<std::bit_cast<uint32_t>(p.x)<<' '<<unsigned(p.flags24c)<<' '<<p.expectedMirror;
            std::cout<<' '<<d[0]<<' '<<d[1];
        } else {
            if(op=="project") {
                float x,y;std::cin>>x>>y;c.publish();const auto p=c.project(x,y);
                std::cout<<std::bit_cast<uint32_t>(p.x)<<' '<<std::bit_cast<uint32_t>(p.y)<<' '<<std::bit_cast<uint32_t>(p.scale)<<'\n';
                continue;
            }
            if(op=="target"||op=="update") {
                float a,b,d,e;std::cin>>a>>b>>d>>e;
                if(op=="target")c.target(a,b,d,e);else c.update(a,b,d,e);
            } else if(op=="move") c.move();
            else if(op=="publish")c.publish();
            else throw std::runtime_error("Unknown camera operation");
            cameraOut(c);
        }
        std::cout<<'\n';
    }
} catch(const std::exception& e) { std::cerr<<e.what()<<'\n';return 1; } }
