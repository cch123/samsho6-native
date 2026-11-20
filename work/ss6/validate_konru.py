#!/usr/bin/env python3
"""Compare all 80 object words after Rimururu's original companion task with the native callback."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from character_tiles_oracle import ROOT,ASSETS,fixture,bits
from validate_mamahaha import BATTLE,ACTORS,BODY,BIRD,TASK
from extract_collision_tables import SOURCE_HASH

DRIVER=r'''
#include "konru.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{2,2,51});
    AuxiliaryObject spirit,body;
    StateEntryActor owner;
    unsigned other,otherAction;
    while(std::cin>>owner.state194>>other>>otherAction) {
        for(auto& w:spirit)std::cin>>w;
        for(auto& w:body)std::cin>>w;
        updateKonru(objects,spirit,body,owner,other,otherAction);
        for(auto w:spirit)std::cout<<w<<' ';
        std::cout<<'\n';
    }
}
'''


def main():
    p=fixture((2,2,51));p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    expected=[];commands=[];cases=[];counts=Counter()
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,2,4)
        p.write(other,BODY+0x1000,4)
        for cycle in range(60):
            for variant in range(8):
                own=[0]*80;o=[0]*80
                ownerAct=(0,0,497,497,501,501,0,0)[variant]
                state=0x300000 if variant==6 else 0
                otherId=33 if variant==1 else 2;otherAct=(576,577)[cycle%2]
                mirror=0x80000 if seat else 0
                own[9]=ownerAct;own[14]=mirror;own[16]=bits(320);own[17]=bits(36)
                offsetX,offsetY={0:(-50,64),497:(27,82),501:(108,70)}[ownerAct]
                near=cycle%3==0
                o[16]=bits(320+(-offsetX if seat else offsetX) if near else 120.25+cycle)
                o[17]=bits((0 if otherId==33 else 36)+offsetY if near else 120.5)
                o[3]=seat;o[4]=seat;o[5]=2;o[0xcc//4]=3;o[9]=771 if variant==7 else 773;o[14]=mirror
                o[0x50//4]=0xfffe0010;o[0x5c//4]=0x12045;o[0x104//4]=2 if variant in (1,3) else 0
                o[0x118//4]=a;o[0x128//4]=35640+6*cycle
                p.write(a+0x194,state,4);p.write(other+0xa10,otherId,4);p.write(BODY+0x1000+0x24,otherAct,4)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own);p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x1ee110,[TASK],limit=30000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                if 0x1b00000<=actual[47]<0x1d00000:actual[47]-=0x1b00000+seat*0x80000-1
                expected.append(actual);cases.append((seat,cycle,variant))
                commands.append(' '.join(map(str,[state,otherId,otherAct,*o,*own])))
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'konru.cpp';exe=tmp/'konru';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
        for case,line,ref in zip(cases,got,expected,strict=True):
            row=list(map(int,line.split()))
            assert row==ref,(case,[(hex(i*4),hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,hover_phases=60,**counts)
    (ROOT/'outputs/ss6-feasibility/konru-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)

if __name__=='__main__':main()

