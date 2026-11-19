#!/usr/bin/env python3
"""Compare native overlays on a real combat image, then the separate score scene, to Japanese GS packets."""
import argparse,hashlib,json,struct,subprocess,tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from extract_console_ranking_art import setup,unpack4,ASSETS,RANK,PACKETS,GLYPH
from character_tiles_oracle import ROOT
from extract_versus_quotes import ISO_PATH,ORIGINAL
from extract_resources import recover
from inspect_iso import Elf,Iso

OUT=ROOT/'outputs/ss6-feasibility'
DRIVER=r'''
#include "console_ranking_art.hpp"
#include <fstream>
#include <iostream>
int main(int argc,char** argv) {
    ss6::ConsoleRankingArt art(argv[1]);
    std::vector<uint8_t> base(640*480*4);
    if(!std::ifstream(argv[2],std::ios::binary).read(reinterpret_cast<char*>(base.data()),base.size()))return 2;
    unsigned phase,age,first;
    while(std::cin>>phase>>age>>first) {
        auto pixels=base;art.paint({phase,age,first},pixels);
        std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
    }
}
'''

def disc_art_hashes():
    disc=Iso(ISO_PATH);elf=disc.read('/SLPS_255.59')
    assert hashlib.sha256(elf).hexdigest()==ORIGINAL
    arc=disc.by_path['/SAM_DATA.BIN']
    catalog={r['name']:r for r in recover(Elf(elf),arc['size'])}
    hashes={}
    for name in ('rank_obj.tex','face.tex','pal_all.bin','cloud_l.tex','cloud_r.tex',
                 'obj0.pal','map_main.tex','map_main.pal'):
        item=catalog[name];raw=disc.read_at(arc['lba']*disc.block+item['offset'],item['size'])
        assert raw==(ASSETS/name).read_bytes(),name
        hashes[name]=hashlib.sha256(raw).hexdigest()
    hashes['GOTH_24.BIN']=hashlib.sha256(disc.read('/BIN/GOTH_24.BIN')).hexdigest()
    return hashes

def original_clear(p):
    # 105380 selects environment one before each display swap. 1015a8
    # builds that environment from the original NTSC half-height field.
    for reg,value in ((16,0x68bf40),(18,0x330000),(19,0x330000)):p.put(reg,value)
    env=0x68c170;calls=[]
    def observe(pc):
        if pc==0x301930:calls.append(p.registers[4:11])
    p.run(0x1015a8,stop_before=(0x1015c8,),observe=observe)
    assert calls==[[env,0,640,224,2,48,1]]
    for base in (env+0xe0,env+0x1d0):
        registers=[p.read(base+i,8) for i in range(0,0x60,8)]
        # TEST, PRIM=sprite, RGBAQ=black, XYZ2 top-left/bottom-right, TEST.
        assert registers==[0x30000,0x47,6,0,0x3f80000000000000,1,0x79006c00,5,
                            0x87009400,5,0x50000,0x47]
    return (0,0,0,255)

