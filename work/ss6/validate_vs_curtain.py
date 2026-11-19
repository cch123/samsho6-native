#!/usr/bin/env python3
"""Compare all native sliding-door pixels with the original submitted GS sprite lists."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT,ASSETS
from extract_versus_result_layout import canvas
from extract_vs_curtain import extract
from validate_versus_result_art import paint

DRIVER=r'''
#include "vs_curtain.hpp"
#include <iostream>
int main(int argc,char** argv){
    ss6::VsCurtain curtain(argv[1]);
    std::vector<uint8_t> pixels(640*480*4);
    for(unsigned frame=0;frame<33;++frame){
        for(int y=0;y<480;++y) for(int x=0;x<640;++x){
            auto* d=pixels.data()+4*(y*640+x);
            d[0]=x+frame*3;d[1]=y+(frame>=18?96:0);d[2]=(x/23+y/17)*27;d[3]=255;
        }
        curtain.paint(frame,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
    }
}
'''
OUT=ROOT/'outputs/ss6-feasibility'

def source_texture(p):
    raw=(ASSETS/'change_base16.tex').read_bytes();addr=0x1600000;slot=0x3a9680+3*40
    for off,v in [(0,addr),(4,512),(8,512),(12,19),(20,9),(24,9)]:p.write(slot+off,v,4)
    p.memory[addr:addr+len(raw)]=raw
    # The protected disc read returns the exact size; the genuine 10aa28
    # classification then selects the slot's appended CLUT instead of bank 7.
    p.write(0x102810,0x03e00008,4);p.write(0x102814,0x00c0102d,4)
    p.run(0x10aa28,[3,0x5dd538]);assert p.read(slot+36,4)==1
    p.run(0x10add8,[3,7]);p.run(0x1162b8);p.run(0x1162f0,[3]);assert p.read(0x43cb70,4)==addr+512**2
    p.run(0x116588,limit=900000)
    clut=np.frombuffer(p.memory,np.uint8,1024,0x1233f40).reshape(8,4,8,4)[:,[0,2,1,3],:,:].reshape(256,4)
    atlas=clut[np.frombuffer(p.memory,np.uint8,512**2,addr)].reshape(512,512,4)
    p.write(0x3ec73c,0,4);p.write(0x32ce08,1,4)
    p.write(0x1e7b70,0x03e00008,4);p.write(0x1e7b74,0,4)
    return {3:atlas}

def draw_source(p,tick):
    for at in (0x345178,0x345180,0x378e08,0x3db8f8):p.write(at,0,4)
    p.run(0x114e80)
    fn,age=(0x125778,tick) if tick<15 else (0x125848,tick-15) if tick<18 else (0x1258a8,tick-18)
    p.run(fn,[0,age],limit=1200000)
    prim=[]
    for i in range(p.read(0x345178,4)):
        tag,color,tex,ptr,n=struct.unpack_from('<5Q',p.memory,0x68c3c0+128*i)
        assert (tag,color&0xffffffff,n)==(0x1ff2,0x80808080,4)
        assert (tex>>20)&63==19 and (tex>>37)&16383==0x3119
        verts=[]
        for k in range(4):
            x,y,z,u,v,c=struct.unpack_from('<5fI',p.memory,ptr+24*k)
            verts.append((x,y,z,u/512,v/512,c))
        prim.append((3,verts))
    return prim

def main():
    data=extract();p=canvas();tex=source_texture(p);held=[];total=0;hashes=[];changed=[]
    y,x=np.mgrid[:480,:640]
    with tempfile.TemporaryDirectory() as d:
        d=Path(d);(d/'main.cpp').write_text(DRIVER);exe=d/'paint'
        subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',d/'main.cpp',ROOT/'src/vs_curtain.cpp','-o',exe],check=True)
        with subprocess.Popen([exe,ASSETS],stdout=subprocess.PIPE) as proc:
            for t in range(33):
                base=np.stack([x+t*3,y+(96 if t>=18 else 0),(x//23+y//17)*27,0*x+255],axis=-1).astype(np.uint8)
                expected=base.copy();prims=draw_source(p,t);total+=len(prims);paint(expected,prims,tex)
                observed=np.frombuffer(proc.stdout.read(640*480*4),np.uint8).reshape(480,640,4)
                if not np.array_equal(expected,observed):
                    bad=np.any(expected!=observed,axis=-1);ty,tx=np.argwhere(bad)[0]
                    raise ValueError((t,int(bad.sum()),int(tx),int(ty),expected[ty,tx],observed[ty,tx]))
                changed.append(int(np.any(expected!=base,axis=-1).sum()));hashes.append(hashlib.sha256(observed).hexdigest())
                if t in (0,4,9,12,15,20,27,32):held.append(Image.fromarray(observed).resize((256,192),Image.Resampling.NEAREST))
            assert proc.wait()==0
    assert changed[0]==0 and changed[15]>300000 and changed[32]>0
    gallery=Image.new('RGB',(1024,384))
    for i,f in enumerate(held):gallery.paste(f,(256*(i%4),192*(i//4)))
    gallery.save(OUT/'vs-curtain-phases.png')
    report=dict(frames=33,GS_sprites=total,RGBA_pixels=33*640*480,format='640x480 logical canvas; original 108118 packet lists, slot-3 embedded palette through 116588, independent center-sample raster with GS integer alpha; LCD/CRT filtering outside comparison',phases={'close':[0,14],'hold':[15,17],'open':[18,32]},sound_frame_15=[-1,15],scene_swap_after_drawing_frame=17,frame_changed_pixels=changed,asset_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),frame_sha256=hashes)
    (OUT/'vs-curtain-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(f'{total} original GS sprites, {33*640*480} original/native matching pixels')
if __name__=='__main__':main()
