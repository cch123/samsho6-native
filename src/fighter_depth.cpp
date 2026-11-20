#include <initializer_list>
#include "fighter_depth.hpp"
#include "scalar_float.hpp"
#include "fighter_roster.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
constexpr uint32_t explicitDepth=0x20000;

ScalarFloat childDepth(const AuxiliaryObject& obj,ScalarFloat bodyDepth) {
    switch(obj[0xcc/4]) {
    case 2:return ScalarFloat::integer(10);
    case 4:return ScalarFloat::integer(20);
    case 3:return ScalarFloat::integer(-10);
    case 9:return ScalarFloat::integer(40);
    case 10:return bodyDepth.add(ScalarFloat::integer(std::bit_cast<int32_t>(obj[0x130/4])));
    default:return ScalarFloat::integer(0);
    }
}

AuxiliaryObject& taskObject(TaggedTaskPools& pools,uint32_t task) {
    return pools.objects.at(pools.tasks.at(task-1)[7]-1);
}
// 1489c0's 18-entry jump table at 5ea1c4; record = body+28 plus one.
bool behindOnRecord(unsigned mode,unsigned record) {
    const auto any=[record](std::initializer_list<unsigned> l){for(auto v:l)if(record==v)return true;return false;};
    switch(mode) {
    case 0:return false;
    case 1:return true;
    case 2:return record==1;
    case 3:return record==2;
    case 4:return record==4;
    case 5:return any({7,11});
    case 6:return any({2,6,10});
    case 7:return any({7,11,15});
    case 8:return any({7,11,15,19});
    case 9:return any({2,6,10,14});
    case 10:return record>=2;
    case 11:return record>=10;
    case 12:return record-1u<4;
    case 13:return record-1u<2;
    case 14:return record-2u<38;
    case 15:return record-66u<16;
    case 16:return record-3u<22;
    case 17:return record>=20;
    default:throw std::logic_error("Missing fighter depth mode");
    }
}
void applyFighterDepthOverride(const FighterTables& tables,const std::array<unsigned,2>& ids,const std::array<unsigned,2>& actions,
                              const std::array<unsigned,2>& steps,uint32_t& p1Depth,uint32_t& p2Depth) {
    // 148900 stops at the first matching body, even when both fighters
    // have an override. ACT numbers in unrelated character banks do not match.
    // The rows (4d3d18, depth_rules.bin) name one ACT each; the mode compares
    // a one-based ACT record, independently of its duration.
    const auto& rules=tables.depthRules();
    for(unsigned i=0;i<2;++i) {
        const auto rule=std::find_if(rules.begin(),rules.end(),[&](auto r) {
            return ids[i]==r.fighter&&actions[i]==r.act;
        });
        if(rule==rules.end())continue;
        const bool needP1Front=(i==0)!=behindOnRecord(rule->mode,steps[i]+1);
        if(needP1Front?ScalarFloat{p2Depth}.less({p1Depth}):ScalarFloat{p1Depth}.less({p2Depth}))
            std::swap(p1Depth,p2Depth);
        break;
    }
}
}
void applyHaohmaruDepthOverride(const FighterTables& tables,const std::array<unsigned,2>& actions,uint32_t& p1Depth,uint32_t& p2Depth) {
    applyFighterDepthOverride(tables,{0,0},actions,{0,0},p1Depth,p2Depth);
}

void updateFighterDepths(BattleRoundState& battle,const std::array<RoundPlayerRef,2>& players,const FighterTables& tables) {
    const auto& p1=players[0].actor;
    const auto& p2=players[1].actor;
    if(!playableFighter(p1.character)||!playableFighter(p2.character))
        throw std::runtime_error("Draw priority requires character-specific action tables");
    bool p1InFront=(p1.stateTable()==1&&battle.entry.attackMarker12d2300)||
                   p1.state194==0x290000||p1.state194==0x340000||p2.state194==0x230000;
    // ACT234/235 override attack ownership. If both bodies use such an ACT,
    // the second iteration of the original loop wins.
    const std::array actions{players[0].body.timeline.action().id(),players[1].body.timeline.action().id()};
    for(unsigned i=0;i<2;++i) {
        const auto action=actions[i];
        if(action==234||action==235)p1InFront=i==1;
    }

    auto& pools=battle.entry.tasks;
    for(unsigned i=0;i<2;++i) {
        auto& body=players[i].body;
        if(!(body.timeline.clock().flags104&explicitDepth))
            body.depthOffsetB0=ScalarFloat::integer((i==0)==p1InFront?27:33).bits;
        // 148860 adds an owner bias even when the bodies exchanged priority.
        // Trail objects read this pre-override owner depth, and 147c1c will
        // refresh them against the final body depth if they are submitted.
        const auto bias=ScalarFloat::integer(i==0?3:-3);
        for(auto task:players[i].storage.objectTasks)if(task) {
            auto& o=taskObject(pools,task);
            if(!(o[0x104/4]&explicitDepth))
                o[0xb0/4]=childDepth(o,{body.depthOffsetB0}).add(bias).bits;
        }
    }
    // Common effects have no owner bias. 1487d0 is a branch-likely:
    // only unmarked objects execute the zero store in its delay slot.
    for(auto task:battle.objectTasks)if(task) {
        auto& o=taskObject(pools,task);
        if(!(o[0x104/4]&explicitDepth))o[0xb0/4]=0;
    }
    applyFighterDepthOverride(tables,{p1.character,p2.character},actions,
        {players[0].body.timeline.clock().step,players[1].body.timeline.clock().step},
        players[0].body.depthOffsetB0,players[1].body.depthOffsetB0);
    // The resource00 round normally has no actor+4 auxiliary body. If it
    // does, 148bb0 tracks the final depth while these actor flags are set.
    for(const auto& player:players) {
        const auto& a=player.actor;
        if(a.auxiliaryObject04&&(a.flags23c&0x01a00000))
            pools.objects.at(a.auxiliaryObject04-1)[0xb0/4]=
                ScalarFloat{player.body.depthOffsetB0}.add(ScalarFloat::integer(1)).bits;
    }
}
}
