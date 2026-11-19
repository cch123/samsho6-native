#!/usr/bin/env python3
"""Run Ken's two super moves from SDL virtual pads through the shipped versus window."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from validate_ken_specials import sequence
from validate_ten_window import gamepads
from validate_versus_gamepads import BUILD, HERE, Original, PIN, PKG, ROOT, digest, run

REPORT=ROOT/'outputs/ss6-feasibility/ken_gamepads_validation.json'


def scenario(side, weapon):
    pre,pads=sequence(side,78 if weapon else 79,'hit' if weapon else 'mikiri')
    if weapon:
        # Both victims land by their own corner. Walk inward to the sword,
        # collect it with Square, then attack again with Circle.
        target=1-side
        def p(n,key=0):return (n,0,key) if target else (n,key,0)
        pads += [p(39,(64,128)[side]),p(4),p(1,256),p(55),p(1,1024)]
    return pre+pads


def verify(folder, original, side, weapon):
    target=1-side
    name='weapon-flip-and-retrieve' if weapon else 'mikiri-secret-above-factory-cap'
    wanted=({3435:'weapon-flip',3521:'weapon-airborne',3689:'weapon-landed',
             3799:'pickup',3855:'rearmed-heavy'} if weapon else
            {1472:'before-mikiri',1473:'after-mikiri',1644:'secret-start',
             1664:'secret-hit',1871:'secret-spent'})
    milestones=[]
    def snapshot(tick,row):
        a,d=2+9*side,2+9*target
        own=row[a:a+6];victim=row[d:d+6]
        armed,blade=row[23+5*target:25+5*target]
        reserve=row[30+side]
        if weapon:
            assert own[3]==200
            if tick==3435:assert own[:3]==[1,78,625] and victim[3]==200
            if tick==3521:assert victim[2:4]==[1295,160] and (armed,blade)==(0,466)
            if tick==3689:assert (armed,blade)==(0,467)
            if tick==3799:assert victim[:3]==[0,51,136] and (armed,blade)==(1,0)
            if tick==3855:assert victim[:3]==[1,8,190] and (armed,blade)==(1,0)
        else:
            assert own[3]==46
            if tick<=1473:
                assert reserve==(8192 if tick==1472 else 16640) and own[:3]==[0,58,84]
            if tick==1644:assert own[:3]==[1,79,612] and reserve==16640 and victim[3]==200
            if tick==1664:assert own[:3]==[1,79,612] and victim[:4]==[2,56,434,195]
            if tick==1871:assert own[:3]==[0,0,613] and reserve==0 and victim[3]==153
        milestones.append(dict(event=wanted[tick],update=row[1],fighter=own,victim=victim,
                               secret_reserve=reserve,defender_armed=armed,weapon_action=blade))
    trace=gamepads(folder,original,side,name,scenario(side,weapon),set(wanted),'ken',observe=snapshot)
    assert len(milestones)==len(wanted)
    trace['milestones']=milestones
    return trace


def main():
    package_sha=digest(PKG/'ss6-viewer')
    assert digest(BUILD/'ss6-viewer')==package_sha,'The package and build must contain the same viewer.'
    replay_sha=digest(BUILD/'ss6-match-replay')
    original=Original()
    with tempfile.TemporaryDirectory(prefix='ss6-ken-controllers-') as path:
        folder=Path(path)
        sdl=shlex.split(run(['pkg-config','--cflags','--libs','sdl3']))
        subprocess.run([*shlex.split(os.getenv('CXX','c++')),'-std=c++20','-O2','-I',ROOT/'src',
                        HERE/'sdl_gamepad_input_test.cpp',BUILD/'libss6-runtime.a',*sdl,'-o',folder/'pads'],check=True)
        cases=[verify(folder,original,side,weapon) for side in range(2) for weapon in (False,True)]
    assert digest(PKG/'ss6-viewer')==package_sha and digest(BUILD/'ss6-match-replay')==replay_sha
    images=sum(len(c['pixels']) for c in cases)
    report=dict(status='passed',viewer_sha256=package_sha,replay_sha256=replay_sha,elf_sha256=PIN,
                harness_sha256=digest(HERE/'sdl_gamepad_input_test.cpp'),physical_pad_samples=original.calls,
                original_instructions=original.operations,packaged_frame_comparisons=images,cases=cases,
                scope='Two virtual SDL controllers, both fighting positions, Japanese default physical inputs. '
                      'Match HUD, fighter state, HP, separate secret reserve, weapon drop and pickup. '
                      'Each sampled 640×480 image is compared with the packaged replay except the pause label. '
                      'The second pad attaches at update 501 before the first physical button is used.')
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(cases)} controller matches, {original.calls} original pad samples, {images} packaged frames passed')


if __name__=='__main__':main()
