#!/usr/bin/env python3
"""Replay selected Rimururu ice attacks and measure individual original ice drawings."""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from validate_dash_motion import digest
from validate_jump_light_presentation import verify_queue
from validate_native_scene import LIB, SOURCE_HASH, compare, fixture
from validate_selected_combat import CAPTURE,OUT,ROOT,SOURCE,prefix
from validate_shin_scene import BANKS


# Inspect the same queue used by the viewer once per ordinary input update.
# Sample the impact and the attached freeze, then each shard after it
# separates. A hit or a damage-state transition alone cannot satisfy this test.
DRIVER=CAPTURE.replace('previous=held;session.tick(pads);',r'''previous=held;session.tick(pads);
        if(argc==5) {
            const auto& m=session.match();const auto& q=m.objectDraws();
            std::cout<<m.fighter(0).actor.fieldA30<<' '<<m.fighter(1).actor.fieldA30;
            for(const auto& r:q.active())if(!r[81] && r[3]==2 && r[9]>=10 && r[9]<=15)
                std::cout<<' '<<r[9]<<' '<<r[10];
            std::cout<<'\n';
        }''').replace('    const auto& m=session.match();const auto& b=m.battle();','    if(argc==5)return 0;\n    const auto& m=session.match();const auto& b=m.battle();')


def play(side,state,opponent):
    lineup=(opponent,2) if side else (2,opponent)
    pair=lambda mine,theirs=0:(theirs,mine) if side else (mine,theirs)
    f=(128,64)[side];pads=prefix(lineup)
    pads[229]=[128,128]
    keys={73:(32,32|f,256|f),76:(f,32,32|f|256)}
    pads.extend([(128,64)]*45+[pair(0)]*9+[pair(key) for key in keys[state]]+[pair(0)]*190)
    return lineup,pads


def snapshot(probe,viewer,assets,tmp,lineup,pads,tick,p,counts,subjects):
    selected=pads[:tick]
    packet=io.BytesIO(subprocess.check_output([probe,assets,*map(str,lineup)],
        input=''.join(f'{x} {y}\n' for x,y in selected).encode()))
    n,=struct.unpack('<I',packet.read(4));raw=[packet.read(328) for _ in range(n)]
    start=packet.tell()
    verify_queue(p,raw,packet.getbuffer()[start:])
    pad=tmp/'inputs.pad';rgb=tmp/'scene.rgba';stage=tmp/'stage.rgba'
    pad.write_text(''.join(f'1 {x} {y}\n' for x,y in selected))
    subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',pad,'--dump',rgb,
                    '--dump-stage',stage],stdout=subprocess.DEVNULL,check=True)
    scene=rgb.read_bytes();arena=stage.read_bytes()
    assert scene[:8]==arena[:8]==struct.pack('<II',640,448)
    results=[]
    for act in subjects:
        target={'slot':2,'action':act,'steps':[]};packet.seek(start)
        source=compare(p,packet,counts,f'{lineup}:{tick}:{act}',scene[8:],target,arena[8:])
        assert target['steps'] and target['quads'] and target['visible_pixels']>0,(lineup,tick,target)
        results.append(dict(action=act,records=target['steps'],quads=target['quads'],visible_pixels=target['visible_pixels']))
    return dict(tick=tick,composition_sha256=source['viewer_sha256'],queue_records=n,subjects=results)


def run_case(probe,viewer,assets,tmp,side,state,opponent):
    lineup,pads=play(side,state,opponent)
    result=subprocess.run([probe,assets,*map(str,lineup),'scan'],capture_output=True,check=True,
                          input=''.join(f'{x} {y}\n' for x,y in pads).encode())
    frames=[list(map(int,s.split())) for s in result.stdout.splitlines()];assert len(frames)==len(pads)
    by_act={}
    for i,row in enumerate(frames[1304:],1305):
        for act,record in zip(row[2::2],row[3::2],strict=True):
            by_act.setdefault(act,[]).append((i,record))
    assert set(by_act)=={10,11,12,13,14,15},(lineup,state,by_act.keys(),frames[-1])
    assert frames[-1][side^1]<200 and frames[-1][side]==200
    p=fixture((*lineup,51));counts=Counter()
    for n,name in enumerate(BANKS):
        blob=(SOURCE/name).read_bytes();base=0x4a4810+n*0x3da0;p.memory[base:base+len(blob)]=blob
    samples={}
    for act,sequence in by_act.items():
        # The first ice overlay is entirely hidden by the impact sprite on
        # some poses. Use the middle of its submitted lifetime to measure it.
        offset=(len(sequence)*2//3 if act==11 else len(sequence)//2)
        samples.setdefault(sequence[offset][0],[]).append(act)
    shots=[snapshot(probe,viewer,assets,tmp,lineup,pads,tick,p,counts,subjects)
           for tick,subjects in sorted(samples.items())]
    return dict(lineup=lineup,attacker=side,state=state,health=frames[-1][:2],captures=shots,
                clock_ranges={k:(v[0][0],v[-1][0]) for k,v in by_act.items()},counts=counts)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer')
    ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets');a=ap.parse_args()
    assert digest(SOURCE.parent/'SLPS_255.59')==SOURCE_HASH
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td);src=tmp/'probe.cpp';src.write_text(DRIVER);probe=tmp/'probe';lib=tmp/'runtime.a';viewer=tmp/'viewer'
        shutil.copy2(LIB,lib);shutil.copy2(a.viewer,viewer)
        subprocess.run(['c++','-O2','-std=c++20','-ffp-contract=off','-I',ROOT/'src',src,lib,'-o',probe],check=True)
        cases=[]
        for side in (0,1):
            for state,opponent in ((73,0),(76,0),(76,2)):
                case=run_case(probe,viewer,a.assets,tmp,side,state,opponent);cases.append(case)
                print(side,state,case['health'],case['clock_ranges'],[(v['tick'],v['subjects']) for v in case['captures']],flush=True)
        report=dict(passed=True,source_sha256=SOURCE_HASH,viewer_sha256=digest(viewer),runtime_sha256=digest(lib),cases=cases,
                    scope='Both human seats, selected character 02 versus 00 and 02 versus 02. Input, real queue and complete 640x448 combat image before HUD. For every sample compare the original 1207e8, 122bc0, 1208b0, 116d10 and 123840 drawing commands with the viewer on its exact combat stage layer. Each ice ACT 10..15 must visibly contribute to the complete picture after occlusion. Independent software GS raster, no hardware scanout.')
        (OUT/'rimururu-ice-scene-validation.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
