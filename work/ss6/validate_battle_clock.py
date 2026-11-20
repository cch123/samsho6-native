#!/usr/bin/env python3
"""Compare the round clock with the Japanese counter, selection logic and GS packets."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from validate_live_rage_hud import ASSETS, MATCH, OUT, PKG, ROOT, atlas, original
from validate_rage_gauge import draw as draw_gauges
from validate_ten_explosion import scenario
from extract_collision_tables import SOURCE_HASH

X,Y,W,H=279,28,82,65
B=0x1c30000
CPP=r'''
#include "rage_gauge.hpp"
#include "battle_clock.hpp"
#include <iostream>
int main(int argc,char** argv) {
    ss6::RageGaugeRenderer hud(argv[1]);
    int s,b,phase0,phase1;uint32_t state0,state1;
    while(std::cin>>s>>b>>phase0>>state0>>phase1>>state1){
        ss6::StateEntryActor left,right;left.rageState120=phase0;left.state194=state0;
        right.rageState120=phase1;right.state194=state1;
        std::vector<uint8_t> image(640*448*4);
        for(int y=28;y<93;++y)for(int x=279;x<361;++x){
            auto* v=image.data()+4*(640*y+x);
            v[0]=x+2*y;v[1]=3*x+y;v[2]=x^y;v[3]=255;
        }
        bool stopped=ss6::roundClockStopped(b,left,right);
        hud.paintClock({s,stopped,true},image);
        std::cout.put(char(stopped));
        for(int y=28;y<93;++y)std::cout.write(reinterpret_cast<char*>(image.data()+4*(640*y+279)),82*4);
    }
}
'''
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def original_clock():
    p=original();p.write(0x4d3d00,B,4)
    return p,{2:atlas(1),10:atlas(2)}

def draw(p,atlases,background,raw_timer,time_option,phase,players):
    p.write(B+4,phase,4);p.write(B+0x114,raw_timer,4);p.write(B+0x13c,time_option,4)
    for side,(meter,state) in enumerate(players):
        a=p.read(0x4d3d08,4)+side*0xf2c
        p.write(a+0x120,meter,4);p.write(a+0x194,state,4)
    # Only the per-frame submission buffers are reset. The HUD itself decides
    # whether to suppress the backing plate, choose infinity and modulate red.
    for at in (0x345178,0x378e08):p.write(at,0,4)
    p.run(0x114e80)
    planes=[]
    def packets(pc):
        if pc==0x108464:
            sub=p.registers[19];slot=p.registers[16]
            assert p.read(sub,4)==0x1ff2 and (p.read(sub+16,8)>>20)&63==19
            start=p.read(sub+24,4)
            vertices=[struct.unpack_from('<5fI',p.memory,start+24*i) for i in range(4)]
            planes.append((vertices[0][2],slot,p.read(sub+8,4),vertices))
    # The translucent backing stays under the timer even when its front plate disappears.
    p.run(0x1baff0,observe=packets,limit=100000)
    p.run(0x1babd0,stop_before=(0x1babf0,),observe=packets,limit=100000)
    assert len(planes) in (3,4)
    stopped=len(planes)==3
    assert [s for _,s,_,_ in planes]==([10,2,2] if stopped else [10,10,2,2])
    assert planes[0][2]==0x40808080
    assert all(c==(0x80000080 if stopped else 0x80808080) for _,_,c,_ in planes[1:])
    out=background.copy()
    for _,slot,mod,v in sorted(planes,key=lambda row:row[0]):
        x,y,_,u,t,_=v[0];x1,y1,_,u1,t1,_=v[3];w,h=int(x1-x),int(y1-y)
        assert (w,h)==(int(u1-u),int(t1-t))
        ids,clut=atlases[slot];colors=clut[ids[int(t):int(t1),int(u):int(u1)]].astype(np.int32)
        region=out[int(y)-Y:int(y1)-Y,int(x)-X:int(x1)-X,:3]
        factors=np.array([(mod>>(i*8))&255 for i in range(3)])
        rgb=colors[:,:,:3]*factors>>7
        alpha=colors[:,:,3:4]*(mod>>24)>>7
        region[:]=region+((rgb-region)*alpha>>7)
    return out,stopped,len(planes)

def standalone(tmp):
    p,atlases=original_clock();y,x=np.mgrid[Y:Y+H,X:X+W]
    bg=np.stack([x+2*y,3*x+y,x^y,np.full_like(x,255)],axis=2).astype(np.uint8)
    configs=[(4,0,0,0,0),(4,0,0x240001,0,0),(4,0,0,2,0),(4,3,0x260001,0,0),
             (4,0,0,0,0x240001),(4,2,0,0,0),(5,2,0,0,0)]
    cases=[(seconds,*c) for seconds in range(-1,100) for c in configs]
    src=tmp/'clock.cpp';src.write_text(CPP);exe=tmp/'clock'
    subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,ROOT/'src/rage_gauge.cpp','-o',exe],check=True)
    output=memoryview(subprocess.check_output([exe,ASSETS],input=''.join(' '.join(map(str,r))+'\n' for r in cases).encode()))
    stride=1+W*H*4;assert len(output)==len(cases)*stride
    n=0
    for i,(s,b,p0,a0,p1,a1) in enumerate(cases):
        expected,hold,npk=draw(p,atlases,bg,s*0x5a00 if s>=0 else 0,3 if s<0 else 0,b,[(p0,a0),(p1,a1)])
        assert bool(output[i*stride])==hold and expected.tobytes()==output[i*stride+1:(i+1)*stride],(i,s,b,p0,a0,p1,a1)
        n+=npk
    return dict(cases=len(cases),packets=n,pixels=len(cases)*W*H)

def live(args):
    viewer,assets,side,limit,tmp=args
    p,atlases=original_clock()
    pre,pads=scenario(side,'late');expanded=[(a,b) for n,a,b in pre+pads for _ in range(n)]
    input_lines=['1 %d %d\n'%r for r in expanded[:1521]]
    opts=['--mode','versus','--round-time',str(limit),f'--p{side+1}-spirit','ten']
    rows=subprocess.check_output([MATCH,assets,*opts,'--rage-hud-fields'],input=''.join(input_lines),text=True).splitlines()
    samples={500,1060,1061,1062,1113,1114,1115,1332,1333,1334,1335,1350,1516,1517,1518}
    # A seconds boundary makes priority-20 publication separately testable.
    for i in range(500,650):
        if rows[i].split()[64]!=rows[i-1].split()[64]:
            samples.update((i,i+1,i+2));break
    records=[]
    for tick in sorted(samples):
        old=rows[tick-2].split();row=rows[tick-1].split()
        # The body requests and timer are from before the visit. The priority
        # five meter has already advanced: reproduce 11e760, then world-4's
        # promotion when its final callback precedes the HUD on that tick.
        players=[]
        for who in range(2):
            at=p.read(0x4d3d08,4)+who*0xf2c;base=23+11*who
            state=int(old[3+10*who])|(int(old[4+10*who])<<16)
            p.write(at+0x10c,3 if who==side else 0,4);p.write(at+0x110,who,4);p.write(at+0xa24,who,4)
            p.write(at+0x194,state,4);p.write(at,0x1d00000+who*0x1000,4)
            for i,off in enumerate((0x120,0x124,0x128,0x130,0x134,0x138,0x23c)):p.write(at+off,int(old[base+i]),4)
            if int(old[50]) and old[46]=='4' and int(old[48])<=0 and not int(old[49]):
                p.write(B,4,4);p.write(B+8,int(old[47]),4);p.run(0x11e760,[who],limit=200000)
            if int(old[base])<2 and int(row[base])==2:
                p.write(at+0xa30,int(old[9+10*who]),4);p.run(0x11f248,[who])
            players.append((p.read(at+0x120,4),state))
        pad=tmp/f'p{side}-{limit}.pad';pad.write_text(''.join(input_lines[:tick]))
        raw=tmp/f'p{side}-{limit}.raw';bmp=raw.with_suffix('.bmp')
        subprocess.run([viewer,'--assets',assets,*opts,'--match-replay',pad,'--dump',raw,'--snapshot',bmp],check=True,stdout=subprocess.DEVNULL)
        scene=np.frombuffer(raw.read_bytes(),np.uint8,offset=8).reshape(448,640,4)
        screenshot=np.asarray(Image.open(bmp).convert('RGBA'))
        window=screenshot[Y:Y+H,X:X+W]
        for top in (453,468):
            assert np.any(np.all(screenshot[top:top+9,:,:3]==[242,237,218],axis=2)),(tick,'control legend',top)
        assert row[12]==row[22]=='0'
        # Both gauges' outer frames overlap the clock by eight pixels.
        # Their fills and sword gauges are outside this rectangle at every HP.
        scene=scene.copy()
        draw_gauges(p,scene,atlases,(0x1bada0,0x1bae60))
        background=scene[Y:Y+H,X:X+W]
        expected,held,packets=draw(p,atlases,background,int(old[65]),3 if limit==0 else 0,int(old[1]),players)
        if not np.array_equal(expected,window):
            points=np.argwhere(np.any(expected!=window,axis=2))[:12]
            raise AssertionError((tick,side,limit,[(int(x+X),int(y+Y),expected[y,x].tolist(),window[y,x].tolist()) for y,x in points]))
        records.append(dict(tick=tick,held=held,seconds_before=int(old[64]),seconds_after=int(row[64]),packets=packets))
    assert any(r['held'] for r in records) and not all(r['held'] for r in records)
    if limit:assert any(r['seconds_before']!=r['seconds_after'] for r in records)
    return dict(player=side+1,limit=limit,frames=records,pixels=len(records)*W*H)

def main():
    assert digest(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    viewer=PKG/'ss6-viewer';assets=PKG/'assets'
    assert digest(viewer)==digest(MATCH.parent/'ss6-viewer')
    for name in ('obj1_16.tex','obj2_16.tex'):assert digest(assets/name)==digest(ASSETS/name)
    with tempfile.TemporaryDirectory(prefix='ss6-clock-') as folder:
        tmp=Path(folder);unit=standalone(tmp)
        with ProcessPoolExecutor(4) as pool:
            matches=list(pool.map(live,[(viewer,assets,side,limit,tmp) for side in range(2) for limit in (0,60)]))
    result=dict(status='passed',elf_sha256=SOURCE_HASH,viewer_sha256=digest(viewer),standalone=unit,packaged=matches,
                scope='Original 1baff0 and 1babd0 through 1babf0 with 141cf8, 1bb050, 1bb0b0 and 117de8. Every value from 00 through 99 and infinity, active/spent/idle, both seats. Full timer plate over a patterned background. Real two-player console inputs, including the Issen backdrop, checked in packaged 640x480 SDL snapshots over the scene without HUD.')
    (OUT/'battle-clock-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(unit,len(matches),'packaged matches',sum(len(m['frames']) for m in matches),'frames',result['viewer_sha256'])
if __name__=='__main__':main()
