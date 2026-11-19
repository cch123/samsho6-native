#include "input_permissions.hpp"
#include "special_requests.hpp"
#include "input_routes.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
ss6::PermissionActor actor() {
    ss6::PermissionActor a;unsigned flags,alias;
    std::cin>>a.flags23c>>a.flags244>>a.flags248>>a.state194>>a.state1a4>>a.character>>flags>>alias
        >>a.bodyFlags38>>a.bodyFlags104>>a.bodyFlags108>>a.bodyAction24>>a.bodyState128
        >>a.auxiliaryAction24>>a.auxiliaryState128>>a.auxiliaryState12c>>a.sampledButton9
        >>a.rageState120>>a.rageAmount124>>a.systemState13c>>a.systemMeter158>>a.fieldA30>>a.x>>a.y;
    a.stateFlags19a=uint8_t(flags);a.aliasFlags1aa=uint8_t(alias);
    for(auto& v:a.timers)std::cin>>v;
    for(auto& v:a.characterBytesF14){unsigned n;std::cin>>n;v=uint8_t(n);}
    return a;
}
template<size_t N>void objects(std::array<std::optional<ss6::PermissionObject>,N>& out) {
    unsigned count;std::cin>>count;
    for(unsigned i=0;i<count;++i){unsigned slot;ss6::PermissionObject o;std::cin>>slot>>o.kind>>o.subtype>>o.action>>o.flags108>>o.x;out.at(slot)=o;}
}
ss6::PermissionContext context() {
    ss6::PermissionContext c;std::cin>>c.mode4c3808>>c.stageObjectIndex>>c.stageObjectX;objects(c.ownObjects);objects(c.battleObjects);return c;
}
ss6::InputSystemConfig config() {
    ss6::InputSystemConfig c;std::array<uint8_t,16> d;
    std::cin>>c.system>>c.character;for(auto& v:d){unsigned n;std::cin>>n;v=uint8_t(n);}if(c.system==6)c.descriptor=d;return c;
}
void effects(const ss6::PermissionActor& a,const ss6::PermissionContext& c){
    std::cout<<a.flags244<<' '<<a.bodyState128<<' '<<c.condition74Diagnostics;
    for(auto v:a.timers)std::cout<<' '<<v;
}
void extra(ss6::PermissionActor& a) {
    std::cin>>a.velocityX50>>a.velocityY5c>>a.auxiliaryFlags104>>a.auxiliaryFlag134>>a.auxiliaryX>>a.auxiliaryY>>a.timerDelta;
}
ss6::ActorCommandInput input(uint32_t seed) {
    ss6::ActorCommandInput input;std::cin>>input.enabled>>input.specialStart>>input.specialCount;
    for(unsigned i=0;i<171;++i)input.sampledFeatures[i]=seed+i;
    for(unsigned i=0;i<32;++i)input.specialPriority[i]=uint8_t(i+seed);
    for(unsigned kind=0;kind<2;++kind) {
        auto slots=kind?std::span<ss6::CommandSlot>(input.special):std::span<ss6::CommandSlot>(input.normal);
        for(unsigned i=0;i<slots.size();++i) {
            auto& s=slots[i];const auto n=seed+i;
            s.definition=int16_t(i);s.alternateDirections=i%2;
            s.progress={uint8_t(n%14),uint8_t(n),uint16_t(n),uint8_t(n%11)};
            std::cin>>s.recognized;
        }
    }
    for(auto& slot:input.special)std::cin>>slot.cancelAllowed;
    return input;
}
void preserved(const ss6::ActorCommandInput& a,const ss6::ActorCommandInput& before) {
    if(a.enabled!=before.enabled||a.specialStart!=before.specialStart||a.specialCount!=before.specialCount||a.specialPriority!=before.specialPriority||a.sampledFeatures!=before.sampledFeatures)
        throw std::runtime_error("Permission stage changed input metadata");
    for(unsigned kind=0;kind<2;++kind) {
        const auto slots=kind?std::span<const ss6::CommandSlot>(a.special):std::span<const ss6::CommandSlot>(a.normal);
        const auto old=kind?std::span<const ss6::CommandSlot>(before.special):std::span<const ss6::CommandSlot>(before.normal);
        for(unsigned i=0;i<slots.size();++i) {
            const auto& s=slots[i];const auto& o=old[i];
            if(s.definition!=o.definition||s.alternateDirections!=o.alternateDirections||s.progress.step!=o.progress.step||s.progress.elapsed!=o.progress.elapsed||s.progress.charge!=o.progress.charge||s.progress.buffered!=o.progress.buffered)
                throw std::runtime_error("Permission stage changed command progress");
        }
    }
}
void routeExtra(ss6::PermissionActor& a) {
    std::cin>>a.flags240>>a.controlKindA20>>a.controlModeC8>>a.controlFlagsB4>>a.aliasRequest19c>>a.aliasPendingTable>>a.aliasPendingIndex
        >>a.offsetX4c>>a.accelerationX54>>a.offsetY58>>a.accelerationY60>>a.request18c>>a.pendingTable>>a.pendingIndex>>a.variantA48>>a.bodyPendingFE;
    unsigned flags;std::cin>>flags;a.flags24c=uint8_t(flags);
    unsigned character;std::cin>>a.auxiliaryTimer130>>a.auxiliaryFrameC0>>a.auxiliaryPendingC4>>character;a.pendingCharacter254=uint8_t(character);
}
ss6::ActorCommandInput routeInput() {
    ss6::ActorCommandInput in;std::cin>>in.specialCount;
    for(auto& v:in.specialPriority){unsigned n;std::cin>>n;v=uint8_t(n);}
    for(auto& s:in.normal)std::cin>>s.recognized;
    for(auto& s:in.special)std::cin>>s.recognized;
    for(auto& s:in.special)std::cin>>s.cancelAllowed;
    unsigned count;std::cin>>count;
    for(unsigned i=0;i<count;++i){unsigned at;uint32_t value;std::cin>>at>>value;in.sampledFeatures.at(at)=value;}
    return in;
}
void routeState(const ss6::PermissionActor& a) {
    std::cout<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '<<a.aliasRequest19c<<' '<<a.aliasPendingTable<<' '<<a.aliasPendingIndex
        <<' '<<a.flags244<<' '<<a.flags248<<' '<<a.bodyFlags38<<' '<<a.bodyFlags104<<' '<<a.controlFlagsB4<<' '<<a.variantA48;
    for(auto v:{a.offsetX4c,a.velocityX50,a.accelerationX54,a.offsetY58,a.velocityY5c,a.accelerationY60})std::cout<<' '<<v;
    for(auto v:a.timers)std::cout<<' '<<v;
    for(auto v:a.characterBytesF14)std::cout<<' '<<unsigned(v);
    std::cout<<' '<<a.auxiliaryFlag134<<' '<<a.auxiliaryTimer130<<' '<<a.auxiliaryFrameC0<<' '<<a.auxiliaryPendingC4<<' '<<a.auxiliaryFlags104<<' '<<unsigned(a.pendingCharacter254);
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::InputPermissions permissions(argv[1]);ss6::InputBindings bindings(argv[1]);ss6::ActionSelection actions(argv[1]);std::string op;
    while(std::cin>>op) {
        if(op=="route") {
            unsigned kind;std::cin>>kind;auto a=actor();extra(a);routeExtra(a);auto opponent=actor();extra(opponent);routeExtra(opponent);
            a.opponentX=opponent.x;opponent.opponentX=a.x;auto system=config(),otherSystem=config();auto in=routeInput(),otherIn=routeInput();
            ss6::SelectionThreat threat;std::cin>>threat.distance;unsigned objectCount;std::cin>>objectCount;
            for(unsigned i=0;i<objectCount;++i){unsigned slot;int objectKind;std::cin>>slot>>objectKind;threat.opponentObjectKinds.at(slot)=objectKind;}
            ss6::SystemCancelContext c;unsigned owner;std::cin>>owner>>c.pad.pressed>>c.mapping.normal[4];
            c.controlOwner=owner?&opponent:&a;c.controlInput=owner?&otherIn:&in;c.controlConfig=owner?&otherSystem:&system;
            ss6::InputSampler sampler;
            if(kind==7) {
                for(unsigned i=0;i<2;++i)for(unsigned j=0;j<6;++j)sampler.pressLatches[i][j]=uint8_t(1+i*6+j);
                for(auto& s:in.normal)s.progress={0xa5,0xa5,0xa5a5,0xa5};
                for(auto& s:in.special)s.progress={0xa5,0xa5,0xa5a5,0xa5};
            }
            int result=-1;
            if(kind==0)result=ss6::requestSystemCancel(a,in,system,actions,c);
            else if(kind==1)ss6::filterCharacterSpecials(a,in);
            else if(kind==2)ss6::requestAliasFallback(a,in);
            else if(kind==3)result=ss6::requestAlternate(a,opponent,in,system,bindings,actions,threat);
            else if(kind==4)ss6::dispatchInputRequests(a,opponent,in,system,bindings,actions,threat,c);
            else if(kind==5)result=ss6::requestForcedState(a,in,system);
            else if(kind==7) {
                int32_t battleState;std::cin>>battleState;
                ss6::requestLockedInput(a,opponent,in,sampler,owner,battleState,system,actions,threat);
            }
            else {
                ss6::ActorCommandInput bound;bindings.initialize(bound,&system);in.specialStart=bound.specialStart;
                ss6::PermissionContext permissionsContext;permissionsContext.mode4c3808=3;permissionsContext.stageObjectX=160;
                ss6::processRecognizedInput(a,opponent,in,system,bindings,permissions,actions,permissionsContext,threat,c);
                result=int(permissionsContext.condition74Diagnostics);
            }
            std::cout<<result<<' '<<c.diagnostics;routeState(a);
            for(const auto& s:in.normal)std::cout<<' '<<s.recognized;
            for(const auto& s:in.special)std::cout<<' '<<s.recognized;
            for(const auto& s:in.special)std::cout<<' '<<s.cancelAllowed;
            for(const auto& s:otherIn.normal)std::cout<<' '<<s.recognized;
            if(kind==7) {
                std::cout<<' '<<a.flags23c;
                for(const auto& s:in.normal)std::cout<<' '<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered);
                for(const auto& s:in.special)std::cout<<' '<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered);
                for(const auto& player:sampler.pressLatches)for(auto v:player)std::cout<<' '<<unsigned(v);
            }
            std::cout<<'\n';
        } else if(op=="request") {
            unsigned kind;std::cin>>kind;auto a=actor();extra(a);auto system=config();ss6::ActorCommandInput in;
            std::cin>>in.specialCount;
            for(auto& v:in.specialPriority){unsigned n;std::cin>>n;v=uint8_t(n);}
            for(auto& s:in.special)std::cin>>s.recognized;
            for(auto& s:in.special)std::cin>>s.cancelAllowed;
            std::cin>>a.request18c>>a.pendingTable>>a.pendingIndex;
            const bool result=kind==0?ss6::requestSpecial(a,in):kind==1?ss6::requestSpecialCancel(a,in,system,bindings):ss6::requestDamageSpecial(a,in);
            std::cout<<result<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '<<a.flags244<<' '<<a.flags248<<' '<<a.bodyFlags38;
            for(auto v:a.characterBytesF14)std::cout<<' '<<unsigned(v);
            std::cout<<'\n';
        } else if(op=="sqrt") {
            uint32_t bits;std::cin>>bits;std::cout<<ss6::ScalarFloat{bits}.sqrt().bits<<'\n';
        } else if(op=="category"||op=="requirement"||op=="cancel") {
            unsigned id;std::cin>>id;auto a=actor();extra(a);bool result;
            if(op=="category")result=permissions.category(id,a);
            else if(op=="requirement")result=permissions.requirement(id,a);
            else {int start;std::cin>>start;result=permissions.cancelAllowed(id,a,start,bindings);}
            std::cout<<result<<' '<<a.auxiliaryFlags104;
            for(auto v:a.timers)std::cout<<' '<<v;
            std::cout<<'\n';
        } else if(op=="apply") {
            auto a=actor();extra(a);auto opponent=actor();extra(opponent);auto system=config();auto c=context();uint32_t seed;std::cin>>seed;
            auto in=input(seed);in.sampledFeatures[9]=a.sampledButton9;const auto before=in;
            permissions.apply(a,opponent,system,c,in,bindings);preserved(in,before);
            effects(a,c);std::cout<<' '<<a.auxiliaryFlags104;
            for(const auto& s:in.normal)std::cout<<' '<<s.recognized;
            for(const auto& s:in.special)std::cout<<' '<<s.recognized;
            for(const auto& s:in.special)std::cout<<' '<<s.cancelAllowed;
            std::cout<<'\n';
        } else if(op=="available") {
            unsigned key;std::cin>>key;auto c=context();std::cout<<ss6::InputPermissions::objectAvailable(key,c)<<'\n';
        } else if(op=="condition"||op=="filter") {
            unsigned id;std::cin>>id;auto a=actor(),opponent=actor();auto system=config();auto c=context();
            if(op=="condition") {
                std::cout<<permissions.condition(id,a,opponent,system,c)<<' ';effects(a,c);std::cout<<'\n';
            } else {
                unsigned start,count;std::cin>>start>>count;
                const auto records=id?std::span<const ss6::InputBindingRecord>(bindings.specialRecords()):std::span<const ss6::InputBindingRecord>(bindings.normalRecords());
                if(start>records.size()||count>records.size()-start)throw std::runtime_error("Invalid permission record range");
                std::array<uint32_t,13> categories;std::array<uint32_t,9> requirements;
                for(auto& v:categories)std::cin>>v;for(auto& v:requirements)std::cin>>v;
                std::vector<ss6::CommandSlot> slots(count);
                for(auto& slot:slots)std::cin>>slot.recognized;
                permissions.filter(a,opponent,system,c,slots,records.subspan(start,count),categories,requirements);
                effects(a,c);for(const auto& slot:slots)std::cout<<' '<<slot.recognized;std::cout<<'\n';
            }
        } else throw std::runtime_error("Unknown input permission operation");
        if(!std::cin)throw std::runtime_error("Incomplete input permission fixture");
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
