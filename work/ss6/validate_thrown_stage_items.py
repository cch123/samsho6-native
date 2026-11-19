#!/usr/bin/env python3
"""Compare complete common-bank item callbacks and the visible ACTs with the Japanese executable."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory

from character_tiles_oracle import ROOT, ASSETS, bits, fixture
from extract_collision_tables import SOURCE_HASH
from validate_native_scene import compare, DRIVER as RENDERER, LIB
from validate_object_pools import OBJECTS, TASKS, handle

BATTLE, ACTORS, BODY, CONTEXT = 0x900000, 0xa00000, 0xb00000, 0xb10000
DRAW = 0x479250
CPP = r"""
#include "thrown_stage_item.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
void out(uint32_t value){std::cout.write(reinterpret_cast<const char*>(&value),4);}
int main(int argc,char** argv){
    AuxiliaryObjects runtime(argv[1],{1,1,51});runtime.setSoundObserver([](auto,const auto&){return -1;});
    ActionBank bank(argv[1],true,1);unsigned item,seat,mode;
    while(std::cin>>item>>seat>>mode){
        TaggedTaskPools p;p.initializeTasks();p.initializeObjects();std::array<uint32_t,48> own{};std::array<uint32_t,64> shared{};
        PlayerObject body(bank,154);body.resourceSlot0c=body.ownerCC=seat;
        for(int i=0;i<6;++i)body.animate(256);
        if(body.timeline.attachedEffect()[1]!=64||body.timeline.attachedEffect()[2]!=54)return 2;
        body.timeline.setPosition(seat?400:240,0);
        body.timeline.setObjectFlags(0x10000000u|seat<<19,0x8000,0);
        GaugeState g;uint32_t jump=0;AuxiliaryObject parent=body.childParentWords();
        AuxiliaryFrame f{g,jump,0,{{{&parent,0x1000,0,0},{&parent,0x1000,0,0}}}};
        auto registry=item==8?std::span<uint32_t>(shared):std::span<uint32_t>(own);
        if(item==8)spawnStageBomb(runtime,p,shared,320.f);
        else throwStageItem(runtime,p,own,shared,seat,item,0x1000,body);
        unsigned tick=0;
        do {
            ObjectDrawQueue q;
            if(tick){
                runtime.updateRegistry(p,registry,f);
                if(item==8&&((mode==1&&tick==20)||(mode==2&&tick==172)))throwStageItem(runtime,p,own,shared,seat,item,0x1000,body);
                runtime.visitRegistry(p,registry,[&](auto t){
                    auto& task=p.tasks.at(t-1);auto& o=p.objects.at(task[7]-1);
                    if(item!=8&&tick==5){
                        if(mode==1)o[0x104/4]|=0x40000;
                        if(mode==2)o[0x104/4]|=0x80000;
                        if(mode==3)o[0x100/4]|=2;
                        if(mode==4)o[0x104/4]|=4;
                    }
                    if(task[0]==0x147540)runtime.releaseHold(p,t);
                    else updateThrownStageItem(runtime,p,t);
                });
            }
            runtime.drawRegistry(p,registry,f,q);
            out(q.count);
            for(auto t:registry)if(t){
                const auto& task=p.tasks.at(t-1);out(task[0]);
                for(auto v:p.objects.at(task[7]-1))out(v);
            }
            out(0);++tick;
            if(tick>360)return 3;
        }while(registry[0]);
    }
}
"""


def compile_probe(tmp, name, source, extra=()):
    cpp=tmp/(name+'.cpp'); exe=tmp/name; cpp.write_text(source)
    subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',cpp,*extra,LIB,'-o',exe],check=True)
    return exe


def setup(p,seat):
    for at,n in ((BATTLE,0x800),(ACTORS,2*0xf2c),(BODY,320),(CONTEXT,32),(OBJECTS,320*256)):
        p.memory[at:at+n]=bytes(n)
    p.run(0x112570);p.run(0x11e290)
    for at,w in ((0x4d3d00,BATTLE),(0x4d3d08,ACTORS),(0x46a908,256),(0x4c3808,3),(0x443150,3),(0x132c398,bits(320))):
        p.write(at,w,4)
    p.memory[0x46a910:0x46a944]=bytes(52)
    for i in range(2):
        actor=ACTORS+i*0xf2c
        for off,w in ((0,BODY),(0xa24,i),(0xa10,1),(0x23c,0x1000)):
            p.write(actor+off,w,4)
        p.write(BATTLE+0x24c+i*4,actor,4)
    for off,w in ((0xc,seat),(0x10,seat),(0x14,1),(0x18,1),(0x1c,5),(0x30,256),
                  (0x38,0x10000000|seat<<19),(0x40,bits(400 if seat else 240)),
                  (0x70,bits(1)),(0xc8,1),(0xcc,seat),(0x104,0x8000),(0x110,64),(0x114,54)):
        p.write(BODY+off,w,4)
    p.write(CONTEXT,ACTORS+seat*0xf2c,4)
    p.write(CONTEXT+4,BODY,4)


def run():
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    p=fixture((1,1,51));counts=Counter();images={};metadata={}
    cases=[(item,seat,mode) for item in range(7,19) for seat in (0,1) for mode in range(3 if item==8 else 5)]
    with TemporaryDirectory() as td:
        tmp=Path(td)
        exe=compile_probe(tmp,'items',CPP,[ROOT/'src'/f for f in ('thrown_stage_item.cpp','auxiliary_objects.cpp','auxiliary_frame.cpp')])
        with (tmp/'results').open('w+b') as native:
            subprocess.run([exe,ASSETS],input=''.join(f'{i} {s} {m}\n' for i,s,m in cases).encode(),stdout=native,check=True)
            native.seek(0)
            def word():return struct.unpack('<I',native.read(4))[0]
            def call(pc,args=()):
                value,n=p.run(pc,list(args),limit=100000);counts['instructions']+=n;return value
            for item,seat,mode in cases:
                setup(p,seat); shared=BATTLE+0x14c;reg=shared if item==8 else BATTLE+0x29c+seat*0x108
                size=64 if item==8 else 48;p.write(BODY+0x128,item,4)
                if item==8:
                    p.write(0x132c4bc,8,4);call(0x141568);assert p.read(0x132c4bc,4)==0xffffffff
                else:call(0x16c2b0,[CONTEXT])
                for tick in range(361):
                    call(0x1207d8)
                    if tick:
                        call(0x147028,[reg,size])
                        if item==8 and ((mode==1 and tick==20) or (mode==2 and tick==172)):
                            call(0x16c2b0,[CONTEXT])
                        if item!=8 and tick==5 and mode:
                            o=p.read(p.read(reg,4)+28,4)
                            off,mask=((0x104,0x40000),(0x104,0x80000),(0x100,2),(0x104,4))[mode-1]
                            p.write(o+off,p.read(o+off,4)|mask,4)
                        call(0x146ef8,[reg,size])
                    call(0x1470a8,[reg,size])
                    n=p.read(0x4a2250,4)
                    assert n==word(),(item,seat,mode,tick,'queue',n)
                    for i in range(size):
                        t=p.read(reg+i*4,4)
                        if not t:continue
                        assert word()==p.read(t,4)
                        o=p.read(t+28,4);expected=list(struct.unpack_from('<80I',p.memory,o))
                        expected[1]=handle(expected[1],TASKS,52)
                        expected[0xbc//4]-=0x1c00000-1
                        if expected[0x118//4]:expected[0x118//4]=(expected[0x118//4]-ACTORS)//0xf2c+1
                        got=struct.unpack('<80I',native.read(320))
                        assert list(got)==expected,(item,seat,mode,tick,[(hex(j*4),hex(a),hex(b)) for j,(a,b) in enumerate(zip(got,expected)) if a!=b])
                        counts['object_rows']+=1
                    assert word()==0
                    if n:
                        assert n==1
                        row=list(struct.unpack_from('<82I',p.memory,DRAW))
                        key=(row[9],row[10],bool(row[14]&0x40000000))
                        if key not in images:
                            images[key]=row
                        if item==8 and mode==0 and seat==0 and tick in (0,30,120,179,180):
                            metadata[str(tick)]=[row[9],row[10],hex(row[35])]
                    counts['frames']+=1
                    if not p.read(reg,4):break
                else:raise AssertionError(('item persisted',item,seat,mode))
                counts['cases']+=1
            assert native.read()==b''
        # Render one representative record per flight, disappearance, ground
        # bomb/flash, launch, bounce and detonation. All records above were
        # submitted by the original 1470a8 in the same register-pool mode.
        samples={}
        for key,row in images.items():
            action,step,flash=key
            pose=(action,step,flash) if action in (55,56,76) else action
            samples.setdefault(pose,row)
        verify_images(tmp,samples,counts)
    out=ROOT/'outputs/ss6-feasibility/thrown-stage-items-validation.json'
    report={'status':'passed','source_elf_sha256':SOURCE_HASH,'runtime_sha256':sha256(LIB.read_bytes()).hexdigest(),'counts':dict(counts),'item_ids':list(range(7,19)),
            'actions':sorted({k[0] for k in images}), 'ground_bomb':metadata}
    out.write_text(json.dumps(report,indent=2)+'\n');print(report)


def verify_images(tmp,samples,counts):
    # Compare completely independent 1208b0 packets, texture uploads and
    # color tables against the normal native renderer over a constant field.
    renderer=compile_probe(tmp,'renders',RENDERER)
    commands=['objects 0 0 0 0 1 '+' '.join(map(str,row)) for row in samples.values()]
    p=fixture((0,0,51))
    stats=Counter()
    with (tmp/'pixels').open('w+b') as data:
        subprocess.run([renderer,ASSETS],input=('\n'.join(commands)+'\n').encode(),stdout=data,check=True);data.seek(0)
        for k in samples:
            compare(p,data,stats,str(k));counts['pixel_frames']+=1
        assert not data.read(1)
    counts['sprite_quads']=stats['quads']


if __name__=='__main__':run()
