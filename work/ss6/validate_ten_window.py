#!/usr/bin/env python3
"""Compare physical Ten controls, the shipped window and the Japanese battle draw commands."""
import argparse
from itertools import groupby
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from validate_shin_scene import (ASSETS, BUILD, CAPTURE_DRIVER, LIB, OUT, PACKAGE, ROOT, SOURCE_HASH,
                                 STAGE_DRIVER, compare_battle_sequence, compile_driver, sha)
from validate_zan_window import scenarios as zan_scenarios, verify_keys, verify_rematch
from validate_versus_heavy import HERE, run


def scenarios(side):
    f=(128,64)[side]
    def pair(n,own=0,other=0):return (n,other,own) if side else (n,own,other)
    def actor(slot,action):return dict(slot=slot,action=action,steps=[])
    for name,seq,wanted in zan_scenarios(side)[:2]:
        yield name,seq,wanted
    def chain(edges):
        return [pair(500),pair(40,f,f^192),pair(8)]+[pair(1,edges.get(i,0)) for i in range(165)]
    yield 'long-chain',chain({0:768,15:256,32:256,49:512,64:512,81:1024,97:1024,114:1024}),{
        560:('chain-opener-hit',actor(1-side,432)),684:('chain-finisher',actor(side,257))}
    yield 'cancel',chain({0:768,15:512,31:512,48:1024,55:32,56:f|32,57:f|256}),{
        620:('chain-cancel-whirlwind',actor(side,529))}
    yield 'ccd',chain({0:768,15:1024,31:1024,52:2048}),{
        624:('element-hit',actor(2,17))}
    # Lose 108 HP first. The original gives an unwounded fighter only a
    # single active tick, which cannot reach this follow-up from neutral.
    seq=[pair(500)]+[pair(65,0,f^192),pair(5),pair(1,0,1024),pair(88)]*3
    seq += [pair(75,f^192,f),pair(8),pair(1,1792),pair(130),pair(130,f,f^192),pair(10),pair(1,1792),pair(230)]
    yield 'issen',seq,{1072:('explosion',dict(kind='effect',bank=4,actions=list(range(6,13)),steps=[])),
                       1333:('issen-contact',actor(1-side,430)),1334:('issen-white-start',actor(1-side,430)),
                       1335:('issen-silhouette',actor(1-side,430)),1348:('issen-hit',actor(1-side,430)),
                       1500:('issen-finish',actor(side,229)),1516:('issen-white-end',actor(side,229)),
                       1517:('issen-stage-hidden',actor(1-side,430)),1518:('issen-stage-restored',actor(1-side,50))}


def gamepads(folder, original, side, name, seq, captures, spirit='ten', observe=None):
    from validate_versus_gamepads import SOFTWARE, evaluate, op
    # Let the second SDL device appear for one neutral pump before each
    # sequence. Its extra tick is accounted for explicitly in the landmarks.
    buttons={mask:i for i,mask in enumerate(SOFTWARE) if mask}
    steps=['+1 N1'];previous=(0,0);at=500;images=[]
    ticks=[(a,b) for n,a,b in seq[1:] for _ in range(n)]
    for (held,_),group in groupby(enumerate(ticks,501),key=lambda item:(item[1],sum(item[0]>k for k in captures))):
        n=sum(1 for _ in group)
        edges=[op(seat,i,bool(held[seat]&mask)) for seat in range(2) for mask,i in buttons.items()
               if (held[seat]^previous[seat])&mask]
        steps.append(' '.join([*edges,f'N{n}']));previous=held;at+=n
        if at in captures:images.append(len(steps))
    result,rows,hashes=evaluate(folder/'pads',folder,original,name,steps,special_slot=side,spirit=spirit,captures=images)
    assert len(images)==len(captures)==len(hashes)
    for i,tick in zip(images,sorted(captures)):
        assert rows[i][1]==tick+1
        victim=2+9*(1-side)
        if spirit=='ten' and name=='issen' and tick>1332:assert rows[i][victim+3]==149
        if name=='long-chain' and tick==684:assert rows[i][2+9*side:5+9*side]==[1,54,257]
        if observe is not None:observe(tick,rows[i])
    return dict(side=side+1,scenario=name,**result,original_input_snapshots=2*len(steps),pixels=hashes)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--development',action='store_true')
    parser.add_argument('--moves',nargs='+');parser.add_argument('--seats',nargs='+',type=int,default=[1,2]);args=parser.parse_args()
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH
    assets=ASSETS if args.development else PACKAGE/'assets'
    viewer=BUILD/'ss6-viewer' if args.development else PACKAGE/'ss6-viewer'
    assert sha(viewer)==sha(BUILD/'ss6-viewer')
    results=[];pad_results=[]
    with tempfile.TemporaryDirectory(prefix='ss6-ten-window-') as temp:
        folder=Path(temp);lib=folder/'runtime.a';shutil.copy2(LIB,lib);shutil.copy2(viewer,folder/'viewer')
        compile_driver(folder,'queue',CAPTURE_DRIVER,lib);compile_driver(folder,'stage',STAGE_DRIVER,lib)
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
                        HERE/'sdl_slash_input_test.cpp',lib,*sdl,'-o',folder/'keys'],check=True)
        if not args.development:
            from validate_versus_gamepads import Original
            original=Original()
            subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
                            HERE/'sdl_gamepad_input_test.cpp',lib,*sdl,'-o',folder/'pads'],check=True)
        for side in (n-1 for n in args.seats):
            if not args.moves:verify_rematch(folder,side,'ten',assets)
            for name,seq,wanted in scenarios(side):
                if args.moves and name not in args.moves:continue
                captures,_=compare_battle_sequence(folder,side,name,'ten',seq,wanted,(),[n for n,_ in wanted.values()],assets,
                    range(1334,1517) if name=='issen' else ())
                for capture in captures:
                    actors=verify_keys(folder,side,seq,capture['update'],'ten',assets)
                    if name=='issen' and capture['update']>=1333:assert actors[1-side][4]==149
                    capture['keyboard_actors']=actors
                results.extend(captures)
                if not args.development and name in ('long-chain','issen'):
                    pad_results.append(gamepads(folder,original,side,name,seq,wanted))
        if not (args.development or args.moves or args.seats!=[1,2]):
            for result in results:
                path=OUT/result['screenshot'];path.parent.mkdir(exist_ok=True);shutil.copy2(folder/path.name,path)
            report=dict(status='passed',original_sha256=SOURCE_HASH,viewer_sha256=sha(viewer),frames=results,virtual_gamepads=pad_results,restart_and_continue_seats=[1,2],
                scope='Native inputs and queue production. Original stage, draw ordering, geometry, texture, and palette callbacks checked against every arena pixel. SDL keyboard compared with the packaged 640x480 window.')
            (OUT/'ten-window-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(results),'Ten battle window checks passed')

if __name__=='__main__':main()
