#!/usr/bin/env python3
"""Validate the Ken fighter, decoy, perfect guard and secret move in the SDL window."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from PIL import Image
from validate_ken_mikiri import pads
from validate_ken_specials import sequence
from validate_shin_scene import (ASSETS, BUILD, CAPTURE_DRIVER, LIB, OUT, PACKAGE, ROOT, SOURCE_HASH,
                                 STAGE_DRIVER, compare_battle_sequence, compile_driver, sha)
from validate_versus_heavy import HERE,run
from validate_zan_window import verify_keys,verify_rematch


def scenarios(side):
    def actor(who,action):return dict(slot=who,action=action,steps=[])
    def effect(bank,actions):return dict(kind='effect',bank=bank,actions=actions,steps=[])
    for stance,hit,action in [('stand',565,86),('duck',556,94),('low',565,102)]:
        seq=pads(side,stance)
        yield stance,seq,{hit-1:(stance+'-decoy',actor(side,action)),
                          hit:(stance+'-hit',actor(side,action)),
                          hit+4:(stance+'-resume',actor(side,action-2))},[hit,hit+4]
    def p(n,a=0,b=0):return (n,b,a) if side else (n,a,b)
    f=(128,64)[side]
    seq=[p(500),p(42,f,f^192),p(8),p(1,1024),p(120),p(60,f,f^192),p(8),p(1,768,256),p(85)]
    yield 'guard',seq,{740:('guard-start',actor(side,314)),745:('guard-success',actor(side,316)),
                       749:('guard-sparks',effect(2,[6,9]))},[]
    before,after=sequence(side,79,'mikiri')
    yield 'secret',before+after,{1647:('secret-start',actor(side,612)),1664:('secret-hit',actor(1-side,434)),
                                 1822:('secret-recovery',actor(side,613))},[1647]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--development',action='store_true')
    parser.add_argument('--seat',type=int,choices=[1,2])
    args=parser.parse_args()
    assets=ASSETS if args.development else PACKAGE/'assets'
    viewer=BUILD/'ss6-viewer' if args.development else PACKAGE/'ss6-viewer'
    assert sha(ASSETS.parent/'SLPS_255.59')==SOURCE_HASH and sha(viewer)==sha(BUILD/'ss6-viewer')
    captures=[];flashes=[]
    with tempfile.TemporaryDirectory(prefix='ss6-ken-window-') as folder:
        work=Path(folder);lib=work/'runtime.a';shutil.copy2(LIB,lib);shutil.copy2(viewer,work/'viewer')
        compile_driver(work,'queue',CAPTURE_DRIVER,lib);compile_driver(work,'stage',STAGE_DRIVER,lib)
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3'],text=True).stdout)
        subprocess.run([*shlex.split(os.environ.get('CXX','c++')),'-std=c++20','-ffp-contract=off','-O2','-I',ROOT/'src',
                        HERE/'sdl_slash_input_test.cpp',lib,*sdl,'-o',work/'keys'],check=True)
        for side in ([args.seat-1] if args.seat else (0,1)):
            for name,seq,wanted,focus in scenarios(side):
                frames,_=compare_battle_sequence(work,side,name,'ken',seq,wanted,focus,
                                                 [label for label,_ in wanted.values()],assets)
                for frame in frames:
                    frame['keyboard_actors']=verify_keys(work,side,seq,frame['update'],'ken',assets)
                captures.extend(frames)
                if name in ('stand','duck','low'):
                    hit=sorted(wanted)[1]
                    for tick in range(hit+1,hit+4):
                        verify_keys(work,side,seq,tick,'ken',assets)
                        with Image.open(work/'keyboard.bmp') as img:
                            assert img.size==(640,480) and img.convert('RGB').getextrema()==((255,255),)*3
                        flashes.append((side+1,name,tick))
            verify_rematch(work,side,'ken',assets)
        if not args.development and not args.seat:
            for frame in captures:
                dest=OUT/frame['screenshot'];dest.parent.mkdir(exist_ok=True);shutil.copy2(work/dest.name,dest)
            report=dict(status='passed',elf_sha256=SOURCE_HASH,viewer_sha256=sha(viewer),frames=captures,
                        white_frames=flashes,restart_and_continue_seats=[1,2],
                        scope='Japanese stage, draw queue, pose, effects and palette projection against every arena pixel. SDL keys against packaged input replay, including the three original all-white presentations per decoy contact.')
            (OUT/'ken-window-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(captures),'Ken windows and',len(flashes),'full white frames passed')


if __name__=='__main__':main()
