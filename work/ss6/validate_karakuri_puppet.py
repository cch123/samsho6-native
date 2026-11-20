#!/usr/bin/env python3
"""Compare all 80 words of character 32's puppet after the original 201b40 task with the native callback.

Fixtures cover modes 0..8 at entry (128 != 12c) and update (128 == 12c), both seats and
facings, owner states that hold the follow (raw 0x18/0x25, table 0) or not, grounded and
airborne owners, finished and running clips, and the 202000 capture predicate (opponent
characters 0x19/0x20 holding the owner in table-2 states 0x51/0x52).
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
#include "karakuri_puppet.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{32,32,51});
    AuxiliaryObject o,body;StateEntryActor owner;unsigned opp;
    while(std::cin>>owner.state194>>owner.flags23c>>opp) {
        for(auto& w:o)std::cin>>w;for(auto& w:body)std::cin>>w;
        owner.character=32;
        try{updateKarakuriPuppet(objects,o,body,owner,opp);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<'\n';
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
    p=fixture((32,32,51));r=random.Random(0x201b40)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,32,4)
        p.write(other+0xa24,1-seat,4)
        for mode in range(9):
            for variant in range(48):
                entry=variant%3==0
                own=[0]*80;o=[0]*80
                owner_mirror=0x80000 if (variant+seat)%2 else 0
                bx=r.choice((160.,245.5,320.,410.25))
                own[0x38//4]=owner_mirror;own[0x40//4]=bits(bx);own[0x44//4]=bits((0.,0.,36.,88.5)[variant%4])
                o[3]=seat;o[4]=seat;o[5]=32;o[0xcc//4]=3;o[9]=0x22f+(variant%5)
                o[14]=0x1000|(0x80000 if variant%5<2 else 0)
                o[16]=bits(bx+r.choice((-60.,-9.,-4.,-0.5,0.,3.25,8.,45.)))
                o[17]=bits((0.,0.,12.5)[variant%3]);o[0x30//4]=256;o[0xc0//4]=variant%2
                o[0x104//4]=(1 if variant%8==3 else 0)|(0x100 if variant%3==1 else 0)|(2 if variant%5==0 else 0)
                o[0x118//4]=a;o[0x128//4]=mode
                o[0x12c//4]=((mode+1+variant%7)%9 if variant%4 else 0xffffffff) if entry else mode
                table,index=[(0,0),(0,0x18),(0,0x25),(1,0x40),(2,0x51),(2,0x52),(2,0x50),(0,1),(2,0x30),(1,0x20)][variant%10]
                st=(index<<16)|table
                flags=(0x1000 if variant%5 else 0)|(0x10 if variant%7 in (1,4) else 0)
                opp=(0x19,0x20,3,0x20)[variant%4]
                p.write(a+0x194,st,4);p.write(a+0x23c,flags,4);p.write(other+0xa10,opp,4)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own)
                p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x201b40,[TASK],limit=60000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                for s,base in enumerate(acts):
                    if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
                expected.append(actual)
                cases.append((seat,mode,variant,entry))
                commands.append(' '.join(map(str,[st,flags,opp,*o,*own])))
    compile_and_compare(DRIVER,'puppet',commands,cases,expected,[])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,modes=list(range(9)),
                scope='Unit fixtures of 201b40 (202000, 201d40, 201bf0, 201e90, 1a3ba8).',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/karakuri-puppet-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
