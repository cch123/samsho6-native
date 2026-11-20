#!/usr/bin/env python3
"""Compare native displays with the original Japanese HUD's submitted drawing packets."""
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from character_tiles_oracle import ROOT, ASSETS, fixture, begin

OUT=ROOT/'outputs/ss6-feasibility'
H,W=448,640
TOP=314
SAMPLE_DRIVER=r'''
#include "rage_gauge.hpp"
#include <iostream>
#include <vector>
int main(int argc,char** argv) {
 ss6::RageGaugeRenderer render(argv[1]);ss6::RageGaugeState state;
 int reset,a,b,c,d,system0,system1;unsigned flags0,flags1;
 while(std::cin>>reset>>a>>b>>c>>d>>system0>>system1>>flags0>>flags1) {
  if(reset) state.reset({b,d});
  state.advance({a,c},{b,d},{system0,system1},{flags0,flags1});
  std::vector<uint8_t> pixels(640*448*4);
  for(int y=0;y<448;++y) for(int x=0;x<640;++x) {
   auto* v=&pixels[(y*640+x)*4];v[0]=(x+2*y)%256;v[1]=(3*x+y)%256;v[2]=(x^y)%256;v[3]=255;
  }
  render.paint(state,pixels);
  for(const auto& p: state.players){
   int values[]={p.state,p.displayed,p.pulse,p.pulseDirection,p.emblemCounter};
   std::cout.write(reinterpret_cast<const char*>(values),sizeof(values));
  }
  std::cout.write(reinterpret_cast<const char*>(pixels.data()+314*640*4),(448-314)*640*4);std::cout.flush();
 }
}
'''
def original():
 p=fixture();begin(p)
 p.memory[0x132f000:0x1330000]=bytes(4096)
 p.write(0x4d3d08,0x1c00000,4)
 for side in range(2):
  actor=0x1c00000+side*0xf2c
  p.write(0x132f5a0+side*4,actor+0x120,4)
  p.write(0x132f598+side*4,actor,4)
 for slot,n in [(2,1),(10,2)]:
  data=(ASSETS/f'obj{n}_16.tex').read_bytes();base=0x1c80000+slot*0x50000
  p.memory[base:base+len(data)]=data
  for offset,value in [(0,base),(4,512),(8,512),(12,19),(20,9),(24,9),(36,1)]:
   p.write(0x3a9680+slot*40+offset,value,4)
 return p

def backdrop():
 y,x=np.mgrid[:H,:W]
 return np.stack([(x+y*2)%256,(3*x+y)%256,x^y,np.full_like(x,255)],axis=-1).astype(np.uint8)

LOWER=(0x1c0718,0x1bff20,0x1c0d08,0x1c0fd0,0x1c02f8,0x1c0920)

def draw(p,frame,atlases,functions=LOWER):
 planes=[]
 def trace(pc):
  r=p.registers
  if pc==0x108464:
   submission=r[19];tex0=p.read(submission+16,8);slot=r[16]
   packet=p.read(submission,4);assert packet in (0x1ff2,0x2ff2)
   additive=packet==0x2ff2
   assert (tex0>>20)&63==19 and (tex0>>55)&1==0
   v=[struct.unpack_from('<5fI',p.memory,p.read(submission+24,4)+24*i) for i in range(4)]
   assert v[0][5]==p.read(submission+8,4) and v[0][5]&0xffffff==0x808080
   planes.append((v[0][2],slot,v,additive))
  elif pc==0x1058f8:
   submission=r[6]
   v=[]
   for i in range(4):
    color=p.read(submission+8+i*16,4); xyz=p.read(submission+16+i*16,8)
    v.append((((xyz&65535)-0x6c00)/16,(((xyz>>16)&65535)-0x7900)/8,xyz>>32,color))
   planes.append((v[0][2],0,v,False))
 for f in functions:p.run(f,limit=200000,observe=trace)
 for _,slot,v,additive in sorted(planes,key=lambda q:q[0]):
  x0,y0=v[0][:2];x1,y1=v[3][:2]
  if x0==x1 or y0>=y1:continue
  y,x=np.mgrid[max(0,int(y0)):min(H,int(y1)),max(0,int(min(x0,x1))):min(W,int(max(x0,x1)))]
  if slot:
   idx,clut=atlases[slot]
   u=(v[0][3]+(x+.5-x0)*(v[3][3]-v[0][3])/(x1-x0)).astype(int)
   t=(v[0][4]+(y+.5-y0)*(v[3][4]-v[0][4])/(y1-y0)).astype(int)
   indices=idx[t,u];color=clut[indices].astype(np.int32);alpha=(color[:,:,3:4]*(v[0][5]>>24))>>7
   dest=frame[y,x,:3].astype(np.int32)
   if additive:
    frame[y,x,:3]=np.where(alpha!=0,np.minimum(255,dest+color[:,:,:3]),dest)
   else:
    frame[y,x,:3]=dest+((color[:,:,:3]-dest)*alpha>>7)
  else:
   left,right=v[0][3],v[3][3]
   for channel in range(3):
    l=(left>>(8*channel))&255;r=(right>>(8*channel))&255
    source=np.floor(l+(r-l)*(x+.5-x0)/(x1-x0)).astype(int)
    dest=frame[y,x,channel].astype(int)
    frame[y,x,channel]=dest+((source-dest)*(left>>24)>>7)
 return len(planes)

