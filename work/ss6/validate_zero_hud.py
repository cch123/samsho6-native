#!/usr/bin/env python3
"""Compare both Japanese Zero HUD meters, sword and their shared portrait plate."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import sys

import numpy as np

from validate_rage_gauge import ASSETS, H, LOWER, OUT, ROOT, W, backdrop, draw, original
from extract_collision_tables import SOURCE_HASH

UPPER=(0x1bada0,0x1be880,0x1bfbd0,0x1bfd40,0x1bae60)
DRIVER=r"""
#include "rage_gauge.hpp"
#include <iostream>
#include <vector>
int main(int argc,char** argv){
 ss6::RageGaugeState state;
 ss6::RageGaugeRenderer renderer(argv[1]);
 int reset;
 while(std::cin>>reset){
  std::array<int,2> sys,rs,amount;
  std::array<ss6::LifeGaugeInput,2> in{};
  for(int s=0;s<2;++s){
   auto& z=in[s];
   std::cin>>sys[s]>>rs[s]>>amount[s]>>z.phase>>z.reserve>>z.remaining
           >>z.life>>z.sword>>z.swordMax>>z.opponentHits>>z.inPersistentHurt;
  }
  if(reset)state.reset(amount);
  state.advance(rs,amount,sys,{},in);
  std::vector<uint8_t> pixels(640*448*4);
  for(int y=0;y<448;++y)for(int x=0;x<640;++x){
   auto* v=pixels.data()+(y*640+x)*4;
   v[0]=(x+2*y)%256;v[1]=(3*x+y)%256;v[2]=(x^y)%256;v[3]=255;
  }
  renderer.paint(state,pixels);
  std::cout.write(reinterpret_cast<char*>(pixels.data()),pixels.size());
 }
}
"""

def atlas():
    out={}
    for slot,n in ((2,1),(10,2)):
        buf=np.frombuffer((ASSETS/f'obj{n}_16.tex').read_bytes(),np.uint8)
        out[slot]=(buf[:-1024].reshape(512,512),buf[-1024:].reshape(8,4,8,4)[:,[0,2,1,3]].reshape(256,4))
    return out

def seed(p,systems):
    p.write(0x4d3d00,0x1c30000,4);p.write(0x1c30004,4,4)
    for i,s in enumerate(systems):
        a=p.read(0x132f598+i*4,4)
        for addr,v in ((0x45689c+i*48,s),(0x132f434+i*152,s),(a+0x10c,s),(a+0xa24,i),(a+0xa34,200)):
            p.write(addr,v,4)
        p.run(0x1be068,[i])

def seat(system,t):
    if system==5:
        life=200 if t<20 else 86 if t<64 else 31 if t<180 else 0
        stored=32 if t<100 else max(0,100-(t-100)*2) if t<160 else min(32,t-160)
        rage=1 if 75<=t<125 else 0
        amount=184 if rage else t if t<75 else max(0,165-2*(t-125))
        swordMax=100 if rage else 95
        return (system,rage,amount<<8,0,stored<<8,0,life,(swordMax-t%30)<<8,swordMax<<8,1,int(20<=t<=36))

    if system!=4:return (system,0,min(184,t)*256,0,0,0,200,100<<8,100<<8,0,0)
    # Lower rises normally, catches up while raging, switches to the
    # independent blue duration and finally spends the meditated reserve.
    if t<35: phase,rage=0,0
    elif t<80:phase,rage=1,1
    elif t<150:phase,rage=2,0
    elif t<200:phase,rage=3,3
    else:phase,rage=4,2 if t<225 else 3
    life=200 if t<8 else 154 if t<35 else 89 if t<53 else 39 if t<194 else 0
    reserve=(20 if t<12 else 80 if t<43 else 100)<<8
    amount=(min(184,t*8) if rage<2 else max(0,184-5*(t-200)) if rage==2 else 0)<<8
    return (system,rage,amount,phase,reserve,max(0,51200-330*(t-150)) if phase==3 else 0,
            life,(100 if t<32 else 80 if t<50 else 95 if t<65 else 100)<<8,100<<8,
            1 if t<40 else 3,int(9<=t<16 or 54<=t<=91))

def set_actor(p,side,sample):
    a=p.read(0x132f598+side*4,4)
    sys,rage,amount,phase,reserve,remaining,life,sword,maxs,hits,hurt=sample
    for off,v in ((0x120,rage),(0x124,amount),(0x13c,phase),(0x140,reserve),(0x144,remaining),
                  (0x194,0x120002 if hurt else 0),(0xa30,life),(0x134,sword),(0x138,maxs)):
        p.write(a+off,v,4)
    p.write(a+0x158,reserve,4)
    p.write(0x132f5c0+(1-side)*4,hits,4)

def main():
    atlases=atlas();packets=pixels=ticks=0
    assert hashlib.sha256((ASSETS.parent/'SLPS_255.59').read_bytes()).hexdigest()==SOURCE_HASH
    with tempfile.TemporaryDirectory() as temp:
        td=Path(temp);cpp=td/'hud.cpp';exe=td/'hud';cpp.write_text(DRIVER)
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',cpp,ROOT/'src/rage_gauge.cpp','-o',exe],check=True)
        ken="--ken" in sys.argv
        groups=[(5,5),(5,4),(4,5),(5,0),(0,5)] if ken else [(4,4),(4,0),(0,4)]
        for systems in groups:
            p=original();seed(p,systems)
            with subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as driver:
                for t in range(244):
                    row=[seat(sys,(t+17*i) if t else 0) for i,sys in enumerate(systems)]
                    for i,sample in enumerate(row):set_actor(p,i,sample)
                    if t==0:p.run(0x1be1a8,limit=200000)
                    driver.stdin.write((' '.join(map(str,[int(not t),*row[0],*row[1]]))+'\n').encode());driver.stdin.flush()
                    actual=np.frombuffer(driver.stdout.read(W*H*4),np.uint8).reshape(H,W,4)
                    for addr in (0x345178,0x378e08,0x3db8f8):p.write(addr,0,4)
                    source=backdrop();packets+=draw(p,source,atlases,UPPER+LOWER)
                    for i,system in enumerate(systems):
                        for top,bot in ([(29,85),(314,448)] if system in (4,5) else [(314,448)]):
                            x0=i*320
                            expected=source[top:bot,x0:x0+320];got=actual[top:bot,x0:x0+320];pixels+=expected.size//4
                            diff=np.any(expected!=got,axis=2)
                            if diff.any():
                                y,x=np.argwhere(diff)[0]
                                raise AssertionError((systems,t,top,int(diff.sum()),x+x0,y+top,expected[y,x],got[y,x],row[i]))
                    ticks+=1
                driver.stdin.close()
    report=dict(status='passed',source_sha256=SOURCE_HASH,frames=ticks,systems=groups,original_GS_packets=packets,
                compared_RGBA_pixels=pixels,source_functions=[hex(v) for v in UPPER+LOWER],
                scope='All five Mu phases, ordinary rage and explosion, both orientations, blue reserve across life and wound boundaries, partial and full sword, every animation cell on original package textures; original submissions in a software GS raster oracle.')
    if ken:report['scope']='Ken green secret reserve over life, blinking usable threshold, both sword stages, 40-point Full Guard pulse and full-gauge fire across independent Ken/Ken, Ken/Zero and Ken/Rage configurations. The original GS packets use the resident Japanese HUD atlases.'
    (OUT/('ken-hud-validation.json' if ken else 'zero-hud-validation.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
