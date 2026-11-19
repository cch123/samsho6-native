#!/usr/bin/env python3
"""Trace a two-round Zero match through the viewer, SDL inputs and the Japanese draw callbacks."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from validate_shin_scene import (ASSETS, BUILD, CAPTURE_DRIVER, LIB, OUT, PACKAGE, ROOT, SOURCE_HASH,
                                 STAGE_DRIVER, compare_battle_sequence, compile_driver, sha)
from validate_ten_window import gamepads
from validate_versus_heavy import HERE, run
from validate_zan_window import verify_keys, verify_rematch
from validate_zero_specials import scenario


def fight(side):
    from itertools import groupby
    pre,per_tick=scenario(side,'hit')
    grouped=[(sum(1 for _ in held),a,b) for (a,b),held in groupby(per_tick,key=lambda row:row[1:])]
    return pre+grouped


def samples(side):
    def actor(slot,action):return dict(slot=slot,action=action,steps=[])
    def effect(bank,actions):return dict(kind='effect',bank=bank,actions=list(actions),steps=[])
    return {700:('meditation',actor(side,146)),714:('meditation-particles',effect(3,range(7,12))),
            4240:('mu-start',actor(side,148)),4252:('mu-rays',effect(4,range(13,19))),
            4278:('mu-active',actor(1-side,0)),4287:('issen-contact',actor(1-side,430)),
            4288:('issen-whiteout',actor(1-side,430)),4360:('issen-strike',actor(side,229))}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--seat',type=int,choices=[1,2])
    args=parser.parse_args()
    assets=ASSETS if args.development else PACKAGE/'assets'
    viewer=BUILD/'ss6-viewer' if args.development else PACKAGE/'ss6-viewer'
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH and sha(viewer)==sha(BUILD/'ss6-viewer')
    captures=[];pads=[]
    with tempfile.TemporaryDirectory(prefix='ss6-zero-window-') as temp:
        folder=Path(temp);lib=folder/'runtime.a';shutil.copy2(LIB,lib);shutil.copy2(viewer,folder/'viewer')
        compile_driver(folder,'queue',CAPTURE_DRIVER,lib);compile_driver(folder,'stage',STAGE_DRIVER,lib)
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        compiler=shlex.split(os.environ.get('CXX','c++'))
        for name,source in [('keys','sdl_slash_input_test.cpp'),('pads','sdl_gamepad_input_test.cpp')]:
            subprocess.run([*compiler,'-std=c++20','-O2','-I',ROOT/'src',HERE/source,lib,*sdl,'-o',folder/name],check=True)
        for side in ([args.seat-1] if args.seat else (0,1)):
            seq=fight(side);wanted=samples(side)
            frames,_=compare_battle_sequence(folder,side,'mu','zero',seq,wanted,(),[name for name,_ in wanted.values()],
                assets,range(4288,4471),range(4240,4286))
            for frame in frames:
                frame['keyboard_actors']=verify_keys(folder,side,seq,frame['update'],'zero',assets)
            verify_rematch(folder,side,'zero',assets)
            captures.extend(frames)
            if not args.development:
                from validate_versus_gamepads import Original
                pads.append(gamepads(folder,Original(),side,'mu',seq,{4252,4278,4287,4360},'zero'))
        if not args.development and not args.seat:
            for frame in captures:
                dest=OUT/frame['screenshot'];dest.parent.mkdir(exist_ok=True);shutil.copy2(folder/dest.name,dest)
            report=dict(status='passed',original_sha256=SOURCE_HASH,viewer_sha256=sha(viewer),frames=captures,
                virtual_gamepads=pads,restart_and_continue_seats=[1,2],
                scope='Two complete human-input paths to match point, meditation and concentration. Compare Japanese stage, tone, queue, palettes, effect quads and arena pixels. Compare packaged screenshots and physical SDL key events, as well as two virtual controllers.')
            (OUT/'zero-window-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(captures),'Zero battle window checks passed')


if __name__=='__main__':main()
