"""Run complete 158b08 on both seats with damage, recovery, pickups, missiles and supers."""
import collections
import random
import struct
import subprocess
import tempfile
from pathlib import Path
from cpu_fight_oracle import cpu_actor
from validate_cpu_decision import world
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest

DRIVER=r'''
#include "cpu_reactions.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){
 InputBindings bindings(argv[1]);InputPermissions permissions(argv[1]);unsigned seat,charid;
 while(std::cin>>seat>>charid){
  StateEntryActor a,b;InputSystemConfig config;CpuDecisionFrame d;GameRandom rng;PermissionContext objects;
  a.character=config.character=charid;unsigned flags,alias,used,x;
  int mode,wins,need,objKind,objOwner,objId,objAction,objFlags;float objX;
  std::cin>>config.system>>d.level100>>d.clockValue>>wins>>need>>rng.mode>>rng.gameSeed>>rng.librarySeed
          >>a.flags23c>>a.flags244>>a.flags248>>a.state194>>a.state1a4>>flags>>alias>>a.conditions15c[1]>>a.conditions15c[2]
          >>a.rageState120>>a.systemState13c>>a.fieldA30>>used>>a.timers[2]>>a.bodyFlags108>>x
          >>b.flags23c>>b.state194>>a.cpuPrevious174>>a.cpuTimerDelta08>>objects.stageObjectIndex>>objects.stageObjectX
          >>objKind>>objOwner>>objId>>objAction>>objFlags>>objX;
  a.stateFlags19a=flags;a.aliasFlags1aa=alias;a.concentrationUsed11c=used;a.x=std::bit_cast<float>(x);
  std::array<CpuReactionProjectile,1> missiles{};unsigned count=0;
  if(objKind==2)d.kind2=CpuObservedObject{};
  if(objKind==4)objects.ownObjects[0]=PermissionObject{4,0,objAction,0,objX};
  if(objKind==5){count=1;missiles[0]={unsigned(objOwner),objId,unsigned(objFlags),objX};}
  auto control=[&](auto visit){for(auto& t:a.controlTimers0c)visit(t);visit(a.controlTimer34);
   visit(a.control88);visit(a.control8c);visit(a.controlFlagsB4);visit(a.flagsB8);visit(a.controlFlagsBC);
   visit(a.controlD8);visit(a.controlE4);visit(a.controlE8);visit(a.controlC4);
   for(auto& n:a.controlMotion38)visit(n);};
  control([](auto& n){std::cin>>n;});
  CpuTactics tactics(argv[1],charid);
  auto ret=updateCpuReaction(a,b,d,{config,bindings,tactics,rng,0,d.level100,0},
    {permissions,objects,wins,need,seat,{missiles.data(),count}});
  std::cout<<ret<<' '<<rng.gameSeed<<' '<<rng.librarySeed<<' ';
  control([](auto n){std::cout<<n<<' ';});std::cout<<'\n';
 }
}
'''
OFFS=(*range(0xc,0x38,4),0x88,0x8c,0xb4,0xb8,0xbc,0xd8,0xe4,0xe8,0xc4,*range(0x38,0x60,4))
def cases(seat):
 s=cpu_actor(seat);p,a,o=s.p,s.a,s.o;r=p.read(0x5d1bf8,4);b=s.b;eo=s.other
 rng=random.Random(0x158b08+seat);base=bytes(p.memory[a:a+0xf2c]);record=s.b+0x254+(1-seat)*0x108
 words=lambda :[p.read(a+n,4) for n in OFFS]
 rows=[];expected=[];hits=collections.Counter()
 for n in range(760):
    typ=n%12;idx=n//12
    p.memory[a:a+0xf2c]=base
    char=[0,1,2,3,4,16,19][idx%7];spirit=[0,1,2,3,4,5,7,8][idx%8]
    if typ==0:spirit=3
    if typ in (1,2):spirit=4
    if typ==3:char=[3,4,16,19][idx%4]
    level=idx%9;hp=(15,61,180)[idx%3];flags=0x1000;state=et=0;f244=f248=0
    cond1=cond2=ef=0;motionFlag=0;stage=-1;obj=owner=oi=action=of=0;ox=0
    rage=system=t2=0;held=0;pending=-1;prev=idx%4;f108=0
    if typ==1:system=2
    if typ==2:system=3;et=((32+idx%28)<<16|2) if idx%2 else ((48+idx%8)<<16)
    if typ==3:state=0x100002;ef=8
    if typ==4:flags|=16;state=0x200002;spirit=8;obj=2 if idx%2 else 0
    if typ==5:flags|=4;state=0x100002;cond1=(1<<30) if idx%3==0 else 0;cond2=8 if idx%3==1 else 0;t2=idx%2
    if typ==6:pending=idx%20
    if typ==7:flags=0;obj=4;action=467 if idx%4 else 0;ox=240
    if typ==8:stage=idx%6;f244=2 if idx%3 else 0;f108=0x40 if idx%2 else 0
    if typ==9:
        obj=5;owner=1-seat if idx%8 else seat;oi=109+idx%12;of=0x80000 if idx%2 else 0
        extent=p.read(0x4e5ab8+8*char+4,2);dist=[24,32,40,48,56,64,80][idx%7]
        ox=240+(1 if of else -1)*(extent+dist)
    if typ==10:held=1
    if typ==11:held=rng.getrandbits(20);motionFlag=rng.randrange(4)<<6;flags|=4 if idx%2 else 16
    for off,v in ((0x10c,spirit),(0xa10,char),(0x100,char),(0x108,level),(0xa30,hp),(0x23c,flags),(0x244,f244),
       (0x248,f248),(0x194,state),(0x160,cond1),(0x164,cond2),(0x120,rage),(0x13c,system),(0x1b8,t2),
       (0xb4,held),(0xbc,motionFlag),(0xd8,pending),(8,256),(0x88,0xa1a1),(0x8c,31),(0xb8,0x5000)):p.write(a+off,v,4)
    p.write(a+0x19a,ef,1);p.write(a+0x11c,idx%2,1);p.write(a+0x174,prev,2);p.write(o+0x108,f108,4)
    p.write(eo+0x194,et,4);p.write(eo+0x23c,0x1000,4);p.write(record+0x28,1,4);p.write(record+0x2c,2,4)
    struct.pack_into('<f',p.memory,o+0x40,240);p.write(0x132c4bc,stage,4);struct.pack_into('<f',p.memory,0x132c398,240)
    for side in range(2):p.memory[b+0x29c+0x108*side:b+0x29c+0x108*side+192]=bytes(192)
    if obj:
        side=seat if obj==4 else 1-seat
        node=0x1c30000;body=node+0x100;p.write(b+0x29c+side*0x108,node,4);p.write(node+0x1c,body,4)
        for off,v in ((0xcc,obj),(0xd0,oi),(0x10,owner),(0x24,action),(0x38,of)):p.write(body+off,v,4)
        struct.pack_into('<f',p.memory,body+0x40,ox)
    for offset in (*range(0xc,0x38,4),*range(0x38,0x60,4)):p.write(a+offset,rng.randrange(1,9) if offset>=0x38 or typ==11 else 0,4)
    p.write(r+0xa8,rng.getrandbits(64),8);p.write(0x3d2e80,rng.getrandbits(32),4);p.write(0x443150,idx%2,4)
    initial=[seat,char,spirit,level,world(s)[0],1,2,idx%2,p.read(0x3d2e80,4),p.read(r+0xa8,8),flags,f244,f248,state,
      p.read(a+0x1a4,4),ef,p.read(a+0x1aa,1),cond1,cond2,rage,system,hp,idx%2,t2,f108,p.read(o+0x40,4),0x1000,et,prev,256,
      stage,240,obj,owner,oi,action,of,ox,*words()]
    ret=p.run(0x158b08,[a+8],limit=50000)[0];rows.append(initial);expected.append([ret,p.read(0x3d2e80,4),p.read(r+0xa8,8),*words()])
    if ret:hits[p.read(a+0x8c,4)]+=1
 return rows,expected,hits

def main():
 assert digest(ELF)==PIN
 with tempfile.TemporaryDirectory() as td:
    driver=Path(td)/'probe.cpp';exe=Path(td)/'probe';driver.write_text(DRIVER)
    subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',driver,ROOT/'src/cpu_reactions.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
    for seat in range(2):
        rows,expected,hits=cases(seat)
        out=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,row))+'\n' for row in rows),text=True,capture_output=True,check=True)
        got=[list(map(int,row.split())) for row in out.stdout.splitlines()]
        assert len(got)==len(rows)
        for i,(g,w) in enumerate(zip(got,expected)):assert g==w,(i,rows[i][:38],[(j,u,v) for j,(u,v) in enumerate(zip(g,w)) if u!=v])
        print(f'P{seat+1}',len(rows),'complete 158b08 visits, forced slots',dict(hits))
if __name__=='__main__':main()
