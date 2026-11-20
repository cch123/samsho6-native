#!/usr/bin/env python3
"""Verify every projected stage-zero strip over the bounded Game Over task lifetime."""
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT,ASSETS
from extract_versus_draw_stage import FRAME_COUNT,capture,prepare
OUT=ROOT/'outputs/ss6-feasibility'
DRIVER=r'''
#include "versus_draw_stage.hpp"
#include <vector>
#include <iostream>
int main(int argc,char** argv) {
 ss6::VersusDrawStage art(argv[1]);std::vector<uint8_t> pixels(640*480*4);
 unsigned tick;while(std::cin>>tick) {
  art.paint(tick,pixels);
  std::cout.write(reinterpret_cast<const char*>(pixels.data()),pixels.size()).flush();
 }
}
'''
def read_layout():
 data=(ASSETS/'versus_draw_stage.bin').read_bytes();signature,version,count,unique=struct.unpack_from('<4s3I',data)
 assert signature==b'VSTG' and version==1 and count==FRAME_COUNT
 pos=16;strips=[]
 for _ in range(unique):
  n=struct.unpack_from('<I',data,pos+8)[0];end=pos+12+16*n
  strips.append(data[pos:end]);pos=end
 frames=[]
 for _ in range(count):
  n=struct.unpack_from('<I',data,pos)[0];pos+=4;frames.append(struct.unpack_from(f'<{n}I',data,pos));pos+=n*4
 assert pos==len(data)
 return strips,frames

def page_tones(p,clock,edge):
 # 1118e4 runs the task queue, then 1118ec calls the frame renderer, whose
 # 113bc8 uploads palettes. Geometry queued earlier sees this frame's tone.
 for at,target in [(0x1118e4,0x112838),(0x1118ec,0x113b28),(0x113bc8,0x116588)]:
  assert p.read(at,4)==0x0c000000|(target>>2)
 start=0x3ebf30;sentinel=b'\x23\x02'
 p.memory[start:start+2048]=sentinel*1024
 p.write(0x4c3808,3,4);p.write(0x4c3818,1,4)
 p.write(0x4ca204,clock,4);p.write(0x1237ccc,edge,4)
 p.run(0x1387b8,stop_before=[0x1388ac],limit=80000)
 assert p.read(0x4ca204,4)==(280 if edge and 30<=clock<280 else clock)
 assert p.memory[start:start+2048]==sentinel*256+b'\x01\x00'*768

def palette(p):
 dest={};tmp=0x1410000
 # Drive the real Game Over task before running the original CLUT converter.
 # A stage-only callback would leave the two palettes in normal color.
 page_tones(p,0,0)
 for i in range(4):
  if i in [0,2]:
   buf=(ASSETS/f'bg00_{i+1}.pal').read_bytes();p.memory[tmp:tmp+len(buf)]=buf
   p.write(tmp,0,2);p.write(0x439b68,0,4);start=512 if i==0 else 768
   p.run(0x116478,[start,256,tmp],limit=150000);p.run(0x116588,limit=350000)
   clut=np.frombuffer(p.memory,np.uint8,count=1024,offset=0x11e7980+4*start).reshape(256,4).copy()
   assert np.array_equal(clut[:,0],clut[:,1]) and np.array_equal(clut[:,1],clut[:,2])
   assert len(np.unique(clut[:,0]))>8 and set(np.unique(clut[:,3]))=={0,128}
  size=1024 if i<2 else 512
  atlas=np.frombuffer((ASSETS/f'bg00_{i+1}.tex').read_bytes(),np.uint8).reshape(size,size)
  dest[4+i]=clut[atlas]
 return dest

