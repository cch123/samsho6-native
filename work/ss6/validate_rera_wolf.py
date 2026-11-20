#!/usr/bin/env python3
"""Compare all 80 words of Rera's wolf Shikuru after the original 1f96a0 task with the native callback.

Fixtures cover wolf states 0..27 at entry and update, both seats and facings, the owner flags
that drive riding (800000), mounting (1000000), crouching (8), the near-owner automatic state 11
(23c bit 4 and attack index >= 0x20), the opponent side read by states 12/13, the match outcome
and life read by states 20/22, and the airborne/landing paths.
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
#include "rera_wolf.hpp"
#include "state_entry.hpp"
#include "command_input.hpp"
#include "stage_camera.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{19,19,51});
    AuxiliaryObject o,body,other;StateEntryActor owner;ActorCommandInput input;StageCamera camera;
    int won,lost;
    while(std::cin>>owner.state194>>owner.flags23c>>owner.fieldA30>>won>>lost>>camera.left>>camera.right>>camera.top) {
        for(unsigned n=91;n<=96;++n)std::cin>>input.sampledFeatures[n];
        for(auto& w:o)std::cin>>w;for(auto& w:body)std::cin>>w;for(auto& w:other)std::cin>>w;
        owner.character=19;
        const ReraWolfWorld world{body,owner,other,bool(won),bool(lost)};
        try{updateReraWolf(objects,o,world);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<'\n';
    }
}
'''
ALLOCATING=set()
SHOOTING=set()


def main():
    p=fixture((19,19,51));r=random.Random(0x1f96a0)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    stage=p.run(0x140040)[0]
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,19,4)
        p.write(other,BODY+0x1000,4);p.write(other+0xa24,1-seat,4);p.write(other+0xa10,19,4)
        for state in range(28):
            for variant in range(48):
                entry=variant%3!=0 and state not in ALLOCATING
                own=[0]*80;opp=[0]*80;o=[0]*80
                owner_mirror=0x80000 if (variant+seat)%2 else 0
                bx=r.choice((160.,245.5,320.,410.25));by=r.choice((0.,0.,36.,88.5))
                own[0x38//4]=owner_mirror;own[0x40//4]=bits(bx);own[0x44//4]=bits(by);own[0xb0//4]=bits(30.)
                opp[0x40//4]=bits(r.choice((100.,330.,470.)));opp[0x44//4]=bits(0.)
                near=variant%4
                dx=(0,8.5,40.25,130.,79.5,121.)[variant%6]*(1 if variant%3 else -1)
                o[3]=seat;o[4]=seat;o[5]=19;o[0xcc//4]=3;o[9]=0x301+(variant%7)
                o[14]=0x1000|(0x80000 if variant%5<2 else 0)
                follow=bx+(40 if owner_mirror else -40)
                o[16]=bits(follow+dx)
                o[17]=bits((0.,0.,12.5,-3.,0.,-0.)[variant%6])
                o[0x30//4]=256;o[0xc0//4]=variant%2
                o[0x104//4]=(1 if variant%8==3 else 0)|(0x100 if variant%3==0 and state not in SHOOTING else 0)
                o[0x104//4]|=(0x40000 if variant%6==1 else 0)|(0x80000 if variant%6==2 else 0)|(0x200000 if variant%6==3 else 0)
                o[0x100//4]=(2 if variant%7==4 else 0)
                o[0x50//4]=r.randrange(-0x30000,0x30000)&0xffffffff;o[0x5c//4]=r.randrange(-0x30000,0x30000)&0xffffffff
                o[0x118//4]=a;o[0x128//4]=state
                o[0x12c//4]=(0xffffffff if variant%4==1 else (8 if variant%5==2 else (state+1)%28)) if entry else state
                
                table,index=[(0,0),(0,0),(1,0x24),(1,0x40),(0,0x31),(2,40),(1,0x49),(0,1),(1,0x50),(0,48),(1,1),(0,0x30)][variant%12]
                st=(index<<16)|table
                if state==26 and variant%2:st=0x300000
                if state==26 and variant%4==1:st=0x300000
                flags=(0x1000 if variant%5 else 0)|(8 if variant%7==2 else 0)|(4 if variant%3==1 else 0)|(0x800000 if variant%9==4 else 0)|(0x1000000 if variant%10==7 else 0)|(0x10 if variant%13==6 else 0)
                hp=(90,100,150)[variant%3];won=variant%2;lost=(variant//2)%2
                held=[1 if (variant+k)%6==0 else 0 for k in range(6)]
                left,right,top=(160,480,240) if variant%2 else (120,440,200)
                p.write(a+0x194,st,4);p.write(a+0x23c,flags,4);p.write(a+0xa30,hp,4)
                for n,h in zip(range(91,97),held):p.write(a+0x2c4+4*n,h,4)
                for off,v in ((0x10,left),(0x14,right),(0x1c,top)):p.write(stage+off,v,4)
                for s,w in ((seat,won),(1-seat,lost)):
                    p.write(BATTLE+0x254+0x108*s+0x28,1+w,4);p.write(BATTLE+0x254+0x108*s+0x2c,2,4)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own)
                p.memory[BODY+0x1000:BODY+0x1000+320]=struct.pack('<80I',*opp)
                p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x1f96a0,[TASK],limit=60000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                for s,base in enumerate(acts):
                    if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
                expected.append(actual)
                cases.append((seat,state,variant,entry))
                commands.append(' '.join(map(str,[st,flags,hp,won,lost,left,right,top,*held,*o,*own,*opp])))
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'pet.cpp';exe=tmp/'pet';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    wrong=[]
    for case,line,ref in zip(cases,got,expected,strict=True):
        if line.startswith('X'):wrong.append((case,line));continue
        row=list(map(int,line.split()))
        if row!=ref:wrong.append((case,[(hex(i*4),hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y]))
    assert not wrong,(len(wrong),wrong[:12])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,states=list(range(28)),
                scope='Unit fixtures of 1f96a0 (1fa138, 1fa1d8, 1f9938, 1f9808, 1f9cf8, 1a3ba8).',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/rera-wolf-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
