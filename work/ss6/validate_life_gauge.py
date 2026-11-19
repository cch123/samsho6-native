#!/usr/bin/env python3
"""Compare the native upper life gauges with the Japanese textured and solid GS packets."""
from pathlib import Path
import json
import struct
import subprocess
import tempfile

import numpy as np
from validate_zero_hud import ASSETS,H,OUT,ROOT,SOURCE_HASH,UPPER,W,atlas,backdrop,draw,original,seed,set_actor
from validate_dash_motion import digest

CPP=r'''
#include "rage_gauge.hpp"
#include <iostream>
using namespace ss6;
int main(int argc,char** argv) {
    RageGaugeState st; RageGaugeRenderer hud(argv[1]);
    std::vector<uint8_t> bg(640*448*4),frame;
    for(int y=0;y<448;y++)for(int x=0;x<640;x++) {
        auto* d=bg.data()+4*(640*y+x);
        d[0]=x+2*y;d[1]=3*x+y;d[2]=x^y;d[3]=255;
    }
    int reset;
    while(std::cin>>reset) {
        std::array<int,2> system,rage,amount;
        std::array<LifeGaugeInput,2> input{};
        for(int i=0;i<2;i++){
            auto& z=input[i];std::cin>>system[i]>>rage[i]>>amount[i]>>z.phase>>z.reserve>>z.remaining
                         >>z.life>>z.sword>>z.swordMax>>z.opponentHits>>z.inPersistentHurt;
        }
        if(reset)st.reset(amount);
        st.advance(rage,amount,system,{},input);
        frame=bg;hud.paintLife(st,frame);
        for(const auto& p:st.players) {
            const int facts[]={p.lifeX,p.lifeWidth,p.lifeTrail,p.lifeGauge.life,p.woundX,p.woundWidth,
                               p.lifeHealing,p.zanLifePulse,p.lifePulse,p.swordPulse};
            std::cout.write(reinterpret_cast<const char*>(facts),sizeof(facts));
        }
        std::cout.write(reinterpret_cast<const char*>(frame.data()+4*640*29),4*640*56);std::cout.flush();
    }
}
'''


def reading(t,system,side):
    # Include a single wound, another hit before decay, healing during a
    # wound, interrupted healing, a low-life hold, a lethal hit and reset.
    t=max(0,t-(5 if side else 0))
    life=200
    for start,amount in ((4,173),(12,145),(55,82),(61,106),(69,78),
                         (80,21),(105,20),(132,19),(165,58),(192,4),(205,0)):
        if t>=start:life=amount
    persistent=int(4<=t<9 or 13<=t<27 or 190<=t<198)
    opp_hits=2 if 12<=t<35 or 80<=t<100 else 1
    reserve=0 if system<4 else ((28 if system==4 else 32)<<8)
    if system==4 and 115<=t<180:reserve=(22 if t<150 else 10 if t<165 else 26)<<8
    phase=(1 if t<80 else 2 if t<160 else 3 if t<200 else 4) if system==4 else 0
    rage=0 if t<80 else 1 if t<157 else 2 if t<170 else 3 if t<200 else 0
    capacity=95 if 7<=t<148 else 100
    sword=(capacity if t%49<21 else capacity-4 if t%49<32 else capacity-29)<<8
    return (system,rage,184<<8 if rage==1 else 20<<8,phase,reserve,40<<8,life,sword,capacity<<8,opp_hits,persistent)


def run(exe,pair):
    p=original();seed(p,pair);atlases=atlas();bg=backdrop()
    count=pixels=ticks=0
    with subprocess.Popen([exe,ASSETS],stdin=subprocess.PIPE,stdout=subprocess.PIPE) as driver:
        for t in range(239):
            k=t if t<224 else t-224;rows=[reading(k,s,i) for i,s in enumerate(pair)]
            for i,row in enumerate(rows):set_actor(p,i,row)
            if k==0:p.run(0x1be1a8,limit=200000)
            for addr in (0x345178,0x378e08,0x3db8f8):p.write(addr,0,4)
            driver.stdin.write((' '.join(map(str,[int(k==0),*rows[0],*rows[1]]))+'\n').encode());driver.stdin.flush()
            state=struct.unpack('<20i',driver.stdout.read(80))
            shown=np.frombuffer(driver.stdout.read(W*56*4),np.uint8).reshape(56,W,4)
            frame=bg.copy();count+=draw(p,frame,atlases,UPPER)
            expected=frame[29:85]
            bad=np.any(shown!=expected,axis=2)
            if np.any(bad):
                y,x=np.argwhere(bad)[0];side=int(x>=320);base=0x132f3a0+152*side
                orig=[p.read(base+i,4) for i in (0,8,16,20)]
                orig += [p.read(0x132f4d0+16*side+i,4) for i in (0,4,8,12)]
                orig += [p.read(0x132f4f0+4*side,4),p.read(0x132f4f8+4*side,4)]
                raise AssertionError((pair,t,int(x),int(y+29),int(bad.sum()),shown[y,x],expected[y,x],
                                      state[10*side:10*(side+1)],orig,rows[side]))
            ticks+=1;pixels+=expected.size//4
        driver.stdin.close();assert driver.wait()==0
    return dict(pair=pair,updates=ticks,original_packets=count,pixels=pixels)


def main():
    assert digest(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);cpp=tmp/'probe.cpp';exe=tmp/'probe';cpp.write_text(CPP)
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',cpp,ROOT/'src/rage_gauge.cpp','-o',exe],check=True)
        cases=[]
        for left,right in ((0,1),(1,0),(2,3),(3,2),(4,5),(5,4)):
            c=run(exe,(left,right));cases.append(c);print(c,flush=True)
    report=dict(passed=True,source_sha256=SOURCE_HASH,atlas_sha256=digest(ASSETS/'obj2_16.tex'),
                source_draws=[hex(f) for f in UPPER],cases=cases,
                updates=sum(c['updates'] for c in cases),rgba_pixels=sum(c['pixels'] for c in cases),
                original_packets=sum(c['original_packets'] for c in cases),
                scope='Full upper life plate and rim, active life, wound, sword and styles 0..5 in both seat orders over a varying-color backdrop. Runs the Japanese HUD update/GS submissions and independently composites each packet at its original depth. Covers full/21/20/19/0 HP, injury/combo/hitstun, healing overtaken by damage, post-KO and next-round reinitialization. Faces, names, wins and clock are separate passes.')
    (OUT/'life-gauge-validation.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
