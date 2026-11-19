#!/usr/bin/env python3
"""Compare the complete upper combat HUD in a released select-mode match with Japanese draw packets."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from PIL import Image

from validate_battle_clock import X,Y,W as CLOCK_W,H as CLOCK_H,draw as draw_clock,original_clock
from validate_select_session import encode
from validate_selected_combat import BUILD,OUT,SOURCE,prefix
from validate_zero_hud import UPPER,atlas,draw,original,seed,set_actor

TOP_ROWS=100
CASES=(((2,0),(0,3),0,0),((1,2),(4,2),0,1),((0,1),(1,5),1,0))

def controls(lineup,spirits,attacker,arena):
    pads=prefix(lineup)
    for side,spirit in enumerate(spirits):
        offset=(1,2,3,-2,-1,0)[spirit]
        for tick in (211,222,233)[:abs(offset)]:
            pads[tick-1][side]=128 if offset>0 else 64
    if arena==1:
        pads[340][1]=128
        pads[354][1]=0
        pads[379][1]=1024
    def pair(button):return (0,button) if attacker else (button,0)
    return pads+([pair((128,64)[attacker])]*45+[pair(1024)]+[pair(0)]*84)*19

def history(exe,assets,pads,fields):
    run=subprocess.run([exe,assets,'--mode','select',fields],text=True,check=True,capture_output=True,
                       input=''.join(f'1 {a} {b}\n' for a,b in pads))
    return [line.split() for line in run.stdout.splitlines()]

def snap(viewer,assets,folder,pads,tick):
    effects=folder/'scene.rgba';window=folder/'window.bmp';replay=folder/'input.pad'
    replay.write_text(encode(pads[:tick]))
    subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',replay,
                    '--dump',effects,'--snapshot',window],check=True,capture_output=True)
    scene=np.frombuffer(effects.read_bytes(),np.uint8,offset=8).reshape(448,640,4).copy()
    with Image.open(window) as im:
        assert im.size==(640,480)
        return scene,np.array(im.convert('RGBA'))

def check(job):
    from validate_fighter_identity_hud import paint_original
    viewer,assets,lineup,spirits,attacker,arena=job
    pads=controls(lineup,spirits,attacker,arena)
    rows=history(BUILD/'ss6-match-replay',assets,pads,'--life-hud-fields')
    choice=history(BUILD/'ss6-match-replay',assets,pads[:1250],'--select-fields')[-1]
    assert (int(choice[25]),int(choice[35]))==lineup and (int(choice[26]),int(choice[36]))==spirits and int(choice[52])==arena
    foe=1-attacker;hp=9+10*foe;wins=12+10*attacker
    first=next(i for i in range(1250,len(rows)) if int(rows[i][hp])<200)
    fresh=next(i for i in range(first+1,len(rows)) if int(rows[i-1][hp])==0 and rows[i][hp]=='200')
    award=next(i for i in range(first+1,fresh) if rows[i][wins]=='1')
    critical=next(i for i in range(first,fresh) if 0<int(rows[i][hp])<=20)
    marks={1250:'opening',first:'contact',first+1:'hud_damage',first+2:'hitstop',
           critical+1:'critical',award:'won_round',award+1:'hud_win',fresh+1:'next_round'}
    gauge=original();seed(gauge,spirits);banks=atlas();clock,clock_banks=original_clock()
    results=[]
    prior_hits=[0,0]
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td)
        for i,row in enumerate(rows[:max(marks)+1]):
            if row[23]!='1':continue
            for side in range(2):
                s=list(map(int,row[30+22*side:52+22*side]))
                set_actor(gauge,side,(s[0],s[21],0,s[5],s[4],0,s[1],s[2],s[3],s[6],s[7]))
                hits=s[6]
                if hits>=2 and hits!=prior_hits[side]:
                    gauge.run(0x1be008,[1-side,hits])
                prior_hits[side]=hits
            if row[24]=='1':gauge.run(0x1be1a8,limit=200000)
            for addr in (0x345178,0x378e08,0x3db8f8):gauge.write(addr,0,4)
            if i not in marks:
                # An entering combo label can cross behind the translucent life plate.
                for pc in (0x1bc580,0x1be880,0x1bfd40):gauge.run(pc,limit=200000)
                continue
            frame,window=snap(viewer,assets,folder,pads,i+1)
            paint_original(frame,characters=lineup,ornaments=False)
            draw(gauge,frame,banks,(0x1bc580,)+UPPER)
            # The HUD runs before the winning hit and before the round scorer.
            # Rules and score here come from the actual match one update earlier.
            previous=rows[i-1]
            points=(int(previous[12]),int(previous[22]))
            paint_original(frame,characters=lineup,wins=points,required=(2,2),portraits=False)
            seconds=int(row[25]);held=int(row[26])
            region=frame[Y:Y+CLOCK_H,X:X+CLOCK_W]
            region[:]=draw_clock(clock,clock_banks,region,seconds*0x5a00 if seconds>=0 else 0,
                                 3 if seconds<0 else 0,4,[(2 if held else 0,0),(0,0)])[0]
            diff=np.argwhere(np.any(frame[:TOP_ROWS]!=window[:TOP_ROWS],axis=2))
            if len(diff):
                y,x=diff[0]
                raise AssertionError((lineup,spirits,i+1,marks[i],len(diff),int(x),int(y),frame[y,x],window[y,x]))
            results.append(dict(tick=i+1,event=marks[i],life=int(row[hp]),wins=points,
                                sha256=sha256(window[:TOP_ROWS].tobytes()).hexdigest()))
            if marks[i]=='hud_damage' and lineup==(2,0):
                Image.fromarray(window).convert('RGB').save(OUT/'battle-life-hud.png')
    return dict(lineup=lineup,spirits=spirits,stage=arena,attacker=attacker+1,captures=results)

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--development',action='store_true')
    opt=cli.parse_args()
    viewer=(BUILD if opt.development else OUT/'native-viewer')/'ss6-viewer'
    assets=SOURCE if opt.development else viewer.parent/'assets'
    with ProcessPoolExecutor(3) as workers:cases=list(workers.map(check,[(viewer,assets,*v) for v in CASES]))
    samples=sum(len(c['captures']) for c in cases)
    report=dict(status='passed',packaged=not opt.development,viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),
                source_sha256=sha256((SOURCE.parent/'SLPS_255.59').read_bytes()).hexdigest(),cases=cases,
                compared_pixels=640*TOP_ROWS*samples,
                scope='Select mode on both stages, all six spirit choices across three matchups. Full-width top 100 lines of the public 640x480 SDL framebuffer, including portrait, gold border, both gauges, clock, empty and won round tokens. The background is the matching scene-only dump. Japanese HUD functions run on the sampled combat inputs; no physical PS2 scanout.')
    path=OUT/('battle-life-hud-window.development.json' if opt.development else 'battle-life-hud-window-validation.json')
    path.write_text(json.dumps(report,indent=2)+'\n')
    print(samples,'frames,',report['compared_pixels'],'pixels')
if __name__=='__main__':main()
