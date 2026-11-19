#include "contact_presentation.hpp"
#include "auxiliary_objects.hpp"
#include "knockout.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
void spawn(ScheduledOpening& effects,BattleRoundState& battle,unsigned descriptor,int x,int y,float scale=1) {
    effects.startContact(descriptor,float(x),float(y),scale,battle.entry.tasks,battle.effectResidency,battle.random);
}
AuxiliaryObject* commonElement(AuxiliaryObjects& objects,BattleRoundState& battle,unsigned victim,bool mirror,int action) {
    if(action<0)return nullptr; // Some damage colors have no attached ACT.
    AuxiliaryObject facing{};facing[0x38/4]=mirror?0x80000:0;
    const auto handle=objects.createCommonEffect(battle.entry.tasks,battle.objectTasks,&facing,0x1396,0);
    if(!handle)return nullptr;
    auto& object=battle.entry.tasks.objects.at(handle-1);
    object[0x118/4]=victim+1;
    objects.request(object,action,false,true);
    object[0x108/4]|=0x2000;
    return &object;
}
unsigned hitColumn(unsigned type,GameRandom& random) {
    // 156fb8 selects the effect size independently of the actor's sword
    // strength. In particular, raw17 (running heavy) and raw12 both use 2.
    if(type==15)return unsigned(random.bounded(3));
    if(type<11)return 0;
    if(type==11||type==13||type==14||type==16)return 1;
    return 2;
}
struct ElementClips {int impact,attached,release;};
// Three independent columns at 4e8758. Only ice (JDG remainder 5)
// leaves a new set of fragments when the attached reaction retires.
constexpr std::array<ElementClips,9> elements{{
    {-1,-1,-1},{4,5,-1},{16,17,-1},{7,8,-1},{19,20,-1},{10,11,12},
    {-1,-1,-1},{-1,-1,-1},{4,5,-1}
}};
}
void spawnElementHurt(AuxiliaryObjects& objects,BattleRoundState& battle,unsigned victim,
                      const PlayerObject& body,const StateEntryActor& actor) {
    const auto parent=body.childParentWords();
    auto* object=commonElement(objects,battle,victim,parent[0x38/4]&0x80000,elements.at(actor.contactKind252).attached);
    if(!object)return;
    auto& o=*object;
    o[0x40/4]=parent[0x40/4];o[0x44/4]=parent[0x44/4];
    const auto anchor=objects.bodyAnchor(actor.character);
    o[0xec/4]=ScalarFloat{o[0xec/4]}.add(ScalarFloat::integer(anchor[0])).bits;
    o[0xf0/4]=ScalarFloat{o[0xf0/4]}.add(ScalarFloat::integer(anchor[1])).bits;
    o[0x108/4]=(o[0x108/4]|0x10000)&~0x2000u;
    battle.entry.tasks.tasks.at(o[1]-1)[0]=0x16e3b8;
    o[0x128/4]=actor.contactKind252;o[0x12c/4]=unsigned(actor.stateIndex());o[0x130/4]=(actor.flags23c>>4)&1;
    o[0x134/4]=actor.landingCount253;
}
void updateElementHurt(AuxiliaryObjects& objects,BattleRoundState& battle,uint32_t task,
                       const std::array<RoundPlayerRef,2>& players) {
    auto& pools=battle.entry.tasks;
    auto& t=pools.tasks.at(task-1);auto& o=pools.objects.at(t[7]-1);
    const unsigned victim=o[0x118/4]-1;
    const auto& p=players.at(victim);
    const auto& a=p.actor;
    const auto element=o[0x128/4];
    // A second hit can enter the very same damage state. An ice overlay
    // created in the air can also shatter on landing without a state change.
    const bool same=a.landingCount253==o[0x134/4] && a.stateTable()==2 &&
                    unsigned(a.stateIndex())==o[0x12c/4];
    if(same && !(element==5 && o[0x130/4] && touchedGround(p.body,a.queuedActionA3c)))return;
    const int release=elements.at(element).release;
    if(release>=0) {
        const bool flip=battle.random.bounded(2)==0;
        const auto mirror=bool(p.body.timeline.clock().objectFlags&0x80000);
        for(int i=0;i<4;++i) {
            auto* fragment=commonElement(objects,battle,victim,mirror,release+i);
            const auto x=ScalarFloat{o[0x40/4]}.add(ScalarFloat::integer(battle.random.bounded(24)));
            const auto y=ScalarFloat{o[0x44/4]}.add(ScalarFloat::integer(battle.random.bounded(12)));
            if(fragment) {
                (*fragment)[0x40/4]=x.sub(ScalarFloat::integer(12)).bits;
                (*fragment)[0x44/4]=y.sub(ScalarFloat::integer(6)).bits;
                if(flip)(*fragment)[0x38/4]^=0x80000;
            }
        }
    }
    t[0]=0x147540;o[0x108/4]|=0x1000;
}
void presentWeaponClash(ScheduledOpening& effects,BattleRoundState& battle,const ContactEvent& event) {
    spawn(effects,battle,8,event.centerX,event.centerY);
}
void presentContact(ScheduledOpening& effects,BattleRoundState& battle,const ContactEvent& event,const CollisionPlayer& target,
                    unsigned defense,bool chip,bool specialHit,uint32_t sourceState,AuxiliaryObjects& objects) {
    auto& random=battle.random;
    if(defense) {
        // 157318 consumes both draws even when defense 3 suppresses the flash.
        const int x=event.centerX+random.bounded(9)+(target.mirrorX?-28:20);
        const int y=event.centerY+random.bounded(5)-2;
        if(defense==3)return;
        const auto type=event.b.fields.type;
        const unsigned part=type==3?0:type==2?1:2;
        spawn(effects,battle,(chip?38:35)+part,x,y);
        if(chip)spawn(effects,battle,32,x,y);
        return;
    }
    const auto& attack=event.a.fields;
    const auto column=hitColumn(attack.type,random);
    int x=0,y=0;float scale=1;
    if(attack.type==31) {
        // 158070/158098 use their own signed-byte table. This differs from
        // 168ea0's body anchor used by the ice itself and skips both jitter draws.
        constexpr std::array<std::array<int8_t,2>,51> anchors{{
            {-12,56},{-6,56},{-6,48},{-12,64},{-12,64},{-16,72},{12,56},{-16,56},
            {-6,72},{0,56},{-20,72},{-12,64},{-24,64},{-24,72},{-10,64},{-6,64},
            {10,56},{-6,48},{-12,56},{-6,56},{10,56},{10,56},{0,56},{-20,56},
            {-6,56},{-12,64},{-24,64},{-12,64},{10,56},{-16,64},{-10,64},{-20,64},
            {-16,64},{-12,64},{-24,48},{-12,56},{10,80},{-12,72},{-24,64},{-10,32},
            {-20,72},{-12,64},{-6,56},{-24,64},{-12,48},{-18,56},{0,12},{-10,20},
            {-20,56},{0,0},{0,0}
        }};
        const auto offset=target.judgmentProfile<anchors.size() ? anchors[target.judgmentProfile] :
                                                                 std::array<int8_t,2>{0,56};
        x=int(target.x+(target.mirrorX?-offset[0]:offset[0]));y=offset[1];scale=1.2f;
    }else {x=event.centerX+random.bounded(15)-7;y=event.centerY+random.bounded(9)-4;}
    if(attack.remainder && target.objectKind<2) {
        // 1570d4 gives 16e218 the unjittered collision center. Unlike the
        // attached reaction, this ACT keeps its birth position as the victim moves.
        if(auto* o=commonElement(objects,battle,target.owner,target.mirrorX,elements.at(attack.remainder).impact)) {
            (*o)[0x40/4]=ScalarFloat::integer(event.centerX).bits;
            (*o)[0x44/4]=ScalarFloat::integer(event.centerY).bits;
        }
    }
    unsigned descriptor=0;
    if(sourceState==0x260001)descriptor=11;
    else if(attack.group<2) {
        // 4d8a20 has a padding word in each four-word row.
        constexpr unsigned first[]={16,13,19,22};
        descriptor=first[attack.variant]+column;
    } else if(attack.group==2||attack.group==3)descriptor=25+column;
    else if(attack.group==5)descriptor=25;
    else return;
    if(specialHit)spawn(effects,battle,28,x,y,scale);
    spawn(effects,battle,descriptor,x,y,scale);
}
}
