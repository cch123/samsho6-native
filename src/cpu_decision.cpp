#include "cpu_decision.hpp"
#include <algorithm>
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
int rageBand(const StateEntryActor& actor) {
    if(actor.rageState120==3)return 3;
    if(actor.rageState120==1 || actor.rageState120==2)return 2;
    return actor.rageAmount124>=0x5c00;
}
void chooseVariant(StateEntryActor& actor,const StateEntryActor& opponent,const CpuDecisionFrame& frame,
                   const CpuTactics& tactics,GameRandom& random) {
    if(actor.character==19 || actor.character==11) {
        const unsigned mask=actor.character==19?0x800000:0x400000;
        actor.controlCC=actor.controlD0=bool(actor.flags23c&mask);
        return;
    }
    const int table=tactics.characterByte(0x1268+actor.controlCC*16+rageBand(opponent)*4+rageBand(actor));
    if(table<2) {
        // A direct mood row changes only the working column. The previous
        // column remains the input to the next decision at 15be04.
        actor.controlD0=table;
        return;
    }
    const int clock=frame.clockValue;
    const int quarter=clock==-1?random.bounded(4):clock<21?0:clock<48?1:clock<64?2:3;
    const int life=std::min(actor.fieldA30/0x678,7);
    const int advantage=actor.fieldA30>opponent.fieldA30+10?2:actor.fieldA30<opponent.fieldA30-10;
    actor.controlD0=tactics.characterByte(0x128c+actor.controlCC*100+quarter*24+life*3+advantage);
}
bool blocked(const StateEntryActor& a) {
    return (a.controlFlagsB4&3) || a.state194==0x330000 || (a.conditions15c[1]&0x300) ||
           a.controlCounterC0==3 || (a.controlFlagsBC&0x80) ||
           ((a.flags23c&0x800000) && (a.flags23c&0x7c5));
}
bool observeObject(const std::optional<CpuObservedObject>& obj,bool kind3,uint32_t& previous) {
    if(!obj){previous=UINT32_MAX;return false;}
    // A live registration remains latched until a scan sees its slot empty.
    // It does not retrigger just because its command or animation changes.
    if(previous!=UINT32_MAX)return false;
    previous=kind3?obj->moveD4:obj->idD0;
    return true;
}
bool newThreat(StateEntryActor& a,const CpuDecisionFrame& f,bool clearPrevious) {
    if(clearPrevious)a.controlE4=UINT32_MAX;
    if(observeObject(f.kind2,false,a.controlE4)) {
        a.flagsB8|=0x40;
        return true;
    }
    if(clearPrevious)a.controlE8=UINT32_MAX;
    if(observeObject(f.kind3Active?f.kind3:std::nullopt,true,a.controlE8)) {
        a.flagsB8|=0x80;
        return true;
    }
    return false;
}
int decideMode(StateEntryActor& a,const StateEntryActor& enemy,const CpuDecisionFrame& f,GameRandom& rng) {
    const auto mode=a.controlC4;
    if(mode>=6)return 0;
    const bool airborne=(a.conditions15c[1]&0x70) || (a.conditionWord17c&0x40000000);
    const bool busy=blocked(a);
    const bool enemyAttack=enemy.stateTable()==1;
    const bool enemySpecial=enemyAttack && enemy.stateIndex()>=64;
    if(mode!=0) {
        if(!(a.controlFlagsBC&0x44) && !airborne && !busy) {
            if(newThreat(a,f,false))return 3;
            if((a.flagsB8&2) && !(a.flags23c&0x200) && enemySpecial && a.stateTable()==0)return 3;
        }
        if(mode!=4 && !(a.controlFlagsBC&0x48) && !busy && airborne && a.velocityY5c<=0 && a.y<=32) {
            if(a.character!=2 || (a.bodyAction24!=0x255 && a.bodyAction24!=0x256))return 4;
        }
        if(!(a.controlFlagsBC&0x42) && !busy && !airborne && (a.flagsB8&2)) {
            const int wallMargin=a.character==46?8:a.character==47?16:34;
            const int x=ScalarFloat{std::bit_cast<uint32_t>(a.x)}.truncate();
            if(enemyAttack && a.cpuRange16a!=3 && (x<=f.cameraLeft+wallMargin || x>=f.cameraRight-wallMargin)
               && rng.bounded(100)<26)return 5;
            return 2;
        }
        if(mode!=1)return 0;
    }
    if(a.controlFlagsBC&1)return 0;
    if(a.flagsB8&0x20) {
        a.flagsB8&=~0x20u;
        if(a.state194!=0x360000 && a.state194!=0x370000)return newThreat(a,f,true)?3:1;
    }
    if((a.flags23c&0x10) || busy)return 0;
    if(a.cpuPrevious174>a.cpuRange168 && !(enemy.flags23c&0x800000) && enemy.stateTable()==0 &&
       (enemy.stateIndex()==2 || enemy.stateIndex()==23))return 1;
    if(mode!=0)return 0;
    const int previous=std::bit_cast<int32_t>(a.controlTimers0c[0]);
    a.controlTimers0c[0]=std::max(0,std::bit_cast<int32_t>(a.controlTimers0c[0]-unsigned(a.cpuTimerDelta08)));
    return previous<=0 && !airborne?1:0;
}
void classifyThreat(StateEntryActor& a,const StateEntryActor& enemy,const CpuDecisionFrame& f,const CpuTactics& t) {
    const CpuObservedObject* obj=nullptr;
    if((a.flagsB8&0x40) && f.kind2 && f.kind2->moveD4>=0)obj=&*f.kind2;
    else if((a.flagsB8&0x80) && f.kind3 && f.kind3->moveD4>=0)obj=&*f.kind3;
    const int key=obj?(obj->moveD4<32?int(obj->resource14)*32+obj->moveD4:0x600+obj->moveD4):
                      int(enemy.character)*32+enemy.stateIndex()-64;
    a.controlDC=t.specialPattern(key,obj!=nullptr);
    a.cpuRange16e=t.distanceBand(a.controlDC,{std::bit_cast<uint32_t>(a.x)},
                                  {std::bit_cast<uint32_t>(obj?obj->x:enemy.x)});
}
int sequenceRow(const StateEntryActor& a,int mode) {
    switch(mode) {
    case 1:return 0x1350+a.controlD0*0x280+8*(a.cpuSituation180*5+a.cpuRange168);
    case 2:return 0x1850+a.controlD0*0xa00+8*(a.cpuSituation182*5+a.cpuRange16a);
    case 3:return ((a.flags23c&0x1000)?0x2c50:0x3bf0)+4*(a.controlDC*5+a.cpuRange16e);
    case 4:return 0x4b90+8*(a.cpuSituation184*2+a.cpuRange16c);
    case 5:return 0x4c10+8*a.cpuRange170;
    default:throw std::logic_error("Invalid CPU decision mode");
    }
}
}

