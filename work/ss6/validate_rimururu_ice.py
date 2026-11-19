#!/usr/bin/env python3
"""Compare each original 16e2c8/16e3b8 attachment with native ice/damage overlays."""
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ASSETS,ELF,PIN,ROOT,digest
from validate_weapon_handling import setup

OUT=ROOT/'outputs/ss6-feasibility/rimururu-ice-validation.json'
OFF=(0xc,0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x38,0x40,0x44,0x70,0xb0,0xc0,0xc4,0xcc,
     0xec,0xf0,0x104,0x108,0x128,0x12c,0x130,0x134)
DRIVER=r"""
#include "contact_presentation.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    ActionBank bank(argv[1],true);AuxiliaryObjects aux(argv[1],{0,0,51});
    unsigned seat,character,element,airborne,change,seed;
    while(std::cin>>seat>>character>>element>>airborne>>change>>seed) {
        BattleRoundState b;
        auto& pools=b.entry.tasks;pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
        b.random.mode=2;b.random.gameSeed=seed;b.random.librarySeed=seed;
        std::array<StateEntryActor,2> actors;
        std::array<PlayerObject,2> bodies{PlayerObject(bank),PlayerObject(bank)};
        std::array<ActorCommandInput,2> inputs{};std::array<InputSystemConfig,2> configs{};
        std::array<RoundActorStorage,2> storage{};std::array<CallbackContext,2> ctx{};
        const std::array<RoundPlayerRef,2> refs{{
            {bodies[0],actors[0],inputs[0],configs[0],storage[0],ctx[0]},
            {bodies[1],actors[1],inputs[1],configs[1],storage[1],ctx[1]}}};
        auto& a=actors[seat];auto& body=bodies[seat];
        a.character=character;a.state194=(35<<16)|2;a.landingCount253=3;a.contactKind252=element;
        a.flags23c=0x1000|(airborne<<4);a.queuedActionA3c=-1;
        auto c=body.timeline.clock();c.objectFlags=0x10000000|(seat<<19);body.timeline.setObjectFlags(c.objectFlags,0,0);
        body.timeline.setPosition(220.75f,airborne?55.5f:0.f);
        spawnElementHurt(aux,b,seat,body,a);
        const auto task=b.objectTasks[0];
        auto print=[&] {
            std::cout<<b.random.gameSeed<<' '<<b.random.librarySeed;
            for(auto h:b.objectTasks)if(h) {
                auto& t=pools.tasks.at(h-1);auto& o=pools.objects.at(t[7]-1);
                std::cout<<' '<<t[0]<<' '<<o[0x118/4];
                for(unsigned offset:OFFSETS)std::cout<<' '<<o[offset/4];
            }
            std::cout<<'\n';
        };
        print();updateElementHurt(aux,b,task,refs);print();
        // The original fragments read the current victim facing. Their source
        // position is the prior overlay's position; deliberately separate both.
        auto& object=pools.objects.at(pools.tasks.at(task-1)[7]-1);
        object[0x40/4]=std::bit_cast<uint32_t>(303.625f);
        object[0x44/4]=std::bit_cast<uint32_t>(76.875f);
        c.objectFlags^=0x80000;body.timeline.setObjectFlags(c.objectFlags,0,0);
        if(change==1)++a.landingCount253;
        if(change==2)a.state194=(36<<16)|2;
        if(change==3)body.timeline.setPosition(222,-1);
        if(change==4)a.state194=0;
        updateElementHurt(aux,b,task,refs);print();
    }
}
""".replace('OFFSETS','{'+','.join(map(str,OFF))+'}')


