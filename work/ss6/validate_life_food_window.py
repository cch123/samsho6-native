#!/usr/bin/env python3
"""Compare real food recovery to the Japanese HP call, delayed gauge and viewer pixels."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image
from validate_dash_motion import digest
from validate_selected_combat import BUILD,OUT,ROOT,SOURCE,prefix
from validate_stage_item_contact import FOOD_ROUTES,original_life
from validate_zero_hud import UPPER,atlas,draw,original,seed,set_actor
from extract_collision_tables import SOURCE_HASH


def check(job):
    viewer,assets,replay,recipe=job
    side,kind,when,before,after,steps=recipe
    pads=prefix((0,1));pads[265][1]=128
    for n,x,y in steps:pads.extend([(x,y)]*n)
    pads.extend([(0,2304) if side else (2304,0)]+[(0,0)]*64)
    lines=''.join(f'1 {x} {y}\n' for x,y in pads)
    def rows(flag):
        run=subprocess.run([replay,assets,'--mode','select','--round-time','99',flag],input=lines,text=True,capture_output=True,check=True)
        return [l.split() for l in run.stdout.splitlines()]
    state=rows('--life-hud-fields');items=rows('--stage-item-fields')
    base=30+22*side;hp=9+10*side;actor=3+10*side
    assert len(pads)==len(state)==len(items) and all(row[:23]==item[:23] for row,item in zip(state,items,strict=True))
    hurt=next(i for i in range(1250,when-12) if int(items[i][hp])==before)
    assert int(items[hurt-1][hp])>before
    assert any(r[actor:actor+3]==['1','35','152'] and r[28]==str(kind) for r in items[when-15:when])
    consume=items[when-2];assert consume[28]=='-1' and int(consume[33+side])==kind
    source_hp=original_life(side,kind,before,float(consume[actor+4]))
    assert source_hp['hp']==after and source_hp['pending']==before-after

    def original_input(t,seat):
        a=list(map(int,state[t-1][30+22*seat:52+22*seat]))
        return (a[0],a[21],0,a[5],a[4],0,a[1],a[2],a[3],a[6],a[7])
    systems=[original_input(when,i)[0] for i in range(2)]
    assert systems==[5,5]
    p=original();seed(p,systems)
    for s in range(2):set_actor(p,s,original_input(when-1,s))
    p.run(0x1be1a8,limit=200000)
    # These pickups happen well after the original red wound disappeared.
    # Run 200 real Japanese HUD updates at the prior HP to reach the same
    # stable geometry before comparing every food recovery update.
    for _ in range(201):
        p.run(0x1be880,limit=200000)
    charts=atlas()
    bounds=(366,566) if side else (73,273)
    frames=[];last=when+after-before+1
    with tempfile.TemporaryDirectory() as td:
        folder=Path(td);rep=folder/'food.pad';shot=folder/'window.bmp';raw=folder/'combat.rgba'
        for t in range(when-1,last+1):
            for s in range(2):set_actor(p,s,original_input(t,s))
            rep.write_text(''.join(f'{sum(1 for _ in same)} {v[0]} {v[1]}\n' for v,same in groupby(pads[:t])))
            subprocess.run([viewer,'--assets',assets,'--mode','select','--round-time','99','--match-replay',rep,
                           '--dump',raw,'--snapshot',shot],stdout=subprocess.DEVNULL,check=True)
            layer=raw.read_bytes();assert struct.unpack_from('<II',layer)==(640,448)
            image=np.frombuffer(layer[8:],np.uint8).reshape(448,640,4).copy()
            for addr in (0x345178,0x378e08,0x3db8f8):p.write(addr,0,4)
            draw(p,image,charts,UPPER)
            srcbase=0x132f3a0+152*side
            source_geom=[p.read(srcbase+off,4) for off in (0,8,16,20)]
            current=list(map(int,state[t-1][base+8:base+12]))
            expected=before+min(after-before,max(0,t-when))
            assert source_geom==current and current[1]==current[2]==expected,(kind,t,current,source_geom,expected)
            assert current[3]==(before if t<=when else after)
            assert int(state[t-1][hp])==(before if t<when else after)
            window=np.asarray(Image.open(shot).convert('RGBA'))
            x0,x1=bounds
            shown=window[45:61,x0:x1];original_pixels=image[45:61,x0:x1]
            if not np.array_equal(shown,original_pixels):
                y,x=np.argwhere(np.any(shown!=original_pixels,axis=2))[0]
                raise AssertionError((kind,t,x+x0,y+45,shown[y,x],original_pixels[y,x]))
            frames.append(dict(tick=t,actor_hp=int(state[t-1][hp]),width=expected,source_target=current[3],x=current[0],
                               rendered_bar_sha256=sha256(shown.tobytes()).hexdigest()))
    return dict(player=side+1,food=kind,health=[before,after],heavy_damage_tick=hurt+1,heal_tick=when,
                original_HP=source_hp['hp'],verified_window_frames=frames)


def main():
    pkg=OUT/'native-viewer'
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=pkg/'ss6-viewer')
    ap.add_argument('--assets',type=Path,default=pkg/'assets');ap.add_argument('--replay',type=Path,default=BUILD/'ss6-match-replay')
    a=ap.parse_args()
    identity=digest(a.viewer),digest(a.replay)
    assert digest(SOURCE.parent/'SLPS_255.59')==SOURCE_HASH
    with ProcessPoolExecutor(4) as pool:
        cases=list(pool.map(check,[(a.viewer,a.assets,a.replay,r) for r in FOOD_ROUTES]))
    assert identity==(digest(a.viewer),digest(a.replay))
    d=dict(passed=True,source_sha256=SOURCE_HASH,viewer_sha256=identity[0],replay_sha256=identity[1],cases=cases,
           window_frames=sum(len(c['verified_window_frames']) for c in cases),
           scope='Public native select mode, two human pads, factory stage-0 items enabled. The recipient takes actual heavy damage before picking up one of four foods. Records the exceptional one-update gap between actor HP change and the first +1 HUD update. Every food-recovery frame compares full 200x16 life-bar pixels to the original Japanese HUD packets, including the updated character and Ken stored gauge. Other upper HUD widgets are outside this window crop.')
    (OUT/'life-food-window-validation.json').write_text(json.dumps(d,indent=2)+'\n')
    print(d['window_frames'],[(c['player'],c['food'],c['health']) for c in cases])

if __name__=='__main__':main()
