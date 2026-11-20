#include "mamahaha.hpp"
#include "companion_motion.hpp"
#include "stage_camera.hpp"
#include "state_entry.hpp"
#include <bit>
#include <stdexcept>

namespace ss6 {
namespace {
using F=ScalarFloat;
using Object=AuxiliaryObject;
constexpr uint32_t mirror=0x80000,finished=0x100000;
F f(float v){return {std::bit_cast<uint32_t>(v)};}
void face(Object& o,bool left) {o[0x38/4]=(o[0x38/4]&~mirror)|(left?mirror:0);}
void copyFacing(Object& o,const Object& parent){face(o,parent[0x38/4]&mirror);}
F signedOffset(const Object& parent,F offset) {
    return parent[0x38/4]&mirror?F{parent[0x40/4]}.sub(offset):F{parent[0x40/4]}.add(offset);
}
F distance(F x,F y) {return x.mul(x).add(y.mul(y)).sqrt();}
bool ready(const Object& bird) {return bird[0xc0/4]&&!(bird[0x104/4]&1);}

// 1a39b8 steers in the object's local facing. Within the dead zone the
// object's existing facing is retained, including when the target crosses it.
int follow(Object& o,const Object& body) {
    const unsigned command=o[0x128/4];
    F x=signedOffset(body,command==13?F{o[0xf4/4]}:f(-50));
    F y=F{body[0x44/4]}.add(command==13?F{o[0xf8/4]}:f(120));
    const F dx=x.sub({o[0x40/4]}),dy=y.sub({o[0x44/4]});
    const auto length=distance(dx,dy);
    if((command<6||command==13)&&steerCompanion(o,x,dx,dy,length,{f(0.07f),f(24),f(0.8f),f(24)}))
        copyFacing(o,body);
    return length.truncate();
}
bool enter(AuxiliaryObjects& objects,Object& o,const Object& body,const StateEntryActor& owner,bool finalWin) {
    unsigned cmd=o[0x128/4];const unsigned previous=o[0x12c/4];
    if(cmd==previous)return false;
    o[0x104/4]&=~0x400002u;
    const bool armed=owner.flags23c&0x1000;
    auto request=[&](unsigned act){objects.request(o,act,false,false);};
    auto perch=[&](float x,float y,unsigned act){
        cmd=13;o[0xf4/4]=f(x).bits;o[0xf8/4]=f(y).bits;o[0x134/4]=act;
    };
    switch(cmd) {
    case 0:request(769);break;
    case 1:request(771);break;
    case 2:request(774);break;
    case 3:request(772);break;
    case 4:request(773);break;
    case 5:request(775);break;
    case 6:copyFacing(o,body);request(776+o[0x130/4]);break;
    case 7:copyFacing(o,body);o[0x104/4]&=~0x800000u;request(779);break;
    case 8: // 1ed900: Purple Nakoruru's body (resource 42) or character 45 is ready at once, command 0
        if(body[0x14/4]==42||owner.character==45){o[0x108/4]|=finished;cmd=0;break;}
        o[0x40/4]=body[0x40/4];o[0x44/4]=body[0x44/4];copyFacing(o,body);request(786);break;
    case 9: // 1ed960: for resource 42 the winner's HP test is inverted
        if(!armed||(finalWin&&((body[0x14/4]==42)==(owner.fieldA30>=100)))){o[0x108/4]|=finished;cmd=previous;}
        else if(finalWin)perch(40,64,781);
        else perch(-41,76,780);
        break;
    case 10:perch(-35,76,armed?782:783);break;
    case 11:perch(-72,24,787);break;
    case 12:perch(-13,20,armed?784:785);break;
    case 14:
        if(o[0x134/4]==787)face(o,F{body[0x40/4]}.less({o[0x40/4]}));
        else {o[0x40/4]=body[0x40/4];o[0x44/4]=body[0x44/4];}
        AuxiliaryObjects::stop(o);request(o[0x134/4]);break;
    case 15:case 16:AuxiliaryObjects::stop(o);copyFacing(o,body);request(769);break;
    case 17:AuxiliaryObjects::stop(o);o[0x40/4]=body[0x40/4];o[0x44/4]=f(64).bits;
        copyFacing(o,body);o[0x104/4]|=0x400002;break;
    }
    if(cmd==13){face(o,!F{o[0x40/4]}.less({body[0x40/4]}));request(769);}
    o[0x128/4]=o[0x12c/4]=cmd;
    return true;
}
}

uint32_t spawnMamahaha(AuxiliaryObjects& objects,TaggedTaskPools& tasks,std::span<uint32_t> registry,
                       unsigned player,uint32_t flags,const Object& body) {
    const auto handle=objects.create(tasks,registry,player,flags,body,0x138c+player,3,0x1ed440);
    if(!handle)throw std::runtime_error("Missing Mamahaha object slot");
    auto& o=tasks.objects.at(handle-1);
    o[0x40/4]=signedOffset(body,f(-100)).bits;o[0x44/4]=F{body[0x44/4]}.add(f(200)).bits;
    objects.request(o,769,true,false);
    o[0x38/4]|=0x1000;o[0x104/4]|=0x4000;
    o[0x108/4]=(o[0x108/4]|0x40000)&~finished;
    o[0x128/4]=8;o[0x12c/4]=0xffffffff;
    return handle;
}

void updateMamahaha(AuxiliaryObjects& objects,Object& o,const Object& body,const StateEntryActor& owner,
                    bool finalWin,const StageCamera& camera) {
    auto& cmd=o[0x128/4];
    if(cmd==o[0x12c/4]&&cmd<6) {
        if(owner.flags23c&0x200000)cmd=16;
        else if(owner.flags23c&0x01000000)cmd=15;
        else if(cmd<3) {
            const auto dx=signedOffset(body,f(-50)).sub({o[0x40/4]});
            const auto dy=F{body[0x44/4]}.add(f(120)).sub({o[0x44/4]});
            if(distance(dx,dy).less(f(24))) {
                const bool facing=((o[0x38/4]^body[0x38/4])&mirror)==0;
                if((owner.flags23c&0x200)&&facing)cmd=5;
                else if((owner.flags23c&1)&&facing)cmd=3;
                else if((owner.flags23c&4)&&owner.stateIndex()>=32)cmd=4;
            }
        }
    }
    if(enter(objects,o,body,owner,finalWin))return;
    const auto dist=follow(o,body);
    const unsigned tracking=dist<101?0:1;
    switch(cmd) {
    case 0:case 1:cmd=tracking;break;
    case 2:case 3:case 4:case 5:if(ready(o))cmd=tracking;break;
    case 6:case 7:if(F{o[0x44/4]}.less({0})||ready(o)||(o[0x100/4]&2))cmd=tracking;break;
    case 8:case 9:case 10:case 11:case 12:case 14:
        if(cmd!=8)o[0x104/4]&=~0x100u;
        if(ready(o)){o[0x108/4]|=finished;if(cmd==8)cmd=tracking;}break;
    case 13:if(dist<2)cmd=14;break;
    case 15:
        copyFacing(o,body);
        if(!(owner.flags23c&0x01000000))cmd=tracking;
        else {
            F x{o[0x40/4]};int32_t speed=0;
            if(!x.add(f(46)).less(F::integer(camera.right)))speed=-0x28000;
            else if(!F::integer(camera.left).less(x.sub(f(46))))speed=0x28000;
            o[0x50/4]=uint32_t(o[0x38/4]&mirror?-speed:speed);
        }break;
    case 16:
        copyFacing(o,body);
        if(!(owner.flags23c&0x200000))cmd=tracking;
        else {o[0x40/4]=body[0x40/4];o[0x44/4]=F{body[0x44/4]}.add(f(54)).bits;}
        break;
    case 17:
        if(owner.state194==0x300000)o[0x104/4]|=2;
        else {objects.request(o,769,true,true);cmd=tracking;}break;
    }
}
}
