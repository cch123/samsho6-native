#include "input_lifecycle.hpp"
#include "input_routes.hpp"
#include "human_input.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
ss6::InputFeatures features() {
    ss6::InputFeatures f{};unsigned count;std::cin>>count;
    for(unsigned i=0;i<count;++i){unsigned at;uint32_t value;std::cin>>at>>value;f.at(at)=value;}
    return f;
}
ss6::ActorCommandInput readInput() {
    ss6::ActorCommandInput in;std::cin>>in.enabled>>in.specialStart>>in.specialCount;
    in.sampledFeatures=features();
    for(auto& v:in.specialPriority){unsigned n;std::cin>>n;v=uint8_t(n);}
    for(unsigned kind=0;kind<2;++kind) {
        const auto slots=kind?std::span<ss6::CommandSlot>(in.special):std::span<ss6::CommandSlot>(in.normal);
        for(auto& s:slots) {
            unsigned step,elapsed,charge,buffer;
            std::cin>>s.definition>>s.alternateDirections>>s.recognized>>s.cancelAllowed>>step>>elapsed>>charge>>buffer;
            s.progress={uint8_t(step),uint8_t(elapsed),uint16_t(charge),uint8_t(buffer)};
        }
    }
    return in;
}
void printInput(const ss6::ActorCommandInput& in) {
    std::cout<<' '<<in.enabled<<' '<<in.specialStart<<' '<<in.specialCount;
    for(auto v:in.sampledFeatures)std::cout<<' '<<v;
    for(auto v:in.specialPriority)std::cout<<' '<<unsigned(v);
    for(unsigned kind=0;kind<2;++kind) {
        const auto slots=kind?std::span<const ss6::CommandSlot>(in.special):std::span<const ss6::CommandSlot>(in.normal);
        for(const auto& s:slots)std::cout<<' '<<s.definition<<' '<<s.alternateDirections<<' '<<s.recognized<<' '<<s.cancelAllowed
            <<' '<<unsigned(s.progress.step)<<' '<<unsigned(s.progress.elapsed)<<' '<<s.progress.charge<<' '<<unsigned(s.progress.buffered);
    }
}
ss6::InputSampler readSampler() {
    ss6::InputSampler s;s.features=features();
    for(auto& p:s.pressLatches)for(auto& v:p){unsigned n;std::cin>>n;v=uint8_t(n);}
    unsigned seed;std::cin>>seed;
    for(unsigned i=0;i<600;++i){s.replayHeld[i]=uint16_t(seed+i*137);s.replayPressed[i]=uint16_t(seed^(i*7919));}
    return s;
}
void printSampler(const ss6::InputSampler& s) {
    for(auto v:s.features)std::cout<<' '<<v;
    for(const auto& p:s.pressLatches)for(auto v:p)std::cout<<' '<<unsigned(v);
    for(const auto* array:{&s.replayHeld,&s.replayPressed})for(auto v:*array)std::cout<<' '<<v;
}
ss6::PermissionActor readActor() {
    ss6::PermissionActor a;unsigned lock,level;
    std::cin>>a.character>>a.flags23c>>a.flags240>>lock>>a.controlKindA20>>a.controlModeC8>>a.state194>>a.bodyFlags38>>a.timerDelta>>level;
    a.flags24c=uint8_t(lock);a.characterBytesF14[4]=uint8_t(level);
    for(auto& v:a.timers)std::cin>>v;
    return a;
}
void printActor(const ss6::PermissionActor& a) {
    std::cout<<' '<<unsigned(a.characterBytesF14[4]);for(auto v:a.timers)std::cout<<' '<<v;
}
void printRequests(const ss6::PermissionActor& a,const ss6::PermissionContext& p,const ss6::SystemCancelContext& c) {
    std::cout<<' '<<a.request18c<<' '<<a.pendingTable<<' '<<a.pendingIndex<<' '<<a.aliasRequest19c<<' '<<a.aliasPendingTable<<' '<<a.aliasPendingIndex
        <<' '<<a.flags23c<<' '<<a.flags244<<' '<<a.flags248<<' '<<a.bodyFlags38<<' '<<a.bodyFlags104<<' '<<a.bodyState128<<' '<<a.variantA48
        <<' '<<a.controlFlagsB4<<' '<<a.auxiliaryFlag134<<' '<<a.auxiliaryTimer130<<' '<<a.auxiliaryFrameC0<<' '<<a.auxiliaryPendingC4<<' '<<a.auxiliaryFlags104<<' '<<unsigned(a.pendingCharacter254);
    for(auto v:a.characterBytesF14)std::cout<<' '<<unsigned(v);
    std::cout<<' '<<p.condition74Diagnostics<<' '<<c.diagnostics;
}
ss6::ActorInputSampling readFrame() {
    ss6::ActorInputSampling f;std::cin>>f.player>>f.expectedFacing>>f.replayIndex>>f.gameMode>>f.battleState>>f.battleField18>>f.opponentSamplingAllowed;return f;
}
void readPads(std::array<ss6::NormalizedPadSample,2>& pads,std::array<ss6::InputMapping,2>& maps) {
    for(unsigned i=0;i<2;++i) {
        std::cin>>pads[i].held>>pads[i].pressed;
        for(auto* array:{&maps[i].normal,&maps[i].mode6})for(auto& v:*array)std::cin>>v;
    }
}
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)throw std::runtime_error("Expected assets directory");
    ss6::CommandInput commands(argv[1]);ss6::HumanInputPipeline human(argv[1]);std::string op;
    while(std::cin>>op) {
        if(op=="clear") {
            unsigned kind,player;std::cin>>kind>>player;auto in=readInput();auto sampler=readSampler();
            if(kind==0)in.clearBuffers();else if(kind==1)in.clearPublished();else sampler.clearPressLatches(player);
            std::cout<<0;printInput(in);printSampler(sampler);
        } else if(op=="charge") {
            auto a=readActor();ss6::ActorCommandInput in;int32_t state,field;
            std::cin>>in.sampledFeatures[46]>>state>>field;ss6::updateCharacterCharge(a,in,state,field);
            std::cout<<0;printActor(a);
        } else if(op=="sample"||op=="tail"||op=="requests") {
            auto a=readActor();auto f=readFrame();std::array<ss6::NormalizedPadSample,2> pads;std::array<ss6::InputMapping,2> maps;readPads(pads,maps);
            if(op=="tail") {
                ss6::finishActorInput(a,f,pads,maps);std::cout<<f.replayIndex;printActor(a);
            } else {
                ss6::PermissionActor opponent;std::cin>>opponent.flags23c;auto in=readInput();auto sampler=readSampler();
                auto route=ss6::ActorInputRoute::HumanSuppressed;
                int locked=int(ss6::inputRequestsLocked(a));
                ss6::PermissionContext permissionContext;ss6::SystemCancelContext cancel;
                if(op=="requests") {
                    ss6::InputSystemConfig config;config.character=a.character;std::cin>>config.system;
                    std::array<uint8_t,16> d;for(auto& v:d){unsigned n;std::cin>>n;v=uint8_t(n);}if(config.system==6)config.descriptor=d;
                    permissionContext.mode4c3808=3;permissionContext.stageObjectX=160;
                    ss6::SelectionThreat threat;threat.distance=300;
                    cancel.pad=pads.at(f.player);cancel.mapping=maps.at(f.player);
                    cancel.controlOwner=&a;cancel.controlInput=&in;cancel.controlConfig=&config;
                    route=human.requests(a,opponent,in,sampler,f,pads,maps,config,permissionContext,threat,cancel);
                } else route=ss6::sampleActorInput(a,opponent,in,sampler,commands,f,pads,maps);
                if(route==ss6::ActorInputRoute::AiRequired)locked=-1;
                std::cout<<unsigned(route)<<' '<<locked;printActor(a);
                if(op=="requests")printRequests(a,permissionContext,cancel);
                printInput(in);printSampler(sampler);
            }
        } else throw std::runtime_error("Unknown input lifecycle operation");
        if(!std::cin)throw std::runtime_error("Incomplete input lifecycle fixture");
        std::cout<<'\n';
    }
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
