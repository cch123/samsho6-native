#!/usr/bin/env python3
"""Compare all 80 words of Mina's companion after the original 1fc750 task with the native callback.

The fixtures cover every Chample state that does not touch a floor item or a
bomb (the item states throw natively until those stage operations are ported),
both seats and facings, owner states that issue automatic commands, the
presentation states with both match outcomes, and the library RNG.
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
#include "chample.hpp"
#include "state_entry.hpp"
#include "stage_item_delivery.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{24,24,51});
    AuxiliaryObject o,body,other;StateEntryActor owner,opponent;StageItemDelivery delivery;
    GameRandom rng;int won,lost;
    while(std::cin>>owner.state194>>owner.flags23c>>owner.fieldA30>>opponent.state194>>won>>lost
                  >>rng.mode>>rng.gameSeed>>rng.librarySeed) {
        for(auto& w:o)std::cin>>w;for(auto& w:body)std::cin>>w;for(auto& w:other)std::cin>>w;
        owner.character=24;
        ChampleWorld world{body,owner,other,opponent,rng,bool(won),bool(lost),&delivery,nullptr};
        try{updateChample(objects,o,world);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<rng.gameSeed<<' '<<rng.librarySeed<<'\n';
    }
}
'''
ITEM_STATES={20,21,22,25,26,27,29}


def main():
    p=fixture((24,24,51));r=random.Random(0x1fc750)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    p.write(0x132c4bc,0xffffffff,4)                 # 1b5960: no floor item
    p.memory[BATTLE+0x14c:BATTLE+0x14c+256]=bytes(256)  # no kind-5 battle object
    reent=p.read(0x5d1bf8,4)
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    states=[s for s in range(43) if s not in ITEM_STATES]+[23,25,27,29]
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,24,4)
        p.write(other,BODY+0x1000,4);p.write(other+0xa24,1-seat,4);p.write(other+0xa10,24,4)
        for state in states:
            for variant in range(24):
                own=[0]*80;opp=[0]*80;o=[0]*80
                owner_mirror=0x80000 if (variant+seat)%2 else 0
                bx=r.choice((160.,245.5,320.,410.25));by=r.choice((0.,0.,36.,88.5))
                own[0x38//4]=owner_mirror;own[0x40//4]=bits(bx);own[0x44//4]=bits(by);own[9]=r.choice((0,185,190,553))
                opp[0x40//4]=bits(r.choice((100.,330.,470.)));opp[0x44//4]=bits(0.)
                near=variant%4
                dx=(0,8.5,40.25,130.)[near]*(1 if variant%3 else -1)
                o[3]=seat;o[4]=seat;o[5]=24;o[0xcc//4]=3;o[9]=769+(variant%7)
                o[14]=0x1000|(0x80000 if variant%5<2 else 0)
                ahead=bx+(-32 if owner_mirror else 32)
                o[16]=bits(ahead+dx if state!=13 else bx+(-30 if variant%2 else 30)*(1 if variant%3 else 0))
                o[17]=bits((0.,0.,12.5,-3.)[variant%4] if state not in (13,19) else (0.,6.,30.)[variant%3])
                o[0x30//4]=256;o[0xc0//4]=variant%2;o[0x104//4]=(1 if variant%8==3 else 0)|(0x100 if variant%3==0 else 0)
                o[0x104//4]|=(0x40000 if variant%6==1 else 0)|(4 if variant%6==2 else 0)
                o[0x50//4]=r.randrange(-0x30000,0x30000)&0xffffffff;o[0x5c//4]=r.randrange(-0x30000,0x30000)&0xffffffff
                o[0x118//4]=a;o[0x128//4]=state
                o[0x12c//4]=(0xffffffff if variant%4==0 else state if variant%4!=3 else 19)
                o[0x130//4]=(0x3c00,300,1)[variant%3];o[0x134//4]=(0xffffffff,823)[variant%2]
                o[0xf4//4]=bits((20.,30.,40.)[variant%3])
                table,index=[(0,0),(0,0),(1,36),(1,82),(1,5),(2,40),(2,10),(0,49),(1,66),(0,48),(1,1),(0,0)][variant%12]
                if state==13 and variant%4!=2:table,index=1,66
                if state==42 and variant%2:table,index=0,48
                st=(index<<16)|table
                flags=(0x1000 if variant%5 else 0)|(8 if variant%7==2 else 0)
                hp=(90,100,150)[variant%3];won=variant%2;lost=(variant//2)%2
                ost=(2 if variant%9==4 else 0)
                mode,game,lib=(0,1,3)[variant%3],r.getrandbits(31),r.getrandbits(48)
                p.write(a+0x194,st,4);p.write(a+0x23c,flags,4);p.write(a+0xa30,hp,4);p.write(other+0x194,ost,4)
                for s,w in ((seat,won),(1-seat,lost)):
                    p.write(BATTLE+0x254+0x108*s+0x28,1+w,4);p.write(BATTLE+0x254+0x108*s+0x2c,2,4)
                p.write(0x443150,mode,4);p.write(0x3d2e80,game,4);p.write(reent+0xa8,lib,8)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own)
                p.memory[BODY+0x1000:BODY+0x1000+320]=struct.pack('<80I',*opp)
                p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x1fc750,[TASK],limit=60000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                for s,base in enumerate(acts):
                    if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
                expected.append(actual+[p.read(0x3d2e80,4),p.read(reent+0xa8,8)])
                cases.append((seat,state,variant))
                commands.append(' '.join(map(str,[st,flags,hp,ost,won,lost,mode,game,lib,*o,*own,*opp])))
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'chample.cpp';exe=tmp/'chample';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    wrong=[]
    for case,line,ref in zip(cases,got,expected,strict=True):
        if line.startswith('X'):wrong.append((case,line));continue
        row=list(map(int,line.split()))
        if row!=ref:wrong.append((case,[(hex(i*4),hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y]))
        counts['state_%d'%case[1]]+=0
    assert not wrong,(len(wrong),wrong[:12])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,states=sorted(set(c[1] for c in cases)),
                scope='Unit fixtures of 1fc750 without floor items or bombs; item states 20..22/25..29 with an item are unported.',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/chample-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