def main():
 assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()=='72420e74e04d7ac39119d1b6ec7d70ed004fc98c5035fade96e87d05d4b9ffbf'
 atlases={}
 for slot,n in [(2,1),(10,2)]:
  buf=np.frombuffer((ASSETS/f'obj{n}_16.tex').read_bytes(),np.uint8)
  # CSM1 8bpp CLUT groups are stored in GS block order 0,2,1,3.
  clut=buf[-1024:].reshape(8,4,8,4)[:,[0,2,1,3],:,:].reshape(256,4)
  atlases[slot]=buf[:-1024].reshape(512,512),clut
 cases=[(1,0,0,0,27),(0,0,51,0,104)]*1+[(0,0,51,0,104)]*15
 cases+=[(0,1,184,0,7)]*33+[(0,0,17,2,184)]*37+[(0,2,77,1,127)]*19
 cases+=[(0,3,0,3,0),(0,0,0,0,0),(1,0,100,0,140),(0,0,7,0,30),(1,1,184,1,184)]
 ten="--ten" in sys.argv
 zan="--zan" in sys.argv
 combinations=[(0,2),(2,0),(1,2),(2,1),(2,2)] if zan else [(0,0),(1,1),(0,1),(1,0)]
 if ten:combinations=[(a,b) for a in range(4) for b in range(4) if 3 in (a,b)]
 p=original();total=0; gallery=[]
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);(td/'test.cpp').write_text(SAMPLE_DRIVER);exe=td/'probe'
  subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',td/'test.cpp',ROOT/'src/rage_gauge.cpp','-o',exe],check=True)
  run=subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
  for i,(systems,(reset,s0,a0,s1,a1)) in enumerate((systems,row) for systems in combinations for row in cases):
   amounts=[a0*256+i%255,a1*256+255-i%255]
   flags=[0x10000 if zan and ((i+who)%4)<2 else 0 for who in (0,1)]
   for side,state in enumerate([s0,s1]):
    actor=p.read(0x132f598+side*4,4)
    p.write(0x45689c+side*0x30,systems[side],4) # versus configuration read by 1be5c0
    p.write(actor+0x10c,systems[side],4);p.write(actor+0x23c,flags[side],4)
    p.write(actor+0x120,state,4);p.write(actor+0x124,amounts[side],4)
   if reset:p.run(0x1be1a8,limit=100000)
   assert tuple(p.read(0x132f434+side*0x98,4) for side in range(2))==systems
   run.stdin.write(f'{reset} {s0} {amounts[0]} {s1} {amounts[1]} {systems[0]} {systems[1]} {flags[0]} {flags[1]}\n'.encode());run.stdin.flush()
   state=struct.unpack('<10i',run.stdout.read(40))
   for at in [0x345178,0x378e08,0x3db8f8]:p.write(at,0,4)
   frame=backdrop();total+=draw(p,frame,atlases)
   for side,s in enumerate([s0,s1]):
    expected=(s,p.read(0x132f3e0+side*0x98,4),p.read(0x132f538+4*side,4),
              -1 if p.read(0x132f540+4*side,4) else 1,p.read(0x132f568+4*side,4))
    assert expected==state[side*5:side*5+5],(i,side,expected,state)
   native=np.frombuffer(run.stdout.read((H-TOP)*W*4),np.uint8).reshape(H-TOP,W,4)
   if not np.array_equal(frame[TOP:],native):
    diffs=np.where(np.any(frame[TOP:]!=native,axis=-1));z,k=diffs[0][0],diffs[1][0]
    raise ValueError((i,len(diffs[0]),int(k),int(z)+TOP,frame[TOP+z,k],native[z,k]))
   if i%len(cases)==20:gallery.append(frame[TOP:].copy())
  run.stdin.close();assert run.wait()==0
 report=dict(ticks=len(cases)*len(combinations),spirits=combinations,rage_states=[0,1,2,3],GS_packets=total,compared_RGBA_pixels=len(cases)*len(combinations)*(H-TOP)*W,
  source='SLPS_255.59 full 1be1a8 reset,1c0718,1bff20,1c0d08,1c0fd0,1c02f8,1c0920 plus callees. Original GS queue entries at 108464 / 1058f8, PSMT8+CPSM32 CSM1. Comparison uses software rasterization of both players on a patterned background, including clipped enlarged emblem. No hardware frame capture.')
 (OUT/('ten-hud-validation.json' if ten else 'zan-hud-validation.json' if zan else 'rage-hud-validation.json')).write_text(json.dumps(report,indent=2)+'\n')
 if not (ten or zan):Image.fromarray(np.vstack(gallery)).save(OUT/'rage-hud-phases.png')
 print(json.dumps(report))
if __name__=='__main__':main()
