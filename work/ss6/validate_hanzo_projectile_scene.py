#!/usr/bin/env python3
"""Start at the character-select page and compare Hanzō's projectile layers with the Japanese GS submission."""
import argparse
from collections import Counter
import io
from itertools import groupby
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from validate_dash_motion import digest
from validate_hanzo_specials import pads
from validate_jump_light_presentation import verify_queue
from validate_native_scene import LIB, SOURCE_HASH, compare, fixture
from validate_rimururu_ice_scene import DRIVER as ICE_DRIVER
from validate_selected_combat import BUILD, OUT, ROOT, SOURCE
from validate_shin_scene import BANKS

DRIVER=ICE_DRIVER.replace('r[3]==2 && r[9]>=10 && r[9]<=15','r[5]==3 && r[51]==2')
REPORT=OUT/'hanzo-projectile-scene-validation.json'
DEMO=OUT/'hanzo-fire.replay'
def encode(seq):
    return ''.join(f'{sum(1 for _ in group)} {pair[0]} {pair[1]}\n' for pair,group in groupby(map(tuple,seq)))

def frames(program,assets,side,state,variant):
    seq,start=pads(side,state,variant);roster=(0,3) if side else (3,0)
    pair=lambda mine,theirs:(theirs,mine) if side else (mine,theirs)
    if state in (69,70) and variant in ('near','guard'):
        seq=seq[:1250]+[pair(0,0)]*10+[pair(16,0)]+[pair(0,0)]*7+seq[start:]
        start=1268
    if state==88:
        seq=seq[:1250]+[(128,64)]*26+[pair(0,0)]*10+seq[start:]
        start=1286
        for j in range(start+10,start+35):
            seq[j]=pair(seq[j][side],(64,128)[side])
    result=subprocess.run([program,assets,*map(str,roster),'scan'],capture_output=True,
                          input=''.join(f'{a} {b}\n' for a,b in seq).encode())
    assert not result.returncode,(side,state,variant,result.stderr.decode(),len(result.stdout.splitlines()))
    rows=[list(map(int,line.split())) for line in result.stdout.splitlines()]
    assert len(rows)==len(seq)
    by_act={}
    for tick,row in enumerate(rows[start:],start+1):
        for act,step in zip(row[2::2],row[3::2],strict=True):
            by_act.setdefault(act,[]).append((tick,step))
    return roster,seq,rows[-1][:2],by_act

def image(probe,viewer,assets,work,roster,seq,tick,p,stats,side,act):
    stream=io.BytesIO(subprocess.check_output([probe,assets,*map(str,roster)],
                       input=''.join(f'{x} {y}\n' for x,y in seq[:tick]).encode()))
    n,=struct.unpack('<I',stream.read(4));unsorted=[stream.read(328) for _ in range(n)]
    verify_queue(p,unsorted,stream.getbuffer()[stream.tell():])
    replay=work/'inputs.pad';replay.write_text(encode(seq[:tick]))
    scene=work/'scene.rgba';stage=work/'stage.rgba'
    subprocess.run([viewer,'--mode','select','--assets',assets,'--match-replay',replay,
                    '--dump',scene,'--dump-stage',stage],check=True,stdout=subprocess.DEVNULL)
    front=scene.read_bytes();background=stage.read_bytes()
    assert front[:8]==background[:8]==struct.pack('<2I',640,448)
    target=dict(slot=side,action=act,steps=[])
    report=compare(p,stream,stats,f'{roster}-{tick}-{act}',front[8:],target,background[8:])
    assert target['steps'],(roster,tick,act,target)
    return dict(tick=tick,act=act,steps=target['steps'],visible_pixels=target['visible_pixels'],rgba_sha256=report['viewer_sha256'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--viewer',type=Path,default=OUT/'native-viewer/ss6-viewer')
    ap.add_argument('--assets',type=Path,default=OUT/'native-viewer/assets')
    ap.add_argument('--scan',action='store_true');args=ap.parse_args()
    assert digest(SOURCE.parent/'SLPS_255.59')==SOURCE_HASH
    scenes=[]
    with tempfile.TemporaryDirectory() as path:
        work=Path(path);cpp=work/'probe.cpp';cpp.write_text(DRIVER);probe=work/'probe';lib=work/'runtime.a';viewer=work/'viewer'
        shutil.copy2(LIB,lib);shutil.copy2(args.viewer,viewer)
        subprocess.run(['c++','-std=c++20','-O2','-ffp-contract=off','-I',ROOT/'src',cpp,lib,'-o',probe],check=True)
        for side in (0,1):
            p=fixture(((0,3,51) if side else (3,0,51)));stats=Counter()
            for n,name in enumerate(BANKS):
                blob=(SOURCE/name).read_bytes();base=0x4a4810+n*0x3da0;p.memory[base:base+len(blob)]=blob
            for state,variant in [(64,'near'),(65,'guard'),(66,'distance'),(69,'near'),(70,'guard'),(71,'distance'),(88,'near'),(90,'near')]:
                roster,seq,health,by_act=frames(probe,args.assets,side,state,variant)
                windows={act:[v[0][0],v[-1][0]] for act,v in by_act.items()}
                print(side,state,variant,health,windows,flush=True)
                if args.scan:continue
                assert by_act,(side,state,variant)
                captures=[]
                for act,sequence in by_act.items():
                    # An ACT can end on a held invisible record (555), or be hidden
                    # behind its caster at impact. Require a genuinely visible pose.
                    indices=[len(sequence)//2,0,len(sequence)//4,3*len(sequence)//4,len(sequence)-1]
                    for pos in dict.fromkeys(indices):
                        shot=image(probe,viewer,args.assets,work,roster,seq,sequence[pos][0],p,stats,side,act)
                        if shot['visible_pixels']:
                            captures.append(shot);break
                    else:raise AssertionError((side,state,variant,act,indices))
                hp_after={64:180,65:199,66:200,69:196,70:197,71:200,88:197,90:160}
                assert health[side]==200 and health[1-side]==hp_after[state],(side,state,variant,health)
                if side==0 and state==64:DEMO.write_text(encode(seq))
                scenes.append(dict(seat=side+1,state=state,outcome=variant,hp=health,windows=windows,captures=captures))
        if args.scan:return
        doc=dict(status='passed',source_sha256=SOURCE_HASH,viewer_sha256=digest(viewer),runtime_sha256=digest(lib),
                 replay=DEMO.name,cases=scenes,scope='Real public character selection and inputs. At each sampled moment verify original queue insertion, depth order, GS actor/effect vertices, palettes and independent raster against the native scene over the real stage. Quantify each individual projectile by omitting its quads and counting changed output pixels.')
        REPORT.write_text(json.dumps(doc,indent=2)+'\n')

if __name__=='__main__':main()
