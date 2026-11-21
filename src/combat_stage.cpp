#include "combat_stage.hpp"
#include "kazuki_fire.hpp"
#include "stage_draw.hpp"
#include <cstdio>
#include <algorithm>
#include <bit>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ss6 {
using namespace stage_draw;

StageCommandGroups readStageCommands(std::span<const uint8_t> bytes,size_t count,bool pieceFlags) {
    StageReader r{bytes};
    StageCommandGroups groups(count);
    for(auto& group:groups) {
        const auto variants=r.word();
        if(!variants||variants>20)throw std::runtime_error("Invalid stage picture count");
        group.resize(variants);
        for(auto& commands:group) {
            const auto n=r.word();
            // A row whose helper is hidden by its own state may export nothing.
            if(n>256)throw std::runtime_error("Invalid stage command count");
            for(unsigned i=0;i<n;++i) {
                StageCommand cmd{r.word(),r.word(),{},{}};
                const auto params=r.word(),pieces=r.word();
                // Kinds 1..8 and 10 are the shared helpers; 9 and 11.. belong
                // to the stage that exported them and state their own size.
                constexpr unsigned expected[]={0,5,5,7,3,6,2,3,3};
                if(!cmd.kind||cmd.kind>63||cmd.slot<4||cmd.slot>8||pieces>4096||
                   (cmd.kind<9?params!=expected[cmd.kind]:params>cmd.parameters.size()))
                    throw std::runtime_error("Invalid stage draw command");
                for(unsigned j=0;j<params;++j)cmd.parameters[j]=r.value();
                const bool rectangles=cmd.kind<3||(cmd.kind>=7&&cmd.kind<=10);
                const unsigned arity=cmd.kind<3&&!pieceFlags?4:5;
                cmd.pieces.resize(pieces);
                for(auto& piece:cmd.pieces) {
                    if(rectangles)piece[4]=-1;
                    for(unsigned j=0;j<arity;++j)piece[j]=r.value();
                }
                if(rectangles&&(!pieces||cmd.pieces[0][2]<=0||cmd.pieces[0][3]<=0))
                    throw std::runtime_error("Invalid stage sprite extents");
                if(cmd.kind>=4&&cmd.kind<=6) {
                    const float columns=cmd.parameters[params-1];
                    if(columns<4||columns>128||std::floor(columns)!=columns||!pieces||pieces%unsigned(columns))
                        throw std::runtime_error("Invalid stage mesh dimensions");
                }
                commands.push_back(std::move(cmd));
            }
        }
    }
    if(!r.bytes.empty())throw std::runtime_error("Trailing stage geometry data");
    return groups;
}

CombatStage::CombatStage(const std::filesystem::path& assets,unsigned stage)
    :stage_(stage),raster_(assets,stage) {
    if(!CombatStageState::supports(stage))throw std::invalid_argument("Unported combat stage");
    char name[32];
    std::snprintf(name,sizeof name,"combat_stage_%02u.bin",stage);
    const auto bytes=readStageFile(assets/(stage==0?"combat_stage.bin":name),4*1024*1024);
    StageReader r{bytes};
    if(stage<2) {
        if(r.word()!=(stage==0?0x30475453u:0x31475453u)||r.word()!=1)throw std::runtime_error("Invalid stage geometry header");
        groups_=readStageCommands(r.bytes,stage==0?24:29,false);
    } else {
        if(r.word()!=0x58475453u||r.word()!=2||r.word()!=stage)throw std::runtime_error("Invalid stage geometry header");
        const auto count=r.word();
        if(count<2||count>256)throw std::runtime_error("Invalid stage group count");
        groups_=readStageCommands(r.bytes,count,true);
    }
    if(stage>=2)trig_=std::make_shared<AngleTrig>(assets);
}

std::vector<CombatStageStrip> CombatStage::geometry(const CombatStageState& state,unsigned* nextDepth) const {
    if(nextDepth)*nextDepth=100;
    if(!state.visible||state.suppressGeometry)return {};
    Projector renderer{{state.camera},100,{}};
    renderer.strips.reserve(160);
    switch(stage_) {
    case 2:drawCombatStage02(renderer,groups_,state.stage02,*trig_);break;
    case 3:drawCombatStage03(renderer,groups_,state.stage03,*trig_);break;
    case 4:drawCombatStage04(renderer,groups_,state.stage04,*trig_);break;
    case 5:drawCombatStage05(renderer,groups_,state.stage05,*trig_);break;
    case 6:drawCombatStage06(renderer,groups_,state.stage06,*trig_);break;
    case 7:drawCombatStage07(renderer,groups_,state.stage07,*trig_);break;
    case 8:drawCombatStage08(renderer,groups_,state.stage08,*trig_);break;
    case 9:drawCombatStage09(renderer,groups_,state.stage09,*trig_);break;
    case 10:drawCombatStage10(renderer,groups_,state.stage10,*trig_);break;
    case 11:drawCombatStage11(renderer,groups_,state.stage11,*trig_);break;
    default:
        renderer.sky(stage_);
        for(unsigned group=0;group<groups_.size();++group)
            renderer.run(groups_[group].at(group?state.pictureForRow(group-1):0));
    }
    std::stable_sort(renderer.strips.begin(),renderer.strips.end(),[](const auto& a,const auto& b){return a.z<b.z;});
    if(nextDepth)*nextDepth=renderer.counter;
    return std::move(renderer.strips);
}

unsigned CombatStage::paint(const CombatStageState& state,std::span<const uint16_t,1024> tones,std::span<uint8_t> rgba) const {
    StageRaster::clear(rgba);
    const auto palette=raster_.palette(tones);
    unsigned nextDepth=100;
    for(const auto& strip:geometry(state,&nextDepth))
        raster_.paint(rgba,strip.slot,strip.color,strip.mode,strip.vertices,palette);
    return nextDepth;
}
}
