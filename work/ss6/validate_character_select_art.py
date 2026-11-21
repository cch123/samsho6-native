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
from extract_select_mode_art import FAMILIES

OUT=ROOT/'outputs/ss6-feasibility'
DRIVER=r'''
#include "character_select_art.hpp"
#include <iostream>
int main(int argc,char**argv){
    ss6::CharacterSelectArt art(argv[1]);ss6::CharacterSelect state;
    std::vector<uint8_t> pixels(640*480*4);
    int mode;
    while(std::cin>>mode>>state.drawFrame>>state.drawRemaining){
        state.configure(mode);if(mode==3)state.submode=0;
        for(auto& seat:state.seats){
            seat.present=state.twoSided()||unsigned(&seat-state.seats.data())==state.soleSeat();
            int kuroko;
            std::cin>>seat.cell>>seat.drawPhase>>seat.drawCount>>seat.controls>>seat.selected>>kuroko;
            seat.kurokoFaces=kuroko>0;seat.kurokoColumns=kuroko;
            seat.character=seat.kurokoFaces&&state.kurokoCell(unsigned(&seat-state.seats.data()),seat.cell)?48:state.roster.at(seat.cell);
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
    # The ARCADE Kuroko hint button: resident icon palette upload at 109630 (as in the spirit page).
    ico=(ASSETS/'ps2_common_icon.pal').read_bytes()
    p.memory[0x1236740:0x1236740+len(ico)]=ico;p.run(0x116588,limit=500000)
    atlases[46]=np.frombuffer(p.memory,np.uint8,1024,0x1236f40).reshape(256,4)[
        np.frombuffer((ASSETS/'ps2_common_icon.tex').read_bytes(),np.uint8).reshape(512,512)].copy()
    cases=[]
    def add(t,c,n,k=0,s=0):
        cases.append((t,1800-t,(c,n,t,k,0),((c+7)%48,n,t,s,1)))
    for t in range(0,60,3):add(t,2,1)
    for cell in range(48):
        for n,t in [(2,83+cell),(3,cell%10),(4,cell%10),(5,cell%15),(6,cell%10)]:add(t,cell,n)
    for n in (7,8,9,10,11):
        for t in range(15 if n!=7 else 6):add(t,(t+3)%48,n)
    for c in (2,3,12,36):add(32,c,2,1,4)
    # Both slots can hold any roster portrait. Populate their actual source
    # CLUTs and compare all named confirmations of the unlocked grid.
    roster=[p.read(0x4c82a8+4*i,4) for i in range(48)]
    assert 53 in roster and 42 in roster and 40 in roster
    portraits={i:upload(p,f'bup_{i:02}',512,False,256) for i in (*range(43),44,45,46,47,48)}
    for cell,next_cell in zip(range(48),list(range(1,48))+[0]):
        portraits_here=[42 if roster[i]==53 else roster[i] for i in (cell,next_cell)]
        cases.append((84,1716,(cell,8,8,0,portraits_here[0]),(next_cell,8,8,0,portraits_here[1])))
    # Kuroko view (12db80): face 0x31 for the first n columns from the cursor's column.
    for n,cell,ph,t in [(1,2,2,30),(3,9,2,41),(8,40,2,55),(8,41,2,70),(5,47,3,4),(8,13,5,7)]:
        cases.append((90+n,1700,(cell,ph,t,0,48,n),((cell+11)%48,2,t,0,0,0)))
    cases=[(3,0,*c) for c in cases];vs=len(cases)
    # Mode-dependent pages (extract_select_mode_art.py). The absent seat of a single-seat
    # mode submits nothing; PRACTICE draws both seats and the stopped-countdown glyphs.
    for mode,submode,seat in FAMILIES:
        if mode in (9,10) and seat:continue
        def both(frame,remain,a,b=None):
            idle=(0,0,0,0,0,0)
            if mode in (9,10):cases.append((mode,submode,frame,remain,a,b or ((a[0]+7)%48,*a[1:])))
            else:cases.append((mode,submode,frame,remain,*((a,idle) if not seat else (idle,a))))
        for t in range(0,60,3):both(t,1800-t,(2,1,t,0,0,0))
        for cell in range(48):
            for n,t in [(2,83+cell),(3,cell%10),(4,cell%10)]:both(100+cell,1739-7*cell,(cell,n,t,0,0,0))
        for n,cell,ph,t in [(1,2,2,30),(3,9,2,41),(8,40,2,55),(8,41,2,70),(5,47,3,4)]:
            both(90+n,1700,(cell,ph,t,0,48,n),((cell+11)%48,2,t,0,0,0))
        for c in (2,3,12,36):both(32,1500,(c,2,1,4,0,0),((c+5)%48,2,1,1,0,0))
        if mode in (9,10):
            for n in (8,9,10,11):
                for t in range(15):both(200+t,1739,((t+3)%48,n,t,0,(t+3)%43,0),((t+9)%48,n,t,0,(t+11)%43,0))
        else:
            for t in range(6):
                for cell in (0,13,26,41):both(300+t,900,(cell,7,t,0,0,0))
    with tempfile.TemporaryDirectory() as temp:
        d=Path(temp);src=d/'driver.cpp';src.write_text(DRIVER);exe=d/'driver'
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',src,ROOT/'src/character_select_art.cpp',
                        ROOT/'src/versus_result_art.cpp','-o',exe],check=True)
        proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE);count=0
        try:
            for mode,submode,frame,remain,p0,p1 in cases:
                p.write(0x4c3808,mode,4);p.write(0x4c38a8,submode,4);present=(0,1) if mode in (3,9,10) else (int(mode in (2,12)),)
                p0=tuple(p0)+(0,)*(6-len(p0));p1=tuple(p1)+(0,)*(6-len(p1))
                for side,(c,ph,t,key,char,kn) in enumerate((p0,p1)):
                    p.write(0x4c82a0+4*side,c,4)
                    for i in range(48):  # face[seat]: identity, or 0x31 over the Kuroko columns
                        p.write(0x4c8370+200*side+4*i,0x31 if kn and (i//6-c//6)%8<kn else i,4)
                atlases[7]=portraits[p0[4]];atlases[8]=portraits[p1[4]]
                p.write(0x4c8280,0,4);p.write(0x4c8288,remain,4);p.run(0x114e80);q=[]
                for side,(c,ph,t,key,char,kn) in enumerate((p0,p1)):
                    if side in present:q+=calls(p,0x12a418,side,ph,t,int(ph in (2,5)),key)[0]
                q+=calls(p,0x135438,frame)[0];q+=calls(p,0x128a68)[0];count+=len(q)
                expected=render(q,atlases)
                proc.stdin.write((' '.join(map(str,(mode,frame,remain,*p0[:5],p0[5],*p1[:5],p1[5])))+'\n').encode());proc.stdin.flush()
                got=np.frombuffer(proc.stdout.read(expected.size),np.uint8).reshape(expected.shape)
                if not np.array_equal(got,expected):
                    ys,xs=np.where(np.any(got!=expected,axis=2));x,y=xs[0],ys[0]
                    Image.fromarray(expected).save('/private/tmp/ss6-select-expected.png');Image.fromarray(got).save('/private/tmp/ss6-select-native.png')
                    raise AssertionError((mode,frame,p0,p1,len(ys),x,y,got[y,x],expected[y,x]))
                if mode==3 and p0[0]==3 and p0[1]==2 and p0[3]==0:
                    Image.fromarray(got).save(OUT/'character-select-native.png')
        finally:proc.stdin.close();proc.wait()
        assert proc.returncode==0
    report=dict(status='passed',original_sha256=ORIGINAL,frames=len(cases),two_seat_frames=vs,mode_frames=len(cases)-vs,
                mode_families=[dict(mode=m,submode=s,seat=seat) for m,s,seat in FAMILIES],
                mode_scope='Mode-word pages: ARCADE 1/2 and SURVIVAL 0xb/0xc single seat with the other seat absent (right-hand layout for seat 1, Kuroko hint frame and button, record frame), PRACTICE 9/10 both seats with the second-seat label and the stopped-countdown glyph pair. Sprite and flat submissions of 12a418/135438/128a68 only: the hint and record text (10a460/109f08) and the single seat fighter object (11d868) are outside both sides of this comparison.',
                confirmed_portraits=len(portraits),original_quads=count,all_rgba_pixels=640*480*len(cases),
                scope='Fully unlocked two-seat character screen (unlock bytes 40..48 = 0): 48 cells in 8 columns, Kuroko Start view, entrance, motion, cursor pulses, confirm, Japanese names, original CLUTs, both dimensional portrait panels, animated scrolling backdrop and countdown. Native display compared to original geometry; no GS hardware or BIOS.')
    (OUT/'character-select-art-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)

if __name__=='__main__':main()
