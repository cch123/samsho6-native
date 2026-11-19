#!/usr/bin/env python3
"""Compare the referee's final-round, menu freeze and CONTINUE handoff to the Japanese callback."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
OUT=ROOT/'outputs/ss6-feasibility/stage_event_menu_validation.json'
DRIVER=r'''
#include "local_versus.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int,char** argv){
    unsigned attacker=std::stoul(argv[2]);LocalVersus session(argv[1]);
    unsigned age=0,rematchTicks=0;std::array<unsigned,2> previous{};
    auto out=[](auto v){std::cout<<+v<<' ';};auto bits=[](float v){return std::bit_cast<uint32_t>(v);};
    for(unsigned i=0;i<16000&&rematchTicks<75;++i){
        const auto& prior=session.match();const auto& b=prior.battle();const auto& e=b.stageEvent;
        const bool menu=b.consoleMenu.active;const auto matchNo=session.matchNumber();
        if(matchNo==2)++rematchTicks;
        out(matchNo);out(menu);out(b.requestedState);out(e.state);out(e.request);out(e.flags);out(e.pending);
        for(auto v:{e.x,e.y,e.z,e.targetX})out(bits(v));out(e.dx);out(e.vx);out(e.ax);
        for(unsigned j=0;j<2;++j)out(bits(prior.fighter(j).body.timeline.motion().x));
        out(prior.fighter(0).body.timeline.clock().objectFlags&0x80000);
        const auto& g=b.gauges;
        auto gaugeTask=std::any_of(b.entry.tasks.tasks.begin(),b.entry.tasks.tasks.end(),[](auto& t){return t[0]==0x11e708;});
        out(gaugeTask);out(g.paused46a940);out(g.delta46a908);out(g.scale1239d84);out(g.scale1239d88);
        for(auto v:g.words910)out(v);
        std::array<unsigned,2> held{};const unsigned pos=(i-500)%294;
        if(menu){++age;held[attacker]=age==51?32:age==53?512:0;}
        else if(i>=500&&matchNo==1&&attacker<2){held[attacker]=pos<70?(attacker?64:128):pos==73?1024:0;}
        std::array<NormalizedPadSample,2> pads;
        for(unsigned j=0;j<2;++j)pads[j]={held[j],held[j]&~previous[j]};previous=held;session.tick(pads);
        const auto& now=session.match();const auto& queue=now.objectDraws();out(session.matchNumber());out(now.battle().consoleMenu.active);
        unsigned count=0;uint32_t others=2166136261u;const ObjectDrawQueue::Record* ref=nullptr;
        for(const auto& r:queue.active()){
            if(r[3]==2&&r[9]>=25&&r[9]<=44&&r[81]==0){++count;ref=&r;}
            else for(auto v:r)others=(others^v)*16777619u;
        }
        out(count);out(others);if(ref)for(auto v:*ref)out(v);std::cout<<'\n';
    }
    return rematchTicks==75?0:1;
}
'''


def case(arg):
    exe,side=arg
    r=subprocess.run([exe,ASSETS,str(side)],text=True,capture_output=True,check=True)
    src,_=setup(0);p=src.p;obj=0x132c0a8
    for addr,name in ((0x46a9b0+2*0x1800,'aid_51.bin'),(0x1a40000,'act_51.bin')):
        data=(ASSETS/name).read_bytes();p.memory[addr:addr+len(data)]=data
    for at,n in ((0x4751b8,0x1a40000),(0x46a9a8,51),(0x4c3808,3)):p.write(at,n,4)
    for j in range(2):p.write(src.a+j*0xf2c,src.o+0x1000*j,4)
    def reset():p.run(0x1b4138,limit=500000)
    reset();menuRows=[];instructions=0;fresh=[];midpoint=None
    for i,line in enumerate(r.stdout.splitlines(),1):
        v=list(map(int,line.split()));old,menu,phase=v[:3];new,active,count,others=v[34:38]
        if old!=new:
            assert not count and new==2
            reset();midpoint=i;continue
        if not menu:
            # Only the ordinary battle can issue or reposition the referee.
            # During the real menu, let the EE callback own its entire body,
            # flags and subphase across all visits (including the first freeze).
            for at,n in zip((0x132c1e0,0x132c1e4,0x132c1e8,0x132c1f8,obj+0x40,obj+0x44,obj+0x48,0x132c210,obj+0x4c,obj+0x50,obj+0x54),v[3:14],strict=True):
                p.write(at,n,4)
        for j in range(2):p.write(src.o+0x1000*j+0x40,v[14+j],4)
        p.write(src.o+0x38,v[16],4);p.write(src.b,phase,4)
        gaugeTask,paused,delta,scaleA,scaleB=v[17:22]
        if gaugeTask and not menu:delta=0 if paused else (scaleA*scaleB)>>8
        p.write(0x46a908,delta,4);p.write(0x46a940,paused,4)
        for j,n in enumerate(v[22:34]):p.write(0x46a910+4*j,n,4)
        p.run(0x1207d8);_,n=p.run(0x1b4228,limit=500000);instructions+=n
        originalCount=p.read(0x4a2250,4)
        assert originalCount==count,(side,i,old,phase,count,originalCount)
        source=struct.unpack_from('<82I',p.memory,0x479250)
        if count:
            assert list(source)==v[38:],(side,i,phase,[(hex(j*4),a,b) for j,(a,b) in enumerate(zip(v[38:],source)) if a!=b])
        if menu or active:
            row=dict(tick=i,prior_menu=menu,delta=delta,paused=paused,act=source[9],step=source[10],
                     clock=source[11],post_step=p.read(obj+0x28,4),post_clock=p.read(obj+0x2c,4),others=others)
            if menuRows:assert others==menuRows[-1]['others'],(side,i,'other drawings changed')
            menuRows.append(row)
        if old==2 and len(fresh)<3:fresh.append([i,source[9],source[10],source[11]])
    assert midpoint and len(menuRows)>50 and menuRows[0]['prior_menu']==0
    assert menuRows[1]['paused']==0 and menuRows[2]['paused']==1
    assert (menuRows[1]['step'],menuRows[1]['clock'])==(menuRows[0]['post_step'],menuRows[0]['post_clock'])
    assert len({(r['act'],r['step'],r['clock']) for r in menuRows[2:]})==1
    assert fresh[0][1:]==[25,0,0],fresh
    return dict(winner=side+1,first_menu_frames=menuRows[:4],paused_updates=len(menuRows)-2,
                last_menu=menuRows[-1],continue_midpoint=midpoint,new_match_frames=fresh,
                original_instructions=instructions)


def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as temp:
        folder=Path(temp);cpp=folder/'menu.cpp';exe=folder/'menu';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        with ProcessPoolExecutor(2) as workers:result=list(workers.map(case,[(exe,0),(exe,1)]))
    OUT.write_text(json.dumps(dict(status='passed',elf_sha256=PIN,lib_sha256=digest(LIB),validator_sha256=digest(Path(__file__)),
                   scope='Both first-to-two fights won by real heavy slash inputs, real console menu and CONTINUE. Execute full Japanese 1b4228 comparing all 82 submitted words on every tick through the rematch. Before menu use prior battle requests/actor motion as external input. During the menu the original model retains its private state including the first unfrozen visit. Check non-referee queue stays unchanged, original 1b4138 resets the next match, compare first 75 fresh updates.',cases=result),indent=2)+'\n')
    print([(r['winner'],r['first_menu_frames'][0]['tick'],r['continue_midpoint']) for r in result])


if __name__=='__main__':main()
