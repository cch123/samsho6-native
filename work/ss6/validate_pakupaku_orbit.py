#!/usr/bin/env python3
"""Compare PakuPaku's (47) orbiting objects after the original task callbacks 16ee10 / 16ee80 with the native port.

Each fixture runs one callback visit: the 16ee10 phase switch to ACT 0x24f (start ACT ended, nothing
pending) and the 16ee98 placement from the owner's history samples 1..4 (owner + a80 / a84 + 20 * i).
Fixtures cover both callbacks, all four orbit slots, both seats, the ACT-end and pending-request
gates, both accumulators across their wrap points (including negative values and deltas), and
both depth halves. The task word 0 and all 80 object words are compared.
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
#include "pakupaku_orbit.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{47,47,51});AngleTrig trig(argv[1]);
    AuxiliaryObject o;ActorHistory history;uint32_t callback;
    while(std::cin>>callback) {
        for(auto& w:o)std::cin>>w;
        for(unsigned k=1;k<=4;++k){uint32_t x,y;std::cin>>x>>y;history.samples[k].x=std::bit_cast<float>(x);history.samples[k].y=std::bit_cast<float>(y);}
        try{updatePakuOrbit(objects,o,callback,history,trig);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<callback<<'\n';
    }
}
'''

def compile_and_compare(commands,cases,expected):
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'orbit.cpp';exe=tmp/'orbit';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    wrong=[]
    for case,line,ref in zip(cases,got,expected,strict=True):
        if line.startswith('X'):wrong.append((case,line));continue
        row=list(map(int,line.split()))
        if row!=ref:wrong.append((case,[(hex(i*4) if i<80 else 'task0',hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y]))
    assert not wrong,(len(wrong),wrong[:12])


def main():
    p=fixture((47,47,51));r=random.Random(0x16ee98)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    deltas=(0,1,128,255,256,257,512,1024,0x7f00,-256,-1)
    angles=(0,1,255,256,0x167ff,0x16800,0x16801,0x2d000,-1,-256,-0x16800,0x7fffff00)
    bounces=(0,255,256,90*256-1,90*256,0xb3ff,0xb400,0xb401,-1,-0x5a00,0x7fffff00)
    for seat in range(2):
        a=ACTORS+seat*0xf2c
        p.write(a,BODY,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,47,4)
        for case in range(2048):
            callback=(0x16ee10,0x16ee80)[case%2]
            o=[0]*80
            o[1]=TASK;o[3]=seat;o[4]=seat;o[5]=47;o[0xcc//4]=6;o[0xd0//4]=0xa8;o[9]=(0x24e,0x24f)[case%2]
            o[14]=0x1000|(0x80000 if case%5<2 else 0)
            o[16]=bits(r.uniform(0,640));o[17]=bits(r.uniform(0,200))
            o[0xc0//4]=(case>>1)%2;o[0x104//4]=(1 if (case>>2)%3==0 else 0)|(0x20000 if case%7==0 else 0)
            o[0x108//4]=0x200000|(0x40000 if case%11==0 else 0)
            o[0xb0//4]=bits(r.choice((0.,20.,40.)))
            o[0x30//4]=r.choice(deltas)&0xffffffff if case%3 else 256
            o[0x118//4]=a;o[0x128//4]=(case>>3)%4
            o[0x12c//4]=(r.choice(angles) if case%4 else r.randrange(0,0x16800))&0xffffffff
            o[0x130//4]=(r.choice(bounces) if case%4 else r.randrange(0,0xb400))&0xffffffff
            hist=[]
            for k in range(1,5):
                x=r.choice((r.uniform(-50,700),320.,0.,-0.,123.456))
                y=r.choice((r.uniform(-20,300),0.,48.5))
                hist+= [bits(x),bits(y)]
                p.write(a+0xa60+20*k+0xc,bits(x),4);p.write(a+0xa60+20*k+0x10,bits(y),4)
            p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
            p.write(TASK,callback,4)
            _,n=p.run(callback,[TASK],limit=60000);counts['ee_instructions']+=n
            actual=list(struct.unpack_from('<80I',p.memory,BIRD))
            for s,base in enumerate(acts):
                if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
            expected.append(actual+[p.read(TASK,4)])
            cases.append((seat,case,hex(callback)))
            commands.append(' '.join(map(str,[callback,*o,*hist])))
    compile_and_compare(commands,cases,expected)
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,
                scope='Unit fixtures of 16ee10 / 16ee80 -> 16ee98 -> 11dff8 (one visit each) with the owner history samples 1..4.',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/pakupaku-orbit-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
