#!/usr/bin/env python3
"""Render Japanese VS spirit/stage selects independently, including GS font cache uploads."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from extract_character_select_art import ASSETS
from extract_spirit_select_art import prepare, ORIGINAL
from extract_versus_quotes import Iso, ISO_PATH
from extract_versus_result_layout import calls
from validate_character_select_art import ROOT, OUT, render, textures, upload

DRIVER=r'''
#include "character_select_art.hpp"
#include <iostream>
int main(int argc,char**argv) {
    ss6::CharacterSelectArt art(argv[1]);ss6::CharacterSelect s;
    s.spiritDirectorVisible=true;s.seats[0].selected=0;s.seats[1].selected=1;
    std::vector<uint8_t> pixels(640*480*4);
    while(std::cin>>s.spiritDrawFrame>>s.drawRemaining>>s.stageOption>>s.stageCursor>>s.characterDirectorVisible) {
        s.drawFrame=s.spiritDrawFrame+int(s.characterDirectorVisible);
        for(auto& seat:s.spirits)std::cin>>seat.drawPhase>>seat.drawCount>>seat.drawCursor;
        for(auto& seat:s.seats){seat.drawPhase=s.characterDirectorVisible?11:0;seat.drawCount=14-(s.spiritDrawFrame%13);}
        art.paint(s,pixels);
        std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
    }
}
'''

def glyphs(p,atlases):
    total=p.read(0x345178,4);cache=0x1a00000
    data=np.frombuffer(p.memory,np.uint8,512*256,cache).reshape(512,256)
    indices=np.empty((512,512),np.uint8);indices[:,::2]=data&15;indices[:,1::2]=data>>4
    atlases[64]=np.frombuffer(p.memory,np.uint8,64,0x348a48).reshape(16,4)[indices]
    out=[]
    def xy(w):return tuple(((w>>(16*k)&65535)-p.read(0x32ce14+4*k,4))//16 for k in (0,1))
    for i in range(total):
        prim,color,tex,uv0,xy0,uv1,xy1=struct.unpack_from('<7Q',p.memory,0x68c3c0+i*128)
        assert prim==0x1ff1 and ((tex>>37)&16383)==0x3080
        x,y=xy(xy0);r,b=xy(xy1);z=int((xy0>>32)&0x7fffffff)
        u,v=((uv0>>s&65535)//16 for s in (0,16));ur,vb=((uv1>>s&65535)//16 for s in (0,16))
        assert (r-x,b-y,ur-u,vb-v)==(24,24,24,24)
        alpha=(color>>24)&255;mod=(max(0,2*alpha-1)<<24)|0xffffff
        out.append((64,[(x,y,z,u/512,v/512,mod),(x,b,z,u/512,vb/512,mod),
                        (r,y,z,ur/512,v/512,mod),(r,b,z,ur/512,vb/512,mod)]))
    return out

def main():
    p=prepare();atlases=textures(p);font=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN')
    atlases.update({2:upload(p,'obj1_16',512,True,0),5:upload(p,'ps2_gage_1_2_3_all',1024,False,768),
                    7:upload(p,'bup_00',512,False,256),8:upload(p,'bup_01',512,False,512),
                    12:upload(p,'vs_obj',512,True,0)})
    # This independent CLUT uses the resident icon palette upload at 109630.
    ico=(ASSETS/'ps2_common_icon.pal').read_bytes()
    p.memory[0x1236740:0x1236740+len(ico)]=ico;p.run(0x116588,limit=500000)
    pal=np.frombuffer(p.memory,np.uint8,1024,0x1236f40).reshape(256,4)
    indices=np.frombuffer((ASSETS/'ps2_common_icon.tex').read_bytes(),np.uint8).reshape(512,512)
    atlases[46]=pal[indices].copy()
    p.memory[0x106b840:0x106b840+len(font)]=font
    for addr,v in ((0x32ce08,1),(0x3a9c20,0x1a00000),(0x43d064,256)):p.write(addr,v,4)
    cases=[]
    def add(a,b,option=0,stage=10,chars=0):
        cases.append((190+len(cases),1200-len(cases),option,stage,chars,a,b))
    for t in range(13):add((1,t,5),(1,t,5),chars=1)
    for t in (0,4,10,20,59):add((1,t,5),(1,t,5))
    for c in range(6):
        for ph,ts in [(2,(0,11,20,49,69,83,250)),(3,range(10)),(4,range(10)),(5,range(6))]:
            for t in ts:add((ph,t,c),(ph,t,(5-c)))
    for s in range(2):
        for opt in (0,1):
            for ph,ts in [(13,(0,6,20,44,70,257)),(17,range(6))]:
                for t in ts:
                    pair=[(14,25,3),(14,35,1)];pair[s]=(ph,t,4);add(*pair,opt)
        for stage in range(11):
            for ph,t in ((20,0),(20,9),(20,30),(22,0),(22,5),(22,14),(22,29),(23,3),(23,9),(23,19),(23,29),(24,4),(24,5),(25,6)):
                pair=[(21,42,3),(21,17,2)];pair[s]=(ph,t,0);add(*pair,stage=stage)
    count=letters=0
    with tempfile.TemporaryDirectory() as temp:
        d=Path(temp);cpp=d/'driver.cpp';exe=d/'driver';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/character_select_art.cpp',
                        ROOT/'src/versus_result_art.cpp','-o',exe],check=True)
        child=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            for frame,rem,opt,stage,chars,a,b in cases:
                for addr,val in ((0x345178,0),(0x345180,0),(0x4c8280,0),(0x4c8288,rem),(0x4c3828,opt),(0x4c8d80,stage)):
                    p.write(addr,val,4)
                for s,(_,_,c) in enumerate((a,b)):p.write(0x4c8d18+52*s+40,c,4)
                p.run(0x114e80);q=[]
                for s,(ph,t,_) in [(1,b),(0,a)]:q+=calls(p,0x1309a8,s,ph,t)[0]
                q+=calls(p,0x1353a0,frame)[0];q+=calls(p,0x12f5f0)[0]
                if chars:
                    for s in range(2):q+=calls(p,0x12a418,s,11,14-(frame%13),0,0)[0]
                    q+=calls(p,0x135438,frame+1)[0];q+=calls(p,0x128a68)[0]
                g=glyphs(p,atlases);q+=g;letters+=len(g);count+=len(q)
                expected=render(q,atlases)
                child.stdin.write((' '.join(map(str,(frame,rem,opt,stage,chars,*a,*b)))+'\n').encode());child.stdin.flush()
                got=np.frombuffer(child.stdout.read(expected.size),np.uint8).reshape(expected.shape)
                if not np.array_equal(got,expected):
                    ys,xs=np.where(np.any(got!=expected,axis=2));y,x=ys[0],xs[0]
                    Image.fromarray(expected).save('/private/tmp/ss6-spirit-original.png');Image.fromarray(got).save('/private/tmp/ss6-spirit-native.png')
                    raise AssertionError((frame,opt,stage,chars,a,b,len(ys),x,y,expected[y,x],got[y,x]))
                if a==(2,83,1):Image.fromarray(got).save(OUT/'spirit-select-native.png')
                if a==(20,30,0) and stage==0:Image.fromarray(got).save(OUT/'stage-select-native.png')
        finally:child.stdin.close();child.wait()
        assert child.returncode==0
    report=dict(status='passed',original_sha256=ORIGINAL,frames=len(cases),rgba_pixels=len(cases)*640*480,
                original_draws=count,glyph_packets=letters,scope='Original 1309a8, 1353a0, 12f5f0, all six factory names/descriptions on both wheels, eleven stage choices, both binary options/owners, two concurrent directors, original 24px Japanese labels from emitted GS packets. Native software RGBA. No hardware readback.')
    (OUT/'spirit-select-art-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
