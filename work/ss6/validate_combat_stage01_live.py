#!/usr/bin/env python3
"""Verify stage 1's arena during selected versus play, introduction skip and Mikiri flash."""
import hashlib
import json
import struct
import subprocess
import tempfile
from itertools import groupby
from pathlib import Path
import numpy as np
from PIL import Image

from validate_combat_stage01 import Original,OUT,ASSETS,ROOT,compare_pixels
from validate_selected_combat import prefix,BUILD
from validate_ken_mikiri import pads as mikiri
from validate_issen_backdrop import original_packets

TRACE=r'''
#include "local_versus.hpp"
#include <bit>
#include <iostream>
using namespace ss6;
int main(int,char** argv) {
    LocalVersus game(argv[1],99,VersusMode::Console,{},true);
    std::array<uint32_t,2> held{},previous{};unsigned tick=0;
    while(std::cin>>held[0]>>held[1]){
        const auto& old=game.match();const auto oldStage=old.combatStage();
        const auto seed=old.battle().random.librarySeed;
        const auto& g=old.battle().gauges;
        const unsigned delta=g.paused46a940?0:(g.scale1239d84*g.scale1239d88)>>8;
        const auto blocked=bool(old.battleBackdropColor());
        std::array<NormalizedPadSample,2> pads;
        for(unsigned i=0;i<2;++i)pads[i]={held[i],held[i]&~previous[i]};
        previous=held;game.tick(pads);++tick;
        const auto& m=game.match();if(m.characterSelect()||m.chosenStage()!=1)continue;
        const auto& s=m.combatStage();const auto& c=s.camera;
        if(!s.visible||oldStage.stage!=1)continue;
        std::cout<<tick<<' '<<s.stage<<' '<<s.suppressGeometry<<' '<<blocked<<' '<<m.mikiriWhiteFrame()<<' '<<m.battleBackdropColor()<<' '<<m.battle().flags138<<' '<<m.battle().timers.values[4]<<' '<<seed<<' '<<delta;
        for(float f:{c.projectionX,c.projectionY,c.depth,c.depthOffset,c.verticalOffset})std::cout<<' '<<std::bit_cast<uint32_t>(f);
        for(const auto& board:{oldStage.layers01,s.layers01})for(const auto& a:board)std::cout<<' '<<a.elapsed<<' '<<a.picture<<' '<<a.flags;
        for(unsigned j=512;j<1024;++j)std::cout<<' '<<m.battle().gauges.paletteTones[j];
        std::cout<<'\n';
    }
}
'''

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run():
    steps=prefix((0,0))
    # R twice (random -> stage 0 -> stage 1), respecting the 30-frame
    # transition between thumbnails. Start at 600 skips the player intros.
    steps[354][1]=0;steps[341][1]=128;steps[379][1]=1024;steps[599][0]=8
    for n,a,b in mikiri(1,'stand')[1:]:steps.extend([(a,b)]*n)
    steps.extend([(128,0)]*31+[(16,0)]+[(0,0)]*30)
    packed=lambda rows:''.join(f'{sum(1 for _ in group)} {a} {b}\n' for (a,b),group in groupby(map(tuple,rows)))
    src=Original();p=src.p;reent=p.read(0x5d1bf8,4)+0xa8
    backdrop=original_packets()
    cases=[];seenWhite=[];lastFlash=0
    viewer=BUILD/'ss6-viewer'
    with tempfile.TemporaryDirectory() as folder:
        folder=Path(folder);f=folder/'observe.cpp';f.write_text(TRACE);driver=folder/'observer'
        subprocess.run(['c++','-std=c++20','-O2','-I',ROOT/'src',f,BUILD/'libss6-runtime.a','-o',driver],check=True)
        trace=subprocess.run([driver,ASSETS],input=''.join(f'{a} {b}\n' for a,b in steps),text=True,capture_output=True,check=True)
        state={r[0]:r for line in trace.stdout.splitlines() if (r:=list(map(int,line.split())))}
        black=[t for t,r in state.items() if r[5]==0xff000000]
        white=[t for t,r in state.items() if r[4]]
        assert len(black)==4 and len(white)==3 and white==[1316,1317,1318],(black,white)
        # The ordinary renderer retains its last priority-10 camera when
        # the fight task publishes new movement in the same update.
        want=set([black[0]-1,*black,black[-1]+1,black[-1]+2,1250,1280,white[0]-1,*white,white[-1]+1,len(steps)])
        for tick in sorted(want):
            row=state[tick]; _,arena,hidden,previousBackdrop,flash,color,flags,timer,seed,delta=row[:10]
            assert arena==1 and hidden==previousBackdrop,(tick,row[:10])
            before=row[15:45];after=row[45:75];tones=row[75:];assert len(tones)==512
            camera=np.array(row[10:15],dtype='<u4').view('<f4').tolist()
            p.write(reent,seed,8)
            for i,(o,_) in enumerate(src.objects):
                p.write(o,before[i*3],4);p.write(o+4,before[i*3+1],4);p.write(o+0x30,before[i*3+2],4)
            frame,depth,layers=src.visit(camera,hidden,None,delta)
            assert after==[p.read(o+k,4) for o,_ in src.objects for k in (0,4,0x30)],(tick,delta,layers,after)
            assert bool(frame)!=bool(hidden)
            if flash:
                if not lastFlash:
                    p.write(0x3ebf24,3,4);p.write(0x3ec730,0x80ffffff,4)
                p.run(0x113aa8);assert p.read(0x3ec73c,4)==1
                vertices=[]
                class Publish(Exception):pass
                def packet(pc):
                    if pc==0x110b28:
                        vertices.extend(struct.unpack_from('<3fI',p.memory,p.registers[4]+16*i) for i in range(4))
                        raise Publish
                try:p.run(0x113b28,observe=packet)
                except Publish:pass
                assert [(v[0],v[1],v[3]) for v in vertices]==[(0,0,0xffffffff),(0,480,0xffffffff),(640,0,0xffffffff),(640,480,0xffffffff)]
                expected=np.full((448,640,4),255,dtype=np.uint8);seenWhite.append(tick)
            else:
                expected=src.rgba(frame,tones,448)
            lastFlash=flash
            actualBackdrop,_=backdrop(flags,timer)
            assert actualBackdrop==color,(tick,color,actualBackdrop)
            if color and frame:assert max(s[0] for s in frame)<9995756
            replay=folder/'live.pad';replay.write_text(packed(steps[:tick]))
            stage=folder/'arena.rgba';scene=folder/'scene.rgba'
            subprocess.run([viewer,'--assets',ASSETS,'--mode','select','--round-time','99','--match-replay',replay,'--dump-stage',stage,'--dump',scene],check=True,stdout=subprocess.DEVNULL)
            def image(path):
                data=path.read_bytes();assert struct.unpack_from('<II',data)==(640,448)
                return np.frombuffer(data,np.uint8,offset=8).reshape(448,640,4)
            compare_pixels(image(stage),expected,('live stage 1',tick))
            if flash:assert (image(scene)==255).all()
            if tick==1250:Image.fromarray(image(scene)).save(OUT/'stage01-selected-versus.png')
            if color==0xff000000:
                blackMask=np.all(image(scene)[:,:,:3]==0,axis=2);assert blackMask.sum()>640*448*0.66
            cases.append(dict(tick=tick,backdrop=color,stage_hidden=hidden,white=bool(flash),packets=len(frame),next_depth=depth,stage_sha256=sha(stage)))
        assert seenWhite==white
    report=dict(status='passed',viewer_sha256=sha(viewer),runtime_sha256=sha(BUILD/'libss6-runtime.a'),
                cases=cases,black_frames=black,white_frames=white,frames=len(cases),compared_RGBA_pixels=len(cases)*640*448,
                scope='Regular versus character and spirit selection, P2 chooses stage 1, skips intro, walks and strikes a Ken afterimage. Full arena output of the production viewer against the real 1a8098 at the actual pre-visit native clocks, RNG, camera and palette. Original 1401e0/1419b0 backdrop and 113aa8/113b28 white presentation, including full production white image. Characters over black compared by coverage, not character pixel oracle.')
    (OUT/'combat_stage01_live_validation.json').write_text(json.dumps(report,indent=2)+'\n');print(report)
if __name__=='__main__':run()
