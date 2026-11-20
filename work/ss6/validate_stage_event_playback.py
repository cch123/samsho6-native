#!/usr/bin/env python3
"""Compare priority-20 referee requests, movement, ACT and original raw drawing queue."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

OUT=ROOT/'outputs/ss6-feasibility/stage_event_playback_validation.json'
LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
DRIVER=r'''
#include "stage_event.hpp"
#include "auxiliary_objects.hpp"
#include <bit>
#include <iostream>
int main(int,char**argv){ss6::StageEventActor a;ss6::StageEventPlayback stage;stage.initialize(a);
    ss6::AuxiliaryObjects auxiliary(argv[1],{0,0,51});ss6::StageEventRules rules(argv[1]);
    ss6::GaugeState g{};ss6::ObjectDrawQueue queue;
    for(unsigned i=0;i<78;++i)std::cout<<stage.body()[i]<<' ';std::cout<<'\n';
    int event,hide,pause,rate,round,mir;float x0,x1;
    while(std::cin>>event>>x0>>x1>>mir>>hide>>pause>>rate>>round){
        ss6::StageEventPlayers p{x0,x1,bool(mir)};
        if(event>=0)rules.request(a,event,true,p);
        if(hide)stage.hideNextDraw();g.paused46a940=pause;g.delta46a908=rate;g.words910[2]=1;
        queue.beginFrame();const int side=stage.visit(a,p,round,g,auxiliary,queue);
        std::cout<<side<<' '<<a.state<<' '<<a.request<<' '<<a.flags<<' '<<a.pending<<' '
                 <<std::bit_cast<uint32_t>(a.targetX)<<' '<<queue.count;
        for(unsigned i=0;i<78;++i)std::cout<<' '<<stage.body()[i];
        if(queue.count)for(auto v:queue.slots[0])std::cout<<' '<<v;
        std::cout<<'\n';
    }}
'''


def inputs(scenario):
    for i in range(325):
        event=-1
        if scenario<15:event=scenario if i==2 else -1
        elif scenario==15:event={2:13,4:14,5:6,6:13}.get(i,-1)
        elif scenario==16:event={2:14,4:13,43:0}.get(i,-1)
        else:event={15:3,90:2,144:6,210:7}.get(i,-1)
        # Crossing sides changes both the sprite mirror and the meaning of
        # walking ACT29/30. Return to center so pending throws exercise both
        # the outside condition and the close extra idle animation.
        x0,x1=(215.5,424.75) if i<95 else (620.25,200.5) if i<165 else (8.5,320.5)
        mir=int(x0>x1);  hide=i in (0,26,159); pause=22<=i<27
        rate=128 if 35<=i<65 else 256
        yield (event,x0,x1,mir,int(hide),int(pause),rate,2 if i<2 else 4 if i<308 else 8)


def case(arg):
    exe,scenario=arg
    src,_=setup(0);p=src.p;obj=0x132c0a8
    for addr,name in ((0x46a9b0+2*0x1800,'aid_51.bin'),(0x1a40000,'act_51.bin')):
        data=(ASSETS/name).read_bytes();p.memory[addr:addr+len(data)]=data
    p.write(0x4751b8,0x1a40000,4);p.write(0x46a9a8,51,4);p.write(0x4c3808,3,4)
    for i in range(2):
        p.write(src.a+i*0xf2c,src.o+0x1000*i,4)
        p.write(src.a+i*0xf2c+0xa24,i,4)
        p.write(src.o+0x1000*i+0xc,i,4)
        p.write(src.o+0x1000*i+0x10,i,4)
        p.write(src.o+0x1000*i+0xcc,i,4)
    p.run(0x1b4138,limit=500000)
    commands=list(inputs(scenario));pads=''.join(' '.join(map(str,c))+'\n' for c in commands)
    r=subprocess.run([exe,ASSETS],text=True,input=pads,capture_output=True,check=True)
    initial,*rows=[list(map(int,line.split())) for line in r.stdout.splitlines()]
    assert initial==list(struct.unpack_from('<78I',p.memory,obj)),(scenario,'initial referee body')
    thrown=[];actions=[];visible=0;original_instructions=0
    for i,((ev,x0,x1,mir,hide,pause,rate,phase),got) in enumerate(zip(commands,rows,strict=True)):
        for side,x in enumerate((x0,x1)):
            struct.pack_into('<f',p.memory,src.o+0x1000*side+0x40,x)
            p.write(src.o+0x1000*side+0x38,(mir^side)<<19,4)
        p.write(src.b,phase,4);p.write(0x46a940,pause,4);p.write(0x46a918,1,4);p.write(0x46a908,rate,4)
        if ev>=0:p.run(0x1b4d90,[ev,1])
        if hide:p.run(0x1b5078)
        p.run(0x1207d8);side=[]
        def observe(pc):
            if pc==0x170480:side.append(p.registers[4])
        _,n=p.run(0x1b4228,limit=500000,observe=observe);original_instructions+=n
        if side:thrown.append([i,side[0]])
        count=p.read(0x4a2250,4);visible+=count
        want=[side[0] if side else -1]+[p.read(t,4) for t in (0x132c1e0,0x132c1e4,0x132c1e8,0x132c1f8,0x132c210)]+[count]
        want+=struct.unpack_from('<78I',p.memory,obj)
        if count:want+=struct.unpack_from('<82I',p.memory,0x479250)
        assert len(want)==len(got),(scenario,i,len(want),len(got))
        diff=[(j,v,w) for j,(v,w) in enumerate(zip(got,want)) if v!=w]
        assert not diff,(scenario,i,diff[:15],got[:7],x0,x1)
        act=p.read(obj+0x24,4)
        if not actions or actions[-1][1]!=act:actions.append([i,act])
    if scenario in (13,14):assert thrown==[[10,scenario-13]],(scenario,thrown)
    if scenario in (15,16):assert [s[1] for s in thrown]==([0,1] if scenario==15 else [1,0]),thrown
    assert visible==len(commands)-3
    return dict(scenario=scenario,ticks=len(commands),visible=visible,deliveries=thrown,actions=actions,
                original_instructions=original_instructions)


def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp);cpp=folder/'driver.cpp';exe=folder/'driver';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,LIB,'-o',exe],check=True)
        with ProcessPoolExecutor(6) as pool:results=list(pool.map(case,[(exe,i) for i in range(18)]))
        doc=dict(status='passed',elf_sha256=PIN,runtime_sha256=digest(LIB),probe_sha256=digest(exe),validator_sha256=digest(Path(__file__)),
                 scope='Priority-20 1b4138/1b4228, all 15 requested states, both sequential weapon deliveries, source 170480 called unmodified, crossings, gauge delta 128/256, global pause, hidden draw, original AID/ACT51, complete first 78 raw object words before/after the draw and the 82-word submitted record each tick. Input positions and round requests are fixtures. The separate shared world effects helper 1b5e30 has inactive unrelated entries in these cases.',results=results)
    OUT.write_text(json.dumps(doc,indent=2)+'\n');print(len(results),'cases',sum(c['ticks'] for c in results),'EE callback visits matched')


if __name__=='__main__':main()
