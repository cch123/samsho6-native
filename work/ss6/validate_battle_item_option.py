#!/usr/bin/env python3
"""Exercise both Japanese item cards and follow the confirmed value to the local VS item gate."""
from hashlib import sha256
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from extract_spirit_select_art import prepare, ORIGINAL
from extract_versus_quotes import Iso, ISO_PATH
from extract_versus_result_layout import calls
from validate_character_select import Source
from validate_character_select_art import render,textures,upload
from validate_spirit_select_art import glyphs
from validate_selected_combat import prefix, OUT, SOURCE as ASSETS

def physical(held):
    # The gameplay replay names buttons A..H. The menu samples the original
    # physical pad face/shoulder bit (A is cross, 0x400).
    codes=(0x400,0x200,2,4,0x400000,0x800000,0x100000,0x200000)
    return (held&248)|sum(code for k,code in enumerate(codes) if held&(256<<k))

def original_menu_frame(phase,trace):
    art=prepare();atlases=textures(art)
    for slot,name,size,indexed,palette in ((2,'obj1_16',512,True,0),(5,'ps2_gage_1_2_3_all',1024,False,768),
         (7,'bup_00',512,False,256),(8,'bup_01',512,False,512),(12,'vs_obj',512,True,0)):
        atlases[slot]=upload(art,name,size,indexed,palette)
    icon=(ASSETS/'ps2_common_icon.pal').read_bytes()
    art.memory[0x1236740:0x1236740+len(icon)]=icon;art.run(0x116588,limit=500000)
    colors=np.frombuffer(art.memory,np.uint8,1024,0x1236f40).reshape(256,4)
    atlases[46]=colors[np.frombuffer((ASSETS/'ps2_common_icon.tex').read_bytes(),np.uint8).reshape(512,512)].copy()
    font=Iso(ISO_PATH).read('/BIN/GOTH_24.BIN');art.memory[0x106b840:0x106b840+len(font)]=font
    for at,v in ((0x345178,0),(0x345180,0),(0x32ce08,1),(0x3a9c20,0x1a00000),(0x43d064,256),
                 (0x4c8280,0),(0x4c8288,trace[1]),(0x4c3828,trace[8]),(0x4c8d80,trace[7])):
        art.write(at,v,4)
    art.run(0x114e80);quads=[]
    for s in (1,0):
        ph,t,c,_=phase[s];art.write(0x4c8d40+52*s,c,4);quads+=calls(art,0x1309a8,s,ph,t)[0]
    quads+=calls(art,0x1353a0,trace[6])[0];quads+=calls(art,0x12f5f0)[0];quads+=glyphs(art,atlases)
    return render(quads,atlases)

def main():
    base=OUT/'native-viewer';viewer=base/'ss6-viewer';assets=base/'assets'
    cases=[]
    with tempfile.TemporaryDirectory() as td:
        tmp=Path(td)
        for value in (0,1):
            pads=prefix((0,1));pads[265][1]=128*value
            source=Source(owner=1,seed=1);screen=None
            for tick,pad in enumerate(pads,1):
                row=source.step([physical(n) for n in pad])
                if tick==265:assert row[8]==0
                if tick==277:
                    assert row[8]==value and tuple(x[0] for x in source.drawSpirit)==(14,13)
                    screen=original_menu_frame(source.drawSpirit,row)
                if row[4]:break
            assert row[4] and row[7:9]==[0,value] and screen is not None
            p=source.p;p.write(0x4c3808,3,4);gate,_=p.run(0x141860);assert gate==value
            replay=tmp/'pads';snapshot=tmp/'card.bmp'
            replay.write_text(''.join(f'1 {a} {b}\n' for a,b in pads[:277]))
            env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
            subprocess.run([viewer,'--assets',assets,'--mode','select','--match-replay',replay,'--snapshot',snapshot],
                           env=env,check=True,stdout=subprocess.DEVNULL)
            got=np.array(Image.open(snapshot).convert('RGB'));want=screen[:,:,:3]
            if not np.array_equal(want,got):
                diff=np.any(want!=got,axis=2);ys,xs=np.nonzero(diff)
                raise AssertionError((value,len(xs),(xs.min(),ys.min(),xs.max(),ys.max()),want[ys[0],xs[0]],got[ys[0],xs[0]]))
            cases.append(dict(value=value,label=('アイテムなし','アイテムあり')[value],confirm_tick=tick,vs_gate=gate,
                              source_rgb_sha256=sha256(want.tobytes()).hexdigest()))
    report=dict(status='passed',source_elf_sha256=ORIGINAL,viewer_sha256=sha256(viewer.read_bytes()).hexdigest(),
                original_gate='141860',global_word='4c3828',full_frame_pixels=2*640*480,cases=cases)
    (OUT/'battle-item-option-validation.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(report)

if __name__=='__main__':main()
