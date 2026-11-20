#!/usr/bin/env python3
"""Compare original GS HUD packets with the packaged viewer after actual local inputs."""
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import sys

import numpy as np
from PIL import Image

from validate_zero_hud import UPPER, LOWER, ROOT, OUT, H, W, atlas, draw, original, seed, set_actor
from validate_fighter_identity_hud import paint_original
from validate_zero_specials import scenario
from validate_ken_rounds import full_guard, secret

PKG=OUT/'native-viewer'
SOURCE=r"""
#include "local_versus.hpp"
#include <iostream>
int main(int argc,char** argv){
 unsigned side=std::stoul(argv[2]);std::array<unsigned,2> systems{};systems[side]=std::stoul(argv[3]);
 ss6::LocalVersus session(argv[1],-1,ss6::VersusMode::Console,systems);
 unsigned n;std::array<uint32_t,2> held{},prior{};
 while(ss6::readVersusReplaySegment(std::cin,n,held)){
  while(n--){
   std::array<ss6::NormalizedPadSample,2> pads;
   for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~prior[i]};
   session.tick(pads);prior=held;const auto& match=session.match();
   std::cout<<match.rageGauge().resetOnLastVisit;
   for(unsigned i=0;i<2;++i){const auto& p=match.rageGauge().players[i];const auto& z=p.lifeGauge;
    std::cout<<' '<<p.system<<' '<<p.state<<' '<<(p.displayed<<8)<<' '<<z.phase
     <<' '<<z.reserve<<' '<<z.remaining<<' '<<p.sampledLife<<' '<<z.sword<<' '<<z.swordMax
     <<' '<<z.opponentHits<<' '<<z.inPersistentHurt;
   }
   std::cout<<' '<<match.identityHud().wins[0]<<' '<<match.identityHud().wins[1]<<'\n';
  }
 }
}
"""

