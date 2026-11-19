#!/usr/bin/env python3
"""Compare the Japanese title/mode GS submissions against the native 640×480 image."""
import argparse
import hashlib
import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from character_tiles_oracle import ROOT,ASSETS
from extract_console_versus_art import prepare,PACKETS,ORIGINAL

REPORT=ROOT/'outputs/ss6-feasibility/console-title-art-validation.json'
DRIVER=r'''
#include "console_title_art.hpp"
#include <iostream>
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    ss6::ConsoleTitleArt art(argv[1]);
    std::vector<uint8_t> pixels(640*480*4);
    unsigned menu,row,dir,tick,title,idle,prompt,fade,white;
    while(std::cin>>menu>>row>>dir>>tick>>title>>idle>>prompt>>fade>>white) {
        art.paint(menu,row,dir,tick,title,idle,pixels,static_cast<ss6::ConsoleTitlePrompt>(prompt),fade,white);
        std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
    }
}
'''

def fixture(assets):
    p=prepare()
    p.run(0x1113e8,[0x43d058]);p.write(0x3aa160,3,4)
    assert p.run(0x1e3f70,[0x43d09f])[0]==0 and p.read(0x43d0d6,1)==0 and p.read(0x443578,4)==0
    assert p.run(0x10c058,[3])[0]==3
    # Slot 5 has a separate PVP; its first entry is cleared on the stack
    # before 1279d4/116478 and the common real CLUT conversion.
    # Keep the one-megabyte image outside libc's diagnostic buffer at 1a00000;
    # later CLUT uploads sample these same retained source indices.
    raw=(assets/'bg_title00.tex').read_bytes();addr=0x1e40000
    p.memory[addr:addr+len(raw)]=raw
    for o,v in [(0,addr),(4,1024),(8,1024),(12,19),(20,10),(24,10),(36,0)]:p.write(0x3a9680+5*40+o,v,4)
    pal=(assets/'bg_title00.pal').read_bytes();addr=0x1410000
    p.memory[addr:addr+512]=pal;p.write(addr,0,2);p.write(0x439b68,0,4)
    p.run(0x116478,[768,256,addr],limit=150000);p.write(0x3ebf2c,1,4);p.run(0x116588,limit=500000)
    tileclut=np.frombuffer(p.memory,np.uint8,1024,0x11e7980+4*768).reshape(256,4)
    font=(assets/'obj0_16.tex').read_bytes()
    assert (ASSETS/'obj0_16.tex').read_bytes()==font
    resident=np.frombuffer(font,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
    tex={0x30cd:tileclut[np.frombuffer(raw,np.uint8)].reshape(1024,1024,4),
         0x3119:resident[np.frombuffer(font,np.uint8,512*512)].reshape(512,512,4)}
    coin=(assets/'font_coin.tex').read_bytes()
    at=p.read(0x3a9680+40*40,4);p.memory[at:at+len(coin)]=coin
    assert p.read(0x3a9680+40*40+36,4)==0
    # Decode the real 11394c CLUT DMA setup. 1099f0 transfers sixteen 8x2
    # rectangles: CSM1's index remap cancels the strip-to-plane permutation.
    writes=[]
    def upload(pc):
        if pc==0x302148:writes.append(tuple(p.registers[5:12]))
    p.run(0x1099f0,[0x3189,at+128*128],observe=upload,stop_before=[0x320820],limit=80000)
    assert writes==[(0x3189,1,0,(i%2)*8,i//2*2,8,2) for i in range(16)]
    tex[0x3189]=np.frombuffer(p.memory,np.uint8,1024,at+16384).reshape(256,4)[
        np.frombuffer(p.memory,np.uint8,16384,at)].reshape(128,128,4)
    p.run(0x1b9e00,[3]);p.run(0x1ba920,[1])
    return p,tex

def packets(p,menu,first,direction,tick,title,idle,prompt):
    for addr,value in [(0x4c8268,title),(0x4c826c,idle),(0x582af8,first),(0x582b00,direction),(0x582b08,tick),
                       (0x345178,0),(0x345180,0),(0x378e08,0),(0x3db8f8,0)]:p.write(addr,value,4)
    p.write(0x4c3808,4 if menu else 0,4);p.write(0x4c3834,int(prompt==2),4)
    p.write(0x4c8278,int(menu),4);p.write(0x4c827c,int(menu),4)
    p.write(0x4c3838,0,4);p.write(0x582230,60 if prompt else 0,4);p.write(0x582234,int(bool(prompt)),4)
    p.run(0x114e80);p.run(0x113aa8)
    # The common submitter precedes pad sampling and the priority-20 scene.
    # The global PS2 start or busy text sorts in front of both title strips.
    _,instructions=p.run(0x118148,limit=150000)
    if not menu:
        _,n=p.run(0x127a88,limit=350000)
    else:
        _,n=p.run(0x1cd700,limit=350000)
    instructions+=n
    if p.read(0x3ec73c,4):
        _,n=p.run(0x113b28,stop_before=(0x113bc8,));instructions+=n
    draw=[]
    for i in range(p.read(0x345178,4)):
        a=PACKETS+i*128
        prim,color,tex,ptr,n=struct.unpack_from('<5Q',p.memory,a)
        if prim==0x1ff3:
            v=[p.read(a+16+16*j,8) for j in range(4)]
            coords=[(((xy&65535)-0x6c00)//16,(((xy>>16)&65535)-0x7900)//8) for xy in v]
            assert coords==[(0,0),(0,480),(640,0),(640,480)] and color>>24&255==128
            draw.append((v[0]>>32,None,0,0,640,480,0,0,0,0,color&0xffffffff));continue
        assert prim==0x1ff2 and n==4
        v=[struct.unpack_from('<5fI',p.memory,ptr+j*24) for j in range(4)]
        assert all(vv[5]==color&0xffffffff for vv in v)
        x,y,z,u,w,_=v[0];r,b,_,ur,wb,_=v[3]
        assert all(c==int(c) for c in [x,y,r,b,u,w,ur,wb])
        draw.append((z,((tex>>37)&16383),int(x),int(y),int(r),int(b),int(u),int(w),int(ur),int(wb),color&0xffffffff))
    return sorted(draw,key=lambda item:item[0]),instructions

def paint(draw,tex,cache):
    base=tuple(draw[:2]);bgkey=(base,tex.get('fade',(0,False)))
    if bgkey not in cache:
        cache.clear()
        frame=np.zeros((480,640,4),np.uint8);frame[:,:,3]=255
        for cmd in base:quad(frame,cmd,tex)
        cache[bgkey]=frame
    frame=cache[bgkey].copy()
    for cmd in draw[2:]:quad(frame,cmd,tex)
    return frame

def quad(frame,cmd,tex):
    _,page,x,y,r,b,u,v,ur,vb,color=cmd
    if page is None:
        frame[y:b,x:r,:3]=[(color>>c)&255 for c in (0,8,16)];return
    rgba=tex[page]
    us=u+((2*np.arange(r-x)+1)*(ur-u))//(2*(r-x))
    vs=v+((2*np.arange(b-y)+1)*(vb-v))//(2*(b-y))
    mod=np.array([(color>>k)&255 for k in (0,8,16,24)],np.int32)
    source=np.minimum(255,rgba[vs[:,None],us].astype(np.int32)*mod//128)
    target=frame[y:b,x:r,:3];target[:]=np.clip(target+((source[:,:,:3]-target)*source[:,:,3:]//128),0,255)

def original_frame(p,tex,menu,row,direction,tick,title,idle,prompt,level=0,white=False,cache=None):
    if cache is None:cache={}
    if tex.get('fade',(0,False))!=(level,white):
        for addr,value in [(0x3ebf18,2),(0x3ec734,level),(0x3ec730,0xffffffff if white else 0xff000000),
                           (0x3ebf2c,1),(0x3ebf24,0)]:p.write(addr,value,4)
        p.run(0x116588,limit=500000)
        clut=np.frombuffer(p.memory,np.uint8,1024,0x11e7980+4*768).reshape(256,4)
        indices=np.frombuffer(p.memory,np.uint8,1024*1024,p.read(0x3a9680+5*40,4))
        tex[0x30cd]=clut[indices].reshape(1024,1024,4);tex['fade']=(level,white)
    items,n=packets(p,menu,row,direction,tick,title,idle,prompt)
    return paint(items,tex,cache),len(items),n

def prompt_lifecycle(p):
    assert (p.read(0x582230,4),p.read(0x582234,4))==(60,1)
    clocks=frames=0
    # The common scheduler keeps one oscillator across menu and battle. Its
    # special submode-5 gate only applies when the parent mode is nonzero.
    phases=[(4,2,1,0,20),(0,2,1,0,125),(6,2,1,0,33),(3,2,0,0,80),
            (4,5,0,0,15),(0,5,0,1,15),(0,2,0,0,131)]
    for mode,sub,busy1,busy2,duration in phases:
        for addr,value in [(0x4c3808,mode),(0x4c38a8,sub),(0x4c3834,busy1),(0x4c3838,busy2)]:
            p.write(addr,value,4)
        for _ in range(duration):
            for addr in (0x345178,0x345180,0x378e08,0x3db8f8):p.write(addr,0,4)
            p.run(0x114e80);p.run(0x118148,limit=150000);frames+=1
            if not (mode and sub==5):clocks+=1
            phase=clocks%120
            assert (p.read(0x582230,4),p.read(0x582234,4))==(abs(60-phase),int(phase<60))
            assert (p.read(0x4c3834,4),p.read(0x4c3838,4))==(busy1,busy2)
            expected=0 if mode or phase>=60 else 1 if busy1 or busy2 else 3
            assert p.read(0x345178,4)==expected
    p.run(0x1ba120);assert (p.read(0x582230,4),p.read(0x582234,4))==(10,0)
    return dict(common_scheduler_frames=frames,oscillator_advances=clocks,
                initial=[60,1],explicit_disc_wait_reset=[10,0],period=120)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--assets',type=Path,default=ASSETS)
    ap.add_argument('--viewer',type=Path);ap.add_argument('--report',type=Path,default=REPORT)
    args=ap.parse_args()
    p,tex=fixture(args.assets);clock=prompt_lifecycle(p);cache={};count=total=0
    cases=[(0,5,0,0,t,t,prompt,0,0) for t in (0,1,29,30,31,59,60,119,120,719) for prompt in (0,1,2)]
    cases.extend((1,r,d,t,0,0,0,0,0) for r in range(6) for d in (0,1,2) for t in range(15 if d else 1))
    levels=sorted({0,256,*range(0,256,25),*range(256,0,-25)})
    for white in (0,1):
        for level in levels:
            cases.extend([(1,0,0,0,50,0,0,level,white),(1,3,2,9,50,0,0,level,white),
                          (0,5,0,0,50,0,1,level,white),(0,5,0,0,50,0,2,level,white)])
    with tempfile.TemporaryDirectory() as tmp:
        cpp=Path(tmp)/'title.cpp';cpp.write_text(DRIVER);exe=cpp.with_suffix('')
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/console_title_art.cpp','-o',exe],check=True)
        with subprocess.Popen([exe,args.assets],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
            for case in cases:
                expected,number,n=original_frame(p,tex,*case,cache=cache);count+=number;total+=n
                if not case[0]:assert number==(1 if case[7]==256 else 2)+(0,3,1)[case[6]]
                proc.stdin.write((' '.join(map(str,case))+'\n').encode());proc.stdin.flush()
                native=np.frombuffer(proc.stdout.read(expected.size),np.uint8).reshape(expected.shape)
                if not np.array_equal(native,expected):
                    bad=np.any(native!=expected,axis=-1);y,x=map(int,np.argwhere(bad)[0])
                    raise AssertionError((case,int(bad.sum()),x,y,native[y,x].tolist(),expected[y,x].tolist()))
            proc.stdin.close();assert proc.wait()==0
    report=dict(status='passed',elf_sha256=ORIGINAL,identical_640x480_frames=len(cases),original_gs_packets=count,
                original_draw_routine_instructions=total,menu_rows=6,scroll_ticks_per_direction=15,
                black_and_white_fade_levels=levels,original_prompt_clock=clock,
                resources={s:hashlib.sha256((args.assets/s).read_bytes()).hexdigest() for s in ('bg_title00.tex','bg_title00.pal','obj0_16.tex','font_coin.tex')},
                scope='Original 118148 with resident 1ba1b0 before input, complete 127a88 idle or 1cd700 mode drawings, final GS colors and UV, original 116588 palette upload/expansion, 113aa8/113b28 forced fullscreen quad and independent resident prompt priority. Both local ports, factory options, hidden/START/WAIT prompts. Includes every intermediate black/white level of the fast title transitions.')
    if args.viewer:report['viewer_sha256']=hashlib.sha256(args.viewer.read_bytes()).hexdigest()
    args.report.write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
