#include "sound_selection.hpp"
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected asset directory");
    ss6::SoundSelection sounds(argv[1]);ss6::GameRandom random;int command,stage;
    while(std::cin>>command>>stage>>random.mode>>random.gameSeed>>random.librarySeed>>sounds.previous[0]>>sounds.previous[1]) {
        const auto result=sounds.resolve(command,stage,random);
        std::cout<<result<<' '<<random.gameSeed<<' '<<random.librarySeed<<' '<<sounds.previous[0]<<' '<<sounds.previous[1]<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
