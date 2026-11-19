#include "native_match.hpp"
#include "native_scene.hpp"
#include "combat_stage.hpp"
#include <iostream>
using namespace ss6;
int main(int,char** argv) {
    NativeMatch m(argv[1],60,VersusMode::Console,nullptr,{},VersusLineup{{{0,0,0},{2,2,1}}});
    for(unsigned i=0;i<2;++i)m.enableCpu(i,3);
    unsigned first=0,last=0,count=0,records=0,step=~0u,visible=0,maxPixels=0;
    auto scene=std::make_unique<NativeScene>(argv[1],std::array{0u,2u,51u});
    auto control=std::make_unique<NativeScene>(argv[1],std::array{0u,2u,51u});
    std::unique_ptr<CombatStage> stage;
    while(m.updates<40000&&!m.finished) {
        m.tick({});
        for(const auto& o:m.objectDraws().active()) {
            if(o[0x144/4]||o[0xcc/4]!=6||o[0x24/4]!=508)continue;
            const auto& f=m.fighter(0);
            if(!count) {
                if(f.actor.stateTable()!=0||f.actor.stateIndex()!=41||f.body.timeline.action().id()!=502||
                   f.body.timeline.clock().step!=1||o[0x118/4]!=1)return 2;
                first=m.updates;
            } else if(m.updates!=last+1)return 3;
            last=m.updates;++count;
            if(step==o[0x28/4])continue;
            step=o[0x28/4];++records;
            if(!stage)stage=std::make_unique<CombatStage>(argv[1],m.battle().matchEnd.metadataStage04);
            std::vector<uint8_t> image(NativeScene::width*NativeScene::height*4);
            const auto depth=stage->paint(m.combatStage(),m.battle().gauges.paletteTones,image);
            auto without=image;auto remaining=std::make_unique<ObjectDrawQueue>();
            for(const auto& r:m.objectDraws().active())
                if(&r!=&o)remaining->slots[remaining->count++]=r;
            remaining->sort();
            // Paint both identical stage/character queues, removing only the
            // registered attachment from the control to measure its own pixels.
            scene->paint(m,image,[](const auto&){},depth);
            control->paint(m,without,[](const auto&){},depth,remaining.get());
            unsigned pixels=0;
            for(size_t i=0;i<image.size();i+=4)
                if(!std::equal(image.begin()+i,image.begin()+i+3,without.begin()+i))++pixels;
            visible+=pixels!=0;maxPixels=std::max(maxPixels,pixels);
        }
    }
    const auto& score=m.battle().match.players;
    if(!visible||!count||records!=27||!m.finished||!score[0].complete())return 4;
    std::cout<<first<<' '<<last<<' '<<count<<' '<<records<<' '<<m.updates<<' '<<score[0].wins<<' '<<score[1].wins<<' '<<visible<<' '<<maxPixels<<'\n';
}