void observeCpuDistances(StateEntryActor& a,const StateEntryActor& enemy,int distance,const CpuTactics& t) {
    const int base=0x228+int(enemy.character)*8+((a.flags23c&0x1000)?0:0x1a0);
    auto half=[&](int offset) {
        const auto bits=uint16_t(t.characterByte(base+offset)|(unsigned(t.characterByte(base+offset+1))<<8));
        return int(std::bit_cast<int16_t>(bits));
    };
    auto band=[&](int offset) {
        for(int i=0;i<3;++i)if(distance<=half(offset+2*i))return i;
        return 3;
    };
    a.cpuPrevious174=a.cpuRange168;
    a.cpuRange168=band(0);
    a.cpuRange16a=band(0x340);
    a.cpuWall178=distance<=half(6);
    if(a.cpuRange168==0)a.conditionWord17c=1;
    else {
        // The middle fifth of each distance interval is inclusive at both
        // ends. The outermost band has a fixed upper endpoint of 320.
        const int lower=half(2*(a.cpuRange168-1));
        const int upper=a.cpuRange168==3?320:half(2*a.cpuRange168);
        a.conditionWord17c=distance>=(3*lower+2*upper)/5 && distance<=(2*lower+3*upper)/5;
    }
    auto delta=[](float v,float origin) {
        return ScalarFloat{std::bit_cast<uint32_t>(v)}.sub({std::bit_cast<uint32_t>(origin)}).truncate();
    };
    const int dx=delta(enemy.x,a.x),dy=delta(enemy.y,a.y);
    auto inBox=[&](int offset) {
        const int direction=(a.bodyFlags38&0x80000)?-1:1;
        return direction*dx<half(offset) && direction*dx>half(offset+2) && dy<half(offset+4) && dy>half(offset+6);
    };
    a.cpuRange16c=inBox(0x680)?0:inBox(0x9c0)?1:2;
}
void observeCpuSituation(StateEntryActor& a,const StateEntryActor& enemy,const CpuTactics& t,const StateEntryRules& rules) {
    const int table=enemy.stateTable(),index=enemy.stateIndex();
    int approach=255,defense=255;
    a.cpuSituation186=-1;
    if(table>=0 && table<=2) {
        const auto variant=(enemy.flags23c&0x200000)?enemy.aliasCharacter1a8:enemy.stateCharacter198;
        const auto row=rules.descriptor(table,index,enemy.character,variant);
        if(table==0){approach=row[3];defense=row[4];}
        if(table==1) {
            approach=index<64?t.normalAttackSituation(index):row[4];
            defense=row[4];a.cpuSituation186=0;
        }
        if(table==2){approach=row[12];defense=row[13];}
    }
    const int direction=enemy.velocityX50>0?1:enemy.velocityX50<0?2:0;
    a.cpuSituation180=approach==254?4+direction:approach;
    a.cpuSituation182=(defense==253 || defense==254)?14+direction:defense;
    a.cpuSituation184=(enemy.flags23c&0x10)?(table==1?3:2):bool(enemy.flags23c&8);
    a.cpuSituation188=a.cpuSituation18a=0;
}
bool beginCpuSequence(StateEntryActor& a,const InputSystemConfig& config,const CpuDecisionFrame& f,
                      const CpuTactics& t,GameRandom& random,unsigned sequence) {
    bool mistake=false;
    if(f.roundIndex<2 && f.battleMode!=0) {
        const int weight=f.difficulty>=7?0:f.difficulty==6?10:f.difficulty==5?15:f.difficulty==4?20:30;
        // Even maximum difficulty makes the zero-threshold draw. It advances
        // the same generator that later selects the next attack.
        mistake=random.bounded(100)<(2-f.roundIndex)*weight;
    }
    auto& motion=a.controlMotion38;
    const auto bytes=t.sequence(sequence);
    motion={0,sequence,0,UINT32_MAX,UINT32_MAX,bytes[0],bytes[1],bytes[2],bytes[3],0};
    if(mistake) {
        motion[1]=0;motion[5]=255;motion[6]=1+random.bounded(3);motion[7]=1+random.bounded(3);motion[8]=0;
    }
    const bool substitute=config.system==8 || (config.system==6 && config.descriptor &&
        (*config.descriptor)[12]==40 && ((*config.descriptor)[4]==17 || (*config.descriptor)[4]==18));
    if(substitute) {
        const int threshold=a.controlC4==2?90:30;
        for(unsigned i=5;i<9;++i) {
            const auto op=motion[i];
            if(op!=0x36 && op!=0x40 && op!=0x41 && op!=0x44 && op!=0x45)continue;
            if(random.bounded(100)>=threshold)continue;
            const int result=random.bounded(100);
            motion[i]=result<60?0x48:result<90?0x46:0x49;
        }
    }
    motion[3]=motion[5];
    return mistake;
}
bool decideCpuAction(StateEntryActor& a,const StateEntryActor& enemy,const InputSystemConfig& config,
                     const CpuDecisionFrame& f,const CpuTactics& t,GameRandom& rng) {
    const int mode=decideMode(a,enemy,f,rng);
    if(!mode)return false;
    a.controlC4=mode;
    if(mode==3)classifyThreat(a,enemy,f,t);
    if(mode!=1)a.flagsB8&=~0xc2u;
    a.controlTimers0c[0]=0;
    if(mode!=5)chooseVariant(a,enemy,f,t,rng);
    const int category=mode==1?0:mode==2 || mode==4?1:2;
    const auto profile=t.chooseProfile(rng,f.level100,f.difficulty,f.clockValue,category);
    a.controlEC=profile.tierE4;
    a.controlF0=profile.patternE8;
    a.controlFieldF4=std::min(profile.actionEC,mode==3?3:7);
    a.controlF8=profile.variantF0;
    const auto sequence=t.characterByte(sequenceRow(a,mode)+a.controlFieldF4);
    if(beginCpuSequence(a,config,f,t,rng,sequence)){a.control88=0;a.control8c=UINT32_MAX;}
    return true;
}
}
