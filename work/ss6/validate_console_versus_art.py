#!/usr/bin/env python3
"""Compare the console menu with the complete original scheduler callback on a patterned arena."""
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from character_tiles_oracle import ROOT,ASSETS
from extract_console_versus_art import prepare, capture, extract, OUT, GLYPH, ORIGINAL

REPORT=ROOT/'outputs/ss6-feasibility/console_versus_art_validation.json'
DRIVER=r'''
#include "console_versus_art.hpp"
#include <iostream>
int main(int argc,char** argv){
 if(argc!=2)return 2;
 ss6::ConsoleVersusArt art(argv[1]);ss6::ConsoleVersusMenuDraw s;
 std::vector<uint8_t> pixels(640*448*4),base(pixels.size());
 for(int y=0;y<448;++y)for(int x=0;x<640;++x){auto* p=base.data()+4*(640*y+x);p[0]=x+3*y;p[1]=x^y;p[2]=4*x+y;p[3]=255;}
 while(std::cin>>s.visible>>s.selection>>s.dialog>>s.choice>>s.backgroundAlpha>>s.panelAlpha>>s.textAlpha>>s.phase2b3c>>s.borderFrame){
  pixels=base;art.paint(s,pixels);std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
 }
}
'''

def reference(p,packets,base):
    # Fetch source bytes by the TEX0 page, index by GS UVs, and apply GS
    # modulation per draw. This reads the font upload scratch at render time.
    def palette8(address,index,embedded):
        if embedded:index=(index&~24)|((index&8)<<1)|((index&16)>>1)
        return np.frombuffer(p.memory,np.uint8,1024,address).reshape(256,4)[index]
    result=base.copy()
    for _,(x,y,r,b),color,source in packets:
        dst=result[y:b,x:r,:3];mod=np.array([(color>>k)&255 for k in (0,8,16,24)])
        if source is None:
            dst[:]=dst+((mod[:3]-dst)*mod[3]//128);continue
        h,w=b-y,r-x
        if source[0]=='glyph':
            _,u,v=source
            uv=np.arange(w)[None,:]+u
            pos=(np.arange(h)[:,None]+v)*256+(uv//2)
            index=(np.frombuffer(p.memory,np.uint8)[GLYPH+pos]>>(4*(uv%2)))&15
            texture=np.frombuffer(p.memory,np.uint8,64,0x348a48).reshape(16,4)[index]
        else:
            page,cbp,u,v=source
            slot=1 if page==0x1a40 else 46
            texAddress=p.read(0x3a9680+40*slot,4)
            assert (page,cbp) in ((0x1a40,0x3119),(0x318d,0x3111))
            idx=np.frombuffer(p.memory,np.uint8,512*512,texAddress).reshape(512,512)[v:v+h,u:u+w].astype(int)
            texture=palette8(texAddress+512*512 if slot==1 else 0x1236f40,idx,slot==1)
        src=np.minimum(255,texture*mod//128)
        dst[:]=dst+((src[:,:,:3]-dst)*src[:,:,3:]//128)
    return result

def main():
    assert OUT.read_bytes()==extract()
    p=prepare();p.run(0x1daf50);p.run(0x1cebb0,[52])
    y,x=np.mgrid[:448,:640];base=np.stack((x+3*y,x^y,4*x+y,np.full_like(x,255)),axis=-1).astype(np.uint8)
    snapshots=[];quads=0;kinds=set()
    # These are the three main choices and both answers to each actual
    # prompt. Continue transfers immediately and has no confirmation box.
    profiles=[(0,0,1),(1,0,1),(2,0,1),(0,3,1),(0,3,0),(2,4,1),(2,4,0),(1,2,1)]
    with tempfile.TemporaryDirectory() as d:
        src=Path(d)/'driver.cpp';src.write_text(DRIVER);exe=Path(d)/'driver'
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',src,ROOT/'src/console_versus_art.cpp','-o',exe],check=True)
        proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            # Full entry and two border cycles; every Japanese description and confirm/cancel
            # highlight, sampled with several different colors at the same logical choice.
            for i in range(184):
                visible=i!=0;j=max(i-1,0)
                selection,dialog,choice=profiles[(j-66)%len(profiles)] if j>=66 else profiles[0]
                for offset,value in [(0,selection),(4,dialog),(8,0),(12,choice)]:p.write(0x582fb8+offset,value,4)
                back,panel=[p.read(a,4) for a in (0x582fc8,0x582fcc)]
                text,phase=[p.read(a,4) for a in (0x582b38,0x582b3c)]
                packets=capture(p,0x1dafa0,[]) if visible else []
                expected=reference(p,packets,base);quads+=len(packets);kinds.add((selection,dialog,choice))
                proc.stdin.write((' '.join(map(str,(int(visible),selection,dialog,choice,back*128//30,panel*192//30,text*17,phase,j)))+'\n').encode());proc.stdin.flush()
                native=np.frombuffer(proc.stdout.read(base.size),np.uint8).reshape(base.shape)
                if not np.array_equal(native,expected):
                    ys,xs,cs=np.where(native!=expected);pt=(ys[0],xs[0],cs[0])
                    raise AssertionError((i,selection,dialog,choice,len(ys),tuple(map(int,pt)),int(native[pt]),int(expected[pt])))
                snapshots.append(i)
        finally:
            proc.stdin.close();proc.wait()
        assert proc.returncode==0
    assert kinds==set(profiles)
    report=dict(source=ORIGINAL,identical_640x448_frames=len(snapshots),submitted_gs_packets=quads,
                tested_item_dialog_highlight_combinations=len(kinds),resource_bytes=OUT.stat().st_size,
                scope='Full 1dafa0 with real 1db850, 1db630, 1db708, 1db980 and 1cf598 callbacks. Both original 20/24px font uploads, slot1 and slot46 GS packets, all fades and 60-step border, including repeated cycles. Compared full RGBA over a patterned arena. No hardware capture.')
    REPORT.write_text(json.dumps(report,indent=2)+'\n');print(REPORT,report)
if __name__=='__main__':main()
