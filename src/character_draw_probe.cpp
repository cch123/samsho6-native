#include "character_draw.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
uint32_t word(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete character draw fixture");return v;}
void emit(auto v){std::cout<<+v<<' ';}
int main(int argc,char** argv){try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::CharacterDraws renderer(argv[1],{0,0,51});ss6::CharacterDrawState state;
    std::string op;while(std::cin>>op) {
        if(op=="state") {state.flags=word();state.color=word();state.primitiveColor=word();state.mode=word();state.additive=word();state.depthOffset.bits=word();continue;}
        if(op!="draw")throw std::runtime_error("Unknown character draw operation");
        ss6::ObjectDrawQueue::Record o;for(auto& v:o)v=word();
        ss6::StageCamera camera;camera.projectionX=std::bit_cast<float>(word());camera.projectionY=std::bit_cast<float>(word());
        camera.depth=std::bit_cast<float>(word());camera.depthOffset=std::bit_cast<float>(word());camera.verticalOffset=std::bit_cast<float>(word());
        ss6::CharacterDrawContext c{camera,{word(),word()},std::bit_cast<int32_t>(word()),std::bit_cast<int32_t>(word())};
        std::vector<ss6::CharacterSprite> sprites;renderer.submit(o,c,state,sprites);
        emit(state.flags);emit(state.color);emit(state.primitiveColor);emit(state.mode);emit(state.additive);emit(state.depthOffset.bits);emit(sprites.size());
        for(const auto& s:sprites) {
            for(auto v:{s.slot,s.palette,s.image,s.flags,s.shadow,s.x.bits,s.y.bits,s.z.bits,s.scaleX.bits,s.scaleY.bits,s.mode,s.color,s.contextFlags,s.contextColor,s.additive,s.depthOffset.bits})emit(v);
        }
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
