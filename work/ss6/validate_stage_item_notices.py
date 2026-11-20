#!/usr/bin/env python3
"""Use Japanese 1b5b80/1b5e30 and its original GS packets as an oracle."""
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile
import numpy as np
from validate_rage_gauge import original,backdrop,ASSETS,ROOT
from validate_zero_hud import atlas
from validate_dash_motion import PIN,ELF,digest

LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
OUT=ROOT/'outputs/ss6-feasibility/stage_item_notices_validation.json'
DRIVER=r'''
#include "stage_item_notices.hpp"
#include <bit>
#include <iostream>
void emit(uint32_t v){std::cout.write(reinterpret_cast<const char*>(&v),4);}
int main(int,char** argv) {
    ss6::StageItemNotices notices;ss6::StageItemNoticeArt art(argv[1]);ss6::StageCamera camera;
    int count,x,kind,rate,firstX,secondX,firstCPU,secondCPU,depth,full;
    while(std::cin>>count) {
        for(int i=0;i<count;++i){std::cin>>kind>>x;emit(notices.show(ss6::StageItemLabel(kind),x));}
        std::cin>>rate>>firstX>>secondX>>firstCPU>>secondCPU>>depth>>full;
        std::cin>>camera.projectionX>>camera.projectionY>>camera.depth>>camera.depthOffset>>camera.verticalOffset;
        notices.visit(rate,camera,{firstX,secondX},{bool(firstCPU),bool(secondCPU)},depth);
        emit(uint32_t(notices.draws().size()));
        for(const auto& q:notices.draws()){
            for(float v:{q.left,q.top,q.right,q.bottom,q.depth})emit(std::bit_cast<uint32_t>(v));
            for(int v:{q.u,q.v,q.width,q.height,q.alpha})emit(v);
        }
        if(full) {
            std::vector<uint8_t> pixels(640*448*4);
            for(int y=0;y<448;++y)for(int x=0;x<640;++x){uint8_t* d=&pixels[(y*640+x)*4];d[0]=x+2*y;d[1]=3*x+y;d[2]=x^y;d[3]=255;}
            for(const auto& q:notices.draws())art.paint(q,pixels);
            std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size());
        }
    }
}
'''

def inputs():
    for t in range(180):
        new={1:[243],12:[325],17:list(range(205,305,10)),18:[312],99:[284,285],160:[-40,820]}.get(t,[])
        new=[((t+j)%3,x) for j,x in enumerate(new)]
        x0=(257 if t<35 else 270) if 5<=t<65 else 228 if 81<=t<129 else -1
        x1=330 if 7<=t<43 else 355 if 55<=t<130 else -1
        cpu=(int(t>=70),int(t>=51));rate=0 if 20<=t<=24 else 128 if 35<=t<=59 else 256
        cam=(320,120,-400,0,-120) if t<16 else (324.75,128.5,-433.25,-3,-118.25) if t<100 else (302,126,-455,4,-124)
        full=t in (1,2,5,9,14,17,23,34,40,51,57,63,69,73,79,81,88,99,105,119,129,130,159,162)
        yield new,rate,x0,x1,*cpu,100+t%3,full,cam

def raster(packets,texture,background=None):
    frame=backdrop() if background is None else background.copy();idx,clut=texture
    # The submitted EE packet has four textured GS vertices. Sample its
    # half-open screen rectangle at pixel centers before the CSM1 lookup.
    for quad in packets:
        x0,y0,_,u0,v0,color=quad[0];x1,y1,_,u1,v1,_=quad[3]
        xs=np.arange(max(0,math.ceil(x0-.5)),min(640,math.ceil(x1-.5)))
        ys=np.arange(max(0,math.ceil(y0-.5)),min(448,math.ceil(y1-.5)))
        if not len(xs) or not len(ys):continue
        u=(u0+(xs+.5-x0)*(u1-u0)/(x1-x0)).astype(int)
        v=(v0+(ys+.5-y0)*(v1-v0)/(y1-y0)).astype(int)
        rgba=clut[idx[v[:,None],u]].astype(np.int32)
        alpha=(rgba[:,:,3:4]*(color>>24))>>7
        dest=frame[ys[:,None],xs,:3].astype(np.int32)
        frame[ys[:,None],xs,:3]=dest+((rgba[:,:,:3]-dest)*alpha>>7)
    return frame

