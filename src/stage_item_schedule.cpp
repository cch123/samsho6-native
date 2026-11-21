#include "stage_item_schedule.hpp"
#include "battle_round.hpp"
#include "scalar_float.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <stdexcept>

namespace ss6 {
StageItemSchedule::StageItemSchedule(const std::filesystem::path& assets) {
    std::ifstream in(assets/"stage_item_schedule.bin",std::ios::binary|std::ios::ate);
    if(!in||in.tellg()!=std::streamoff(table_.size()))throw std::runtime_error("Invalid stage item schedule");
    in.seekg(0);
    if(!in.read(reinterpret_cast<char*>(table_.data()),table_.size()))throw std::runtime_error("Truncated stage item schedule");
}

int StageItemSchedule::roll(BattleRoundState& b,unsigned stage,int second) const {
    // 14e938 rolls before checking the time latch. Even a second with no
    // spawn advances the same stream used by combat and sound selection.
    const int roll=b.random.bounded(8);
    if(stage>=12||b.lastItemSecond==second)return -1;
    b.lastItemSecond=second;
    const auto seconds=table_.begin()+0x170;
    const auto found=std::find(seconds,table_.end(),second);
    if(found==table_.end())return -1;
    const auto row=table_.begin()+20*stage;
    const int group=row[4+(found-seconds)];
    if(group==255)return -1;
    switch(table_.at(0xf0+group*8+roll)) {
    case 0:return b.random.bounded(4);
    case 1:return 4+b.random.bounded(3);
    case 2:return 8;
    case 3:return 7;
    case 4:return row[0]; // Stage-specific throwable.
    default:return -1;
    }
}

std::optional<StageItemDrop> StageItemSchedule::next(BattleRoundState& b,const StageEventPlayers& players) const {
    // 141860: never in the demo; two-human fights need the item option, while
    // arcade always delivers. Survival uses another producer.
    if(b.gameMode==0||b.survival()||(b.gameMode==3&&!b.stageItemsOption4c3828))return std::nullopt;
    if(b.timers.decrease(3)>0||b.stageItems.busy())return std::nullopt;
    // 140fa0 looks up just the first kind-5 battle object. A live fuse
    // keeps another item off the stage even after its carrier has departed.
    const auto& pools=b.entry.tasks;
    for(auto task:b.objectTasks)if(task) {
        const auto& obj=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        if(obj[0xcc/4]!=5)continue;
        const unsigned act=obj[0x24/4];
        if(act==76||act==78||act==133)return std::nullopt;
        break;
    }
    int kind;
    if(b.practice()) {
        // 145068: the practice menu row ITEM chooses the kind; RANDOM draws 112300(0x13).
        if(!b.practiceRules)return std::nullopt;
        kind=practiceItemDelivery(*b.practiceRules,b.random);
        if(kind<0)return std::nullopt;
    } else {
        int second=60-b.timers.values[1]/0x5a00;
        if(second<0){b.timers.clear(1);second=60;}
        kind=roll(b,b.matchEnd.metadataStage04,second);
        if(kind<0)return std::nullopt;
        // In local versus the three score awards are replaced by a bomb or
        // a thrown item. Keep the extra random call in its original position.
        if(b.gameMode==3&&kind>=4&&kind<=6)kind=b.random.bounded(2)?7:8;
    }
    const int fromRight=b.random.bounded(2);
    const int anchor=b.random.bounded(4);
    auto scalar=[](float x){return ScalarFloat{std::bit_cast<uint32_t>(x)};};
    ScalarFloat target{};
    switch(anchor) {
    case 0:target=scalar(players.x0);break;
    case 1:target=scalar(players.x1);break;
    case 2:target=scalar(players.x0).add(scalar(players.x1)).mul({0x3f000000});break;
    default:target=scalar(b.camera.projectionX);break;
    }
    b.timers.set(3,360+60*b.random.bounded(8));
    return StageItemDrop{kind,target.truncate(),fromRight};
}
}
