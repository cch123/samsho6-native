#include "input_features.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main() {
 try {
    ss6::InputSampler input;std::string op;
    while(std::cin>>op) {
        if(op=="seed") {
            for(auto& v:input.features)std::cin>>v;
            for(auto& player:input.pressLatches)for(auto& v:player){unsigned n;std::cin>>n;v=uint8_t(n);}
            for(auto* array:{&input.replayHeld,&input.replayPressed})for(auto& v:*array)std::cin>>v;
        } else if(op=="sample") {
            bool derive;unsigned player;ss6::NormalizedPadSample pad;ss6::InputMapping mapping;ss6::InputSamplingContext c;
            std::cin>>derive>>player>>pad.held>>pad.pressed>>c.facing>>c.actualFacing>>c.reverseDirections>>c.playback>>c.replayIndex>>c.gameMode;
            for(auto* array:{&mapping.normal,&mapping.mode6})for(auto& v:*array)std::cin>>v;
            if(derive)input.advance(player,pad,mapping,c);else input.sampleRaw(player,pad,mapping,c);
            for(auto v:input.features)std::cout<<v<<' ';
            for(const auto& p:input.pressLatches)for(auto v:p)std::cout<<unsigned(v)<<' ';
            if(uint32_t(c.replayIndex)<600)std::cout<<input.replayHeld[c.replayIndex]<<' '<<input.replayPressed[c.replayIndex];
            else std::cout<<"0 0";
            std::cout<<'\n';
        } else if(op=="recording") {
            for(auto* array:{&input.replayHeld,&input.replayPressed})for(auto v:*array)std::cout<<v<<' ';
            std::cout<<'\n';
        } else throw std::runtime_error("Unknown input-feature probe operation");
        if(!std::cin)throw std::runtime_error("Incomplete input-feature fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