def main():
    assert digest(ELF)==PIN
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'notice.cpp';cpp.write_text(DRIVER);exe=cpp.with_suffix('')
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,ROOT/'src/stage_item_notices.cpp',LIB,'-o',exe],check=True)
        cases=list(inputs());cmd=''
        for new,delta,x0,x1,c0,c1,depth,full,cam in cases:cmd+=' '.join(map(str,[len(new),*(v for pair in new for v in pair),delta,x0,x1,c0,c1,depth,int(full),*cam]))+'\n'
        buf=subprocess.run([exe,ASSETS],input=cmd.encode(),capture_output=True,check=True).stdout
    p=original();p.run(0x1b5b08,limit=100000);p.write(0x4c3808,3,4)
    battle=0x1c30000;p.write(0x4d3d00,battle,4);p.memory[battle:battle+0x500]=bytes(0x500)
    tex=atlas()[10];soundsEmitted=accepted=dropped=packetsSeen=frames=n=0;pos=0;images={};full_slots=False
    for tick,(new,delta,x0,x1,c0,c1,depth,full,cam) in enumerate(cases):
        for a,f in zip((0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a6c,0x4a2a68),cam):
            struct.pack_into('<f',p.memory,a,f)
        struct.pack_into('<f',p.memory,0x4a2a64,-160)
        for i,(x,cpu) in enumerate(((x0,c0),(x1,c1))):
            ptr=0x1ba0000+i*0x1000;o=ptr+0x100
            p.write(battle+0x29c+i*0x108,ptr if x>=0 else 0,4)
            p.write(ptr+0x1c,o,4);p.write(o+0xcc,4,4);struct.pack_into('<2f',p.memory,o+0x40,x,0)
            p.write(p.read(0x4d3d08,4)+i*0xf2c+0xa20,cpu,4)
        for kind,x in new:
            free=any(not p.read(0x132c4c8+i*0xac+0x24,4) for i in range(10))
            sounds=[]
            def sound(pc):
                if pc==0x1e7b70:sounds.append((p.registers[4]&0xffffffff,p.registers[5]))
            _,ins=p.run(0x1b5b80,[kind,x,80],limit=200000,observe=sound);n+=ins
            ok,=struct.unpack_from('<I',buf,pos);pos+=4
            assert bool(ok)==free and sounds==([(0xffffffff,65)] if free and kind==0 else []),(tick,kind,x,ok,sounds)
            soundsEmitted+=len(sounds)
            accepted+=ok;dropped+=1-ok
        p.write(0x46a908,delta,4);p.write(0x3db8f4,depth,4)
        for a in (0x345178,0x378e08,0x3db8f8):p.write(a,0,4)
        packets=[]
        def take(pc):
            if pc!=0x108464:return
            r=p.registers;submission=r[19];ptr=p.read(submission+24,4);tex0=p.read(submission+16,8)
            assert r[16]==10 and p.read(submission,4)==0x1ff2 and (tex0>>20)&63==19
            packets.append([struct.unpack_from('<5fI',p.memory,ptr+i*24) for i in range(4)])
        _,ins=p.run(0x1b5e30,limit=500000,observe=take);n+=ins
        full_slots|=all(p.read(0x132c4c8+i*0xac+0x24,4) for i in range(10))
        count,=struct.unpack_from('<I',buf,pos);pos+=4
        assert count==len(packets),(tick,count,len(packets))
        for i,quad in enumerate(packets):
            x,y,z,u,v,col=quad[0];right,bottom,_,u1,v1,_=quad[3]
            got=struct.unpack_from('<5f5I',buf,pos);pos+=40
            want=(x,y,right,bottom,z,int(u),int(v),int(u1-u),int(v1-v),col>>24)
            assert got==want,(tick,i,got,want)
        packetsSeen+=len(packets)
        if full:
            want=raster(packets,tex).tobytes();got=buf[pos:pos+len(want)];pos+=len(want)
            assert got==want,(tick,'pixels',sum(a!=b for a,b in zip(got,want)))
            frames+=1;images[tick]=hashlib.sha256(got).hexdigest()
    assert pos==len(buf) and dropped and full_slots
    doc=dict(status='passed',elf_sha256=PIN,runtime_sha256=digest(LIB),module_sha256=digest(ROOT/'src/stage_item_notices.cpp'),
             atlas_sha256=digest(ASSETS/'obj2_16.tex'),updates=len(cases),packets=packetsSeen,full_images=frames,pixels=frames*640*448,
             accepted_labels=accepted,healing_sounds=soundsEmitted,refused_without_sound=dropped,all_ten_slots=True,original_instructions=n,images=images,
             scope='Native slot gate, raw delta 0/128/256, 60-visit healing, defense-down and bomb rise/fade, 4-cell weapon indicators for both human sides/CPU, weapon motion after indicator creation, overlapping, saturation, slot reuse, offscreen culling, three cameras, EE submitted clut/geometry and final pixels on a known patterned background. Camera, gameplay recovery and ground weapon pointers are supplied by fixture.')
    OUT.write_text(json.dumps(doc,indent=2)+'\n');print(frames,'images',packetsSeen,'packets',accepted,'labels',soundsEmitted,'sounds',dropped,'refused')
if __name__=='__main__':main()
