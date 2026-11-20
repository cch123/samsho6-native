#!/usr/bin/env python3
"""Compare all 80 words of character 33's karuta after the original 203920 task with the native callback.

Fixtures cover modes 0..3 (and an out-of-range mode) at entry and update, both seats and
facings, both variants (130), the floor landing of mode 1, the owner's distance window and
arming checks of mode 2, and the owner's 244 bit 0x200000 / timer 21 written by mode 3.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile

from character_tiles_oracle import ROOT,ASSETS,fixture,bits
from validate_mamahaha import BATTLE,ACTORS,BODY,BIRD,TASK
from extract_collision_tables import SOURCE_HASH

DRIVER=r'''
#include "karuta.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{33,33,51});
    AuxiliaryObject o,body;StateEntryActor owner;StageCamera camera;
    while(std::cin>>owner.state194>>owner.flags23c>>owner.flags244>>owner.timers[21]>>camera.top) {
        for(auto& w:o)std::cin>>w;for(auto& w:body)std::cin>>w;
        owner.character=33;
        try{updateKaruta(objects,o,body,owner,camera);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<owner.flags244<<' '<<uint32_t(owner.timers[21])<<'\n';
    }
}
'''

def compile_and_compare(driver,name,commands,cases,expected,extra):
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/(name+'.cpp');exe=tmp/name;src.write_text(driver)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    wrong=[]
    for case,line,ref in zip(cases,got,expected,strict=True):
        if line.startswith('X'):wrong.append((case,line));continue
        row=list(map(int,line.split()))
        if row!=ref:wrong.append((case,[(hex(i*4) if i<80 else extra[i-80],hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y]))
    assert not wrong,(len(wrong),wrong[:12])


def main():
    p=fixture((33,33,51));r=random.Random(0x203920)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    stage=p.run(0x140040)[0]
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,33,4)
        for mode in (0,1,2,3,5):
            for variant in range(64):
                entry=variant%3==0
                own=[0]*80;o=[0]*80
                owner_mirror=0x80000 if (variant+seat)%2 else 0
                bx=r.choice((160.,245.5,320.,410.25))
                own[0x38//4]=owner_mirror;own[0x40//4]=bits(bx);own[0x44//4]=bits((0.,0.,0.,36.)[variant%4])
                px=bx+(40. if owner_mirror else -40.)
                o[3]=seat;o[4]=seat;o[5]=33;o[0xcc//4]=3;o[9]=0x235+(variant%6)
                o[14]=0x1000|(0x80000 if variant%5<2 else 0)
                o[16]=bits(px+r.choice((-30.,-24.,-23.5,0.,12.,24.,24.5,60.)))
                o[17]=bits((0.,-0.,12.5,-3.,0.)[variant%5]);o[0x30//4]=256
                o[0xc0//4]=variant%2;o[0x104//4]=(1 if variant%8 in (3,6) else 0)|(4 if variant%3!=1 else 0)|(0x100 if variant%4==2 else 0)|(2 if variant%5==0 else 0)
                o[0x118//4]=a;o[0x128//4]=mode;o[0x130//4]=variant%2
                o[0x12c//4]=((mode+1+variant%5)%4 if variant%4 else 0xffffffff) if entry else mode
                table,index=[(0,0),(0,0),(1,0x40),(2,0x20),(0,1)][variant%5]
                st=(index<<16)|table
                flags=(0x1000 if variant%6 else 0)
                f244=(0x200000 if variant%7==3 else 0)|0x10;t21=(0,0x500)[variant%2]
                top=(240,200)[variant%2]
                p.write(a+0x194,st,4);p.write(a+0x23c,flags,4);p.write(a+0x244,f244,4);p.write(a+0x1b0+21*4,t21,4)
                p.write(stage+0x1c,top,4)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own)
                p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x203920,[TASK],limit=60000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                for s,base in enumerate(acts):
                    if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
                expected.append(actual+[p.read(a+0x244,4),p.read(a+0x1b0+21*4,4)])
                cases.append((seat,mode,variant,entry))
                commands.append(' '.join(map(str,[st,flags,f244,t21,top,*o,*own])))
    compile_and_compare(DRIVER,'karuta',commands,cases,expected,['244','timer21'])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,modes=[0,1,2,3,5],
                scope='Unit fixtures of 203920 (2039a8, 203b20, 1a3ba8) with the owner 244 / timer 21 writes.',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/karuta-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