class OriginalArt:
    def __init__(self):
        self.p=p=setup();self.quads=0;self.clear=original_clear(p)
        raw=(ASSETS/'rank_obj.tex').read_bytes()
        self.indices={41:np.frombuffer((ASSETS/'map_main.tex').read_bytes(),np.uint8).reshape(1024,1024),
                      8:np.frombuffer(raw,np.uint8,512*512).reshape(512,512)}
        for slot,name in [(30,'cloud_l'),(43,'cloud_r'),(10,'face')]:
            self.indices[slot]=unpack4((ASSETS/(name+'.tex')).read_bytes(),512)
        self.rankPal=np.frombuffer(raw,np.uint8,1024,512*512).reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4)
    def frame(self,phase,age,first,base):
        p=self.p;p.run(0x114e80)
        for a in (0x345178,0x345180,0x378e08,0x3ec73c,0x439a40):p.write(a,0,4)
        for a,v in ((0x258,phase),(0x260,age),(0x25c,first)):p.write(RANK+a,v,4)
        slots={};last=0
        def watch(pc):
            nonlocal last
            if pc==0x1149d0:last=p.registers[6]&255
            if pc==0x108464:slots[p.read(0x345178,4)-1]=last
        if phase==7:
            p.write(0x1fff008,0x1ffff00,8);p.run(0x1e9174,observe=watch,limit=25000)
        else:
            if phase==11:p.write(0x582214,1,4)  # A scene change has already been queued.
            p.run(0x1e8b38,observe=watch,limit=350000,stop_before=(0x115a00,) if phase==6 and age==64 else ())
        if phase in (11,12):
            assert p.read(0x5852c8+4*12,4)==0x1e9750
            assert p.read(RANK+0x258,4)==12 and p.read(0x345178,4)==0
        p.run(0x116588,limit=500000)
        def colors(addr,n):return np.frombuffer(p.memory,np.uint8,n*4,addr).reshape(n,4)
        dst=base.copy() if phase<=6 else np.full_like(base,self.clear);dst[:,:,3]=255
        draws=[]
        for i in range(p.read(0x345178,4)):
            a=PACKETS+128*i;typ,col,tex,uv,xy,uv1,xy1=struct.unpack_from('<7Q',p.memory,a)
            c=np.array([col>>(8*j)&255 for j in range(4)],np.int32)
            if typ==0x1ff3:
                (x,y),(r,b)=[(((q&65535)-0x6c00)/16,(((q>>16)&65535)-0x7900)/8) for q in (p.read(a+16,8),p.read(a+64,8))]
                draws.append((p.read(a+16,8)>>32,x,y,r,b,c,None));continue
            if typ==0x1ff2:
                s=slots[i];q0=struct.unpack_from('<5fI',p.memory,uv);q1=struct.unpack_from('<5fI',p.memory,uv+72)
                x,y,z,u,v,_=q0;r,b,_,ur,vb,_=q1
                pal=self.rankPal if s==8 else colors(0x1232880,256) if s==41 else colors(0x11e7980+64*((tex>>37&16383)-0x3081),16)
                texture=self.indices[s]
            else:
                assert typ==0x1ff1 and (tex>>37)&16383==0x3080
                (x,y),(r,b)=[(((q&65535)-p.read(0x32ce14,4))/16,(((q>>16)&65535)-p.read(0x32ce18,4))/16) for q in (xy,xy1)]
                z=(xy>>32)&0x7fffffff;u,v=(uv&65535)//16,((uv>>16)&65535)//16
                ur,vb=u+(r-x),v+(b-y);texture=unpack4(p.memory[GLYPH:GLYPH+512*256],512);pal=colors(0x348a48,16)
            draws.append((z,x,y,r,b,c,(texture,pal,u,v,ur,vb)))
        self.quads+=len(draws)
        for _,x,y,r,b,color,src in sorted(draws,key=lambda q:q[0]):
            x0,y0=max(0,int(x)),max(0,int(y));x1,y1=min(640,int(r)),min(480,int(b))
            if x1<=x0 or y1<=y0:continue
            rgb=dst[y0:y1,x0:x1,:3];existing=rgb.astype(np.int32)
            if src is None:shaded=color[:3];alpha=color[3]
            else:
                index,pal,u,v,ur,vb=src
                us=np.floor(u+(np.arange(x0,x1)+.5-x)*(ur-u)/(r-x)).astype(int).clip(0,index.shape[1]-1)
                vs=np.floor(v+(np.arange(y0,y1)+.5-y)*(vb-v)/(b-y)).astype(int).clip(0,index.shape[0]-1)
                texels=pal[index[vs[:,None],us]].astype(np.int32)*color//128
                shaded=np.minimum(texels[:,:,:3],255);alpha=texels[:,:,3:]
            rgb[:]=np.clip(existing+((shaded-existing)*alpha//128),0,255)
        return dst,len(draws)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--assets',type=Path,default=ASSETS);ap.add_argument('--viewer',type=Path)
    ap.add_argument('--background',type=Path,default=OUT/'combat-stage00-jump.png')
    ap.add_argument('--report',type=Path,default=OUT/'console-ranking-art-validation.json');args=ap.parse_args()
    base=np.asarray(Image.open(args.background).convert('RGBA'));assert base.shape==(480,640,4)
    reference=OriginalArt()
    cases=[]
    sample={0:[0],1:[0,480,539],2:[0,1,17,29,57,59],3:[0,4,26,47,49,60,83,105,119,120,180,239,240,267,300,333,359],
            4:[0,1,15,29,47,59],5:[0,59,60,359],6:[0,1,24,41,63,64],7:[1],8:[0,25,59,60,61,76,88,100,119,139,179,180,181,203,225,239],
            9:[0,1,21,50,59],10:[0,1,25,50,51,71,72,73,144,200,380,550,711,950,1100,1250,1367,1368,1370,1440,1600,1668,1690,1727,1728],11:[1],12:[0,1,21]}
    for phase,ticks in sample.items():
        for tick in ticks:cases.append((phase,tick,max(0,19-max(0,tick-1)//72) if phase==10 else 0))
    named=[(3,120),(6,64),(8,88),(10,1370)]
    hashes={};nonempty=0
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);cpp=tmp/'ranking.cpp';cpp.write_text(DRIVER);exe=cpp.with_suffix('')
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/console_ranking_art.cpp','-o',exe],check=True)
        template=tmp/'input.rgba';template.write_bytes(base.tobytes())
        with subprocess.Popen([exe,args.assets,template],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as proc:
            for phase,tick,first in cases:
                proc.stdin.write(f'{phase} {tick} {first}\n'.encode());proc.stdin.flush()
                frame,n=reference.frame(phase,tick,first,base)
                got=np.frombuffer(proc.stdout.read(frame.size),np.uint8).reshape(frame.shape)
                if not np.array_equal(frame,got):
                    mask=np.any(frame!=got,axis=2);y,x=map(int,np.argwhere(mask)[0])
                    raise AssertionError((phase,tick,int(mask.sum()),x,y,frame[y,x].tolist(),got[y,x].tolist()))
                if n:nonempty+=1
                if (phase,tick) in named:hashes[f'{phase}/{tick}']=hashlib.sha256(frame.tobytes()).hexdigest()
            proc.stdin.close();assert proc.wait()==0
    report=dict(status='passed',japanese_elf_sha256=ORIGINAL,exact_640x480_frames=len(cases),phases=len(sample),nonempty=nonempty,
                disc_art_sha256=disc_art_hashes(),gs_clear_buffers=2,post_transition_phase12_gs_packets=0,original_gs_packets=reference.quads,selected_image_hashes=hashes,geometry_sha256=hashlib.sha256((args.assets/'console_ranking_art.bin').read_bytes()).hexdigest(),
                background=str(args.background.name),scope='Priority-20 factory Japanese rank art and its original depth-sorted GS packets. The initial phases are composited on a supplied real combat image; CPU choices, live battle clocks and stage tint are validated separately. Optical latency, modified system-save scores and display-hardware filtering are outside the comparison.')
    if args.viewer:report['viewer_sha256']=hashlib.sha256(args.viewer.read_bytes()).hexdigest()
    args.report.write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':main()
