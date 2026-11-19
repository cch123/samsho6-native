#!/usr/bin/env python3
"""Compare the complete stage-one graphics task against native geometry, CLUTs and pixels."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from validate_combat_stage import ASSETS, ROOT, OUT, PROJECTION, SourceStage, pack_strip, compare_pixels
from extract_versus_result_layout import canvas
from extract_collision_tables import SOURCE_HASH

ROWS=(3,4,5,20,21,22,23,24,25,26)
COUNT=(4,3,6,4,4,4,4,4,6,4)
DRIVER=r'''
#include "combat_stage.hpp"
#include <fstream>
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    CombatStage art(argv[1],1);const std::filesystem::path out=argv[2];
    CombatStageState s;s.stage=1;s.visible=true;
    unsigned id,tones,full;
    auto write=[](std::ofstream& f,auto v){f.write(reinterpret_cast<const char*>(&v),sizeof(v));};
    while(std::cin>>id>>s.suppressGeometry>>tones>>full){
        auto& c=s.camera;
        std::cin>>c.projectionX>>c.projectionY>>c.depth>>c.depthOffset>>c.verticalOffset;
        for(auto& layer:s.layers01)std::cin>>layer.picture;
        unsigned depth;const auto strips=art.geometry(s,&depth);
        std::ofstream gs(out/(std::to_string(id)+".gs"),std::ios::binary);
        write(gs,depth);write(gs,unsigned(strips.size()));
        for(const auto& strip:strips){write(gs,strip.z);write(gs,strip.slot);write(gs,strip.color);write(gs,unsigned(strip.vertices.size()));
            for(const auto& v:strip.vertices){write(gs,v.x);write(gs,v.y);write(gs,v.u);write(gs,v.v);}
        }
        if(full){
            std::array<uint16_t,1024> paletteTones{};
            for(unsigned i=512;i<1024;++i)paletteTones[i]=tones==7?(i%11<4?1:0):tones;
            std::vector<uint8_t> rgba(640*480*4);
            if(art.paint(s,paletteTones,rgba)!=depth)return 1;
            std::ofstream f(out/(std::to_string(id)+".rgba"),std::ios::binary);
            f.write(reinterpret_cast<const char*>(rgba.data()),rgba.size());
        }
    }
}
'''

class Original(SourceStage):
    number=1
    def __init__(self):
        self.p=p=canvas()
        self.cache={}
        self.instructions=0;self.submissions=0
        p.write(0x50e048,0x60000000,4);p.write(0x510ce8,p.read(0x652d14,4),4)
        for slot,bank in ((4,32),(5,32),(6,48),(7,48)):p.run(0x10add8,(slot,bank))
        for routine in (0x1a7d98,0x1a7e70):p.run(routine,limit=500000)
        p.run(0x13847c,stop_before=[0x1384cc])
        self.objects=[]
        for row in ROWS:
            a=p.read(0x514a50+row*0x48+0x28,4)
            self.objects.append((p.read(a,4),p.read(a+4,4)))
        assert [p.read(t+4,4)//p.read(t,4) for _,t in self.objects]==list(COUNT)
    def visit(self,camera,hide,forced,delta):
        p=self.p
        # These are the original world coordinates published by the preceding
        # battle visit. Foreground samples and the arena use separate snapshots.
        for addr,f in zip(PROJECTION,camera):struct.pack_into('<f',p.memory,addr,f)
        p.write(0x50e04c,hide,4);p.write(0x46a908,delta,4)
        if forced is not None:
            for i,(obj,param) in enumerate(self.objects):
                rate=p.read(param,4)
                p.write(obj,((forced+i)%COUNT[i])*rate,4);p.write(obj+0x30,1,4)
        p.run(0x114e80)
        frame=[]
        def submit(pc):
            if pc!=0x1149d0:return
            slot=p.registers[6]&255;addr=p.registers[4];count=p.registers[5]
            vertices=[struct.unpack_from('<5fI',p.memory,addr+24*j) for j in range(count)]
            z,color=vertices[0][2],vertices[0][5]
            assert color==0xffffffff and slot in (4,5,6,7) and count in (4,10)
            assert all(z==v[2] and color==v[5] for v in vertices)
            frame.append((z,slot,color,[(x,y,u,v) for x,y,_,u,v,_ in vertices]))
        _,steps=p.run(0x1a8098,limit=200000,observe=submit);self.instructions+=steps;self.submissions+=len(frame)
        depth=p.read(0x3db8f4,4)
        return sorted(frame,key=lambda s:s[0]),depth,[p.read(o+4,4) for o,_ in self.objects]

def samples():
    normal=(320,120,-400,0,-120)
    # Left/right and elevated cameras, fractional positions, bounded shake,
    # varying depths, original monochrome tone bits, partial CLUT conversion.
    cameras=[normal,(177,125,-423,0,-125),(468,132,-478,-2,-132),(310.25,194.5,-545.5,5,-184.5),
             (330,215,-660,0,-215),(320.75,112,-385.25,-12,-108)]
    for n in range(35):
        fx=None if n<5 else n
        palette=(0,1,4,7)[(n//3)%4]
        yield cameras[n%len(cameras)],int(n in (19,28)),fx,[256,128,0,64,256][n%5],palette,n not in (10,11,13,17,20,22,24,29,31,34)

def verify():
    exeHash=hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()
    assert exeHash==SOURCE_HASH
    source=Original();inputs=[];frames=[];pictures=[set() for _ in ROWS]
    previews=[];channels=Counter();imageCount=verts=0
    with tempfile.TemporaryDirectory() as temp:
        tmp=Path(temp);cpp=tmp/'stage.cpp';cpp.write_text(DRIVER);exe=tmp/'stage'
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',cpp,
                        ROOT/'src/combat_stage.cpp',ROOT/'src/combat_stage_state.cpp',ROOT/'work/ss6/build-native/libss6-runtime.a','-o',exe],check=True)
        for i,(cam,hide,key,delta,palette,full) in enumerate(samples()):
            frame,depth,keys=source.visit(cam,hide,key,delta)
            for seq,k in zip(pictures,keys):seq.add(k)
            inputs.append(' '.join(map(str,[i,hide,palette,int(full),*cam,*keys])))
            frames.append((frame,depth,palette,full))
        subprocess.run([exe,ASSETS,tmp],input='\n'.join(inputs),text=True,check=True)
        for i,(frame,depth,palette,full) in enumerate(frames):
            actual=(tmp/f'{i}.gs').read_bytes()
            expected=struct.pack('<2I',depth,len(frame))+b''.join(map(pack_strip,frame))
            if expected!=actual:
                d=next((n for n,(a,b) in enumerate(zip(actual,expected)) if a!=b),min(len(actual),len(expected)));word=d&~3
                raise ValueError(('GS packet mismatch',i,d,len(expected),len(actual),expected[word:word+4].hex(),actual[word:word+4].hex()))
            channels.update((slot,len(v)) for z,slot,col,v in frame);verts+=sum(len(v) for _,_,_,v in frame)
            if full:
                tones=[(1 if j%11<4 else 0) if palette==7 else palette for j in range(512,1024)]
                expected=source.rgba(frame,tones,480)
                seen=np.fromfile(tmp/f'{i}.rgba',np.uint8).reshape(480,640,4)
                compare_pixels(seen,expected,('640x480',i,palette));imageCount+=1
                if i in (0,2,4):
                    previews.append(Image.fromarray(seen[:448]).resize((320,224)))
        assert [sorted(k) for k in pictures]==[list(range(n)) for n in COUNT]
        sheet=Image.new('RGB',(320*len(previews),224))
        for i,img in enumerate(previews):sheet.paste(img,(320*i,0))
        sheet.save(OUT/'combat-stage01-cameras.png')
    report=dict(status='passed',elf_sha256=exeHash,geometry_sha256=hashlib.sha256((ASSETS/'combat_stage_01.bin').read_bytes()).hexdigest(),
                actual_callback='0x1a8098',original_instructions=source.instructions,updates=len(frames),submitted_strips=source.submissions,
                exact_vertices=verts,shape_counts={str(k):v for k,v in sorted(channels.items())},full_images=imageCount,
                compared_RGBA_pixels=imageCount*640*480,animated_rows=list(ROWS),pictures_per_row=list(COUNT),
                scope='Complete original GS submission, full RGBA through the separate software triangle model, level background-only. Center, pan, high camera, fractional zoom/offset and shake, hide, factory color and full/partial grayscale. All ten props with every picture. Native and Japanese stage clocks verified separately; this rendering oracle supplies their picture IDs.')
    (OUT/'combat_stage01_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':verify()
