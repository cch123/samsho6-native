#!/usr/bin/env python3
"""Render the Japanese VS-next non-text queue independently of the native painter."""
import json
import struct
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT,ASSETS
from extract_versus_result_layout import canvas,calls,extract

OUTPUT=ROOT/'outputs/ss6-feasibility'
DRIVER=r'''
#include "versus_result_art.hpp"
#include <iostream>
#include <vector>
int main(int argc,char** argv) {
 ss6::VersusResultArt art(argv[1]);unsigned s,t,b,h;
 while(std::cin>>s>>t>>b>>h) {
  std::vector<uint8_t> out(640*h*4,77);art.paint(s,t,b,out);
  std::cout.write(reinterpret_cast<const char*>(out.data()),out.size());std::cout.flush();
 }
}
'''
def textures(p):
 # Original palette initialization/copy and color conversion; the explicit mode
 # and dimensions match the file-size classification in 10aa28 for slots 4/8.
 data=(ASSETS/'menu_bg00_00.tex').read_bytes();p.memory[0x1450000:0x1450000+len(data)]=data
 p.write(0x3a9680+4*40,0x1450000,4);p.run(0x1162b8);p.run(0x1162f0,[4])
 palette=(ASSETS/'win_00.pal').read_bytes();addr=0x1410000
 p.memory[addr:addr+len(palette)]=palette;p.write(addr,0,2);p.write(0x439b68,0,4)
 p.run(0x116478,[256,256,addr],limit=150000);p.write(0x3ebf2c,1,4);p.run(0x116588,limit=350000)
 bg=np.frombuffer(p.memory,dtype=np.uint8,count=1024,offset=0x1233f40).reshape(8,4,8,4)[:,[0,2,1,3],:,:].reshape(256,4)
 win=np.frombuffer(p.memory,dtype=np.uint8,count=1024,offset=0x11e7980+4*256).reshape(256,4)
 assert len(np.unique(win,axis=0))>160 and len(np.unique(bg,axis=0))>100
 return {4:bg[np.frombuffer(data,dtype=np.uint8,count=1024**2).reshape(1024,1024)].copy(),
         8:win[np.frombuffer((ASSETS/'win_00.tex').read_bytes(),np.uint8).reshape(512,512)].copy()}

def paint(out,primitives,tex):
 height=out.shape[0]
 for slot,vertices in sorted(primitives,key=lambda q:q[1][0][2]):
  v=np.asarray(vertices,dtype=np.float64);xy=v[:,:2]
  (left,top),(right,bottom)=xy.min(axis=0),xy.max(axis=0)
  x0,y0=max(0,int(np.ceil(left-.5))),max(0,int(np.ceil(top-.5)))
  x1,y1=min(640,int(np.ceil(right-.5))),min(height,int(np.ceil(bottom-.5)))
  if x1<=x0 or y1<=y0:continue
  sy,sx=np.mgrid[y0:y1,x0:x1];target=out[y0:y1,x0:x1,:3]
  if not slot:
   color=int(v[0,3]);assert color>>24==255
   target[:]=[(color>>n)&255 for n in [16,8,0]];continue
  # All VS quads are screen-axis-aligned. The four distinct UV corners
  # preserve the source rotation of the portrait strip at the atlas bottom.
  o=xy[0];ix=1 if xy[1,0]!=o[0] else 2;iy=3-ix
  rx=(sx+.5-o[0])/(xy[ix,0]-o[0]);ry=(sy+.5-o[1])/(xy[iy,1]-o[1])
  uv=v[:,3:5]*tex[slot].shape[0]
  u=np.floor(uv[0,0]+(uv[ix,0]-uv[0,0])*rx+(uv[iy,0]-uv[0,0])*ry).astype(int)
  t=np.floor(uv[0,1]+(uv[ix,1]-uv[0,1])*rx+(uv[iy,1]-uv[0,1])*ry).astype(int)
  c=tex[slot][t,u].astype(np.int32);dst=target.astype(np.int32)
  target[:]=dst+((c[:,:,:3]-dst)*c[:,:,3:4]>>7)

