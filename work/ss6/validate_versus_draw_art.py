#!/usr/bin/env python3
"""Render the original Game Over object's real queue and the two final GS caption packets."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from character_tiles_oracle import ASSETS, ATLAS, ROOT, begin, bits, fixture
import validate_native_scene as character_raster
from validate_dash_motion import ELF, PIN, digest

W,H=640,480
ACTOR=0x1e40000
QUEUE=0x479250
LIB=ROOT/'work/ss6/build-native/libss6-runtime.a'
OUTPUT=ROOT/'outputs/ss6-feasibility/versus_draw_art_validation.json'
DRIVER=r'''
#include "versus_draw_art.hpp"
#include <iostream>
#include <memory>
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    auto draw=std::make_unique<ss6::VersusDrawArt>(argv[1]);
    std::vector<unsigned char> base(640*480*4);
    for(int y=0;y<480;++y)for(int x=0;x<640;++x){
        auto* p=base.data()+4*(640*y+x);p[0]=x+y*2;p[1]=3*x+y;p[2]=x^y;p[3]=255;
    }
    unsigned frame,tick,slot;
    while(std::cin>>frame>>tick>>slot) {
        auto out=base;
        draw->paint(frame,tick,slot,out);
        std::cout.write(reinterpret_cast<const char*>(out.data()),out.size()).flush();
    }
}
'''

def setup():
    character_raster.HEIGHT=H  # The standalone character oracle defaults to the battle viewport.
    p=fixture()
    begin(p)
    # 138734 initializes the draw slot with the original 00 resource. The
    # startup CLUT was loaded by 113890; index zero of each bank is cleared.
    palette=bytearray((ASSETS/'obj0.pal').read_bytes())
    for i in range(0,len(palette),32):palette[i:i+2]=bytes(2)
    p.memory[0x1e80000:0x1e80000+512]=palette
    p.run(0x116478,[0,128,0x1e80000])
    for off,val in [(0,0x1fc0000),(4,512),(8,512),(12,20),(20,9),(24,9),(36,0)]:
        p.write(0x3a9680+12*40+off,val,4)
    data=(ASSETS/'font_otherscene16.tex').read_bytes()
    p.memory[0x1fc0000:0x1fc0000+len(data)]=data
    for addr,val in zip([0x4a2a58,0x4a2a5c,0x4a2a60,0x4a2a64,0x4a2a68,0x4a2a6c],[320,120,-400,-160,-120,0]):
        p.write(addr,bits(val),4)
    p.write(0x46a948,-2,4);p.write(0x4c3808,3,4)
    for i in range(256,1024):p.write(0x3ebf30+2*i,1,2)
    p.run(0x10a920,[0x43ab70,128]);p.run(0x116588,limit=500000)
    return p

def bodies(p,slot,base):
    for fn,args in [(0x11d528,[ACTOR]),(0x11d570,[ACTOR,slot,320,0,0]),(0x11d908,[ACTOR,1793,1,0])]:
        p.run(fn,args,limit=200000)
    frames=[];raster={};report={}
    for tick in range(32):
        p.run(0x1207d8);p.run(0x11d6c8,[ACTOR]);p.run(0x11d868,[ACTOR]);p.run(0x11d730,[ACTOR])
        assert p.read(0x4a2250,4)==1 and p.read(QUEUE+0x24,4)==1793 and p.read(QUEUE+12,4)==slot
        step=p.read(QUEUE+0x28,4);assert step==min(tick//8,2)
        if step not in raster:
            begin(p);draws=[]
            def trace(pc):
                if pc==0x108910:
                    ptr,_,arg=p.registers[4:7]
                    verts=struct.unpack_from('<24I',p.memory,ptr)
                    assert (arg>>8)&255==128
                    pal=0x11e7980+(arg&255)*64
                    draws.append((pal,(verts,p.read(0x3a8e44,4),p.read(0x348b10,4))))
            p.run(0x1208b0,[QUEUE],limit=500000,observe=trace);p.run(0x116d10,limit=500000)
            img=bytearray(base.tobytes())
            for pal,q in draws:
                ys=struct.unpack('<24f',struct.pack('<24I',*q[0]))[1::6]
                assert min(ys)>=0 and max(ys)<=512, (slot,tick,ys)
                character_raster.original_quad(p,pal,p.memory[ATLAS:ATLAS+131072],img,q)
            raster[step]=np.frombuffer(img,np.uint8).reshape(H,W,4)
            pixels=int(np.any(raster[step]!=base,axis=2).sum())
            assert draws and pixels>100
            report[step]=dict(quads=len(draws),visiblePixels=pixels)
        frames.append(raster[step])
    assert p.read(ACTOR+0xc0,4)==1
    return frames,report

def packets(p,frame):
    # The submitted float vertices already include the PS2 renderer's
    # clamp to 511. Capture the final TEX0 CLUT page, not the raw descriptor.
    for a in [0x345178,0x345180,0x378e08,0x3db8f8]:p.write(a,0,4)
    planes=[]
    def trace(pc):
        r=p.registers
        if pc==0x108464:
            submission=r[19];tex0=p.read(submission+16,8)
            assert r[18]==12 and (tex0>>20)&63==20
            pal=((tex0>>37)&16383)-0x3081;assert pal in (0,1)
            v=[struct.unpack_from('<5fI',p.memory,p.read(submission+24,4)+24*i) for i in range(4)]
            assert all(row[5]==v[0][5] for row in v) and v[0][5]&0xffffff==0x808080
            planes.append((v[0][2],pal,v))
        if pc==0x1058f8:
            sub=r[6];q=[]
            for i in range(4):
                color=p.read(sub+8+16*i,4);xyz=p.read(sub+16+16*i,8)
                assert color==0x80000000
                q.append((((xyz&65535)-0x6c00)//16,(((xyz>>16)&65535)-0x7900)//8,xyz>>32))
            planes.append((q[0][2],-1,q))
    p.run(0x138af0,[frame],limit=100000,observe=trace)
    return sorted(planes,key=lambda ptr:ptr[0])

def render(p,draws,pixels,atlas):
    output=pixels.copy()
    for _,pal,v in draws:
        x0,y0=v[0][:2];x1,y1=v[-1][:2]
        x=np.arange(max(0,int(x0)),min(W,int(x1)))
        y=np.arange(max(0,int(y0)),min(H,int(y1)))
        dst=output[y[0]:y[-1]+1,x[0]:x[-1]+1,:3]
        if pal<0:
            dst[:]=0
            continue
        u=(v[0][3]+(x+.5-x0)*(v[3][3]-v[0][3])/(x1-x0)).astype(int)
        t=(v[0][4]+(y+.5-y0)*(v[3][4]-v[0][4])/(y1-y0)).astype(int)
        entries=np.frombuffer(p.memory,np.uint8,64,0x11e7980+pal*64).reshape(16,4)
        src=entries[atlas[np.ix_(t,u)]].astype(int)
        alpha=src[:,:,3:4]*(v[0][5]>>24)//128
        dst[:]=dst+((src[:,:,:3]-dst)*alpha//128)
    return output

def main():
    assert digest(ELF)==PIN
    y,x=np.mgrid[:H,:W];base=np.stack([x+2*y,3*x+y,x^y,np.full_like(x,255)],axis=-1).astype(np.uint8)
    p=setup()
    blob=np.frombuffer(p.memory,np.uint8,512*256,0x1fc0000).reshape(512,256)
    atlas=np.empty((512,512),np.uint8);atlas[:,::2]=blob&15;atlas[:,1::2]=blob>>4
    report=dict(source=PIN,slotPoses={},checkedFrames=0,finalGsQuads=0,
                comparison='Original EE object init, playback, draw and CLUTs. Final GS caption packet vertices independently sampled on patterned 640x480 RGBA. Software reference; no physical PS2 video capture.')
    with tempfile.TemporaryDirectory() as d:
        src=Path(d)/'driver.cpp';src.write_text(DRIVER);exe=Path(d)/'driver'
        subprocess.run(['c++','-std=c++20','-O2','-I',str(ROOT/'src'),str(src),str(ROOT/'src/versus_draw_art.cpp'),str(ROOT/'src/action_runtime.cpp'),str(ROOT/'src/native_scene.cpp'),str(LIB),'-o',str(exe)],check=True)
        proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            for slot in [0,1]:
                frames,poses=bodies(p,slot,base);report['slotPoses'][slot]=poses
                # Includes replaying/rewinding independently of scene time
                # and all three poses underneath the immediately skipped title.
                cases=[(t,t) for t in range(301)]+[(280,t) for t in (0,7,8,15,16,23,24)]
                for frame,tick in cases:
                    draws=packets(p,frame);report['finalGsQuads']+=len(draws)
                    expected=render(p,draws,frames[min(tick,31)],atlas)
                    proc.stdin.write(f'{frame} {tick} {slot}\n'.encode());proc.stdin.flush()
                    data=proc.stdout.read(W*H*4)
                    assert len(data)==W*H*4
                    actual=np.frombuffer(data,np.uint8).reshape(H,W,4)
                    if not np.array_equal(actual,expected):
                        dy,dx,ch=np.where(actual!=expected)
                        at=dy[0],dx[0],ch[0]
                        raise AssertionError((slot,frame,tick,(int(dx[0]),int(dy[0]),int(ch[0])),int(actual[at]),int(expected[at]),len(dy)))
                    report['checkedFrames']+=1
        finally:
            proc.stdin.close();proc.wait()
        assert proc.returncode==0
    OUTPUT.write_text(json.dumps(report,indent=2)+'\n')
    print(OUTPUT,report['checkedFrames'],report['finalGsQuads'])
if __name__=='__main__':main()
