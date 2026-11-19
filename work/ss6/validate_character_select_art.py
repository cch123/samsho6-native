#!/usr/bin/env python3
"""Compare the native select page to Japanese sprite submissions and uploaded CLUTs."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT,ASSETS
from extract_character_select_art import setup
from extract_versus_result_layout import calls
from validate_versus_result_art import textures
from extract_versus_quotes import ORIGINAL

OUT=ROOT/'outputs/ss6-feasibility'
DRIVER=r'''
#include "character_select_art.hpp"
#include <iostream>
int main(int argc,char**argv){
    ss6::CharacterSelectArt art(argv[1]);ss6::CharacterSelect state;
    std::vector<uint8_t> pixels(640*480*4);
    while(std::cin>>state.drawFrame>>state.drawRemaining){
        for(auto& seat:state.seats){
            std::cin>>seat.cell>>seat.drawPhase>>seat.drawCount>>seat.controls>>seat.selected;
            seat.character=state.roster.at(seat.cell);
        }
        art.paint(state,pixels);
        std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
    }
}
'''

def upload(p,name,w,embedded,bank):
    buf=(ASSETS/(name+'.tex')).read_bytes();indices=np.frombuffer(buf,np.uint8,count=w*w).reshape(w,w)
    if embedded:
        # 1162f0 uploads the appended palette in 16x16 blocks.
        base=0x1400000;p.memory[base:base+len(buf)]=buf
        p.write(0x3a9680+4*40,base,4)
        # The caller's bank does not determine appended CLUT addressing.
        colors=np.frombuffer(buf,np.uint8,count=1024,offset=w*w).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
    else:
        data=(ASSETS/(name+'.pal')).read_bytes();at=0x1600000;dest=at+0x2000
        p.memory[at:at+len(data)]=data
        p.write(0x439b68,1,4);p.write(0x43cc60,dest,4);p.write(0x3ebf28,at,4)
        p.run(0x116478,[bank,256,dest],limit=100000);p.run(0x116588,limit=500000)
        colors=np.frombuffer(p.memory,np.uint8,count=1024,offset=0x11e7980+bank*4).reshape(256,4)
    return colors[indices].copy()

def render(primitives,atlases):
    out=np.zeros((480,640,4),np.uint8);out[:,:,3]=255
    for slot,vertices in sorted(primitives,key=lambda q:q[1][0][2]):
        v=np.array(vertices);x,y=v[0,:2];r,b=v[3,:2]
        y0,y1=max(0,int(min(y,b))),min(480,int(max(y,b)))
        x0,x1=max(0,int(min(x,r))),min(640,int(max(x,r)))
        if x0>=x1 or y0>=y1:continue
        dst=out[y0:y1,x0:x1,:3]
        if not slot:
            color=int(v[0,3])
            rgb=np.array([(color>>s)&255 for s in (0,8,16)])
            dst[:]=dst+(rgb-dst)*(((color>>24)+1)//2)//128
            continue
        atlas=atlases[slot];w=atlas.shape[1];u,t=v[0,3:5];ue,te=v[3,3:5]
        sx=np.floor(w*(u+(np.arange(x0,x1)+.5-x)*(ue-u)/(r-x))).astype(int).clip(0,w-1)
        sy=np.floor(w*(t+(np.arange(y0,y1)+.5-y)*(te-t)/(b-y))).astype(int).clip(0,w-1)
        tex=atlas[sy[:,None],sx].astype(int);color=int(v[0,5])
        mod=np.array([((color>>s&255)+1)//2 for s in (0,8,16,24)])
        src=tex*mod//128
        dst[:]=dst+((src[:,:,:3]-dst)*src[:,:,3:4]//128)
    return out

def main():
    p=setup();atlases=textures(p);atlases.update({k:upload(p,n,w,e,b) for k,n,w,e,b in [
        (5,'char_face_1024',1024,False,512),(2,'obj1_16',512,True,0),(12,'vs_obj',512,True,0),
        (7,'bup_00',512,False,256),(8,'bup_01',512,False,256)]})
    cases=[]
    def add(t,c,n,k=0,s=0):
        cases.append((t,1800-t,(c,n,t,k,0),((c+7)%42,n,t,s,1)))
    for t in range(0,60,3):add(t,2,1)
    for cell in range(42):
        for n,t in [(2,83+cell),(3,cell%10),(4,cell%10),(5,cell%15),(6,cell%10)]:add(t,cell,n)
    for n in (7,8,9,10,11):
        for t in range(15 if n!=7 else 6):add(t,(t+3)%42,n)
    for c in (2,3,12,36):add(32,c,2,1,4)
    # Both slots can hold any roster portrait. Populate their actual source
    # CLUTs and compare all named confirmations, including the random-only 42.
    roster=[p.read(0x4c82a8+4*i,4) for i in range(42)]
    portraits={i:upload(p,f'bup_{i:02}',512,False,256) for i in (*range(40),42)}
    for cell,next_cell in zip(range(42),list(range(1,42))+[0]):
        portraits_here=[42 if roster[i]==53 else roster[i] for i in (cell,next_cell)]
        cases.append((84,1716,(cell,8,8,0,portraits_here[0]),(next_cell,8,8,0,portraits_here[1])))
    with tempfile.TemporaryDirectory() as temp:
        d=Path(temp);src=d/'driver.cpp';src.write_text(DRIVER);exe=d/'driver'
        subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',src,ROOT/'src/character_select_art.cpp',
                        ROOT/'src/versus_result_art.cpp','-o',exe],check=True)
        proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE);count=0
        try:
            for frame,remain,p0,p1 in cases:
                for side,(c,ph,t,key,char) in enumerate((p0,p1)):p.write(0x4c82a0+4*side,c,4)
                atlases[7]=portraits[p0[4]];atlases[8]=portraits[p1[4]]
                p.write(0x4c8280,0,4);p.write(0x4c8288,remain,4);p.run(0x114e80);q=[]
                for side,(c,ph,t,key,char) in enumerate((p0,p1)):
                    q+=calls(p,0x12a418,side,ph,t,int(ph in (2,5)),key)[0]
                q+=calls(p,0x135438,frame)[0];q+=calls(p,0x128a68)[0];count+=len(q)
                expected=render(q,atlases)
                proc.stdin.write((' '.join(map(str,(frame,remain,*p0,*p1)))+'\n').encode());proc.stdin.flush()
                got=np.frombuffer(proc.stdout.read(expected.size),np.uint8).reshape(expected.shape)
                if not np.array_equal(got,expected):
                    ys,xs=np.where(np.any(got!=expected,axis=2));x,y=xs[0],ys[0]
                    Image.fromarray(expected).save('/private/tmp/ss6-select-expected.png');Image.fromarray(got).save('/private/tmp/ss6-select-native.png')
                    raise AssertionError((frame,p0,p1,len(ys),x,y,got[y,x],expected[y,x]))
                if p0[0]==3 and p0[1]==2 and p0[3]==0:
                    Image.fromarray(got).save(OUT/'character-select-native.png')
        finally:proc.stdin.close();proc.wait()
        assert proc.returncode==0
    report=dict(status='passed',original_sha256=ORIGINAL,frames=len(cases),confirmed_portraits=len(portraits),original_quads=count,all_rgba_pixels=640*480*len(cases),
                scope='Factory two-seat character screen, 42 real roster cells, entrance, motion, cursor pulses, confirm, Japanese names, original CLUTs, both dimensional portrait panels, animated scrolling backdrop and countdown. Native display compared to original geometry; no GS hardware or BIOS.')
    (OUT/'character-select-art-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
