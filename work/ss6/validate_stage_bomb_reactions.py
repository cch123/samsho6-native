#!/usr/bin/env python3
"""Real selected fighters in the blast, compared with original guard and damage callbacks."""
import itertools
import json
import struct
import subprocess
import tempfile
from pathlib import Path
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_selected_combat import prefix
from validate_weapon_handling import setup

LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
REPORT=ROOT/'outputs/ss6-feasibility/stage-bomb-reaction-validation.json'
BOMB,EVENT=0x1e90000,0x1eb0000
DRIVER=r'''
#include "local_versus.hpp"
#include "combat_decision.hpp"
#include <iostream>
int main(int,char** argv){try{
    if(std::string(argv[2])=="boundaries") {
        ss6::ReactionTables reactions(argv[1]);int state,flags,reverse;unsigned src104,src108;
        while(std::cin>>state>>flags>>reverse>>src104>>src108){
            ss6::DefenseSnapshot def{};def.system=5;def.stateIndex=state;def.actorFlags23c=0x1000|flags;
            ss6::CollisionPlayer from{};from.objectKind=5;from.objectFlags104=src104;from.objectFlags108=src108;
            auto defense=ss6::selectDefense(from,def);
            ss6::ReactionTarget target{};target.flags23c=def.actorFlags23c;target.flags24c=reverse;
            ss6::ActorTimers unused{},bt{};unsigned action;
            if(defense)reactions.applyGuard(target,unused,bt,defense,0,action);
            else{uint32_t sf=0;action=reactions.applyGroundHit(target,unused,bt,26,0,false,false,0,sf,true).action;}
            const auto timing=reactions.descriptor(defense?(defense==3?8:target.pendingState):target.secondaryReaction);
            ss6::AuxiliaryObject bomb{};ss6::AuxiliaryObjects::pauseWhirlwind(bomb,timing.firstTimer,timing.secondTimer);
            std::cout<<unsigned(defense)<<' '<<target.pendingTable<<' '<<target.pendingState<<' '<<action<<' '
                     <<bt.values[0]<<' '<<bt.values[1]<<' '<<bomb[0xdc/4]<<'\n';
        }
        return 0;
    }
    unsigned seat=std::stoi(argv[2]);ss6::LocalVersus s(argv[1],99,ss6::VersusMode::Console,{},true);
    unsigned n,x,y;std::array<uint32_t,2> old{};
    while(std::cin>>n>>x>>y){
        const std::array<uint32_t,2> held{x,y};
        for(unsigned k=0;k<n;++k){std::array<ss6::NormalizedPadSample,2> pads;
            for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~old[i]};
            old=held;s.tick(pads);}
        const auto& m=s.match();const auto& f=m.fighter(seat);const auto& a=f.actor;const auto& c=f.body.timeline.clock();
        auto word=[](auto u){std::cout<<int64_t(u)<<' ';};
        for(auto v:{a.state194,a.flags23c,a.flags244,uint32_t(a.flags24c),uint32_t(a.effectiveFlags()),
                   f.input.sampledFeatures[0xfc/4],f.input.sampledFeatures[0xd8/4],f.input.sampledFeatures[0xd4/4],
                   uint32_t(f.body.timeline.action().id()),c.step,c.fractionalTime,uint32_t(a.timers[0]),
                   uint32_t(a.timers[1]),uint32_t(a.timerDelta),uint32_t(a.fieldA30)})word(v);
        const auto& owner=m.fighter(1-seat);word(owner.actor.timers[0]);word(owner.actor.timers[1]);word(owner.hits);word(owner.guards);
        bool seen=false;const auto& b=m.battle();
        for(auto t:b.objectTasks)if(t){const auto& o=b.entry.tasks.objects.at(b.entry.tasks.tasks.at(t-1)[7]-1);
            if(o[0xcc/4]!=5||o[0x10/4]==seat)continue;
            for(auto offset:{0xc,0x10,0x14,0x24,0x28,0x30,0x104,0x108,0xdc,0xfc})word(o[offset/4]);
            seen=true;break;}
        if(!seen)for(int z=0;z<10;++z)word(0);
        std::cout<<'\n';
    }
}catch(const std::exception& e){std::cerr<<e.what();return 1;}}
'''

def original(target,pre,forced=None):
    s,_=setup(target,target);p,a,o=s.p,s.a,s.o
    for off,val in zip((0xc,0x10,0x14,0x24,0x28,0x30,0x104,0x108,0xdc,0xfc),pre[19:29]):p.write(BOMB+off,val,4)
    p.write(BOMB+0xcc,5,4);p.write(BOMB+0xd0,110,4)
    for adr,v,size in ((a+0x194,pre[0],4),(a+0x23c,pre[1],4),(a+0x244,pre[2],4),(a+0x24c,pre[3],1),
                       (a+0x19a,pre[4],1),(a+0x3c0,pre[5],4),(a+0x39c,pre[6],4),(a+0x398,pre[7],4),(a+0x10c,5,4),
                       (o+0xc,target,4),(o+0xcc,target,4),(EVENT+0x40,BOMB,4),(EVENT+0x68,o,4)):
        p.write(adr,v,size)
    if forced:
        state,extraFlags,flag24c=forced
        p.write(a+0x194,state<<16,4);p.write(a+0x19a,0,1);p.write(a+0x24c,flag24c,1)
        p.write(a+0x23c,0x1000|extraFlags,4)
    defense,n=p.run(0x155850,[EVENT]);s.instructions+=n
    if defense:s.run(0x14d5a0,a,BOMB,defense,0)
    else:s.run(0x14d198,a,BOMB,0,26,0,0)
    ans=dict(defense=defense,state=p.read(a+0x192,2),first=p.read(a+0x1b0,4),second=p.read(a+0x1b4,4),
             bomb=p.read(BOMB+0xdc,4),owner=[p.read(s.other+j,4) for j in (0x1b0,0x1b4)])
    s.run(0x1491e0,a);s.run(0x149d08,a);s.run(0x149918,a);s.run(0x11d8e0,o)
    ans.update(action=p.read(o+0x24,4),table=p.read(a+0x194,2),instructions=s.instructions)
    return s,ans

