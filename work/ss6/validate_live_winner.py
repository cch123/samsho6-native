#!/usr/bin/env python3
"""Compare a packaged first-to-two winner screen with the original portrait and text packets."""
from itertools import groupby
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from PIL import Image
from extract_versus_result_layout import canvas,calls
from validate_versus_result_art import textures,paint,OUTPUT
from validate_versus_result_text import original_quote,stamp,FONT_RAM,CACHE,Iso,ISO_PATH
from validate_dash_motion import ELF,PIN,ROOT,digest
from mips_probe import Probe

def encode(pads):
    return ''.join(f'{sum(1 for _ in run)} {a} {b}\n' for (a,b),run in groupby(pads))

def reference(scene,atlas,side,clock,background,glyphs,font,visible):
    primitives=[]
    scene.write(0x4c3810,side,4);scene.write(0x3db8f8,0,4)
    for fn,age in [(0x136480,clock),(0x136500,clock),(0x136930,clock),
                   (0x136988,clock),(0x1364a8,background),(0x1366e0,clock),(0x1369b0,clock)]:
        primitives.extend(calls(scene,fn,age)[0])
    rgba=np.zeros((480,640,4),np.uint8);rgba[:,:,3]=255
    paint(rgba,primitives,atlas)
    buf=bytearray(rgba.tobytes())
    if clock>=60:
        for sprite in glyphs[:visible]:stamp(buf,sprite,font)
    return bytes(buf)

def validate():
    assert digest(ELF)==PIN
    scene=canvas();atlas=textures(scene)
    text=Probe(ELF.read_bytes(),finite_model=True)
    font=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN')
    text.memory[FONT_RAM:FONT_RAM+len(font)]=font
    text.write(0x3a9c20,CACHE,4);text.write(0x32ce08,1,4);text.write(0x43d064,256,4)
    palette=[bytes(text.memory[0x348a48+i*4:0x348a4c+i*4]) for i in range(16)]
    match=ROOT/'work/ss6/build-native/ss6-match-replay';pkg=OUTPUT/'native-viewer'
    cases=[]
    with tempfile.TemporaryDirectory() as name:
        tmp=Path(name)
        for side in (0,1):
            def pad(n):return (0,n) if side else (n,0)
            seq=[(0,0)]*440+([pad(64 if side else 128)]*45+[pad(1024)]+[(0,0)]*84)*30
            def replay(pads):
                lines=''.join(f'1 {a} {b}\n' for a,b in pads)
                return [r.split() for r in subprocess.run([match,pkg/'assets','--result-fields'],
                        input=lines,text=True,capture_output=True,check=True).stdout.splitlines()]
            rows=replay(seq)
            stop=next(i+1 for i,r in enumerate(rows) if r[2]=='1')
            assert rows[stop-1][25]==str(side)
            _,glyphs,_=original_quote(text,int(rows[stop-1][26]))
            # Remove the attacks used to win the match. A single deliberate
            # press in the second version expands the line over the white flash.
            for hurry in (False,True):
                inputs=seq[:stop]+[(0,0)]*330
                rows=replay(inputs)
                if hurry:
                    t=next(i for i,r in enumerate(rows) if r[23]!='0' and r[31]=='61')
                    inputs[t+1]=pad(512);rows=replay(inputs)
                for tick in (24,45,59,60,61,63,64,82,153,280):
                    moment=next(i for i,r in enumerate(rows) if r[23]!='0' and r[28]==str(tick))
                    r=rows[moment];visible=int(r[30]);bg=int(r[29])
                    expected=reference(scene,atlas,side,tick,bg,glyphs,palette,visible)
                    script=tmp/'match.pad';script.write_text(encode(inputs[:moment+1]))
                    path=tmp/'window.bmp'
                    subprocess.run([ROOT/'battle.command','--mode','fixed-versus','--match-replay',script,'--snapshot',path],check=True)
                    image=Image.open(path).convert('RGBA');actual=image.tobytes()
                    assert image.size==(640,480) and actual==expected,(side,hurry,tick,visible)
                    if not side and not hurry and tick==280:
                        image.save(OUTPUT/'versus-winner.png')
                    cases.append(dict(winner=side+1,early_reveal=hurry,update=moment+1,
                                      result_frame=tick,glyphs=min(visible,len(glyphs)),
                                      sha256=hashlib.sha256(actual).hexdigest()))
    report=dict(status='passed',original_sha256=PIN,viewer_sha256=digest(pkg/'ss6-viewer'),
                scope='Both sides win fixed local matches by ordinary inputs. Compare all 640x480 window pixels to rasterized original packets, including early reveal on the four-tick white flash. Fade ramp and successor menus are outside this comparison.',cases=cases)
    (OUTPUT/'live_winner_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(len(cases),'packaged winner screen frames')
if __name__=='__main__':validate()
