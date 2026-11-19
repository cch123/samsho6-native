#!/usr/bin/env python3
"""Compare each Hanzō projectile's allocation and callback against the original Japanese ELF."""
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from validate_dash_motion import ASSETS, ELF, PIN, ROOT, digest
from validate_weapon_handling import setup

OUT=ROOT/'outputs/ss6-feasibility/hanzo-projectile-validation.json'
OFF=(*range(0xc,0x70,4),0x70,0x8c,0xb0,0xb4,0xc0,0xc4,0xc8,0xcc,0xd0,0xd4,0x100,0x104,0x108,0x11c)
CASTS=((0x4df478,64,11),(0x4df48c,69,12),(0x4df4a0,88,13),(0x4df4dc,90,135))
# Simultaneous marks exercise the precedence of natural end, boundary,
# contact against the object, hit, block and landing.
EVENTS=((0,0,0,17),(0,0,0,0),(0,0,0,-3),(0,0,1,17),(1,0,1,17),(4,0,0,-3),
        (0x40000,0,0,17),(0x80000,0,0,17),(0x200000,0,0,17),(0x2c0000,0,0,17),
        (0x40000,2,0,17),(0,2,0,17),(0x40004,2,1,-3),(0x40000,0,0,-3))
DRIVER=r'''#include "hanzo_projectile.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects aux(argv[1],{3,3,51});
    unsigned side,phase,state,strength,actorFlags,flags,marks,ended;int height;
    while(std::cin>>side>>phase>>state>>strength>>actorFlags>>flags>>marks>>ended>>height) {
        TaggedTaskPools pools;pools.initializeOwners();pools.initializeTasks();pools.initializeObjects();
        std::array<uint32_t,48> reg{};AuxiliaryObject body{};
        for(auto& value:body)std::cin>>value;
        StateEntryActor actor;actor.character=3;actor.flags23c=actorFlags;actor.state194=(state<<16)|1;
        actor.callbacks260[3]=strength;actor.registry28c[11]=phase;
        spawnHanzoProjectile(aux,pools,reg,side,actor,body);
        auto& t=pools.tasks.at(reg[0]-1);auto& o=pools.objects.at(t[7]-1);
        auto print=[&]{std::cout<<int(hanzoProjectileFlags(o[0xd0/4]))<<' '<<t[0]<<' '<<o[0x118/4];
            for(auto off:OFFSETS)std::cout<<' '<<o[off/4];std::cout<<'\n';};
        print();
        o[0x104/4]=flags|0x140;o[0x100/4]=marks;o[0xc0/4]=ended;
        o[0xc4/4]=0xffffffff;o[0x44/4]=std::bit_cast<uint32_t>(float(height));
        for(unsigned i=0x4c/4;i<0x64/4;++i)o[i]=73+i;
        updateHanzoProjectile(aux,pools,reg[0]);print();
    }
}'''.replace('OFFSETS','{'+','.join(map(str,OFF))+'}')

def samples():
    commands=[];expected=[];ends=Counter();instructions=0;finish={}
    for side in (0,1):
        src,reg=setup(side,3);p,a,o=src.p,src.a,src.o
        for phase,state,id in CASTS:
            for strength in range(3):
                # Keep source allocator state between spawns. For each possible
                # terminal condition restore the same freshly created object.
                actor_flags=0x1000|(0x08000000 if strength==2 else 0)
                state_index=state+strength if state in (64,69) else state
                for off,v in ((0x194,(state_index<<16)|1),(0x26c,strength),(0x2b8,phase),(0x28c,0),(0x23c,actor_flags)):
                    p.write(a+off,v,4)
                for off,v in ((0x104,0x8000),(0x10c,0),(0x110,17),(0x114,13),(0x20,side),(0xc8,0)):
                    p.write(o+off,v,4)
                body=struct.unpack_from('<80I',p.memory,o)
                obj,n=p.run(0x16d9c8,[a],limit=100000);instructions+=n
                task=p.read(obj+4,4)
                assert p.read(obj+0x118,4)==a and p.read(obj+0xd0,4)==id
                cls,n=p.run(0x14dc00,[obj]);instructions+=n
                assert cls==(11 if id==135 else 10)
                initial=p.read(obj+0xc4,4);shared,n=p.run(0x1690b0,[3,initial]);instructions+=n
                assert shared==(initial==724)
                finish[id]=dict(category=cls,owner_hitstop=shared)
                raw=p.memory[obj:obj+320];pc=p.read(task,4)
                def snap():
                    return [p.read(0x4e4b38+12*id+10,1),p.read(task,4),side+1,*[p.read(obj+off,4) for off in OFF]]
                original=snap()
                for flags,marks,ended,height in EVENTS:
                    p.memory[obj:obj+320]=raw
                    p.write(task,pc,4)
                    for off,v in ((0x104,flags|0x140),(0x100,marks),(0xc0,ended),(0xc4,0xffffffff)):
                        p.write(obj+off,v,4)
                    struct.pack_into('<f',p.memory,obj+0x44,float(height))
                    for i in range(0x4c//4,0x64//4):p.write(obj+4*i,73+i,4)
                    _,n=p.run(0x16def0,[task],limit=100000);instructions+=n
                    commands.append((side,phase,state_index,strength,actor_flags,flags,marks,ended,height,*body))
                    expected.extend((original,snap()));next_act=p.read(obj+0xc4,4)
                    if next_act!=0xffffffff:ends[str(next_act)]+=1
    return commands,expected,ends,instructions,finish

def main():
    assert digest(ELF)==PIN
    cases,want,ends,instructions,finish=samples()
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);cpp=folder/'objects.cpp';exe=folder/'objects';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/hanzo_projectile.cpp',
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        data=subprocess.check_output([exe,ASSETS],input=''.join(' '.join(map(str,c))+'\n' for c in cases),text=True)
    raw=[list(map(int,row.split())) for row in data.splitlines()]
    assert len(raw)==len(want)
    for i,(got,expected) in enumerate(zip(raw,want)):
        assert got==expected,(cases[i//2][:9],i%2,[(hex(OFF[k-3]) if k>=3 else k,hex(v),hex(w)) for k,(v,w) in enumerate(zip(got,expected)) if v!=w])
    doc=dict(status='passed',original=PIN,native_source=digest(ROOT/'src/hanzo_projectile.cpp'),casts=CASTS,
             cases=len(cases),native_snapshots=len(want),original_instructions=instructions,terminal_clips=ends,finish_and_hitstop=finish,
             offsets=[hex(off) for off in OFF],scope='Original 16d9c8 allocations from the four script records, 16def0 task visits on both sides and all strengths. Compare the task callback, collision byte, queued ACT, owner, facing, position, motion, terminal flags and precedence across hit, block, clash, expiry and landing.')
    OUT.write_text(json.dumps(doc,indent=2)+'\n');print(doc)

if __name__=='__main__':main()