def scenario(exe,seat,pose):
    when=(4145,2544)[seat];q=prefix((0,1));q[265][1]=128
    q += [[128,64]]*32+[[0,0]]*5+[[0,1024]]
    q += [[0,0] for _ in range(when+13-len(q))]
    if seat:q[1840]=[2304,0];q[2384]=[2304,0]
    back=(64,128)[seat]
    if pose=='jump':key,lead=16,3
    elif pose=='crouch':key,lead=32,20
    elif pose=='guard crouch':key,lead=32|back,39
    elif pose=='guard stand':key,lead=back,3
    else:key,lead=0,1
    for i in range(when-lead,when+2):q[i][seat]=key
    if pose.startswith('guard'):q[when-8][1-seat]=1024
    groups=[(sum(1 for _ in g),*r) for r,g in itertools.groupby(map(tuple,q[:when-2]))]
    groups += [(1,*r) for r in q[when-2:]]
    proc=subprocess.run([exe,ASSETS,str(seat)],input=''.join(f'{n} {x} {y}\n' for n,x,y in groups),text=True,capture_output=True,check=True)
    arr=[list(map(int,r.split())) for r in proc.stdout.splitlines()];rows=arr[-15:]
    pre,post=rows[:2]
    if pre[22] not in (55,56) or pre[23]<1 or post[17:19]==pre[17:19]:return None
    s,want=original(seat,pre);p,a=s.p,s.a
    assert (post[0]&0xffff,post[0]>>16,post[8])==(want['table'],want['state'],want['action']),(seat,pose,post,want)
    assert post[17]-pre[17]==int(want['defense']==0) and post[18]-pre[18]==int(want['defense']!=0)
    # 151eb0 runs later in the same frame as impact. Its two timers count
    # down serially with the real 128/256 actor rate, while the bomb has a
    # separate stop clock in the subsequent 11d6c8 move pass.
    sync=[]
    for i,row in enumerate(rows[1:]):
        if row[0]!=post[0] or (i and row[17:19]!=post[17:19]):break
        p.write(a+0x1ac,row[13],4);s.run(0x151eb0,a)
        p.write(BOMB+0x30,row[24],4);s.run(0x11d6c8,BOMB)
        vals=[p.read(a+j,4) for j in (0x1b0,0x1b4)]+[p.read(BOMB+0xdc,4)]
        assert row[11:13]+[row[27]]==vals,(seat,pose,i,row[11:13],row[27],vals,want)
        sync.append(vals)
        if vals==[0,0,0]:break
    assert len(sync)>=4 and (pose.startswith('guard') or sync[-1]==[0,0,0]),(pose,sync)
    assert pre[15:17]==post[15:17]==want['owner']==[0,0]
    return dict(seat=seat+1,pose=pose,pad_tick=when,pre_state=pre[0],bomb_flags108=pre[26],
                original=want,post_hit_clocks=sync),pre

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);cpp=folder/'bomb.cpp';exe=folder/'bomb';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        rows=[];boundaries=[]
        for seat in range(2):
            for pose in ('standing','crouch','jump','guard crouch','guard stand'):
                value=scenario(exe,seat,pose)
                if not value:continue
                r,pre=value;rows.append(r)
                if pose=='standing':
                    for state,flags,reverse in ((0,0,2),(1,8,2),(8,16,0),(47,0,0),(6,0,0),(7,8,0)):
                        _,entry=original(seat,pre,(state,flags,reverse))
                        args=[state,flags,reverse,pre[25],pre[26]]
                        trial=subprocess.run([exe,ASSETS,'boundaries'],input=' '.join(map(str,args))+'\n',
                                             text=True,capture_output=True,check=True)
                        want=[entry[key] for key in ('defense','table','state','action','first','second','bomb')]
                        assert list(map(int,trial.stdout.split()))==want,(seat,args,want,trial.stdout)
                        boundaries.append(dict(player=seat+1,state=state,flags24c=reverse,original=entry))
    assert all({'standing','crouch','jump','guard crouch'}<={r['pose'] for r in rows if r['seat']==s} for s in (1,2))
    assert {r['original']['state'] for r in boundaries}>={52,53}
    REPORT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,runtime_sha256=digest(LIB),real_selected_matches=rows,
        isolated_original_boundaries=boundaries,scope='Actual raw26 common bomb, attack record 55 or 56, real two-player inputs. Defense and timing executed in Japanese code, including 155850, 14d198/14d5a0, 151578, 1491e0 and 149d08. Actor and object clocks followed to zero or the next contact/state change. Alternate facing reaction and already-active perfect/air guard checked separately at their original entry boundary.'),indent=2)+'\n')
    for r in rows:print(r['seat'],r['pose'],r['original']['defense'],r['original']['state'],r['original']['action'],r['post_hit_clocks'])
if __name__=='__main__':main()