def original(args):
    seat,character,element,airborne,change,seed=args
    # Only the supplied character ID/position affect these common-bank
    # constructors. Retain the real allocator and both common effect tables.
    src,_=setup(seat)
    p,a,body,battle=src.p,src.a,src.o,src.b
    for name,at in [('aid',0x46a9b0+2*0x1800),('act',0x1a60000)]:
        data=(ASSETS/f'{name}_51.bin').read_bytes()
        p.memory[at:at+len(data)]=data
    reg=battle+0x14c
    p.write(0x4751b8,0x1a60000,4);p.write(0x46a9a8,51,4)
    p.memory[reg:reg+256]=bytes(256)
    p.write(a+0xa10,character,4);p.write(a+0x194,(35<<16)|2,4)
    p.write(a+0x198,0xffff,2);p.write(a+0x252,element,1);p.write(a+0x253,3,1)
    p.write(a+0x23c,0x1000|(airborne<<4),4);p.write(a+0xa3c,-1,4)
    p.write(body+0x38,0x10000000|(seat<<19),4);p.write(body+0x3c,0,4);p.write(body+0xc0,0,4)
    p.write(body+0x104,0,4)
    struct.pack_into('<2f',p.memory,body+0x40,220.75,55.5 if airborne else 0)
    p.write(0x443150,2,4);p.write(0x3d2e80,seed,4)
    libc=p.read(0x5d1bf8,4)+0xa8;p.write(libc,seed,8)
    src.run(0x16e2c8,a,element,35)
    task=p.read(reg,4);obj=p.read(task+0x1c,4)
    def snap():
        v=[p.read(0x3d2e80,4),p.read(libc,8)]
        for h in struct.unpack_from('<64I',p.memory,reg):
            if h:
                o=p.read(h+0x1c,4)
                assert p.read(o+0x118,4)==a
                v.extend([p.read(h,4),seat+1,*[p.read(o+off,4) for off in OFF]])
        return v
    out=[snap()]
    src.run(0x16e3b8,task);out.append(snap())
    struct.pack_into('<2f',p.memory,obj+0x40,303.625,76.875)
    p.write(body+0x38,p.read(body+0x38,4)^0x80000,4)
    if change==1:p.write(a+0x253,4,1)
    elif change==2:p.write(a+0x194,(36<<16)|2,4)
    elif change==3:struct.pack_into('<2f',p.memory,body+0x40,222,-1)
    elif change==4:p.write(a+0x194,0,4)
    src.run(0x16e3b8,task);out.append(snap())
    return out,src.instructions


def main():
    assert digest(ELF)==PIN
    cases=[(seat,character,element,airborne,exit,seed) for seat,character in ((0,2),(1,2),(0,0),(1,1))
           for element in (3,5) for airborne in (0,1) for exit,seed in ((1,1),(2,5),(3,9),(4,21))]
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);cpp=tmp/'ice.cpp';cpp.write_text(DRIVER);exe=tmp/'ice';src=ROOT/'src'
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',src,cpp,src/'contact_presentation.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input=''.join(' '.join(map(str,q))+'\n' for q in cases),text=True)
    rows=iter(got.splitlines());instructions=0;shattered=0
    for case in cases:
        expected,n=original(case);instructions+=n
        for phase,want in enumerate(expected):
            line=list(map(int,next(rows).split()))
            assert line==want,(case,phase,len(line),len(want),[(i,hex(x),hex(y)) for i,(x,y) in enumerate(zip(line,want)) if x!=y][:10])
        count=(len(want)-2)//(len(OFF)+2)
        if count>1:
            assert count==5 and case[2]==5
            assert [want[2+(len(OFF)+2)*i+2+OFF.index(0xc4)] for i in range(1,5)]==[12,13,14,15]
            shattered+=1
    assert next(rows,None) is None and shattered
    doc=dict(passed=True,source=PIN,cases=len(cases),snapshots=3*len(cases),shattered=shattered,
             original_instructions=instructions,object_fields=list(map(hex,OFF)),
             scope='Two allocated sides, 3 character anchors, both element 3/5 tables, air/ground, generation replacement, state replacement, landing, leaving damage. Compares all four newly allocated fragments, RNG and pending ACT against full original 16e2c8 and 16e3b8 routines.')
    OUT.write_text(json.dumps(doc,indent=2)+'\n')
    print(doc)

if __name__=='__main__':main()
