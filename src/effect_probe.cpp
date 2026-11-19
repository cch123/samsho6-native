#include "effect_runtime.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
void print(const ss6::EffectState& s) {
    std::cout<<s.step<<' '<<s.time<<' '<<s.speed;
    for(auto v:s.motion)std::cout<<' '<<v;
    std::cout<<' '<<s.scale.bits<<' '<<s.scaleVelocity.bits<<' '<<s.scaleAcceleration.bits<<' '<<s.color;
    for(auto v:s.colorMotion)std::cout<<' '<<uint32_t(v);
}
int main(int argc,char** argv) {
    try {
        if(argc!=2)throw std::runtime_error("Usage: ss6-effect-probe ASSETS");
        ss6::EffectBank bank(argv[1]);std::string op;
        while(std::cin>>op) {
            unsigned b,a,flags,n,paused;
            if(op=="quad") {
                unsigned step;float x,y,z,scale,cx,cy,cw;
                std::cin>>b>>a>>step>>flags>>x>>y>>z>>scale>>cx>>cy>>cw;
                ss6::EffectInstance i(bank.action(b,a),flags,x,y,z,scale);
                i.state.step=step;i.enterRecord();
                ss6::StageCamera camera;camera.x=cx;camera.y=cy;camera.width=cw;camera.publish();
                const auto q=ss6::projectEffect({bank.action(b,a).at(step),i.state},camera);
                for(const auto& v:q.vertices)for(auto f:v)std::cout<<std::bit_cast<uint32_t>(f)<<' ';
                std::cout<<q.u<<' '<<q.v<<' '<<q.textureWidth<<' '<<q.textureHeight<<' '<<q.asset<<' '<<q.palette<<' '<<q.mirrorX<<' '<<q.mirrorY<<'\n';
                continue;
            }
            if(op!="run")throw std::runtime_error("Unknown effect command");
            std::cin>>b>>a>>flags>>n>>paused;
            ss6::EffectInstance i(bank.action(b,a),flags,280,0,0,1);
            std::cout<<i.alive()<<' ';print(i.state);std::cout<<" 0\n";
            for(unsigned t=0;t<n;++t) {
                auto d=i.update(paused==1||(paused==2&&t%3==0));
                std::cout<<i.alive()<<' ';print(i.state);std::cout<<' '<<bool(d);
                if(d){std::cout<<' ';print(d->state);}std::cout<<'\n';
            }
        }
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
