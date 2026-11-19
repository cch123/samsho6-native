"""Compare 158990's lookahead/advance block with 159018, 159108, 1591e0 and 158df8."""
import random
import struct
import subprocess
import tempfile
from pathlib import Path
from cpu_fight_oracle import cpu_actor
from validate_cpu_decision import world
from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_cpu_reactions import OFFS

DRIVER=r'''
#include "cpu_execution.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv){ unsigned charid,spirit,desc;
 while(std::cin>>charid>>spirit>>desc){
  StateEntryActor a;CpuDecisionFrame f;GameRandom r;InputSystemConfig c{spirit,charid};a.character=charid;
  std::array<uint8_t,16> descriptor{};for(auto& b:descriptor){unsigned v;std::cin>>v;b=v;}if(spirit==6)c.descriptor=descriptor;
  std::cin>>r.mode>>r.gameSeed>>r.librarySeed>>f.difficulty>>f.roundIndex>>f.battleMode>>a.flags23c>>a.state194>>a.state1a4
          >>a.bodyFlags104>>a.bodyFlags108>>a.timers[3]>>a.controlF8>>a.controlModeC8;
  auto control=[&](auto visit){for(auto& x:a.controlTimers0c)visit(x);visit(a.controlTimer34);
   visit(a.control88);visit(a.control8c);visit(a.controlFlagsB4);visit(a.flagsB8);visit(a.controlFlagsBC);
   visit(a.controlD8);visit(a.controlE4);visit(a.controlE8);visit(a.controlC4);
   for(auto& x:a.controlMotion38)visit(x);for(auto& x:a.conditions15c)visit(x);
  };control([](auto& x){std::cin>>x;});
  CpuTactics t(argv[1],charid);advanceCpuSequence(a,c,f,t,r);
  std::cout<<r.gameSeed<<' '<<r.librarySeed<<' ';control([](auto x){std::cout<<x<<' ';});std::cout<<'\n';
 }
}
'''
def cases(seat):
 s=cpu_actor(seat);p,a,o=s.p,s.a,s.o
 labels=(*OFFS,0x15c,0x160,0x164);initial=bytes(p.memory[a:a+0xf2c]);rng=random.Random(158+seat)
 r=p.read(0x5d1bf8,4);rows=[];wants=[]
 for i in range(650):
    p.memory[a:a+0xf2c]=initial
    spirit=[0,8,6][i%3];desc=i%8
    p.write(a+0x10c,spirit,4);p.write(a+0x114,desc,4)
    descriptor=list(p.memory[0x4d7068+16*desc:0x4d7068+16*(1+desc)])
    if spirit==6:
        d=p.run(0x14f4e0,[a+0x10c],limit=500)[0];descriptor=list(p.memory[d:d+16])
    p.write(0x443150,i%2,4);p.write(r+0xa8,rng.getrandbits(64),8);p.write(0x3d2e80,rng.getrandbits(32),4)
    p.write(0x43d05c,i%8,1)
    p.write(a+0x23c,0x1000|(0x10 if i%5==0 else 0),4);p.write(a+0x194,((i%13)<<16)|(i%3),4)
    p.write(o+0x104,rng.randrange(4)<<18,4);p.write(o+0x108,rng.randrange(4)<<5,4)
    p.write(a+0x1bc,int(i%3==2),4);p.write(a+0xf8,i%21,4);p.write(a+0xc8,35,4)
    for off in labels:p.write(a+off,rng.getrandbits(32),4)
    seq=([127,255,22,34,128,158,12,124,251][i%9]);idx=i%4
    for off,val in ((0x38,i%2),(0x3c,seq),(0x40,idx),(0xc4,i%5),(0xb4,rng.randrange(4)<<12|4),(0xbc,0x80 if i%7==0 else 0),
        (0x50,104),(0x54,105),(0x58,106)):p.write(a+off,val,4)
    for j in range(4):p.write(a+0x4c+4*j,[0,54,104,105,106,110,111,124][(j+i//4)%8],4)
    take=lambda:[p.read(a+off,4) for off in labels]
    rows.append([0,spirit,desc,*descriptor,i%2,p.read(0x3d2e80,4),p.read(r+0xa8,8),i%8,world(s)[1],p.read(0x4c3808,4),p.read(a+0x23c,4),
       p.read(a+0x194,4),p.read(a+0x1a4,4),p.read(o+0x104,4),p.read(o+0x108,4),p.read(a+0x1bc,4),p.read(a+0xf8,4),35,*take()])
    for call in (0x159018,0x159108,0x1591e0):s.run(call,a+8)
    if p.read(a+0x38,4):s.run(0x158df8,a+8)
    wants.append([p.read(0x3d2e80,4),p.read(r+0xa8,8),*take()])
 return rows,wants
def main():
 assert digest(ELF)==PIN
 with tempfile.TemporaryDirectory() as td:
    driver=Path(td)/'probe.cpp';exe=Path(td)/'probe';driver.write_text(DRIVER)
    subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',driver,ROOT/'src/cpu_execution.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
    for side in range(2):
        rows,wants=cases(side)
        result=subprocess.run([exe,ASSETS],input=''.join(' '.join(map(str,row))+'\n' for row in rows),text=True,capture_output=True,check=True)
        got=[list(map(int,row.split())) for row in result.stdout.splitlines()];assert len(rows)==len(got)
        for i,(g,w) in enumerate(zip(got,wants)):assert g==w,(i,rows[i],[(j,u,v) for j,(u,v) in enumerate(zip(g,w)) if u!=v])
        print(f'P{side+1}',len(rows),'whole lookahead and page advance visits matched')
if __name__=='__main__':main()
