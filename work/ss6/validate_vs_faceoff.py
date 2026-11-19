#!/usr/bin/env python3
"""Compare the VS director, its two clocks, and the 640x480 displayed artwork to the Japanese ELF."""
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT,ASSETS
from extract_versus_result_layout import canvas,calls
from validate_character_select_art import render,upload

OUT=ROOT/'outputs/ss6-feasibility'
BUILD=ROOT/'work/ss6/build-native'
DRIVER=r'''
#include "versus_faceoff.hpp"
#include <iostream>
int main(int argc,char** argv) {
    unsigned a=std::stoi(argv[2]),b=std::stoi(argv[3]);
    ss6::VersusFaceoffArt art(argv[1],{a,b});
    ss6::SoundSelection sounds(argv[1]);
    ss6::VersusFaceoff screen;
    std::vector<uint8_t> pixels(640*480*4);
    char op;unsigned x,y;
    while(std::cin>>op>>x>>y) {
        if(op=='p') {
            ss6::VersusFaceoff s;s.drawFrame=x;s.drawBackground=y;
            art.paint(s,pixels);std::cout.write((const char*)pixels.data(),pixels.size()).flush();
        } else {
            sounds.beginFrame();screen.tick({x,y},{a,b},sounds);
            std::cout<<screen.frame<<" "<<screen.background<<" "<<screen.drawFrame<<" "<<screen.drawBackground
                     <<" "<<screen.white<<" "<<screen.flashNext<<" "<<screen.requested;
            for(auto& ev:sounds.events())std::cout<<" "<<int(ev.kind)<<" "<<ev.bank<<" "<<ev.tone;
            std::cout<<std::endl;
        }
    }
}
'''
def references(p,ids):
    # 125e10 overwrites the top 128 entries of the first CLUT with the top
    # half of vs_back.pal. 1261b8 loads the two portraits into banks 512/768.
    addr=0x1400000
    for offset,name,start,count in [(0,'vs_obj',0,256),(256,'vs_back',128,128)]:
        palette=(ASSETS/(name+'.pal')).read_bytes()
        p.memory[addr:addr+len(palette)]=palette
        if start==0:p.write(addr,0,2)
        p.write(0x439b68,0,4)
        p.run(0x116478,[start,count,addr+offset],limit=150000)
    p.write(0x3ebf2c,1,4);p.run(0x116588,limit=500000)
    colors=np.frombuffer(p.memory,np.uint8,count=1024,offset=0x11e7980).reshape(256,4)
    img=np.frombuffer((ASSETS/'vs_back.tex').read_bytes(),np.uint8).reshape(1024,1024)
    textures={4:colors[img].copy(),12:upload(p,'vs_obj',512,True,0)}
    for side,char in enumerate(ids):
        textures[(8,6)[side]]=upload(p,f'bup_{char:02}',512,False,512+side*256)
    return textures

def pixels(exe,ids,frames):
    p=canvas();tex=references(p,ids)
    for n,c in enumerate(ids):p.write(0x456890+48*n,c,4)
    proc=subprocess.Popen([exe,ASSETS,*map(str,ids)],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    try:
        for foreground,background in frames:
            p.write(0x3db8f8,0,4)
            draws,_=calls(p,0x126370,foreground,background)
            # This routine only draws axis-aligned sprites. Reorder corners
            # before applying the independent affine UV/raster model.
            ordered=[(slot,sorted(v,key=lambda a:(a[1],a[0]))) for slot,v in draws]
            expected=render(ordered,tex)
            proc.stdin.write(f'p {foreground} {background}\n'.encode());proc.stdin.flush()
            data=proc.stdout.read(expected.nbytes)
            actual=np.frombuffer(data,np.uint8).reshape(expected.shape)
            if not np.array_equal(actual,expected):
                yy,xx=np.nonzero(np.any(actual!=expected,axis=2))
                i=len(xx)//2;x=xx[i];y=yy[i]
                raise AssertionError((ids,foreground,background,len(xx),int(x),int(y),actual[y,x],expected[y,x]))
            if ids==(0,1) and foreground==450:Image.fromarray(actual).save(OUT/'versus-faceoff-native.png')
    finally:
        proc.stdin.close();proc.stdout.close();proc.wait()

def director(exe,ids,press):
    p=canvas()
    # Keep all interpolators and 126680's original flash decision. Replace
    # draw-only leaves, debug printing and external mixer/transition callbacks.
    leaves=(0x126580,0x126748,0x126888,0x126a78,0x126d20,0x127028,0x127178,0x127368,0x127400,0x127648,
            0x1132c0,0x1170d8,0x117170,0x1e7ad0,0x1e7b40,0x1e7af8,0x1e7d60,0x1252f0)
    for pc in leaves:p.memory[pc:pc+8]=struct.pack('<II',0x03e00008,0x0000102d)
    for n,c in enumerate(ids):p.write(0x456890+48*n,c,4)
    p.write(0x4c38a8,2,4)
    requested=False;age=0;flash=0;checks=[];commands=[]
    for update in range(540):
        keys=press.get(update,(0,0));commands.append('t %d %d'%keys)
        for n,word in enumerate(keys):p.write(0x1237ccc+12*n,word,4)
        events=[];draw=[];next_flash=[]
        def observe(pc):
            nonlocal requested
            r=p.registers
            if pc==0x126370:draw.extend(r[4:6])
            if pc==0x117170:next_flash.append(r[4])
            if pc==0x1e7d60:events.extend((1,r[4],r[5]))
            if pc==0x1e7b40:events.extend((3,0,2))
            if pc==0x1e7ad0:events.extend((7,0,0))
            if pc==0x1252f0:
                assert r[4:8]==[3,0,0x126310,0x139760];requested=True
        p.run(0x125f28,limit=350000,observe=observe)
        checks.append([p.read(0x4c8208,4),p.read(0x4c820c,4),*draw,flash,int(bool(next_flash)),int(requested),*events])
        flash=int(bool(next_flash))
        if requested:
            age+=1
            if age==18:break
    actual=subprocess.run([exe,ASSETS,*map(str,ids)],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True)
    rows=[list(map(int,s.split())) for s in actual.stdout.splitlines()]
    assert len(rows)==len(checks)
    for i,(row,original) in enumerate(zip(rows,checks)):assert row==original,(ids,i,row,original)
    return len(checks)

def main():
    with tempfile.TemporaryDirectory() as tmp:
        driver=Path(tmp)/'driver.cpp';driver.write_text(DRIVER);exe=Path(tmp)/'driver'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',driver,BUILD/'libss6-runtime.a','-o',exe],check=True)
        poses=[(f,f) for f in [0,5,15,17,31,55,110,190,192,245,275,290,306,360,420,450,480,499,516]]+[(480,31),(497,67)]
        pixels(exe,(0,1),poses);pixels(exe,(22,42),[(41,41),(300,201),(485,65)])
        steps=[director(exe,(0,1),{}),director(exe,(42,29),{29:(2,0),30:(2,0)}),
               director(exe,(23,0),{30:(8,0),32:(0,8)}),director(exe,(0,1),{291:(0,0x400)})]
    report=dict(status='passed',elf_sha256=hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest(),
                original_director_updates=sum(steps),sequences=steps,rendered_frames=len(poses)+3,
                compared_pixels=(len(poses)+3)*640*480,scope='125f28 director to fight request and 18 transition visits, 126370 original draw lists, original external CLUT conversions with independent point-sampled 640x480 raster. Transition overlay verified separately.')
    (OUT/'versus_faceoff_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report)
if __name__=='__main__':main()

