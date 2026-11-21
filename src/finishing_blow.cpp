#include "finishing_blow.hpp"
#include "collision.hpp"
#include "match_progress.hpp"
#include "state_entry.hpp"
#include "input_bindings.hpp"

namespace ss6 {
namespace {
// 14dac8 derives the category from the attacker's effective state when the
// lethal damage is requested. Recovery-frame hits can outlive the attack.
int actorCategory(const StateEntryActor& a,const InputBindings& bindings) {
    const bool armed=a.flags23c&0x1000;
    if(a.stateTable()!=1)return (a.flags248&0x40000000u)?(armed?2:4):-1;
    const int state=a.stateIndex();
    // 168dc8/168d48 index the same character command table as the input
    // selector. Identical state numbers can award different finish classes.
    if(bindings.specialSecondCategory(a.character,state))return 13;
    if(bindings.specialFirstCategory(a.character,state))return 11;
    if(state>=65)return 10;
    switch(state) {
    case 38:return 12;
    case 39:return 7;
    case 21:return 9;
    case 33:return 6;
    case 22:return 5;
    default:break;
    }
    if(state>=41&&state<55)return 8;
    if(a.flags23c&0x800)return 3;
    if(!armed)return 4;
    const auto flags=a.effectiveFlags();
    return flags&4?2:(flags&2?1:0);
}

int roundOutcome(int category) {
    switch(category) {
    case 13:return 0;
    case 11:return 1;
    case 9:return 2;
    case 12:return 3;
    case 7:case 8:return 4;
    default:return 5;
    }
}

void record(StateEntryActor& source,PlayerMatchStats& stats,const ContactEvent* event,
            bool projectile,bool guard,bool counter,bool captureDamage,const InputBindings& bindings,int projectileCategory,
            bool concentration) {
    // 1576e8 latches the first lethal request even if another hit or throw
    // record arrives before the life commit. That request owns the result.
    if(source.flags244&0x08000000)return;
    const int table=source.stateTable(),state=source.stateIndex();
    // 14dc00 classifies the bird from its own command at impact, even
    // when Nakoruru has moved on to a different body action.
    const int category=projectile?projectileCategory:actorCategory(source,bindings);
    stats.outcome1c=roundOutcome(category);
    stats.outcome20=0;
    if(!projectile&&!captureDamage&&(table!=1||state<64)) {
        stats.outcome20=2;
        if(table==1&&event&&(event->a.fields.group<3||event->a.fields.group==4))stats.outcome20=1;
    }
    if(!(source.flags23c&0x1000))source.flags248|=0x20000;
    if(category==2&&(table!=1||(state!=17&&state!=18&&state!=20&&state!=22)))source.flags248|=0x40000;
    if(category==6)source.flags248|=0x80000;
    if(counter)source.flags248|=0x100000;
    if(concentration)source.flags248|=0x800000; // 15787c
    if(table==1&&state==31)source.flags248|=0x200000;
    if(table==1&&state>=39&&state<55)source.flags248|=0x400000;
    // Local versus mode 3 deliberately has no profile-write side effect
    // from 14e8d8. The two actor flags still feed round-end playback.
    source.flags244|=0x08000000;
    if(guard)source.flags244|=0x10000000;
}
}
int contactFinishCategory(const StateEntryActor& a,const InputBindings& bindings){return actorCategory(a,bindings);}
int projectileFinishCategory(const AuxiliaryObject& object,const StateEntryActor& owner,const StateEntryActor& opponent,
                             const InputBindings& bindings) {
    const auto kind=object[0xcc/4];
    if(kind==5)return 14;
    if(kind==3) {
        // 14dc00 reads the companion command at impact. Profile 4 can
        // finish its technique after the opponent has entered the paired pose.
        const auto profile=object[0x18/4];
        if(profile==1||profile==45)return object[0x128/4]==7?11:10;
        if(profile==4) {
            if(object[0x24/4]==810||opponent.stateIndex()==87)return 13;
            if(bindings.specialFirstCategory(owner.character,owner.stateIndex()))return 11;
        }
        return 10;
    }
    if(kind!=2)return 10;
    const auto id=object[0xd0/4];
    if(id>=65&&id<=73)return int((id-65)%3);
    if(id>=85&&id<=94)return 13;
    switch(id) {
    case 9:case 20:case 23:case 29:case 37:case 123:case 132:case 134:
    case 178:case 181:case 182:return 13;
    case 26:case 28:case 35:case 52:case 55:case 95:case 96:case 99:case 135:
    case 138:case 142:case 149:case 150:case 156:case 162:case 163:case 164:
    case 169:case 180:return 11;
    case 104:case 105:return 1;
    case 106:case 107:case 108:return 2;
    case 188:return 4;
    default:return 10;
    }
}
bool isCounterContact(const StateEntryActor& target,const PlayerMatchStats& sourceStats,const ContactEvent& event) {
    return (event.b.fields.low7&1)||
           ((target.flags240&1)&&sourceStats.hitCount0c==0&&target.stateTable()!=2);
}
void recordContactFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& stats,
                         const ContactEvent& event,bool projectile,bool guarded,bool counter,const InputBindings& bindings,int projectileCategory,
                         bool concentration) {
    if(target.pendingDamageA38>=target.fieldA30)
        record(source,stats,&event,projectile,guarded,!guarded&&counter,false,bindings,projectileCategory,concentration);
}
void recordScriptFinish(StateEntryActor& source,const StateEntryActor& target,PlayerMatchStats& stats,
                        bool projectile,bool captureDamage,const InputBindings& bindings,int projectileCategory,bool concentration) {
    // 1413d8 checks the KO bit before its pending-life test. 1575d0 only
    // compares pending damage, so these entry conditions remain separate.
    if(!(target.flags23c&0x80)&&target.pendingDamageA38>=target.fieldA30)
        record(source,stats,nullptr,projectile,false,false,captureDamage,bindings,projectileCategory,concentration);
}
}
