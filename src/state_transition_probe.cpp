#include "state_entry.hpp"
#include <bit>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace {
//The fixture codec describes memory fields, not transition rules. Python
//compares these fields and also checks that unrepresented bytes stay intact.
template<class F>void fields(ss6::StateEntryActor& a,ss6::ActorCommandInput& input,F f) {
#define A(off,member) f('a',off,a.member,#member)
#define B(off,member) f('b',off,a.member,#member)
#define X(off,member) f('x',off,a.member,#member)
    A(0x23c,flags23c);A(0x244,flags244);A(0x248,flags248);
    A(0xa10,character);A(0xa18,damageCharacterA18);
    A(0x194,state194);A(0x1a4,state1a4);A(0x198,stateCharacter198);A(0x1a8,aliasCharacter1a8);
    A(0x19a,stateFlags19a);A(0x1aa,aliasFlags1aa);
    A(0x18c,request18c);A(0x190,pendingTable);A(0x192,pendingIndex);
    A(0x19c,aliasRequest19c);A(0x1a0,aliasPendingTable);A(0x1a2,aliasPendingIndex);
    A(0x1ac,timerDelta);A(0xc0,controlCounterC0);A(0xa2c,fieldA2c);A(0xf10,fieldF10);A(0x252,contactKind252);
    A(0x120,rageState120);A(0x124,rageAmount124);A(0x128,rageDecay128);
    A(0x130,swordWait130);A(0x134,swordCurrent134);A(0x138,swordMaximum138);
    A(0x13c,systemState13c);A(0x144,systemTime144);A(0x14c,bonusState14c);A(0x150,bonusTime150);A(0x154,bonusRate154);A(0x158,systemMeter158);
    B(0x104,bodyFlags104);B(0x108,bodyFlags108);B(0xfe,bodyPendingFE);
    B(0xe4,bodyFieldE4);B(0xe8,bodyFieldE8);B(0x124,bodyField124);B(0x44,y);
    B(0x4c,offsetX4c);B(0x50,velocityX50);B(0x54,accelerationX54);
    B(0x58,offsetY58);B(0x5c,velocityY5c);B(0x60,accelerationY60);
    X(0x128,auxiliaryState128);X(0x24,auxiliaryAction24);X(0xc4,auxiliaryPendingC4);
    X(0xc0,auxiliaryFrameC0);X(0x104,auxiliaryFlags104);
    for(unsigned i=0;i<a.timers.size();++i)A(0x1b0+4*i,timers[i]);
    for(unsigned i=0;i<a.callbacks260.size();++i)A(0x260+4*i,callbacks260[i]);
    for(unsigned i=0;i<a.override27c.size();++i)A(0x27c+4*i,override27c[i]);
    for(unsigned i=0;i<a.registry28c.size();++i)A(0x28c+4*i,registry28c[i]);
    for(unsigned i=0;i<a.conditions15c.size();++i)A(0x15c+4*i,conditions15c[i]);
    for(unsigned i=0;i<a.characterBytesF14.size();++i)A(0xf14+i,characterBytesF14[i]);
    for(unsigned i=0;i<input.sampledFeatures.size();++i)f('a',0x2c4+4*i,input.sampledFeatures[i],"feature");
    for(unsigned bank=0;bank<2;++bank)for(unsigned i=0;i<(bank?32u:31u);++i) {
        auto& slot=bank?input.special[i]:input.normal[i];const unsigned base=0x2c4+(bank?0x684:0x502)+6*i;
        f('a',base,slot.progress.step,"step");f('a',base+1,slot.progress.elapsed,"elapsed");
        f('a',base+2,slot.progress.charge,"charge");f('a',base+4,slot.progress.buffered,"buffered");
        f('a',0x2c4+(bank?0x328:0x2ac)+4*i,slot.recognized,"recognized");
        if(bank)f('a',0x2c4+0x3a8+4*i,slot.cancelAllowed,"cancelAllowed");
    }
#undef A
#undef B
#undef X
}
uint64_t hash(const auto& rows) {
    uint64_t h=14695981039346656037ull;
    for(const auto& row:rows)for(uint32_t word:row)for(unsigned j=0;j<4;++j) {
        h^=(word>>(8*j))&255;h*=1099511628211ull;
    }
    return h;
}
uint32_t readWord(){uint32_t v;if(!(std::cin>>v))throw std::runtime_error("Incomplete transition fixture");return v;}
template<class T>void readValue(T& v) {
    const auto bits=readWord();
    if constexpr(std::is_same_v<T,float>)v=std::bit_cast<float>(bits);
    else if constexpr(std::is_signed_v<T>)v=std::bit_cast<T>(static_cast<std::make_unsigned_t<T>>(bits));
    else v=static_cast<T>(bits);
}
template<class T>uint32_t bits(T v) {
    if constexpr(std::is_same_v<T,float>)return std::bit_cast<uint32_t>(v);
    else return static_cast<std::make_unsigned_t<T>>(v);
}
void readPools(ss6::TaggedTaskPools& p) {
    p.freedStacks=readWord();p.freeObjectHead=readWord();p.freeObjectCount=readWord();
    const auto nt=readWord();for(unsigned i=0;i<nt;++i) {
        auto& row=p.tasks.at(readWord());for(auto& v:row)v=readWord();
    }
    const auto no=readWord();for(unsigned i=0;i<no;++i) {
        auto& row=p.objects.at(readWord());for(auto& v:row)v=readWord();
    }
    const auto ns=readWord();for(unsigned i=0;i<ns;++i) {
        const auto handle=readWord(),flags=readWord(),value=readWord();p.stacks[handle]={flags,value};
    }
}
void writePools(const ss6::TaggedTaskPools& p) {
    std::cout<<' '<<p.freedStacks<<' '<<p.freeObjectHead<<' '<<p.freeObjectCount<<' '<<hash(p.tasks)<<' '<<hash(p.objects);
    for(const auto& [handle,header]:p.stacks)std::cout<<' '<<handle<<' '<<header.flags<<' '<<header.value;
    std::cout<<' '<<p.stackDiagnostics.size();for(auto handle:p.stackDiagnostics)std::cout<<' '<<handle;
}
}
int main(int argc,char** argv) {
 try {
    if(argc<2)throw std::runtime_error("Expected assets or --layout");
    if(std::string(argv[1])=="--layout") {
        ss6::StateEntryActor a;ss6::ActorCommandInput input;
        fields(a,input,[](char area,unsigned offset,auto& v,const char* name){std::cout<<area<<' '<<offset<<' '<<sizeof(v)<<' '<<name<<'\n';});return 0;
    }
    const ss6::StateEntryRules rules(argv[1]);unsigned op;
    while(std::cin>>op) {
        const auto table=readWord(),index=readWord(),character=readWord(),variant=readWord();
        if(op==0) {
            for(auto v:rules.descriptor(table,index,character,variant))std::cout<<unsigned(v)<<' ';
        } else if(op==1)std::cout<<rules.attackWindow(character,index);
        else {
            ss6::StateEntryActor a;ss6::ActorCommandInput input;ss6::StateEntryContext context;ss6::InputSystemConfig config;
            context.player=readWord();context.opponentFlagsB8=readWord();context.linkedObjectFlags108=readWord();context.attackMarker12d2300=readWord();
            config.system=readWord();std::array<uint8_t,16>d;for(auto& v:d)v=uint8_t(readWord());config.descriptor=d;
            fields(a,input,[](char,unsigned,auto& v,const char*){readValue(v);});config.character=a.character;
            readPools(context.tasks);
            if(op==2)rules.pose(a,index);
            else if(op==3)rules.conditions(a,context,index);
            else if(op==4)rules.enter(a,input,config,context,table,index);
            else if(op==5)rules.transition(a,input,config,context);
            else if(op==6)context.tasks.cancelTasks(index);
            else if(op==7)context.tasks.cancelObjects(index);
            else if(op==8)context.tasks.clearDisplay(index,context.player);
            else if(op==9)rules.transitionAlias(a,input,config,context);
            else if(op==10)rules.updateMetadata(a,context);
            else throw std::runtime_error("Unknown transition operation");
            std::cout<<context.opponentFlagsB8<<' '<<*context.linkedObjectFlags108<<' '<<context.attackMarker12d2300;
            fields(a,input,[](char,unsigned,auto& v,const char*){std::cout<<' '<<bits(v);});writePools(context.tasks);
        }
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
