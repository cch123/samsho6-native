#!/usr/bin/env python3
"""Compare all 80 words of Kazuki's fire after the original 1f7318 task (1f76a0 once launched) with the native one.

Fixtures cover the orbit at every fire level and angle phase, the launched homing flight
(134 == 1) with and without the opponent's active concentration (142120), its expiry paths
(timer, wall/ground contact, 100 bit 2) and the spent state (134 == 2), level stepping in
1f7520 from every visible level including the appearing case, and 14ac90 (opponent 33
holding the owner with ACT 0x240/0x241). The owner's fire level f15 is compared afterwards.
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
#include "kazuki_fire.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    AuxiliaryObjects objects(argv[1],{16,16,51});AngleTrig trig(argv[1]);
    AuxiliaryObject o,body,other;StateEntryActor owner;
    unsigned level,held,conc;
    while(std::cin>>level>>held>>conc) {
        for(auto& w:o)std::cin>>w;for(auto& w:body)std::cin>>w;for(auto& w:other)std::cin>>w;
        owner.character=16;owner.characterBytesF14[1]=uint8_t(level);
        const KazukiFireWorld world{body,owner,other,bool(held),bool(conc),trig};
        try{updateKazukiFire(objects,o,world);}catch(const std::exception& e){std::cout<<"X "<<e.what()<<'\n';continue;}
        for(auto w:o)std::cout<<w<<' ';
        std::cout<<unsigned(owner.characterBytesF14[1])<<'\n';
    }
}
'''


def main():
    p=fixture((16,16,51));r=random.Random(0x1f7318)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4);p.write(TASK+28,BIRD,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    acts=[p.read(0x4751b0+4*s,4) for s in range(2)]
    expected=[];commands=[];cases=[];counts=Counter()
    for seat in range(2):
        a=ACTORS+seat*0xf2c;other=ACTORS+(1-seat)*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa24,seat,4);p.write(a+0xa10,16,4)
        p.write(other,BODY+0x1000,4);p.write(other+0xa24,1-seat,4)
        for launched in (0,1,2):
            for variant in range(160):
                own=[0]*80;opp=[0]*80;o=[0]*80
                level=variant%4
                owner_mirror=0x80000 if (variant+seat)%2 else 0
                bx=r.choice((160.,245.5,320.,410.25));by=r.choice((0.,0.,36.,88.5))
                own[0x38//4]=owner_mirror;own[0x40//4]=bits(bx);own[0x44//4]=bits(by)
                held=variant%9==4
                opp_char=0x21 if held or variant%7==1 else (3 if variant%2 else 12)
                opp[0x40//4]=bits(r.choice((100.,330.,470.)));opp[0x44//4]=bits((0.,40.,90.)[variant%3])
                opp[0x24//4]=(0x240 if variant%2 else 0x241) if held else 0x1d4
                conc=launched==1 and variant%5==2
                o[3]=seat;o[4]=seat;o[5]=16;o[0xcc//4]=3;o[9]=0x251+(variant%5)
                o[14]=0x1000|(0x80000 if variant%6<3 else 0)
                o[16]=bits(bx+r.choice((-90.,-40.,0.,35.5,120.)));o[17]=bits(by+r.choice((10.,64.,140.)))
                o[0x30//4]=256;o[0xc0//4]=variant%2
                o[0x104//4]=(1 if variant%8==3 else 0)|(0x40000 if variant%10==6 else 0)|(0x200000 if variant%11==7 else 0)
                o[0x100//4]=2 if variant%13==5 else 0
                o[0x50//4]=r.randrange(-0x30000,0x30000)&0xffffffff;o[0x5c//4]=r.randrange(-0x30000,0x30000)&0xffffffff
                o[0x118//4]=a
                o[0x124//4]=(-1,0,1,2,3,4)[variant%6]&0xffffffff
                o[0x128//4]=(0,0,1,2)[variant%4]
                o[0x12c//4]=r.choice((0,7,359,360,1080,35993,-5&0xffffffff,(-36001)&0xffffffff))
                o[0x130//4]=(0x3c00,300,1,0)[variant%4]
                o[0x134//4]=launched
                p.write(a+0xf15,level,1)
                p.write(other+0xa10,opp_char,4)
                # 142120: the opponent's 14eb78 block (system 4 has an effect) and its state 13c.
                p.write(other+0x10c,4 if conc else 0,4);p.write(other+0x13c,3 if conc else 0,4)
                p.memory[BODY:BODY+320]=struct.pack('<80I',*own)
                p.memory[BODY+0x1000:BODY+0x1000+320]=struct.pack('<80I',*opp)
                p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                _,n=p.run(0x1f7318,[TASK],limit=60000);counts['ee_instructions']+=n
                actual=list(struct.unpack_from('<80I',p.memory,BIRD))
                for s,base in enumerate(acts):
                    if base<actual[47]<=base+0x100000 and s==seat:actual[47]-=base-1
                expected.append(actual+[p.read(a+0xf15,1)])
                cases.append((seat,launched,variant))
                commands.append(' '.join(map(str,[level,int(held),int(conc),*o,*own,*opp])))
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'fire.cpp';exe=tmp/'fire';src.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,
                        ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        got=subprocess.check_output([exe,ASSETS],input='\n'.join(commands)+'\n',text=True).splitlines()
    wrong=[]
    for case,line,ref in zip(cases,got,expected,strict=True):
        if line.startswith('X'):wrong.append((case,line));continue
        row=list(map(int,line.split()))
        if row!=ref:wrong.append((case,[(hex(i*4),hex(x),hex(y)) for i,(x,y) in enumerate(zip(row,ref)) if x!=y]))
    assert not wrong,(len(wrong),wrong[:12])
    report=dict(status='passed',source=SOURCE_HASH,cases=len(cases),object_words=80,
                scope='Unit fixtures of 1f7318/1f76a0/1f7520 (orbit, launched homing, expiry, level steps).',
                ee_instructions=counts['ee_instructions'])
    (ROOT/'outputs/ss6-feasibility/kazuki-fire-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['cases'],'cases passed')

if __name__=='__main__':main()
