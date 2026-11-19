#!/usr/bin/env python3
"""Compare original winner-text packet positions and uploaded glyphs against native RGBA output."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

from extract_versus_quotes import ASSETS, ISO_PATH, extract
from inspect_iso import Iso
from mips_probe import Probe
from validate_dash_motion import ELF, PIN, ROOT, digest

FONT_RAM=0x106b840
CACHE=0x1a00000
PACKETS=0x68c3c0
OUTPUT=ROOT/'outputs/ss6-feasibility/versus_result_text_validation.json'
W,H=640,480
NATIVE_DRIVER=r'''
#include "versus_result_text.hpp"
#include <iostream>
#include <vector>
int main(int argc,char**argv){
    if(argc!=2)return 2;
    ss6::VersusResultText text(argv[1]);
    std::vector<uint8_t> base(640*480*4);
    for(int y=0;y<480;++y)for(int x=0;x<640;++x){
        auto p=base.data()+4*(640*y+x);
        p[0]=x+3*y+17;p[1]=7*x+y;p[2]=x+5*y;p[3]=255;
    }
    int q,limit;
    while(std::cin>>q>>limit){
        auto rgba=base;
        text.paint(q,limit,rgba);
        std::cout.put(char(text.glyphCount(q)));
        std::cout.write(reinterpret_cast<const char*>(rgba.data()),rgba.size()).flush();
    }
}
'''


def original_quote(p,q):
    ptr,ins=p.run(0x1a3070,[0,2,q]);lines=[]
    for j in range(3):
        addr=p.read(ptr+8+j*4,4)
        if not addr:break
        lines.append(bytes(p.memory[addr:p.memory.index(0,addr)]).decode('cp932'))
    count=sum(map(len,lines))

    def draw(limit):
        nonlocal ins
        for addr in [0x345178,0x345180]:p.write(addr,0,4)
        p.write(0x3d3aa0,limit,4)
        finished,n=p.run(0x1a2870,[ptr],limit=1200000);ins+=n
        shown=count if limit<0 else min(count,limit)
        assert p.read(0x3d3ab0,4)==p.read(0x345178,4)==shown
        assert finished==int(count<limit)
        sprites=[]
        xyoff=[p.read(addr,4) for addr in (0x32ce14,0x32ce18)]
        def xy(value):return tuple(((value>>(16*j)&0xffff)-xyoff[j])//16 for j in (0,1))
        for i in range(shown):
            regs=struct.unpack_from('<7Q',p.memory,PACKETS+128*i)
            prim,rgbaq,tex,uv0,xy0,uv1,xy1=regs
            assert prim==0x1ff1 and rgbaq&0xffffffff==0x80808080
            assert (tex>>20)&0x3f==20 and (tex>>37)&0x3fff==0x3080 and not ((tex>>56)&31)
            x,y=xy(xy0);right,bottom=xy(xy1)
            assert (right-x,bottom-y)==(24,24)
            u=(uv0&0xffff)//16;v=(uv0>>16&0xffff)//16
            assert uv1-uv0==(24*16)*(1+0x10000)
            pix=b''.join(bytes(p.memory[CACHE+(v+row)*256+u//2:CACHE+(v+row)*256+u//2+12]) for row in range(24))
            sprites.append((x,y,pix))
        return sprites
    all_glyphs=draw(-1)
    for limit in (0,1,count//2,count-1,count,count+1):assert draw(limit)==all_glyphs[:limit]
    return lines,all_glyphs,ins


def stamp(dst,sprite,palette):
    # The reference consumes emitted GS sprite/UV values and the original
    # upload cache directly, independently of the extractor's SJIS lookup.
    x,y,texels=sprite
    for row in range(24):
        for col in range(24):
            texel=texels[row*12+col//2]>>(4*(col&1))&15
            r,g,b,alpha=palette[texel]
            if not alpha:continue
            at=4*((y+row)*W+x+col)
            for j,c in enumerate((r,g,b)):
                dst[at+j]=(c*alpha+dst[at+j]*(128-alpha))//128


def validate():
    assert digest(ELF)==PIN
    asset=ASSETS/'versus_quotes_00.bin'
    assert asset.read_bytes()==extract(ISO_PATH)
    original=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN')
    p=Probe(ELF.read_bytes(),finite_model=True)
    p.memory[FONT_RAM:FONT_RAM+len(original)]=original
    # Set up the font upload cache, full logical screen mode and normal
    # RGB scale. All original rendering, SJIS and glyph-count code executes.
    p.write(0x3a9c20,CACHE,4);p.write(0x32ce08,1,4);p.write(0x43d064,256,4)
    palette=[bytes(p.memory[0x348a48+4*i:0x348a4c+4*i]) for i in range(16)]
    base=bytes(c for y in range(H) for x in range(W) for c in ((x+3*y+17)&255,(7*x+y)&255,(x+5*y)&255,255))
    cases=[];snapshots=0;instructions=0
    with tempfile.TemporaryDirectory(prefix='ss6-result-text-') as name:
        tmp=Path(name);cpp=tmp/'check.cpp';exe=tmp/'check'
        cpp.write_text(NATIVE_DRIVER)
        subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',cpp,
                        ROOT/'src/versus_result_text.cpp','-o',exe],check=True)
        with subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as native:
            def compare(q,limit,n,expected):
                nonlocal snapshots
                native.stdin.write(f'{q} {limit}\n'.encode());native.stdin.flush()
                assert native.stdout.read(1)==bytes([n])
                got=native.stdout.read(len(base))
                if got!=expected:
                    delta=next(i for i,(a,b) in enumerate(zip(expected,got,strict=True)) if a!=b)
                    raise AssertionError((q,limit,delta//4%W,delta//4//W,delta%4,expected[delta],got[delta]))
                snapshots+=1
            for q in range(16):
                lines,sprites,ins=original_quote(p,q);instructions+=ins
                frame=bytearray(base);count=len(sprites)
                compare(q,0,count,frame)
                for n,s in enumerate(sprites,1):
                    stamp(frame,s,palette);compare(q,n,count,frame)
                for extra in (-1,count+1,256):compare(q,extra,count,frame)
                cases.append(dict(quote=q,lines=lines,glyphs=count,first_xy=sprites[0][:2],full_rgba_sha256=hashlib.sha256(frame).hexdigest()))
            native.stdin.close()
            assert native.wait(timeout=10)==0
    report=dict(status='passed',elf_sha256=PIN,font_disc_path='/BIN/GOTH_24.BIN',font_sha256=hashlib.sha256(original).hexdigest(),
                glyphs=struct.unpack_from('<H',asset.read_bytes(),4)[0],asset_sha256=digest(asset),canvas=[W,H],
                original_calls=['1a3070','1a2870 including 113028, 10a1c0, 1090a8, 108c98'],original_instructions=instructions,
                original_draws=16*7,compared_full_rgba_frames=snapshots,quotes=cases,
                validator_sha256=digest(Path(__file__)),source_sha256=digest(ROOT/'src/versus_result_text.cpp'),
                scope='All 16 Japanese Haohmaru victory linesets. Compare every prefix and completion/uncapped limits to original GS sprites, original font-cache uploads and 16-color CLUT on a patterned 640x480 canvas. Logical full-frame projection. Original console GS output was not captured.')
    OUTPUT.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'{len(cases)} quotes, {snapshots} complete RGBA frames, {instructions} EE instructions PASS')


if __name__=='__main__':validate()
