#!/usr/bin/env python3
"""Run Nakoruru's original 1ed440 callback against the native companion task."""
from collections import Counter
from hashlib import sha256
import json
import random
import struct
import subprocess
import tempfile
from pathlib import Path
from character_tiles_oracle import ROOT,ASSETS,fixture,bits
from extract_collision_tables import SOURCE_HASH

BATTLE,ACTORS,BODY,BIRD,TASK=0x900000,0xa00000,0xb00000,0xb10000,0xb20000
DRIVER=r'''
#include "mamahaha.hpp"
#include "stage_camera.hpp"
#include "state_entry.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char**argv){
    AuxiliaryObjects objects(argv[1],{1,1,51});AuxiliaryObject bird,body;
    StateEntryActor owner;StageCamera camera;int final;
    while(std::cin>>owner.flags23c>>owner.state194>>owner.fieldA30>>final){
        for(auto& w:bird)std::cin>>w;for(auto& w:body)std::cin>>w;
        updateMamahaha(objects,bird,body,owner,final,camera);
        for(auto w:bird)std::cout<<w<<' ';std::cout<<'\n';
    }
}
'''

def main():
    p=fixture((1,1,51));r=random.Random(0x1ed440)
    p.write(0x4d3d00,BATTLE,4);p.write(0x4d3d08,ACTORS,4)
    assert sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    p.write(TASK+28,BIRD,4)
    stage,_=p.run(0x140040);p.write(stage+0x10,160,4);p.write(stage+0x14,480,4)
    count=Counter();expect=[];lines=[];labels=[]
    for seat in (0,1):
        a=ACTORS+seat*0xf2c
        p.write(a,BODY,4);p.write(a+4,BIRD,4);p.write(a+0xa10,1,4);p.write(a+0xa24,seat,4)
        p.write(ACTORS+(1-seat)*0xf2c+0xa10,0,4)
        for command in range(18):
            for entry in (0,1):
                for i in range(10):
                    owner=[0]*80;o=[0]*80
                    attack=[0,1,4,0x200,0,0,0,0,0,0][i]
                    if command==15 and i%2:attack=0x1000000
                    if command==16 and i%2:attack=0x200000
                    state=0x300000 if i%3==0 else 0x210001
                    hp=(90,110)[i%2];final=i%3==0;flags=attack|(0x1000 if i%3!=1 else 0)
                    armed=bool(flags&0x1000)
                    o[3]=seat;o[4]=seat;o[5]=1;o[7]=5;o[9]=769;o[14]=0x10000000|(0x80000 if i&1 else 0)
                    o[16]=bits(r.choice((185.,280.,520.)));o[17]=bits(r.choice((-5.,17.,122.,201.)))
                    o[0x50//4]=r.randrange(-0x34000,0x34000)&0xffffffff;o[0x5c//4]=r.randrange(-0x34000,0x34000)&0xffffffff
                    o[0xf4//4]=bits(-41.);o[0xf8//4]=bits(76.);o[0x130//4]=i%3;o[0x134//4]=787 if i%2 else 780
                    o[0xcc//4]=3;o[0x104//4]=0x200|(1 if i%4==0 else 0);o[0xc0//4]=i%2
                    o[0x100//4]=2 if i==3 else 0;o[0x118//4]=a;o[0x128//4]=command;o[0x12c//4]=0xffffffff if entry else command
                    owner[0x38//4]=0x80000 if i%3 else 0
                    owner[0x40//4]=bits(r.choice((180.,245.,320.)));owner[0x44//4]=bits(r.choice((0.,28.,87.)));owner[5]=1
                    if i in (1,2,3):o[16]=bits((245.+(50 if owner[14] else -50))+(i-2)*.4);owner[16]=bits(245.);owner[17]=bits(0.);o[17]=bits(120.)
                    if i==5:o[16]=bits(245.);o[17]=bits(118.);owner[16]=bits(296.25);owner[17]=bits(0.)
                    if i==7:o[16]=bits(245.);o[17]=bits(120.);owner[16]=bits(296.);owner[17]=0
                    for addr,v in [(a+0x23c,flags),(a+0x194,state),(a+0xa30,hp),(BATTLE+0x254+seat*0x108+0x28,int(final)*2),(BATTLE+0x254+seat*0x108+0x2c,2)]:p.write(addr,v,4)
                    p.memory[BODY:BODY+320]=struct.pack('<80I',*owner);p.memory[BIRD:BIRD+320]=struct.pack('<80I',*o)
                    _,n=p.run(0x1ed440,[TASK],limit=30000);count['original_instructions']+=n
                    got=list(struct.unpack_from('<80I',p.memory,BIRD))
                    if 0x1b00000<=got[0xbc//4]<0x1d00000:got[0xbc//4]-=(0x1b00000+seat*0x80000)-1
                    expect.append(got);labels.append((seat,command,entry,i));count['cases']+=1
                    lines.append(' '.join(map(str,[flags,state,hp,int(final),*o,*owner])))
    with tempfile.TemporaryDirectory() as tmp:
        src=Path(tmp)/'probe.cpp';src.write_text(DRIVER);exe=src.with_suffix('')
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,ROOT/'src/mamahaha.cpp',ROOT/'src/auxiliary_objects.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        out=subprocess.run([exe,ASSETS],input='\n'.join(lines)+'\n',capture_output=True,text=True,check=True)
        for lab,actual,ref in zip(labels,out.stdout.splitlines(),expect,strict=True):
            row=list(map(int,actual.split()));assert row==ref,(lab,[(hex(j*4),hex(v),hex(w)) for j,(v,w) in enumerate(zip(row,ref)) if v!=w])
    path=ROOT/'outputs/ss6-feasibility/mamahaha_validation.json'
    path.write_text(json.dumps(dict(all_passed=True,elf_sha256=SOURCE_HASH,counts=dict(count),commands=list(range(18)),seats=[0,1]),indent=2)+'\n');print(count)
if __name__=='__main__':main()