def forced_text_depth():
 # A button press during the flash can show glyphs before the automatic
 # reveal. Check the actual GS register payloads, including font XYZ bit 31.
 from validate_versus_result_text import FONT_RAM,CACHE,PACKETS,ISO_PATH,Iso
 p=canvas()
 for at in (0x101598,0x1015b4):assert p.read(at,4)==0x24090030
 p.run(0x303358,[0x1c00000,0,640,224,2,0x30],stop_before=[0x303510],limit=80000)
 assert p.read(0x1c00018,8)==0x4e and p.read(0x1c00078,8)==0x47
 assert (p.read(0x1c00010,8)>>24)&15==0 and (p.read(0x1c00070,8)>>16)&7==5
 font=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN');p.memory[FONT_RAM:FONT_RAM+len(font)]=font
 for a,v in [(0x3a9c20,CACHE),(0x3ec73c,0),(0x32ce08,1),(0x43d064,256),(0x345178,0),(0x3d3aa0,1)]:p.write(a,v,4)
 p.run(0x136930,[60],limit=100000);ptr,_=p.run(0x1a3070,[0,2,0]);p.run(0x1a2870,[ptr],limit=150000)
 assert p.read(0x345178,4)==2
 xyz=[p.read(PACKETS+16,8),p.read(PACKETS+160,8)]
 for i in range(2):
  p.write(0x3a8e30,1,4);start=0x1c70000
  end,_=p.run(0x105920,[PACKETS+i*128,start],limit=100000)
  assert struct.pack('<Q',xyz[i]) in bytes(p.memory[start:end])
 z=[v>>32 for v in xyz];assert z[1]>z[0]
 return dict(zbuf='PSMZ32',test='GEQUAL',flash_z=z[0],glyph_z=z[1],forced_glyph_visible=True)

def main():
 depth=forced_text_depth()
 extract();p=canvas();tex=textures(p)
 cases=[(s,t,t,480) for s in (0,1) for t in range(65)]
 cases.extend((s,99,b,h) for s in (0,1) for h in [448,480] for b in [82,83,206,207,828,829,830,831,1023,9997])
 total=pixels=0;gallery=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'check.cpp').write_text(DRIVER);exe=td/'check'
  subprocess.run(['c++','-O2','-std=c++20','-I',ROOT/'src',td/'check.cpp',ROOT/'src/versus_result_art.cpp','-o',exe],check=True)
  proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
  for side,t,bg,h in cases:
   p.write(0x4c3810,side,4);p.write(0x3db8f8,0,4)
   prim=[]
   for entry,clock in [(0x136480,t),(0x136500,t),(0x136930,t),(0x136988,t),(0x1364a8,bg),(0x1366e0,t),(0x1369b0,t)]:
    prim.extend(calls(p,entry,clock)[0])
   proc.stdin.write(f'{side} {t} {bg} {h}\n'.encode());proc.stdin.flush()
   source=np.zeros((h,640,4),np.uint8);source[:,:,3]=255
   paint(source,prim,tex)
   actual=np.frombuffer(proc.stdout.read(h*640*4),np.uint8).reshape(h,640,4)
   if not np.array_equal(source,actual):
    bad=np.any(source!=actual,axis=-1);y,x=next(zip(*np.where(bad)))
    raise ValueError((side,t,bg,h,bad.sum(),int(x),int(y),source[y,x],actual[y,x]))
   pixels+=h*640;total+=len(prim)
   if side==0 and t in [3,15,23,44,59,60,64] or (side==1 and t==3):
    gallery.append(Image.fromarray(source).resize((256,192),Image.Resampling.NEAREST))
  proc.stdin.close();assert proc.wait()==0
 image=Image.new('RGB',(256*4,192*2))
 for i,item in enumerate(gallery):image.paste(item,(i%4*256,i//4*192))
 image.save(OUTPUT/'versus-result-art-phases.png')
 report=dict(cases=len(cases),early_glyph=depth,source_primitives=total,RGBA_pixels=pixels,scopes='Japanese Haohmaru both winners, all 0..64 portrait stages, 11 background tile rows on separate clocks including 83/207/829 wraps, opaque four-tick flash, dialogue backdrop, raw CLUT allocations/transfer and no-tint 116588 colorization; 640x480 and clipped 640x448. Source vertices at the drawing ABI are software-rasterized on an opaque black canvas. Text, hardware scanout and framebuffer filtering are outside this comparison.')
 (OUTPUT/'versus-result-art-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