def render(frame,textures):
 dst=np.zeros((480,640,4),np.uint8);dst[:,:,3]=255
 def edge(a,b,x,y):return (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0])
 def inside(w,a,b):return (w>0)|((w==0)&((b[1]<a[1])|((b[1]==a[1])&(b[0]>a[0]))))
 for _,slot,mod,verts in frame:
  tex=textures[slot];v=np.array(verts)
  for i in range(2,len(v)):
   a,b,c=v[i-2:i+1];area=edge(a,b,c[0],c[1])
   if area<0:b,c=c,b;area=-area
   if not area:continue
   lower=np.maximum([0,0],np.ceil(np.asarray([a[:2],b[:2],c[:2]]).min(axis=0)-.5).astype(int))
   upper=np.minimum([640,480],np.ceil(np.asarray([a[:2],b[:2],c[:2]]).max(axis=0)-.5).astype(int))
   if any(upper<=lower):continue
   y,x=np.mgrid[lower[1]:upper[1],lower[0]:upper[0]]
   wa=edge(b,c,x+.5,y+.5);wb=edge(c,a,x+.5,y+.5);wc=edge(a,b,x+.5,y+.5)
   mask=inside(wa,b,c)&inside(wb,c,a)&inside(wc,a,b)
   x=x[mask];y=y[mask]
   uv=[np.clip(np.floor((wa[mask]*a[k]+wb[mask]*b[k]+wc[mask]*c[k])*tex.shape[0]/area),0,tex.shape[0]-1).astype(int) for k in (2,3)]
   color=tex[uv[1],uv[0]].astype(np.int32);current=dst[y,x,:3].astype(np.int32)
   alpha=(color[:,3:4]*(((mod>>24)+1)//2))>>7
   rgb=(color[:,:3]*(((mod&255)+1)//2))>>7
   dst[y,x,:3]=current+((rgb-current)*alpha>>7)
 return dst

def main():
 page=prepare()
 for clock in range(FRAME_COUNT):
  for edge in (0,4):page_tones(page,clock,edge)
 expected,timeline=read_layout();p=prepare();textures=palette(p)
 distinct=set();lengths=Counter();total=0;ss=None
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'test.cpp').write_text(DRIVER);exe=td/'probe'
  subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',td/'test.cpp',ROOT/'src/versus_draw_stage.cpp','-o',exe],check=True)
  proc=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
  for i,ids in enumerate(timeline):
   frame=capture(p);total+=len(frame);assert len(frame)==len(ids)
   for id_,(_,slot,color,v) in zip(ids,frame):
    lengths[len(v)]+=1;assert expected[id_]==struct.pack(f'<3I{len(v)*4}f',slot,color,len(v),*(x for vert in v for x in vert))
   if ids in distinct:continue
   distinct.add(ids)
   source=render(frame,textures);proc.stdin.write(f'{i}\n'.encode());proc.stdin.flush()
   native=np.frombuffer(proc.stdout.read(480*640*4),np.uint8).reshape(480,640,4)
   if not np.array_equal(native,source):
    bad=np.any(native!=source,axis=-1);y,x=next(zip(*np.where(bad)))
    raise ValueError((i,int(bad.sum()),int(x),int(y),source[y,x],native[y,x]))
   if ss is None:ss=source
  proc.stdin.close();assert proc.wait()==0
 Image.fromarray(ss).save(OUT/'versus-draw-stage00.png')
 report=dict(visits=len(timeline),submitted_strips=total,distinct_strips=len(expected),unique_screens=len(distinct),
             strip_vertex_counts=dict(sorted(lengths.items())),compared_RGBA_pixels=len(distinct)*480*640,
             page_tone_cases=FRAME_COUNT*2, tone_1_entries=[256,1023],stage_banks=[512,768],
             scope='SLPS_255.59 fixed-camera stage-zero 1a7810 callback for Game Over. Frame task 1387b8 is exercised with and without skip inputs and applies grayscale on its first visit. The 116478/116588 source conversion feeds an independent software triangle raster for complete strips. Stage-only 640x480, global transition fade and overlays excluded. No live GS capture.')
 (OUT/'versus-draw-stage-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