def check(args):
    folder,side,ken,mode,viewer,assets= args
    if mode=='guard':seq=full_guard(side)
    elif ken:seq=secret(side)+[(590,0,0)]
    else:
        frames,steps=scenario(side,'hit');seq=frames+steps
    lines=['1 %d %d\n'%(a,b) for n,a,b in seq for _ in range(n)]
    result=subprocess.run([folder/'driver',assets,str(side),str(5 if ken else 4)],input=''.join(lines),text=True,capture_output=True,check=True)
    samples=[list(map(int,l.split())) for l in result.stdout.splitlines()]
    assert len(samples)==len(lines)
    groups=[0,0];groups[side]=5 if ken else 4
    p=original();atlases=atlas();seed(p,groups)
    # Every changing history field advances through the game's own routines.
    # The standalone synthetic test independently verifies 1c0700's raw-rage
    # easing. For this window-only test the published width is its input.
    phases=[r[4+side*11] for r in samples]
    if ken:
        reserve=[r[5+11*side] for r in samples];life=[r[7+11*side] for r in samples]
        lower=[r[3+11*side]>>8 for r in samples]
    if mode=='guard':
        states=[r[2+side*11] for r in samples]
        full=states.index(1)+1;spent=states.index(0,full)+1
        assert lower[full-1:spent-1]==[184]*(spent-full) and lower[spent-1]==144
        checks={full-1,full,full+5,spent-1,spent,spent+8}
    elif ken:
        ready=next(i for i,v in enumerate(life,1) if 0<v<=32)
        guard=next(i for i,v in enumerate(lower,1) if v>=40)
        spent=next(i for i in range(ready,len(reserve)) if reserve[i]==0)+1
        first=next(i for i in range(spent,len(reserve)) if reserve[i]>0)+1
        full=next(i for i in range(first,len(reserve)) if reserve[i]==8192)+1
        checks={500,ready-1,ready,ready+10,guard-1,guard,guard+8,spent-1,spent,first-1,first,full}
        assert full-first==31,(first,full)
    else:
        enter=phases.index(3)+1;spent=phases.index(4,enter)+1
        checks={500,700,715,enter-1,enter,enter+6,enter+14,spent-1,spent,spent+1}
    target=folder/f'{mode}-p{side}';target.mkdir();report=[]
    life_left,life_right=(361,580) if side else (59,279)
    regions=[(29,85,life_left,life_right),(314,448,0,640)]
    prior_hits=[0,0]
    for tick,row in enumerate(samples,1):
        if tick>max(checks):break
        actors=[row[1:12],row[12:23]]
        for i,sample in enumerate(actors):
            set_actor(p,i,sample)
            hits=sample[9]
            if hits>=2 and hits!=prior_hits[i]:p.run(0x1be008,[1-i,hits])
            prior_hits[i]=hits
        if tick==1 or row[0]:p.run(0x1be1a8,limit=200000)
        for at in (0x345178,0x378e08,0x3db8f8):p.write(at,0,4)
        if tick not in checks:
            for pc in (0x1bc580,0x1be880,0x1bfbd0,0x1bfd40,0x1c0d08,0x1c0fd0,0x1c02f8,0x1c0920):
                p.run(pc,limit=200000)
            continue
        rep=target/'input.pad';rep.write_text(''.join(lines[:tick]))
        scene=target/'scene.rgba';bmp=target/'window.bmp';spirits=['rage','rage'];spirits[side]='ken' if ken else 'zero'
        subprocess.run([viewer,'--assets',assets,'--mode','versus','--p1-spirit',spirits[0],
                        '--p2-spirit',spirits[1],'--match-replay',rep,'--dump',scene,'--snapshot',bmp],
                       check=True,capture_output=True)
        data=scene.read_bytes();assert struct.unpack_from('<II',data)==(W,H)
        expected=np.frombuffer(data[8:],np.uint8).reshape(H,W,4).copy()
        # The gold portrait frames overlap the life plates at their outer edges.
        paint_original(expected,ornaments=False)
        draw(p,expected,atlases,(0x1bc580,)+UPPER+LOWER)
        paint_original(expected,wins=row[23:25],portraits=False)
        shot=Image.open(bmp).convert('RGBA');got=np.asarray(shot)
        # Clock overlays both ends of the original life plate. Compare the
        # life, reserve and sword plus the entire lower HUD across both sides.
        for y,z,left,right in regions:
            diff=np.any(got[y:z,left:right]!=expected[y:z,left:right],axis=2)
            if diff.any():
                a,b=np.argwhere(diff)[0]
                raise AssertionError((side,tick,len(np.argwhere(diff)),b+left,a+y,got[a+y,b+left],expected[a+y,b+left]))
        if mode=='secret' and not side and tick in (ready+10,guard+8,first):
            shot.convert('RGB').save(OUT/{ready+10:'ken-secret-ready.png',guard+8:'ken-full-guard-ready.png',first:'ken-secret-recharge.png'}[tick])
        if mode=='guard' and not side and tick==full+5:
            shot.convert('RGB').save(OUT/'ken-full-rage.png')
        if not ken and not side and tick in (500,enter+6,spent+1):
            label={500:'reserve',enter+6:'concentration',spent+1:'spent'}[tick]
            shot.convert('RGB').save(OUT/f'zero-hud-{label}.png')
        entry=dict(tick=tick,life=actors[side][6],reserve=actors[side][4])
        if ken:
            entry.update(lower_displayed=lower[tick-1],rage_state=actors[side][1],
                         secret_available=0<entry['life']<=entry['reserve']//256)
        else:
            entry.update(phase=phases[tick-1],time=actors[side][5])
        report.append(entry)
    pixels_per_check=sum((v-y)*(r-l) for y,v,l,r in regions)
    return dict(scenario=mode,spirit_seat=side+1,priority20_updates=max(checks),compared_hud_pixels=len(checks)*pixels_per_check,screenshots=report)

def main():
    ken='--ken' in sys.argv
    staging='--development' in sys.argv
    viewer=(ROOT/'work/ss6/build-native' if staging else PKG)/'ss6-viewer'
    assets=ROOT/'work/ss6/extracted/resources' if staging else PKG/'assets'
    digest=hashlib.sha256(viewer.read_bytes()).hexdigest()
    assert digest==hashlib.sha256((ROOT/'work/ss6/build-native/ss6-viewer').read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);cpp=folder/'driver.cpp';cpp.write_text(SOURCE)
        subprocess.run(['c++','-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',cpp,ROOT/'work/ss6/build-native/libss6-runtime.a','-o',folder/'driver'],check=True)
        modes=('secret','guard') if ken else ('concentration',)
        cases=[(folder,side,ken,mode,viewer,assets) for mode in modes for side in (0,1)]
        with ProcessPoolExecutor(2) as pool:results=list(pool.map(check,cases))
    report=dict(status='passed',packaged_viewer_sha256=digest,source='Actual SDL software framebuffer, Japanese original HUD packet oracle and native arena background. Includes both combatant orders, held meditation across first-round loss, activation, Issen and exhaustion.',cases=results)
    if ken:report['source']='Two-sided life under 32 and actual Ken secret input, Full Guard threshold, recovery after secret use, blocked attack filling lower rage to 184, spending Full Guard from full to 144, packaged SDL screenshot versus original HUD geometry and textures.'
    output=OUT/('ken-live-hud-validation.json' if ken else 'zero-live-hud-validation.json')
    if staging:output=output.with_suffix('.development.json')
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(report)

if __name__=='__main__':main()
